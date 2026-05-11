#!/usr/bin/env python3
"""Build tom_refactor_202605a/primary/mech_model_runner from `<id>.py` scripts.

For each `<id>` in ORDER:
  1. Dynamically import `<id>.py`, read `SUBJECT` / `BODY` attrs.
  2. Call `transform(wt)` on a worktree starting at the cumulative chain head
     (begins at `upstream/mech_preflight`, advances by 1 commit per script).
  3. Commit with formatted message `<id>: <subject>\\n\\n<body>\\n\\nRefactor chain ID: <id>`.
  4. Run pre-commit; amend if it auto-fixed.

The orchestrator builds the chain locally only. After that:
  - It auto-tags the OLD `upstream/<chain_branch>` HEAD as
    `backup/<UTC-timestamp>/<area>` and pushes that tag.
  - Prints the force-push command for the new chain (manual step).

This replaces the old "cherry-pick from `tom_refactor/<N>`" approach — scripts
are now the **single source of truth**; chain advances by re-running them.
Any script edit takes effect on the next orchestrator run.
"""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).parent
REPO = Path("/Users/tom/main/workspaces/ws-main/worktrees/sglang-dev-a")
WT = Path("/tmp/refactor-wt-mech-model-runner")
BASE = "tom_refactor_202605a/primary/mech_preflight"
CHAIN_BRANCH = "tom_refactor_202605a/primary/mech_model_runner"
SKILL_PATH = REPO / ".claude/skills/mechanical-refactor-verify"


# Chain ordering. Each entry is the `<id>` part of a `<id>.py` script in this
# directory. Each script provides its own SUBJECT and (optional) BODY.
ORDER: list[str] = [
    "extract-init-cublas",
    "extract-apply-torch-tp",
    "extract-init-threads-binding",
    "inline-max-pool-size",
    "extract-prealloc-symm-pool",
    "extract-kv-cache-dtype",
    "introduce-weight-updater",
    "wu-move-from-disk",
    "wu-move-from-distributed",
    "wu-move-from-tensor",
    "wu-move-from-ipc",
    "introduce-weight-exporter",
    "we-move-save-get",
    "extract-update-expert-location",
    "extract-init-device-graphs",
    "extract-piecewise-cuda-graphs",
    "extract-hybrid-arch-props",
    "drop-hybrid-arch-delegates",
    "extract-autotune-helpers",
    "extract-kernel-warmup",
    "extract-lora-moe-buffers",
    "init-dist",
    "introduce-rwt-skeleton",
    "rwt-migrate-register-bootstrap",
    "rwt-migrate-modelexpress-publish",
    "introduce-ngram-embedding-mgr",
    "nem-migrate-maybe-prepare",
    "nem-migrate-cuda-graph",
    "nem-drop-legacy-fields",
    "drop-rank-zero-filter",
    "move-resolve-language-model",
    "move-step-span-name",
    "kvc-introduce-skeleton",
    "kvc-extract-mla-dim",
    "kvc-migrate-leaves",
    "kvc-migrate-init-pools",
    "kvc-migrate-configure",
    "kvc-drop-mixin-inheritance",
    "dg-mech-rename",
    "kw-mech-rename",
    "ha-mech-drop-is-draft-worker",
    "nem-mech-rename",
    "nem-mech-frozen",
    "rwt-mech-rename",
    "rwt-mech-slots",
    "fix-mla-ci-workflow",
]


def run(cmd: list[str], *, cwd: Path, check: bool = True) -> str:
    print(f"$ {' '.join(cmd)}", flush=True)
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=check)
    if result.stdout:
        print(result.stdout, end="", flush=True)
    if result.stderr:
        print(result.stderr, end="", flush=True)
    return result.stdout + result.stderr


def make_worktree() -> None:
    if WT.exists():
        run(["git", "worktree", "remove", "--force", str(WT)], cwd=REPO, check=False)
        if WT.exists():
            shutil.rmtree(WT)
    run(["git", "fetch", "upstream", BASE], cwd=REPO)
    run(["git", "worktree", "add", "--detach", str(WT), f"upstream/{BASE}"], cwd=REPO)


def load_script(id: str):
    """Import `<id>.py` as a module and return it."""
    script_path = HERE / f"{id}.py"
    if not script_path.exists():
        raise FileNotFoundError(f"missing transform script: {script_path}")
    spec = importlib.util.spec_from_file_location(f"_chain_{id.replace('-', '_')}", script_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def commit_message(*, id: str, subject: str, body: str) -> str:
    body_clean = (body or "").rstrip()
    parts = [f"{id}: {subject}"]
    if body_clean:
        parts.extend(["", body_clean])
    parts.extend(["", f"Refactor chain ID: {id}"])
    return "\n".join(parts) + "\n"


def run_pre_commit(wt: Path) -> None:
    files = run(["git", "diff", "--name-only", "HEAD~1", "HEAD"], cwd=wt).split()
    if not files:
        return
    run(["pre-commit", "run", "--files", *files], cwd=wt, check=False)
    porcelain = run(["git", "status", "--porcelain"], cwd=wt).strip()
    if porcelain:
        run(["git", "add", "-A"], cwd=wt)
        run(["git", "commit", "--amend", "--no-edit", "--quiet"], cwd=wt)


def backup_old_chain_head() -> None:
    """Tag the current upstream/<CHAIN_BRANCH> HEAD before any force-push.

    Per PR_CHAIN.md backup rule. Tag name encodes a UTC second-precision
    timestamp so multiple rebuilds in one day each get a distinct backup tag.

    Pushed to **origin** (fzyzcjy/sglang fork) — upstream sgl-project repo
    rules reject `backup/*` namespace, so origin is the durable home for
    backup tags.

    Skips silently on first build (no upstream branch yet).
    """
    run(["git", "fetch", "upstream", CHAIN_BRANCH], cwd=REPO, check=False)
    sha = run(
        ["git", "rev-parse", "--verify", "--quiet", f"upstream/{CHAIN_BRANCH}"],
        cwd=REPO,
        check=False,
    ).strip()
    if not sha:
        print(f"\n=== no existing upstream/{CHAIN_BRANCH} — skipping backup tag ===", flush=True)
        return
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")
    area = CHAIN_BRANCH.split("/")[-1]
    tag_name = f"backup/{timestamp}/{area}"
    print(f"\n=== backing up old upstream/{CHAIN_BRANCH} ({sha[:12]}) as {tag_name} on origin ===", flush=True)
    run(["git", "tag", tag_name, sha], cwd=REPO)
    run(["git", "push", "origin", f"refs/tags/{tag_name}"], cwd=REPO)


def tag_new_chain_head(head_sha: str) -> None:
    """Tag the freshly-built chain HEAD as `chain/<UTC-timestamp>/<area>`.

    Symmetric to ``backup_old_chain_head`` — same namespace style, also pushed
    to origin so each rebuild leaves a durable, dated reference to the new
    chain even if a later rebuild force-overwrites the branch.

    Created locally in REPO (not WT) so the tag survives worktree teardown.
    """
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")
    area = CHAIN_BRANCH.split("/")[-1]
    tag_name = f"chain/{timestamp}/{area}"
    print(f"\n=== tagging new chain HEAD ({head_sha[:12]}) as {tag_name} on origin ===", flush=True)
    run(["git", "tag", tag_name, head_sha], cwd=REPO)
    run(["git", "push", "origin", f"refs/tags/{tag_name}"], cwd=REPO)


def main() -> None:
    # Make sure scripts can `from _helpers import ...` and `from _runner import run_pr`.
    if str(HERE) not in sys.path:
        sys.path.insert(0, str(HERE))
    if SKILL_PATH.exists() and str(SKILL_PATH) not in sys.path:
        sys.path.insert(0, str(SKILL_PATH))

    make_worktree()
    for id in ORDER:
        print(f"\n=== {id} ===", flush=True)
        module = load_script(id)
        subject = getattr(module, "SUBJECT", "")
        body = getattr(module, "BODY", "")
        if not subject:
            raise RuntimeError(f"{id}.py is missing SUBJECT")
        module.transform(WT)
        msg = commit_message(id=id, subject=subject, body=body)
        run(["git", "add", "-A"], cwd=WT)
        run(["git", "commit", "-m", msg, "--quiet"], cwd=WT)
        run_pre_commit(WT)

    print("\n=== chain built. final HEAD ===", flush=True)
    run(["git", "log", "--oneline", "-32"], cwd=WT)
    head = run(["git", "rev-parse", "HEAD"], cwd=WT).strip()
    backup_old_chain_head()
    tag_new_chain_head(head)
    print(
        f"\nTo publish, force-push the chain head:\n"
        f"  git -C {WT} push -f upstream HEAD:refs/heads/{CHAIN_BRANCH}\n"
        f"(HEAD={head[:12]})\n",
        flush=True,
    )


if __name__ == "__main__":
    main()
