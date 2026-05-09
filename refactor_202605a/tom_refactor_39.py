#!/usr/bin/env python3
"""Reproducible transform: replace ModelRunnerKVCacheMixin with KVCacheConfigurator
(composition).

- Renames `model_runner_kv_cache_mixin.py` -> `kv_cache_configurator.py`.
- Renames the class `ModelRunnerKVCacheMixin` -> `KVCacheConfigurator`.
- Adds a real `__init__` taking the kv-cache-related fields explicitly.
- Drops the `self: ModelRunner` annotations on the methods.
- Drops the docstrings on `_apply_token_constraints` / `_resolve_max_num_reqs`.
- Updates `model_runner.py` to no longer subclass the mixin and instead build
  a `KVCacheConfigurator` lazily inside an `init_memory_pool` wrapper that
  copies outputs back onto `self`.
"""

import sys
from pathlib import Path

sys.path.append(".claude/skills/mechanical-refactor-verify")
from mechanical_refactor_verify_utils import (
    verify_mechanical_refactor,
    git_add_and_commit,
)

BASE_COMMIT = "tom_refactor/38"
TARGET_COMMIT = "tom_refactor/39"


def transform(dir_root: Path) -> None:
    src = dir_root / "python/sglang/srt/model_executor/model_runner_kv_cache_mixin.py"
    dst = dir_root / "python/sglang/srt/model_executor/kv_cache_configurator.py"
    text = src.read_text()

    init_block = (
        "class KVCacheConfigurator:\n"
        "\n"
        "    def __init__(\n"
        "        self,\n"
        "        *,\n"
        "        # --- Deployment / device ---\n"
        "        device: str,\n"
        "        gpu_id: int,\n"
        "        mem_fraction_static: float,\n"
        "        page_size: int,\n"
        "        # --- Parallel ranks / sizes ---\n"
        "        dp_size: int,\n"
        "        pp_size: int,\n"
        "        # --- Model + server config aggregates (config aggregate exception) ---\n"
        "        model_config,\n"
        "        server_args,\n"
        "        # --- Dtype info ---\n"
        "        kv_cache_dtype,\n"
        "        state_dtype,\n"
        "        # --- Spec / draft worker ---\n"
        "        spec_algorithm,\n"
        "        is_draft_worker: bool,\n"
        "        # --- Architecture flags ---\n"
        "        is_hybrid_swa: bool,\n"
        "        is_hybrid_swa_compress: bool,\n"
        "        use_mla_backend: bool,\n"
        "        enable_hisparse: bool,\n"
        "        # --- PP layer slice ---\n"
        "        start_layer: int,\n"
        "        end_layer: int,\n"
        "        num_effective_layers: int,\n"
        "        # --- Initial pool state (may be None on target; pre-set on draft) ---\n"
        "        req_to_token_pool,\n"
        "        token_to_kv_pool_allocator,\n"
        "        memory_pool_config,\n"
        "        # --- Initial running-request budget (configure() may shrink it) ---\n"
        "        max_running_requests: int,\n"
        "    ) -> None:\n"
        "        self.device = device\n"
        "        self.gpu_id = gpu_id\n"
        "        self.mem_fraction_static = mem_fraction_static\n"
        "        self.page_size = page_size\n"
        "        self.dp_size = dp_size\n"
        "        self.pp_size = pp_size\n"
        "        self.model_config = model_config\n"
        "        self.server_args = server_args\n"
        "        self.kv_cache_dtype = kv_cache_dtype\n"
        "        self.state_dtype = state_dtype\n"
        "        self.spec_algorithm = spec_algorithm\n"
        "        self.is_draft_worker = is_draft_worker\n"
        "        self.is_hybrid_swa = is_hybrid_swa\n"
        "        self.is_hybrid_swa_compress = is_hybrid_swa_compress\n"
        "        self.use_mla_backend = use_mla_backend\n"
        "        self.enable_hisparse = enable_hisparse\n"
        "        self.start_layer = start_layer\n"
        "        self.end_layer = end_layer\n"
        "        self.num_effective_layers = num_effective_layers\n"
        "        # --- Pool state (mutated during init_memory_pool) ---\n"
        "        self.req_to_token_pool = req_to_token_pool\n"
        "        self.token_to_kv_pool_allocator = token_to_kv_pool_allocator\n"
        "        self.memory_pool_config = memory_pool_config\n"
        "        self.max_running_requests = max_running_requests\n"
        "        # --- Outputs filled during init_memory_pool ---\n"
        "        self.max_total_num_tokens: int = 0\n"
        "        self.full_max_total_num_tokens: int = 0\n"
        "        self.swa_max_total_num_tokens: int = 0\n"
        "        self.token_to_kv_pool = None\n"
        "        # HiSparse-specific fields are written by _init_pools when relevant.\n"
        "        self.c128_max_total_num_tokens = None\n"
        "        self.c128_state_pool_size = None\n"
        "        self.c4_max_total_num_tokens = None\n"
        "        self.c4_state_pool_size = None\n"
        "\n"
        "    def _profile_available_bytes(self, pre_model_load_memory: int) -> int:\n"
    )

    old_class_open = (
        "class ModelRunnerKVCacheMixin:\n"
        "    def _profile_available_bytes(self: ModelRunner, pre_model_load_memory: int) -> int:\n"
    )
    assert old_class_open in text
    text = text.replace(old_class_open, init_block)

    # Drop `self: ModelRunner` -> `self` on remaining methods.
    method_renames = [
        (
            "    def handle_max_mamba_cache(self: ModelRunner, total_rest_memory):\n",
            "    def handle_max_mamba_cache(self, total_rest_memory):\n",
        ),
        (
            "    def calculate_mla_kv_cache_dim(self: ModelRunner) -> int:\n",
            "    def calculate_mla_kv_cache_dim(self) -> int:\n",
        ),
        (
            "    def _calculate_mamba_ratio(self: ModelRunner) -> int:\n",
            "    def _calculate_mamba_ratio(self) -> int:\n",
        ),
        (
            "    def _init_pools(self: ModelRunner):\n",
            "    def _init_pools(self):\n",
        ),
        (
            "    def _apply_memory_pool_config(self: ModelRunner, config: MemoryPoolConfig):\n",
            "    def _apply_memory_pool_config(self, config: MemoryPoolConfig):\n",
        ),
        (
            "    def init_memory_pool(self: ModelRunner, pre_model_load_memory: int):\n",
            "    def init_memory_pool(self, pre_model_load_memory: int):\n",
        ),
    ]
    for old, new in method_renames:
        assert old in text, f"missing: {old!r}"
        text = text.replace(old, new)

    # Drop docstring on _apply_token_constraints
    old_apply_constraints = (
        "    def _apply_token_constraints(self: ModelRunner, token_capacity: int) -> int:\n"
        '        """Apply external constraints to token capacity: user cap, PP sync.\n'
        "\n"
        "        Page alignment is handled by the configurator, not here.\n"
        "        If constraints change the value, the configurator re-runs and re-aligns.\n"
        '        """\n'
    )
    new_apply_constraints = (
        "    def _apply_token_constraints(self, token_capacity: int) -> int:\n"
    )
    assert old_apply_constraints in text
    text = text.replace(old_apply_constraints, new_apply_constraints)

    # Drop docstring on _resolve_max_num_reqs
    old_resolve = (
        "    def _resolve_max_num_reqs(self: ModelRunner, token_capacity: int) -> int:\n"
        '        """Compute max concurrent requests (per dp worker) from the finalized\n'
        '        token capacity."""\n'
    )
    new_resolve = (
        "    def _resolve_max_num_reqs(self, token_capacity: int) -> int:\n"
    )
    assert old_resolve in text
    text = text.replace(old_resolve, new_resolve)

    # Write to renamed file and remove old file.
    dst.write_text(text)
    src.unlink()

    # ---- Update model_runner.py ----
    mr = dir_root / "python/sglang/srt/model_executor/model_runner.py"
    text = mr.read_text()

    # Imports: drop the mixin import, add KVCacheConfigurator import
    text = text.replace(
        "from sglang.srt.model_executor.kernel_warmup import kernel_warmup as _kernel_warmup\n"
        "from sglang.srt.model_executor.weight_exporter import WeightExporter\n",
        "from sglang.srt.model_executor.kernel_warmup import kernel_warmup as _kernel_warmup\n"
        "from sglang.srt.model_executor.kv_cache_configurator import KVCacheConfigurator\n"
        "from sglang.srt.model_executor.weight_exporter import WeightExporter\n",
    )
    text = text.replace(
        "from sglang.srt.model_executor.model_runner_kv_cache_mixin import (\n"
        "    ModelRunnerKVCacheMixin,\n"
        ")\n",
        "",
    )

    # Class no longer inherits the mixin
    text = text.replace(
        "class ModelRunner(ModelRunnerKVCacheMixin):\n",
        "class ModelRunner:\n",
    )

    # Insert new init_memory_pool wrapper method.
    new_method = (
        "\n\n"
        "    def init_memory_pool(self, pre_model_load_memory: int):\n"
        "        # Construct lazily here, after `initialize()` has set the layer-slice\n"
        "        # fields (`start_layer` etc.), kv_cache_dtype, and friends.\n"
        "        self.kv_cache_configurator = KVCacheConfigurator(\n"
        "            device=self.device,\n"
        "            gpu_id=self.gpu_id,\n"
        "            mem_fraction_static=self.mem_fraction_static,\n"
        "            page_size=self.page_size,\n"
        "            dp_size=self.dp_size,\n"
        "            pp_size=self.pp_size,\n"
        "            model_config=self.model_config,\n"
        "            server_args=self.server_args,\n"
        "            kv_cache_dtype=self.kv_cache_dtype,\n"
        "            state_dtype=self.dtype,\n"
        "            spec_algorithm=self.spec_algorithm,\n"
        "            is_draft_worker=self.is_draft_worker,\n"
        "            is_hybrid_swa=self.is_hybrid_swa,\n"
        "            is_hybrid_swa_compress=self.is_hybrid_swa_compress,\n"
        "            use_mla_backend=self.use_mla_backend,\n"
        "            enable_hisparse=self.enable_hisparse,\n"
        "            start_layer=self.start_layer,\n"
        "            end_layer=self.end_layer,\n"
        "            num_effective_layers=self.num_effective_layers,\n"
        "            req_to_token_pool=self.req_to_token_pool,\n"
        "            token_to_kv_pool_allocator=self.token_to_kv_pool_allocator,\n"
        "            memory_pool_config=self.memory_pool_config,\n"
        "            max_running_requests=self.server_args.max_running_requests,\n"
        "        )\n"
        "        self.kv_cache_configurator.init_memory_pool(pre_model_load_memory)\n"
        "        # Copy outputs back so existing consumers (e.g. cuda_graph_runner) that\n"
        "        # read `model_runner.token_to_kv_pool` keep working without indirection.\n"
        "        cfg = self.kv_cache_configurator\n"
        "        self.req_to_token_pool = cfg.req_to_token_pool\n"
        "        self.token_to_kv_pool = cfg.token_to_kv_pool\n"
        "        self.token_to_kv_pool_allocator = cfg.token_to_kv_pool_allocator\n"
        "        self.memory_pool_config = cfg.memory_pool_config\n"
        "        self.max_total_num_tokens = cfg.max_total_num_tokens\n"
        "        self.max_running_requests = cfg.max_running_requests\n"
        "        self.full_max_total_num_tokens = cfg.full_max_total_num_tokens\n"
        "        self.swa_max_total_num_tokens = cfg.swa_max_total_num_tokens\n"
        "        self.page_size = cfg.page_size\n"
        "        self.state_dtype = cfg.state_dtype\n"
        "        if cfg.c128_max_total_num_tokens is not None:\n"
        "            self.c128_max_total_num_tokens = cfg.c128_max_total_num_tokens\n"
        "            self.c128_state_pool_size = cfg.c128_state_pool_size\n"
        "            self.c4_max_total_num_tokens = cfg.c4_max_total_num_tokens\n"
        "            self.c4_state_pool_size = cfg.c4_state_pool_size\n"
    )

    # Insert before `update_decode_attn_backend`. Anchor on the unique
    # surrounding context: end of `create_piecewise_cuda_graphs(...)` call
    # block followed by an empty line and then `def update_decode_attn_backend`.
    anchor = (
        "            gpu_id=self.gpu_id,\n"
        "        )\n"
        "\n"
        "\n"
        "    def update_decode_attn_backend(self, stream_idx: int):\n"
    )
    assert anchor in text, "anchor before update_decode_attn_backend not found"
    text = text.replace(
        anchor,
        "            gpu_id=self.gpu_id,\n"
        "        )\n"
        + new_method
        + "\n"
        "    def update_decode_attn_backend(self, stream_idx: int):\n",
    )

    mr.write_text(text)

    git_add_and_commit(
        "Replace ModelRunnerKVCacheMixin with KVCacheConfigurator (composition)",
        cwd=str(dir_root),
    )


if __name__ == "__main__":
    verify_mechanical_refactor(
        base_commit=BASE_COMMIT,
        target_commit=TARGET_COMMIT,
        transform=transform,
    )
