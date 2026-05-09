#!/usr/bin/env python3
"""Replace `ModelRunnerKVCacheMixin` with `KVCacheConfigurator` (composition).

- Renames file `model_runner_kv_cache_mixin.py` -> `kv_cache_configurator.py`.
- Renames class `ModelRunnerKVCacheMixin` -> `KVCacheConfigurator`.
- Adds an explicit `__init__` taking ALL fields the methods access via `self.X`.
- Drops the `self: ModelRunner` annotations on each method.
- Drops two method docstrings that referenced the mixin context.
- ModelRunner: drops the mixin inheritance, replaces with composition. Adds an
  `init_memory_pool` wrapper method that builds a configurator, runs it, and
  copies output fields back to `self`.
"""

import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.append(str(HERE))
sys.path.append(".claude/skills/mechanical-refactor-verify")
from _helpers import insert_after, replace_call_site
from mechanical_refactor_verify_utils import (
    git_add_and_commit,
    verify_mechanical_refactor,
)

BASE_COMMIT = "tom_refactor/38"
TARGET_COMMIT = "tom_refactor/39"

INIT_BODY = """\

    def __init__(
        self,
        *,
        device: str,
        gpu_id: int,
        mem_fraction_static: float,
        page_size: int,
        dp_size: int,
        pp_size: int,
        model_config,
        server_args,
        kv_cache_dtype,
        state_dtype,
        spec_algorithm,
        is_draft_worker: bool,
        is_hybrid_swa: bool,
        is_hybrid_swa_compress: bool,
        use_mla_backend: bool,
        enable_hisparse: bool,
        start_layer: int,
        end_layer: int,
        num_effective_layers: int,
        mambaish_config,
        hybrid_gdn_config,
        req_to_token_pool,
        token_to_kv_pool_allocator,
        memory_pool_config,
        max_running_requests,
    ) -> None:
        self.device = device
        self.gpu_id = gpu_id
        self.mem_fraction_static = mem_fraction_static
        self.page_size = page_size
        self.dp_size = dp_size
        self.pp_size = pp_size
        self.model_config = model_config
        self.server_args = server_args
        self.kv_cache_dtype = kv_cache_dtype
        self.state_dtype = state_dtype
        self.spec_algorithm = spec_algorithm
        self.is_draft_worker = is_draft_worker
        self.is_hybrid_swa = is_hybrid_swa
        self.is_hybrid_swa_compress = is_hybrid_swa_compress
        self.use_mla_backend = use_mla_backend
        self.enable_hisparse = enable_hisparse
        self.start_layer = start_layer
        self.end_layer = end_layer
        self.num_effective_layers = num_effective_layers
        self.mambaish_config = mambaish_config
        self.hybrid_gdn_config = hybrid_gdn_config
        self.req_to_token_pool = req_to_token_pool
        self.token_to_kv_pool_allocator = token_to_kv_pool_allocator
        self.memory_pool_config = memory_pool_config
        self.max_running_requests = max_running_requests
        self.max_total_num_tokens: int = 0
        self.full_max_total_num_tokens: int = 0
        self.swa_max_total_num_tokens: int = 0
        self.token_to_kv_pool = None
        self.c128_max_total_num_tokens = None
        self.c128_state_pool_size = None
        self.c4_max_total_num_tokens = None
        self.c4_state_pool_size = None
"""

WRAPPER_METHOD = """\


    def init_memory_pool(self, pre_model_load_memory: int):
        self.kv_cache_configurator = KVCacheConfigurator(
            device=self.device,
            gpu_id=self.gpu_id,
            mem_fraction_static=self.mem_fraction_static,
            page_size=self.page_size,
            dp_size=self.dp_size,
            pp_size=self.pp_size,
            model_config=self.model_config,
            server_args=self.server_args,
            kv_cache_dtype=self.kv_cache_dtype,
            state_dtype=self.dtype,
            spec_algorithm=self.spec_algorithm,
            is_draft_worker=self.is_draft_worker,
            is_hybrid_swa=self.is_hybrid_swa,
            is_hybrid_swa_compress=self.is_hybrid_swa_compress,
            use_mla_backend=self.use_mla_backend,
            enable_hisparse=self.enable_hisparse,
            start_layer=self.start_layer,
            end_layer=self.end_layer,
            num_effective_layers=self.num_effective_layers,
            mambaish_config=self.mambaish_config,
            hybrid_gdn_config=self.hybrid_gdn_config,
            req_to_token_pool=self.req_to_token_pool,
            token_to_kv_pool_allocator=self.token_to_kv_pool_allocator,
            memory_pool_config=self.memory_pool_config,
            max_running_requests=self.server_args.max_running_requests,
        )
        self.kv_cache_configurator.init_memory_pool(pre_model_load_memory)
        cfg = self.kv_cache_configurator
        self.req_to_token_pool = cfg.req_to_token_pool
        self.token_to_kv_pool = cfg.token_to_kv_pool
        self.token_to_kv_pool_allocator = cfg.token_to_kv_pool_allocator
        self.memory_pool_config = cfg.memory_pool_config
        self.max_total_num_tokens = cfg.max_total_num_tokens
        self.max_running_requests = cfg.max_running_requests
        self.full_max_total_num_tokens = cfg.full_max_total_num_tokens
        self.swa_max_total_num_tokens = cfg.swa_max_total_num_tokens
        self.page_size = cfg.page_size
        self.state_dtype = cfg.state_dtype
        if cfg.c128_max_total_num_tokens is not None:
            self.c128_max_total_num_tokens = cfg.c128_max_total_num_tokens
            self.c128_state_pool_size = cfg.c128_state_pool_size
            self.c4_max_total_num_tokens = cfg.c4_max_total_num_tokens
            self.c4_state_pool_size = cfg.c4_state_pool_size
"""


def transform(dir_root: Path) -> None:
    src = dir_root / "python/sglang/srt/model_executor/model_runner_kv_cache_mixin.py"
    dst = dir_root / "python/sglang/srt/model_executor/kv_cache_configurator.py"

    # ---- Rename file ----
    src.rename(dst)

    # ---- Rename class + drop annotations + drop docstrings + add __init__ ----
    text = dst.read_text()

    # Drop `self: ModelRunner` annotations on every method.
    method_renames = [
        ("    def _profile_available_bytes(self: ModelRunner, pre_model_load_memory: int) -> int:\n",
         "    def _profile_available_bytes(self, pre_model_load_memory: int) -> int:\n"),
        ("    def handle_max_mamba_cache(self: ModelRunner, total_rest_memory):\n",
         "    def handle_max_mamba_cache(self, total_rest_memory):\n"),
        ("    def calculate_mla_kv_cache_dim(self: ModelRunner) -> int:\n",
         "    def calculate_mla_kv_cache_dim(self) -> int:\n"),
        ("    def _calculate_mamba_ratio(self: ModelRunner) -> int:\n",
         "    def _calculate_mamba_ratio(self) -> int:\n"),
        ("    def _init_pools(self: ModelRunner):\n",
         "    def _init_pools(self):\n"),
        ("    def _apply_memory_pool_config(self: ModelRunner, config: MemoryPoolConfig):\n",
         "    def _apply_memory_pool_config(self, config: MemoryPoolConfig):\n"),
        (
            "    def _resolve_memory_pool_config(\n        self: ModelRunner, pre_model_load_memory: int\n    ) -> MemoryPoolConfig:\n",
            "    def _resolve_memory_pool_config(\n        self, pre_model_load_memory: int\n    ) -> MemoryPoolConfig:\n",
        ),
        ("    def init_memory_pool(self: ModelRunner, pre_model_load_memory: int):\n",
         "    def init_memory_pool(self, pre_model_load_memory: int):\n"),
    ]
    for old, new in method_renames:
        text = replace_call_site(text, old=old, new=new)

    # Drop docstring on _apply_token_constraints (and its annotation).
    text = replace_call_site(
        text,
        old=(
            "    def _apply_token_constraints(self: ModelRunner, token_capacity: int) -> int:\n"
            '        """Apply external constraints to token capacity: user cap, PP sync.\n'
            "\n"
            "        Page alignment is handled by the configurator, not here.\n"
            "        If constraints change the value, the configurator re-runs and re-aligns.\n"
            '        """\n'
        ),
        new="    def _apply_token_constraints(self, token_capacity: int) -> int:\n",
    )

    # Drop docstring on _resolve_max_num_reqs (and its annotation).
    text = replace_call_site(
        text,
        old=(
            "    def _resolve_max_num_reqs(self: ModelRunner, token_capacity: int) -> int:\n"
            '        """Compute max concurrent requests (per dp worker) from the finalized\n'
            '        token capacity."""\n'
        ),
        new="    def _resolve_max_num_reqs(self, token_capacity: int) -> int:\n",
    )

    # Rename class + insert __init__ block.
    text = replace_call_site(
        text,
        old="class ModelRunnerKVCacheMixin:\n",
        new="class KVCacheConfigurator:\n" + INIT_BODY,
    )

    dst.write_text(text)

    # ---- Update model_runner.py: drop mixin, add KVCacheConfigurator + wrapper ----
    mr = dir_root / "python/sglang/srt/model_executor/model_runner.py"
    text = mr.read_text()

    # Replace the mixin import with the configurator import.
    text = replace_call_site(
        text,
        old=(
            "from sglang.srt.model_executor.model_runner_kv_cache_mixin import (\n"
            "    ModelRunnerKVCacheMixin,\n"
            ")\n"
        ),
        new="from sglang.srt.model_executor.kv_cache_configurator import KVCacheConfigurator\n",
    )

    # Drop the inheritance.
    text = replace_call_site(
        text,
        old="class ModelRunner(ModelRunnerKVCacheMixin):\n",
        new="class ModelRunner:\n",
    )

    # Insert the wrapper `init_memory_pool` method right before `update_decode_attn_backend`.
    text = insert_after(
        text,
        anchor=(
            "            model_config=self.model_config,\n"
            "        )\n"
            "\n"
            "    def update_decode_attn_backend(self, stream_idx: int):\n"
        ),
        addition="",
    )
    # The simpler form: replace the close + blank + def with close + wrapper + blank + def.
    text = replace_call_site(
        text,
        old=(
            "            model_config=self.model_config,\n"
            "        )\n"
            "\n"
            "    def update_decode_attn_backend(self, stream_idx: int):\n"
        ),
        new=(
            "            model_config=self.model_config,\n"
            "        )"
            + WRAPPER_METHOD
            + "\n"
            "    def update_decode_attn_backend(self, stream_idx: int):\n"
        ),
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
