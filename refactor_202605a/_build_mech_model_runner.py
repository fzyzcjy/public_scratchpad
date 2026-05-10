#!/usr/bin/env python3
"""Build tom_refactor_202605a/raw/mech_model_runner from /18-/48 onto mech_preflight.

For each /N (N=18..48):
  1. cherry-pick upstream/tom_refactor/N onto a worktree starting at mech_preflight head
  2. amend the commit message to <id>: <subject>\\n\\n\\nRefactor chain ID: <id>\\n

The script only builds the chain locally; push to upstream is a separate
manual step (see PR_CHAIN.md). Only the chain head ref
`tom_refactor_202605a/raw/mech_model_runner` is pushed — no per-commit
leaf branches.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

REPO = Path("/Users/tom/main/workspaces/ws-main/worktrees/sglang-dev-a")
WT = Path("/tmp/refactor-wt-mech-model-runner")
BASE = "tom_refactor_202605a/raw/mech_preflight"
CHAIN_BRANCH = "tom_refactor_202605a/raw/mech_model_runner"


# /18..48 → identifier (chronological order; each /N is exactly 1 commit on /N-1).
MAPPING: list[tuple[int, str, str]] = [
    (18, "extract-init-cublas",            "Extract init_cublas to free function in utils.common"),
    (19, "extract-apply-torch-tp",         "Extract apply_torch_tp to free function in layers.model_parallel"),
    (20, "extract-init-threads-binding",   "Extract init_threads_binding to free function in utils.numa_utils"),
    (21, "inline-max-pool-size",           "Inline max_token_pool_size property at sole consumer"),
    (22, "extract-prealloc-symm-pool",     "Extract prealloc_symmetric_memory_pool to free function"),
    (23, "extract-kv-cache-dtype",         "Extract configure_kv_cache_dtype to mem_cache.kv_cache_dtype"),
    (24, "introduce-weight-updater",       "Introduce WeightUpdater and move weights update group lifecycle methods"),
    (25, "wu-move-from-disk",              "Move update_weights_from_disk onto WeightUpdater"),
    (26, "wu-move-from-distributed",       "Move update_weights_from_distributed onto WeightUpdater"),
    (27, "wu-move-from-tensor",            "Move update_weights_from_tensor and helpers onto WeightUpdater"),
    (28, "wu-move-from-ipc",               "Move update_weights_from_ipc onto WeightUpdater"),
    (29, "introduce-weight-exporter",      "Introduce WeightExporter and move weights send group methods"),
    (30, "we-move-save-get",               "Move weight save and get_weights_by_name methods onto WeightExporter"),
    (31, "extract-update-expert-location", "Extract ModelRunner.update_expert_location to free function in expert_location_updater"),
    (32, "extract-init-device-graphs",     "Extract init_device_graphs to free function in model_executor.device_graphs"),
    (33, "extract-piecewise-cuda-graphs",  "Extract init_piecewise_cuda_graphs to free function in model_executor.device_graphs"),
    (34, "extract-hybrid-arch-props",      "Extract 7 hybrid-arch properties to free functions in configs.hybrid_arch"),
    (35, "drop-hybrid-arch-delegates",     "Drop hybrid-arch property delegates from ModelRunner; update consumers"),
    (36, "extract-autotune-helpers",       "Extract _should_run_flashinfer_autotune and _flashinfer_autotune_cache_path to free functions"),
    (37, "extract-kernel-warmup",          "Extract kernel_warmup and _flashinfer_autotune to free functions"),
    (38, "extract-lora-moe-buffers",       "Extract _init_lora_cuda_graph_moe_buffers to free function in lora_manager"),
    (39, "init-dist",                      "Extract init_torch_distributed to distributed/bootstrap.py"),
    (40, "introduce-rwt-skeleton",         "Extract RemoteInstanceWeightTransport skeleton with remote_instance_init_transfer_engine"),
    (41, "rwt-migrate-register-bootstrap", "Migrate _register_to_engine_info_bootstrap to RemoteInstanceWeightTransport"),
    (42, "rwt-migrate-modelexpress-publish", "Migrate ModelExpress metadata publishing to RemoteInstanceWeightTransport"),
    (43, "introduce-ngram-embedding-mgr",  "Introduce NgramEmbeddingManager (PR 1/3 of ngram embedding migration)"),
    (44, "nem-migrate-maybe-prepare",      "Migrate _maybe_prepare_ngram_embedding to NgramEmbeddingManager (PR 2/3)"),
    (45, "nem-migrate-cuda-graph",         "Migrate CudaGraphRunner ngram-embedding reads to NgramEmbeddingManager (PR 3/3)"),
    (46, "move-rank-zero-filter",          "Move RankZeroFilter from model_runner.py to utils/log_utils.py"),
    (47, "move-resolve-language-model",    "Move resolve_language_model from model_runner.py to model_loader/utils.py"),
    (48, "move-step-span-name",            "Move _build_step_span_name from model_runner.py to utils/profile_utils.py"),
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


def commit_message(*, id: str, subject: str) -> str:
    return f"{id}: {subject}\n\n\nRefactor chain ID: {id}\n"


def main() -> None:
    make_worktree()
    for n, id, subject in MAPPING:
        print(f"\n=== /{n} -> {id} ===", flush=True)
        run(["git", "cherry-pick", "--no-commit", f"upstream/tom_refactor/{n}"], cwd=WT)
        msg = commit_message(id=id, subject=subject)
        run(["git", "commit", "-m", msg, "--quiet"], cwd=WT)
    print("\n=== chain built. final HEAD ===", flush=True)
    run(["git", "log", "--oneline", "-32"], cwd=WT)
    head = run(["git", "rev-parse", "HEAD"], cwd=WT).strip()
    print(
        f"\nTo publish, force-push the chain head:\n"
        f"  git -C {WT} push -f upstream HEAD:refs/heads/{CHAIN_BRANCH}\n"
        f"(HEAD={head[:12]})\n",
        flush=True,
    )


if __name__ == "__main__":
    main()
