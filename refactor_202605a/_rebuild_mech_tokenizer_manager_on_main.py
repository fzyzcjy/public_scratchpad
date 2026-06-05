#!/usr/bin/env python3
"""Rebuild tom_refactor_202605a/primary/mech_tokenizer_manager on the LATEST
upstream/main instead of the stacked ``mech_preflight`` base.

Why this script exists (decision log, 2026-06-05):
  * The canonical ``_build_mech_tokenizer_manager.py`` stacks the chain on
    ``upstream/tom_refactor_202605a/primary/mech_preflight`` — a branch that is
    itself ~3 weeks behind ``upstream/main`` (243 commits of drift).
  * ``mech_preflight`` touches only model_runner / scheduler preflight code; it
    does NOT modify ``tokenizer_manager.py`` or create the
    ``tokenizer_manager_components/`` package. The tokenizer-manager transforms
    are therefore self-contained and can be replayed directly on a pristine
    ``upstream/main`` without the preflight base.
  * Task: replay this chain on the latest ``upstream/main`` so the refactor
    reflects current upstream state. Hence BASE = upstream/main here.

Differences vs the canonical builder:
  * BASE = ``main`` (resolved as ``upstream/main``).
  * STOP-ON-FIRST-ERROR with a loud marker + keeps the worktree for inspection.
  * No backup-tag push, no force-push hint. Pure local build for iteration.
"""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
import traceback
from pathlib import Path

HERE = Path(__file__).parent
REPO = Path("/Users/tom/main/workspaces/ws-main/worktrees/sglang-dev-a")
WT = Path("/tmp/refactor-wt-mech-tok-on-main")
BASE = "main"
SKILL_PATH = REPO / ".claude/skills/mechanical-refactor-verify"

# Import ORDER from the canonical builder so the two never drift.
_canonical_spec = importlib.util.spec_from_file_location(
    "_canonical_builder", HERE / "_build_mech_tokenizer_manager.py"
)
_canonical = importlib.util.module_from_spec(_canonical_spec)
_canonical_spec.loader.exec_module(_canonical)
ORDER: list[str] = _canonical.ORDER


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
    """Delegate to the canonical builder so PR grouping stays in one place."""
    return _canonical.commit_message(id=id, subject=subject, body=body)


def run_pre_commit(wt: Path) -> None:
    files = run(["git", "diff", "--name-only", "HEAD~1", "HEAD"], cwd=wt).split()
    if not files:
        return
    run(["pre-commit", "run", "--files", *files], cwd=wt, check=False)
    porcelain = run(["git", "status", "--porcelain"], cwd=wt).strip()
    if porcelain:
        run(["git", "add", "-A"], cwd=wt)
        run(["git", "commit", "--amend", "--no-edit", "--quiet"], cwd=wt)


def resume_worktree(start_id: str) -> int:
    """Reset the kept worktree to its last good commit and return the ORDER
    index to resume from (the position of ``start_id``)."""
    if not WT.exists():
        raise RuntimeError(f"cannot resume: worktree {WT} missing — run full build first")
    run(["git", "reset", "--hard", "HEAD"], cwd=WT)
    run(["git", "clean", "-fd"], cwd=WT)
    if start_id not in ORDER:
        raise RuntimeError(f"resume id {start_id!r} not in ORDER")
    return ORDER.index(start_id)


def main() -> None:
    if str(HERE) not in sys.path:
        sys.path.insert(0, str(HERE))
    if SKILL_PATH.exists() and str(SKILL_PATH) not in sys.path:
        sys.path.insert(0, str(SKILL_PATH))

    start_idx = 0
    if len(sys.argv) >= 3 and sys.argv[1] == "resume":
        start_idx = resume_worktree(sys.argv[2])
        print(f"=== RESUME from [{start_idx + 1}/{len(ORDER)}] {sys.argv[2]} ===", flush=True)
    else:
        make_worktree()
    for idx, id in enumerate(ORDER):
        if idx < start_idx:
            continue
        print(f"\n=== [{idx + 1}/{len(ORDER)}] {id} ===", flush=True)
        try:
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
        except Exception:
            print(f"\n!!!!!! FAILED AT STEP {idx + 1}/{len(ORDER)}: {id} !!!!!!", flush=True)
            traceback.print_exc()
            print(f"\nWorktree kept for inspection at: {WT}", flush=True)
            sys.exit(1)

    print("\n=== final --all-files pre-commit pass ===", flush=True)
    run(["pre-commit", "run", "--all-files"], cwd=WT, check=False)
    porcelain = run(["git", "status", "--porcelain"], cwd=WT).strip()
    if porcelain:
        run(["git", "add", "-A"], cwd=WT)
        run(["git", "commit", "--amend", "--no-edit", "--quiet"], cwd=WT)

    print("\n=== chain built successfully. final HEAD ===", flush=True)
    run(["git", "log", "--oneline", "-45"], cwd=WT)
    head = run(["git", "rev-parse", "HEAD"], cwd=WT).strip()
    print(f"\nALL {len(ORDER)} STEPS OK. HEAD={head[:12]}; worktree at {WT}\n", flush=True)


if __name__ == "__main__":
    main()
