#!/usr/bin/env python3
"""Build tom_refactor_202605a/primary/mech_scheduler from `<id>.py` scripts.

Pattern matches `_build_mech_model_runner.py`. ORDER lists the 17 commit
identifiers (C1-C17 per the mech-scheduler plan).

For each `<id>` in ORDER:
  1. Dynamically import `<id>.py`, read `SUBJECT` / `BODY` attrs.
  2. Call `transform(wt)` on a worktree starting at the cumulative chain head
     (begins at `upstream/mech_preflight`, advances by 1 commit per script).
  3. Commit with formatted message `<id>: <subject>\\n\\n<body>\\n\\nRefactor chain ID: <id>`.
  4. Run pre-commit; amend if it auto-fixed.

After build:
  - Auto-tag the OLD `upstream/<chain_branch>` HEAD as `backup/<UTC>/<area>` and
    push that tag to origin (per PR_CHAIN.md backup rule).
  - Print the force-push command for the new chain (manual step).
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
WT = Path("/tmp/refactor-wt-mech-scheduler")
BASE = "tom_refactor_202605a/primary/mech_preflight"
CHAIN_BRANCH = "tom_refactor_202605a/primary/mech_scheduler"
SKILL_PATH = REPO / ".claude/skills/mechanical-refactor-verify"


# Chain ordering. Each entry is the `<id>` part of a `<id>.py` script in this
# directory.
ORDER: list[str] = [
    # Group A — Scheduler 主类抽出 (each: prep + move)
    "extract-get-draft-kv-pool-prep",
    "extract-get-draft-kv-pool-move",
    "extract-maybe-register-hicache-draft-prep",
    "extract-maybe-register-hicache-draft-move",
    "extract-build-kv-cache-pre-prep",
    "extract-build-kv-cache-prep",
    "extract-build-kv-cache-move",
    "init-mode-conditional-defaults",
    "introduce-scheduler-request-receiver-prep",
    "introduce-scheduler-request-receiver-move",
    # Group B — Mixin mech-move (each: prep + move)
    "migrate-dp-attn-mixin-prep",
    "migrate-dp-attn-mixin-move",
    "migrate-profiler-mixin-pre-rename",
    "migrate-profiler-mixin-pre-prep",
    "migrate-profiler-mixin-prep",
    "migrate-profiler-mixin-move",
    "migrate-update-weights-mixin-pre-prep1",
    "migrate-update-weights-mixin-pre-prep2",
    "migrate-update-weights-mixin-prep",
    "migrate-update-weights-mixin-move",
    "move-on-idle-to-scheduler-main",  # single (doc exception)
    "introduce-pool-stats-observer-prep",
    "introduce-pool-stats-observer-move",
    "introduce-invariant-checker-pre-prep",
    "introduce-invariant-checker-prep",
    "introduce-invariant-checker-move",
    "introduce-kv-events-publisher-pre-rename",
    "introduce-kv-events-publisher-prep",
    "introduce-kv-events-publisher-move",
    "introduce-load-inquirer-prep",
    "introduce-load-inquirer-move",
    "introduce-metrics-reporter-pre-rename",
    "introduce-metrics-reporter-prep",
    "introduce-metrics-reporter-move",
    "move-maybe-log-idle-metrics-to-metrics-reporter",  # single (doc exception)
    "introduce-logprob-result-processor-pre-rename",
    "introduce-logprob-result-processor-prep",
    "introduce-logprob-result-processor-move",
    "introduce-output-streamer-prep",
    "introduce-output-streamer-move",
    "introduce-batch-result-processor-prep",
    "introduce-batch-result-processor-move",
    # Tail follow-ups: relocate residual module-level free items out of
    # scheduler.py (mech move + non-mech cleanup).
    "move-free-items-from-scheduler-py",
    "cleanup-scheduler-py-free-items",
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


def main() -> None:
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
    print(
        f"\nTo publish, force-push the chain head:\n"
        f"  git -C {WT} push -f upstream HEAD:refs/heads/{CHAIN_BRANCH}\n"
        f"(HEAD={head[:12]})\n",
        flush=True,
    )


if __name__ == "__main__":
    main()
