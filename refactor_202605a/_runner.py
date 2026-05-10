"""Shared runner for `<id>.py` transform scripts in tom_refactor_202605a chain.

Each per-PR script defines a `transform(wt: Path)` function that mutates the
worktree (no commit) and calls `run_pr(transform=..., base=..., target=...,
id=..., subject=..., body=...)`. The runner builds the commit message itself
from `id`/`subject`/`body` so that commit message and PR description stay in
lockstep — see PR_CHAIN.md "PR body / commit description 规则".

Three modes (typer subcommand):

    run     create a fresh worktree at BASE, run transform, commit with the
            formatted message, run pre-commit, and force-push the resulting
            commit as TARGET. This is the production flow used to (re-)build
            the chain.
    verify  create a fresh worktree at BASE, run transform, commit, run
            pre-commit, and diff against the existing TARGET on upstream.
            PASS = no diff. Use for review of an already-pushed PR.
    apply   run transform on a caller-supplied worktree directory (no commit,
            no push). Use for manual debugging — point at a local checkout of
            BASE and inspect the resulting working tree.

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
    if target_dir.exists():
        _exec(["git", "worktree", "remove", "--force", str(target_dir)], cwd=REPO, check=False)
        if target_dir.exists():
            shutil.rmtree(target_dir)
    _exec(["git", "fetch", "upstream", base_ref], cwd=REPO)
    _exec(["git", "worktree", "add", "--detach", str(target_dir), f"upstream/{base_ref}"], cwd=REPO)


def _build_commit_message(*, id: str, subject: str, body: str) -> str:
    body_clean = body.rstrip()
    parts = [f"{id}: {subject}"]
    if body_clean:
        parts.extend(["", body_clean])
    parts.extend(["", f"Refactor chain ID: {id}"])
    return "\n".join(parts) + "\n"


def _commit(wt: Path, *, message: str) -> None:
    porcelain = _exec(["git", "status", "--porcelain"], cwd=wt).strip()
    if not porcelain:
        return
    _exec(["git", "add", "-A"], cwd=wt)
    _exec(["git", "commit", "-m", message, "--quiet"], cwd=wt)


def _run_pre_commit(wt: Path) -> None:
    files = _exec(["git", "diff", "--name-only", "HEAD~1", "HEAD"], cwd=wt).split()
    if not files:
        return
    _exec(["pre-commit", "run", "--files", *files], cwd=wt, check=False)
    porcelain = _exec(["git", "status", "--porcelain"], cwd=wt).strip()
    if porcelain:
        _exec(["git", "add", "-A"], cwd=wt)
        _exec(["git", "commit", "--amend", "--no-edit", "--quiet"], cwd=wt)


def _cleanup(wt: Path) -> None:
    _exec(["git", "worktree", "remove", "--force", str(wt)], cwd=REPO, check=False)


def _safe_wt_name(target: str) -> str:
    return target.replace("/", "-")


def run_pr(
    *,
    transform: Callable[[Path], None],
    base: str,
    target: str,
    id: str,
    subject: str,
    body: str,
) -> None:
    """Entry point used by per-PR scripts. Reads sys.argv via typer."""
    app = typer.Typer(add_completion=False, no_args_is_help=True)
    commit_message = _build_commit_message(id=id, subject=subject, body=body)

    @app.command()
    def run(
        keep: Annotated[bool, typer.Option(help="Keep worktree after push (for inspection)")] = False,
    ) -> None:
        """Build the PR commit and force-push to upstream."""
        wt = Path(f"/tmp/refactor-wt-{_safe_wt_name(target)}")
        _make_worktree(wt, base)
        sys.path.insert(0, str(SKILL_PATH))
        transform(wt)
        _commit(wt, message=commit_message)
        head_after = _exec(["git", "rev-parse", "HEAD"], cwd=wt).strip()
        head_base = _exec(["git", "rev-parse", f"upstream/{base}"], cwd=REPO).strip()
        if head_after == head_base:
            print(f"WARN: transform produced no commit; force-pushing BASE to {target}")
        else:
            _run_pre_commit(wt)
        _exec(["git", "push", "-f", "upstream", f"HEAD:refs/heads/{target}"], cwd=wt)
        # Sync local branch to upstream so `git branch` view stays clean.
        _exec(["git", "fetch", "upstream", target], cwd=REPO)
        new_head = _exec(["git", "rev-parse", "HEAD"], cwd=wt).strip()
        _exec(
            ["git", "update-ref", f"refs/heads/{target}", new_head],
            cwd=REPO,
            check=False,
        )
        _exec(
            ["git", "branch", f"--set-upstream-to=upstream/{target}", target],
            cwd=REPO,
            check=False,
        )
        if not keep:
            _cleanup(wt)
            print(f"DONE {target}")
        else:
            print(f"DONE {target} (worktree kept at {wt})")

    @app.command()
    def verify() -> None:
        """Re-run transform and diff against upstream/<target>; PASS if no diff."""
        wt = Path(f"/tmp/verify-wt-{_safe_wt_name(target)}")
        _make_worktree(wt, base)
        sys.path.insert(0, str(SKILL_PATH))
        transform(wt)
        _commit(wt, message=commit_message)
        head_after = _exec(["git", "rev-parse", "HEAD"], cwd=wt).strip()
        head_base = _exec(["git", "rev-parse", f"upstream/{base}"], cwd=REPO).strip()
        if head_after != head_base:
            _run_pre_commit(wt)
        _exec(["git", "fetch", "upstream", target], cwd=REPO)
        diff = _exec(
            ["git", "diff", f"upstream/{target}", "--", "."],
            cwd=wt,
            check=False,
        ).strip()
        if diff:
            print(f"FAIL: {target} differs from transform output:")
            print(diff[:5000])
            _cleanup(wt)
            raise typer.Exit(code=1)
        print(f"PASS: {target} reproduces the commit exactly.")
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
