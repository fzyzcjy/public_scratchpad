#!/usr/bin/env python3
"""Cut 7 hybrid-arch ModelRunner properties + 1 helper to free functions in
`configs/hybrid_arch.py`. Each property body is cut byte-identical (via
`find_method_lines` + line-range slice) and reassembled with `self.X`
substitutions. ModelRunner properties become 1-line delegates.
"""

import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.append(str(HERE))
sys.path.append(".claude/skills/mechanical-refactor-verify")
from _helpers import (
    append_to_file,
    dedent_method_to_function,
    find_method_lines,
)
from mechanical_refactor_verify_utils import (
    git_add_and_commit,
    verify_mechanical_refactor,
)

BASE_COMMIT = "tom_refactor/33"
TARGET_COMMIT = "tom_refactor/34"


def _swap_method(mr: Path, *, method_name: str, delegate: str) -> str:
    """Cut method [start, end) from ModelRunner, splice ``delegate`` in its place,
    and return the original method text for free-function construction."""
    text = mr.read_text()
    start, end = find_method_lines(text, class_name="ModelRunner", method_name=method_name)
    src = text.splitlines(keepends=True)
    method_text = "".join(src[start:end])
    mr.write_text("".join(src[:start] + [delegate] + src[end:]))
    return method_text


def _to_free_func(method_text: str, *, old_sig: str, new_sig: str, subs: dict[str, str]) -> str:
    """Dedent method body, drop @property decorator, swap signature, apply subs."""
    fn = dedent_method_to_function(method_text)
    fn = fn.replace("@property\n", "", 1)
    fn = fn.replace(old_sig, new_sig)
    for old, new in subs.items():
        fn = fn.replace(old, new)
    return fn


def transform(dir_root: Path) -> None:
    mr = dir_root / "python/sglang/srt/model_executor/model_runner.py"
    ha = dir_root / "python/sglang/srt/configs/hybrid_arch.py"

    # Bootstrap target file with imports.
    ha.write_text(
        "from __future__ import annotations\n"
        "\n"
        "\n"
        "from sglang.srt.configs import (\n"
        "    BailingHybridConfig,\n"
        "    FalconH1Config,\n"
        "    GraniteMoeHybridConfig,\n"
        "    JetNemotronConfig,\n"
        "    JetVLMConfig,\n"
        "    KimiLinearConfig,\n"
        "    Lfm2Config,\n"
        "    Lfm2MoeConfig,\n"
        "    Lfm2VlConfig,\n"
        "    NemotronH_Nano_VL_V2_Config,\n"
        "    NemotronHConfig,\n"
        "    Qwen3_5Config,\n"
        "    Qwen3_5MoeConfig,\n"
        "    Qwen3NextConfig,\n"
        ")\n"
        "from sglang.srt.configs.linear_attn_model_registry import get_linear_attn_config\n"
        "from sglang.srt.configs.model_config import ModelConfig\n"
    )

    mc_subs = {"self.model_config": "model_config"}
    mc_idw_subs = {**mc_subs, "self.is_draft_worker": "is_draft_worker"}

    # Cut each property; replace with 1-line delegate; build free function.
    properties = [
        ("qwen3_next_config", "get_qwen3_next_config",
         "def qwen3_next_config(self):\n",
         "def get_qwen3_next_config(model_config: ModelConfig):\n",
         mc_subs,
         "    @property\n    def qwen3_next_config(self):\n        return get_qwen3_next_config(self.model_config)\n\n"),
        ("hybrid_lightning_config", "get_hybrid_lightning_config",
         "def hybrid_lightning_config(self):\n",
         "def get_hybrid_lightning_config(model_config: ModelConfig):\n",
         mc_subs,
         "    @property\n    def hybrid_lightning_config(self):\n        return get_hybrid_lightning_config(self.model_config)\n\n"),
        ("hybrid_gdn_config", "get_hybrid_gdn_config",
         "def hybrid_gdn_config(self):\n",
         "def get_hybrid_gdn_config(model_config: ModelConfig):\n",
         mc_subs,
         "    @property\n    def hybrid_gdn_config(self):\n        return get_hybrid_gdn_config(self.model_config)\n\n"),
        ("mamba2_config", "get_mamba2_config",
         "def mamba2_config(self):\n",
         "def get_mamba2_config(model_config: ModelConfig, *, is_draft_worker: bool):\n",
         mc_idw_subs,
         "    @property\n    def mamba2_config(self):\n        return get_mamba2_config(self.model_config, is_draft_worker=self.is_draft_worker)\n\n"),
        ("kimi_linear_config", "get_kimi_linear_config",
         "def kimi_linear_config(self):\n",
         "def get_kimi_linear_config(model_config: ModelConfig):\n",
         mc_subs,
         "    @property\n    def kimi_linear_config(self):\n        return get_kimi_linear_config(self.model_config)\n\n"),
    ]
    for name, _, old_sig, new_sig, subs, delegate in properties:
        method_text = _swap_method(mr, method_name=name, delegate=delegate)
        append_to_file(ha, _to_free_func(method_text, old_sig=old_sig, new_sig=new_sig, subs=subs))

    # `_get_linear_attn_registry_result` is a method (not @property). The free
    # function drops the per-instance cache (cache field deletion lands in /35);
    # body is hand-written to match the documented exception.
    _swap_method(
        mr,
        method_name="_get_linear_attn_registry_result",
        delegate=(
            "    def _get_linear_attn_registry_result(self):\n"
            "        return _get_linear_attn_registry_result(self.model_config)\n\n"
        ),
    )
    append_to_file(
        ha,
        "def _get_linear_attn_registry_result(model_config: ModelConfig):\n"
        "    return get_linear_attn_config(model_config.hf_config)\n",
    )

    # Remaining two properties depend on the helper.
    method_text = _swap_method(
        mr,
        method_name="linear_attn_model_spec",
        delegate=(
            "    @property\n"
            "    def linear_attn_model_spec(self):\n"
            "        return get_linear_attn_model_spec(self.model_config)\n\n"
        ),
    )
    fn = _to_free_func(
        method_text,
        old_sig="def linear_attn_model_spec(self):\n",
        new_sig="def get_linear_attn_model_spec(model_config: ModelConfig):\n",
        subs={"self._get_linear_attn_registry_result()": "_get_linear_attn_registry_result(model_config)"},
    )
    append_to_file(ha, fn)

    method_text = _swap_method(
        mr,
        method_name="mambaish_config",
        delegate=(
            "    @property\n"
            "    def mambaish_config(self):\n"
            "        return get_mambaish_config(self.model_config, is_draft_worker=self.is_draft_worker)\n"
        ),
    )
    fn = _to_free_func(
        method_text,
        old_sig="def mambaish_config(self):\n",
        new_sig="def get_mambaish_config(model_config: ModelConfig, *, is_draft_worker: bool):\n",
        subs={
            "self.mamba2_config": "get_mamba2_config(model_config, is_draft_worker=is_draft_worker)",
            "self.hybrid_gdn_config": "get_hybrid_gdn_config(model_config)",
            "self.kimi_linear_config": "get_kimi_linear_config(model_config)",
            "self.hybrid_lightning_config": "get_hybrid_lightning_config(model_config)",
            "self._get_linear_attn_registry_result()": "_get_linear_attn_registry_result(model_config)",
        },
    )
    append_to_file(ha, fn)

    # ---- Update model_runner.py imports. ----
    text = mr.read_text()

    # Drop the `from sglang.srt.configs import (...)` block (now only used in
    # hybrid_arch.py).
    old_configs_block = (
        "from sglang.srt.configs import (\n"
        "    BailingHybridConfig,\n"
        "    FalconH1Config,\n"
        "    GraniteMoeHybridConfig,\n"
        "    JetNemotronConfig,\n"
        "    JetVLMConfig,\n"
        "    KimiLinearConfig,\n"
        "    Lfm2Config,\n"
        "    Lfm2MoeConfig,\n"
        "    Lfm2VlConfig,\n"
        "    NemotronH_Nano_VL_V2_Config,\n"
        "    NemotronHConfig,\n"
        "    Qwen3_5Config,\n"
        "    Qwen3_5MoeConfig,\n"
        "    Qwen3NextConfig,\n"
        ")\n"
    )
    assert old_configs_block in text, "configs import block not found"
    text = text.replace(old_configs_block, "")

    # Replace the `linear_attn_model_registry` import with the new hybrid_arch
    # import block.
    old_import = (
        "from sglang.srt.configs.linear_attn_model_registry import get_linear_attn_config\n"
    )
    new_import = (
        "from sglang.srt.configs.hybrid_arch import (\n"
        "    _get_linear_attn_registry_result,\n"
        "    get_hybrid_gdn_config,\n"
        "    get_hybrid_lightning_config,\n"
        "    get_kimi_linear_config,\n"
        "    get_linear_attn_model_spec,\n"
        "    get_mamba2_config,\n"
        "    get_mambaish_config,\n"
        "    get_qwen3_next_config,\n"
        ")\n"
    )
    assert old_import in text, "linear_attn_model_registry import not found"
    text = text.replace(old_import, new_import)

    mr.write_text(text)

    git_add_and_commit(
        "Extract 7 hybrid-arch properties to free functions in configs.hybrid_arch",
        cwd=str(dir_root),
    )


if __name__ == "__main__":
    verify_mechanical_refactor(
        base_commit=BASE_COMMIT,
        target_commit=TARGET_COMMIT,
        transform=transform,
    )
