#!/usr/bin/env python3
"""Build tom_refactor_202605a/primary/mech_preflight by cherry-picking /0-/17.

Steps:
  1. Create a fresh worktree at upstream/main.
  2. For each entry in COMMITS, cherry-pick all source commits with
     --no-commit, then make a single commit with the formatted message
     `<id>: <subject>\\n\\n\\nRefactor chain ID: <id>\\n`.
  3. Force-push the worktree HEAD to upstream/tom_refactor_202605a/primary/mech_preflight.

Run locally; reads upstream branches from REPO.
"""

from __future__ import annotations

import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

REPO = Path("/Users/tom/main/workspaces/ws-main/worktrees/sglang-dev-a")
WT = Path("/tmp/refactor-wt-mech-preflight")
TARGET = "tom_refactor_202605a/primary/mech_preflight"


COMMITS: list[tuple[str, list[str], str]] = [
    # (identifier, [source_commits], subject)
    ("convert-self-x-to-locals", ["upstream/tom_refactor/0"],
     "Convert local-only self.X attributes to locals"),
    ("drop-dead-prefill-locals", ["upstream/tom_refactor/1"],
     "Remove dead self.adder/can_run_list/running_bs writes in Scheduler._get_new_batch_prefill_raw"),
    ("drop-unused-tm-fields", ["f9bc80737d"],
     "Remove unused fields in TokenizerManager"),
    ("drop-unused-engine-eagle-fields", ["131c339b16"],
     "Remove unused fields in Engine and EagleDraftWorker"),
    ("drop-unused-spec-disagg-fields", ["267bd00cd5"],
     "Remove unused fields in speculative decoding and disaggregation"),
    # /4 main + /4 autofix (autofix removes FanOutCommunicator import made unused by /4 main).
    ("drop-unused-mgr-runtime-fields", ["c1a86685ec", "4cc299c726"],
     "Remove unused fields in scheduler/Req and manager runtime infrastructure"),
    ("direct-hicache-storage", ["437480a77d"],
     'Replace getattr(self, "enable_hicache_storage") with direct access'),
    ("direct-max-prefill-tokens", ["e6c7107af3"],
     'Replace getattr(self, "max_prefill_tokens") with direct access'),
    ("direct-is-generation", ["6d3e0cd142"],
     'Replace getattr(self, "is_generation") with direct access in score mixin'),
    ("cache-linear-attn-registry", ["upstream/tom_refactor/6"],
     "Cache _linear_attn_registry_cache with sentinel"),
    ("drop-hisparse-guard", ["upstream/tom_refactor/7"],
     "Delete dead hasattr guard for hisparse_coordinator"),
    ("init-forward-pass-timer", ["upstream/tom_refactor/8"],
     "Convert forward_pass_device_timer to None-init"),
    # /9 chronological order: lift first, then init-conditional refinement.
    ("lift-running-batch-mbs", ["5ffc549417"],
     "Lift running_batch and running_mbs to unconditional access"),
    ("init-running-mbs-pp", ["bf894e0c3f"],
     "Make running_mbs init conditional on PP mode"),
    ("drop-metrics-collector-guard", ["f0be5b9729"],
     'Drop redundant hasattr(self, "metrics_collector") guard'),
    ("direct-model-config", ["b064c6ac63"],
     'Replace getattr(self, "model_config") with direct access in score mixin'),
    ("fix-lora-loads", ["upstream/tom_refactor/11"],
     "Fix LoRA pool not appearing in /v1/loads"),
    ("annotate-dead-slo-field", ["upstream/tom_refactor/12"],
     "Annotate dead max_running_requests_under_SLO"),
    ("init-forward-ct-cur-batch", ["5a90678b7f"],
     "Initialize forward_ct and cur_batch before starting watchdog daemon"),
    ("direct-watchdog-defenses", ["f5c278e9b4", "f702369b7e"],
     "Replace getattr defenses on scheduler in create_scheduler_watchdog with direct access"),
    ("add-mechanical-refactor-verify-skill", ["upstream/tom_refactor/14"],
     "Add mechanical-refactor-verify skill from miles"),
    # /15 chronological order: parallel-state introduced first (with autofix +
    # py3.10 slots squashed in), then disagg-prefill rank fix on top.
    ("parallel-state", ["a9ac366486", "458363aa03", "795fedcbe3"],
     "Bundle Scheduler rank/size fields into a frozen ParallelState"),
    ("fix-disagg-prefill-rank", ["b40369adef"],
     "Fix stale self.tp_rank/pp_rank in SchedulerDisaggregationPrefillMixin"),
    ("inject-parallel-state-profiler", ["upstream/tom_refactor/16"],
     "Inject ParallelState into ProfilerV2"),
    ("fix-trace-filename-collision", ["upstream/tom_refactor/17"],
     "Fix V2 trace filename collisions when DP/PP/EP enabled"),
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
    run(["git", "fetch", "upstream", "main"], cwd=REPO)
    run(["git", "worktree", "add", "--detach", str(WT), "upstream/main"], cwd=REPO)


def commit_message(*, id: str, subject: str) -> str:
    return f"{id}: {subject}\n\n\nRefactor chain ID: {id}\n"


def cherry_pick_and_commit(*, id: str, sources: list[str], subject: str) -> None:
    for src in sources:
        run(["git", "cherry-pick", "--no-commit", src], cwd=WT)
    msg = commit_message(id=id, subject=subject)
    run(["git", "commit", "-m", msg, "--quiet"], cwd=WT)


def backup_old_chain_head() -> None:
    """Tag the current upstream/<TARGET> HEAD before any force-push.

    Per PR_CHAIN.md backup rule. Tag name encodes a UTC second-precision
    timestamp so multiple rebuilds in one day each get a distinct backup tag.
    Skips silently on first build (no upstream branch yet).
    """
    run(["git", "fetch", "upstream", TARGET], cwd=REPO, check=False)
    sha = run(
        ["git", "rev-parse", "--verify", "--quiet", f"upstream/{TARGET}"],
        cwd=REPO,
        check=False,
    ).strip()
    if not sha:
        print(f"\n=== no existing upstream/{TARGET} — skipping backup tag ===", flush=True)
        return
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")
    area = TARGET.split("/")[-1]
    tag_name = f"backup/{timestamp}/{area}"
    # Push backup tag to origin (fzyzcjy/sglang fork) — upstream sgl-project
    # repo rules reject `backup/*` namespace.
    print(f"\n=== backing up old upstream/{TARGET} ({sha[:12]}) as {tag_name} on origin ===", flush=True)
    run(["git", "tag", tag_name, sha], cwd=REPO)
    run(["git", "push", "origin", f"refs/tags/{tag_name}"], cwd=REPO)


def main() -> None:
    make_worktree()
    for id, sources, subject in COMMITS:
        print(f"\n=== {id} ===", flush=True)
        cherry_pick_and_commit(id=id, sources=sources, subject=subject)
    print("\n=== done. final HEAD ===", flush=True)
    run(["git", "log", "--oneline", "-30"], cwd=WT)
    backup_old_chain_head()
    head = run(["git", "rev-parse", "HEAD"], cwd=WT).strip()
    print(
        f"\nTo publish, force-push the chain head:\n"
        f"  git -C {WT} push -f upstream HEAD:refs/heads/{TARGET}\n"
        f"(HEAD={head[:12]})\n",
        flush=True,
    )


if __name__ == "__main__":
    main()
