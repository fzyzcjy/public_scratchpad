"""Shared runner for `<id>.py` transform scripts in tom_refactor_202605a chain.

Scripts now describe a single commit by identifier; they do **not** push to
any per-commit branch. Push semantics are handled by the chain-rebuild
orchestrators (`_build_<area>.py`). See PR_CHAIN.md for the workflow.

Each per-PR script defines a `transform(wt: Path)` function that mutates the
worktree (no commit) and calls
`run_pr(transform=..., base=..., area_branch=..., id=..., subject=..., body=...)`.
The runner builds the commit message itself from `id`/`subject`/`body` so
that commit message and (eventual) PR description stay in lockstep.

Three modes (typer subcommand):

    run     create a fresh worktree at BASE, run transform, commit with the
            formatted message, run pre-commit. Builds the commit locally;
            does NOT push anywhere — the chain orchestrator owns the push.
    verify  find the commit in upstream/<area_branch> whose subject starts
            with `<id>: `, create a worktree at that commit's parent, run
            transform, commit, run pre-commit, and diff against the found
            commit. PASS = no diff.
    apply   run transform on a caller-supplied worktree directory (no commit,
            no push). Use for manual debugging.

Commit message format:

    <id>: <subject>

    <body>

    Refactor chain ID: <id>

Transform must NOT call `git add` / `git commit` itself — runner handles that.
"""

# /// script
# requires-python = ">=3.10"
# dependencies = ["typer"]
# ///

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from typing import Annotated, Callable, Optional

import typer

REPO = Path("/Users/tom/main/workspaces/ws-main/worktrees/sglang-dev-a")
SKILL_PATH = REPO / ".claude/skills/mechanical-refactor-verify"


def _exec(cmd: list[str], *, cwd: Optional[Path] = None, check: bool = True) -> str:
    result = subprocess.run(
        cmd, cwd=cwd, capture_output=True, text=True, check=check
    )
    return result.stdout + result.stderr


def _make_worktree(target_dir: Path, base_ref: str) -> None:
    """`base_ref` may be a local revision (sha, refname) or `upstream/<ref>` after fetch."""
    if target_dir.exists():
        _exec(["git", "worktree", "remove", "--force", str(target_dir)], cwd=REPO, check=False)
        if target_dir.exists():
            shutil.rmtree(target_dir)
    _exec(["git", "worktree", "add", "--detach", str(target_dir), base_ref], cwd=REPO)


def _build_commit_message(*, id: str, subject: str, body: str) -> str:
    body_clean = body.rstrip()
    parts = [f"{id}: {subject}"]
    if body_clean:
        parts.extend(["", body_clean])
    parts.extend(["", f"Refactor chain ID: {id}"])
    return "\n".join(parts) + "\n"


def _commit(wt: Path, *, message: str) -> bool:
    porcelain = _exec(["git", "status", "--porcelain"], cwd=wt).strip()
    if not porcelain:
        return False
    _exec(["git", "add", "-A"], cwd=wt)
    _exec(["git", "commit", "-m", message, "--quiet"], cwd=wt)
    return True


def _run_pre_commit(wt: Path) -> None:
    files = _exec(["git", "diff", "--name-only", "HEAD~1", "HEAD"], cwd=wt).split()
    if not files:
        return
    _exec(["pre-commit", "run", "--files", *files], cwd=wt, check=False)
    porcelain = _exec(["git", "status", "--porcelain"], cwd=wt).strip()
    if porcelain:
        _exec(["git", "add", "-A"], cwd=wt)
        _exec(["git", "commit", "--amend", "--no-edit", "--quiet"], cwd=wt)


def _find_chain_commit(area_branch: str, id: str) -> str:
    """Return the SHA of the commit in upstream/<area_branch> whose subject
    starts with `<id>: `. Raises if not found or ambiguous.
    """
    _exec(["git", "fetch", "upstream", area_branch], cwd=REPO)
    log = _exec(
        ["git", "log", "--format=%H %s", f"upstream/{area_branch}"],
        cwd=REPO,
    )
    matches = [
        line.split(" ", 1)[0]
        for line in log.splitlines()
        if line.partition(" ")[2].startswith(f"{id}: ")
    ]
    if not matches:
        raise RuntimeError(f"no commit with subject prefix '{id}: ' on upstream/{area_branch}")
    if len(matches) > 1:
        raise RuntimeError(
            f"multiple commits with subject prefix '{id}: ' on upstream/{area_branch}: {matches}"
        )
    return matches[0]


def _cleanup(wt: Path) -> None:
    _exec(["git", "worktree", "remove", "--force", str(wt)], cwd=REPO, check=False)


def _safe_wt_name(s: str) -> str:
    return s.replace("/", "-")


def run_pr(
    *,
    transform: Callable[[Path], None],
    base: str,
    area_branch: str,
    id: str,
    subject: str,
    body: str,
) -> None:
    """Entry point used by per-PR scripts. Reads sys.argv via typer."""
    app = typer.Typer(add_completion=False, no_args_is_help=True)
    commit_message = _build_commit_message(id=id, subject=subject, body=body)

    @app.command()
    def run(
        keep: Annotated[bool, typer.Option(help="Keep worktree after build (for inspection)")] = False,
    ) -> None:
        """Build the commit locally on a worktree at BASE; no push."""
        wt = Path(f"/tmp/refactor-wt-{_safe_wt_name(id)}")
        _exec(["git", "fetch", "upstream", base], cwd=REPO)
        _make_worktree(wt, f"upstream/{base}")
        sys.path.insert(0, str(SKILL_PATH))
        transform(wt)
        committed = _commit(wt, message=commit_message)
        if committed:
            _run_pre_commit(wt)
        head = _exec(["git", "rev-parse", "HEAD"], cwd=wt).strip()
        if not keep:
            print(f"DONE {id} (HEAD={head[:12]}); cleaned up worktree")
            _cleanup(wt)
        else:
            print(f"DONE {id} (HEAD={head[:12]}); worktree kept at {wt}")

    @app.command()
    def verify() -> None:
        """Reproduce the chain commit and diff against upstream/<area_branch>."""
        try:
            chain_sha = _find_chain_commit(area_branch, id)
        except RuntimeError as e:
            print(f"FAIL: {e}")
            raise typer.Exit(code=1)
        wt = Path(f"/tmp/verify-wt-{_safe_wt_name(id)}")
        _make_worktree(wt, f"{chain_sha}~1")
        sys.path.insert(0, str(SKILL_PATH))
        transform(wt)
        committed = _commit(wt, message=commit_message)
        if committed:
            _run_pre_commit(wt)
        diff = _exec(
            ["git", "diff", chain_sha, "--", "."],
            cwd=wt,
            check=False,
        ).strip()
        if diff:
            print(f"FAIL: {id} differs from upstream/{area_branch} commit {chain_sha[:12]}:")
            print(diff[:5000])
            _cleanup(wt)
            raise typer.Exit(code=1)
        print(f"PASS: {id} reproduces upstream/{area_branch} commit {chain_sha[:12]} exactly.")
        _cleanup(wt)

    @app.command()
    def apply(
        worktree: Annotated[Path, typer.Argument(help="Worktree directory to apply transform to")],
    ) -> None:
        """Run transform on an existing worktree (no commit/push). Manual debug."""
        sys.path.insert(0, str(SKILL_PATH))
        transform(worktree)
        print(f"applied transform to {worktree}")

    @app.command(name="show-message")
    def show_message() -> None:
        """Print the commit message that `run`/`verify` will use."""
        print(commit_message, end="")

    app()
