#!/usr/bin/env python3
"""Reproducible transform: extract 7 hybrid-arch ModelRunner properties (+ 1
internal helper) to free functions in `sglang.srt.configs.hybrid_arch`.

Each free function body is byte-identical to the original property body, with
`self.model_config` rewritten to the `model_config` kwarg. The two configs
that depend on `is_draft_worker` (`mamba2_config`, `mambaish_config`) take it
as a kwarg.

Functions get a `get_` prefix so they don't shadow the ModelRunner properties
they delegate from (mechanical namespacing rename, not a semantic rename).
The ModelRunner properties remain as 1-line `return get_X(...)` delegates so
no callers are touched in this PR. The internal helper
`_get_linear_attn_registry_result` drops the per-ModelRunner cache (cache field
is removed in PR /35); the call cost is negligible during init.
"""

import sys
from pathlib import Path

sys.path.append(".claude/skills/mechanical-refactor-verify")
from mechanical_refactor_verify_utils import (
    verify_mechanical_refactor,
    git_add_and_commit,
)

BASE_COMMIT = "tom_refactor/33"
TARGET_COMMIT = "tom_refactor/34"


def transform(dir_root: Path) -> None:
    ha = dir_root / "python/sglang/srt/configs/hybrid_arch.py"
    ha_content = (
        "from __future__ import annotations\n"
        "\n"
        "from typing import Any, Optional\n"
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
        "\n"
        "\n"
        "def get_qwen3_next_config(model_config: ModelConfig):\n"
        "    config = model_config.hf_config\n"
        "    if isinstance(config, Qwen3NextConfig):\n"
        "        return config\n"
        "    return None\n"
        "\n"
        "\n"
        "def get_hybrid_lightning_config(model_config: ModelConfig):\n"
        "    config = model_config.hf_config\n"
        "    if isinstance(config, BailingHybridConfig):\n"
        "        return config\n"
        "    return None\n"
        "\n"
        "\n"
        "def get_hybrid_gdn_config(model_config: ModelConfig):\n"
        "    config = model_config.hf_config.get_text_config()\n"
        "    if isinstance(\n"
        "        config,\n"
        "        Qwen3NextConfig\n"
        "        | Qwen3_5Config\n"
        "        | Qwen3_5MoeConfig\n"
        "        | JetNemotronConfig\n"
        "        | JetVLMConfig,\n"
        "    ):\n"
        "        return config\n"
        "    return None\n"
        "\n"
        "\n"
        "def get_mamba2_config(model_config: ModelConfig, *, is_draft_worker: bool):\n"
        "    config = model_config.hf_config\n"
        "    if isinstance(config, NemotronHConfig) and is_draft_worker:\n"
        "        # NemotronH MTP draft models have no Mamba layers (pattern like \"*E\")\n"
        "        # so they shouldn't use HybridLinearAttnBackend\n"
        '        pattern = getattr(config, "mtp_hybrid_override_pattern", None)\n'
        '        if pattern is not None and "M" not in pattern:\n'
        "            return None\n"
        "    if isinstance(\n"
        "        config,\n"
        "        FalconH1Config\n"
        "        | NemotronHConfig\n"
        "        | Lfm2Config\n"
        "        | Lfm2MoeConfig\n"
        "        | Lfm2VlConfig,\n"
        "    ):\n"
        "        return config\n"
        "    if isinstance(config, NemotronH_Nano_VL_V2_Config):\n"
        "        return config.llm_config\n"
        "\n"
        "    if isinstance(config, GraniteMoeHybridConfig):\n"
        "        has_mamba = any(\n"
        '            layer_type == "mamba"\n'
        '            for layer_type in getattr(config, "layer_types", [])\n'
        "        )\n"
        "        if not has_mamba:\n"
        "            return None\n"
        "        else:\n"
        "            return config\n"
        "\n"
        "    return None\n"
        "\n"
        "\n"
        "def get_kimi_linear_config(model_config: ModelConfig):\n"
        "    config = model_config.hf_config\n"
        "    if isinstance(config, KimiLinearConfig):\n"
        "        return config\n"
        "    return None\n"
        "\n"
        "\n"
        "def _get_linear_attn_registry_result(model_config: ModelConfig):\n"
        "    return get_linear_attn_config(model_config.hf_config)\n"
        "\n"
        "\n"
        "def get_linear_attn_model_spec(model_config: ModelConfig):\n"
        "    result = _get_linear_attn_registry_result(model_config)\n"
        "    return result[0] if result else None\n"
        "\n"
        "\n"
        "def get_mambaish_config(model_config: ModelConfig, *, is_draft_worker: bool):\n"
        "    existing = (\n"
        "        get_mamba2_config(model_config, is_draft_worker=is_draft_worker)\n"
        "        or get_hybrid_gdn_config(model_config)\n"
        "        or get_kimi_linear_config(model_config)\n"
        "        or get_hybrid_lightning_config(model_config)\n"
        "    )\n"
        "    if existing:\n"
        "        return existing\n"
        "    result = _get_linear_attn_registry_result(model_config)\n"
        "    return result[1] if result else None\n"
    )
    ha.write_text(ha_content)

    # ---- Update model_runner.py: replace property bodies with delegates. ----
    mr = dir_root / "python/sglang/srt/model_executor/model_runner.py"
    text = mr.read_text()

    # qwen3_next_config
    old = (
        "    @property\n"
        "    def qwen3_next_config(self):\n"
        "        config = self.model_config.hf_config\n"
        "        if isinstance(config, Qwen3NextConfig):\n"
        "            return config\n"
        "        return None\n"
    )
    new = (
        "    @property\n"
        "    def qwen3_next_config(self):\n"
        "        return get_qwen3_next_config(self.model_config)\n"
    )
    assert old in text, "qwen3_next_config property body not found"
    text = text.replace(old, new)

    # hybrid_lightning_config
    old = (
        "    @property\n"
        "    def hybrid_lightning_config(self):\n"
        "        config = self.model_config.hf_config\n"
        "        if isinstance(config, BailingHybridConfig):\n"
        "            return config\n"
        "        return None\n"
    )
    new = (
        "    @property\n"
        "    def hybrid_lightning_config(self):\n"
        "        return get_hybrid_lightning_config(self.model_config)\n"
    )
    assert old in text, "hybrid_lightning_config property body not found"
    text = text.replace(old, new)

    # hybrid_gdn_config
    old = (
        "    @property\n"
        "    def hybrid_gdn_config(self):\n"
        "        config = self.model_config.hf_config.get_text_config()\n"
        "        if isinstance(\n"
        "            config,\n"
        "            Qwen3NextConfig\n"
        "            | Qwen3_5Config\n"
        "            | Qwen3_5MoeConfig\n"
        "            | JetNemotronConfig\n"
        "            | JetVLMConfig,\n"
        "        ):\n"
        "            return config\n"
        "        return None\n"
    )
    new = (
        "    @property\n"
        "    def hybrid_gdn_config(self):\n"
        "        return get_hybrid_gdn_config(self.model_config)\n"
    )
    assert old in text, "hybrid_gdn_config property body not found"
    text = text.replace(old, new)

    # mamba2_config
    old = (
        "    @property\n"
        "    def mamba2_config(self):\n"
        "        config = self.model_config.hf_config\n"
        "        if isinstance(config, NemotronHConfig) and self.is_draft_worker:\n"
        "            # NemotronH MTP draft models have no Mamba layers (pattern like \"*E\")\n"
        "            # so they shouldn't use HybridLinearAttnBackend\n"
        '            pattern = getattr(config, "mtp_hybrid_override_pattern", None)\n'
        '            if pattern is not None and "M" not in pattern:\n'
        "                return None\n"
        "        if isinstance(\n"
        "            config,\n"
        "            FalconH1Config\n"
        "            | NemotronHConfig\n"
        "            | Lfm2Config\n"
        "            | Lfm2MoeConfig\n"
        "            | Lfm2VlConfig,\n"
        "        ):\n"
        "            return config\n"
        "        if isinstance(config, NemotronH_Nano_VL_V2_Config):\n"
        "            return config.llm_config\n"
        "\n"
        "        if isinstance(config, GraniteMoeHybridConfig):\n"
        "            has_mamba = any(\n"
        '                layer_type == "mamba"\n'
        '                for layer_type in getattr(config, "layer_types", [])\n'
        "            )\n"
        "            if not has_mamba:\n"
        "                return None\n"
        "            else:\n"
        "                return config\n"
        "\n"
        "        return None\n"
    )
    new = (
        "    @property\n"
        "    def mamba2_config(self):\n"
        "        return get_mamba2_config(self.model_config, is_draft_worker=self.is_draft_worker)\n"
    )
    assert old in text, "mamba2_config property body not found"
    text = text.replace(old, new)

    # kimi_linear_config
    old = (
        "    @property\n"
        "    def kimi_linear_config(self):\n"
        "        config = self.model_config.hf_config\n"
        "        if isinstance(config, KimiLinearConfig):\n"
        "            return config\n"
        "        return None\n"
    )
    new = (
        "    @property\n"
        "    def kimi_linear_config(self):\n"
        "        return get_kimi_linear_config(self.model_config)\n"
    )
    assert old in text, "kimi_linear_config property body not found"
    text = text.replace(old, new)

    # _get_linear_attn_registry_result (helper, not a @property)
    old = (
        "    def _get_linear_attn_registry_result(self):\n"
        "        if self._linear_attn_registry_cache is _UNSET:\n"
        "            self._linear_attn_registry_cache = get_linear_attn_config(\n"
        "                self.model_config.hf_config\n"
        "            )\n"
        "        return self._linear_attn_registry_cache\n"
    )
    new = (
        "    def _get_linear_attn_registry_result(self):\n"
        "        return _get_linear_attn_registry_result(self.model_config)\n"
    )
    assert old in text, "_get_linear_attn_registry_result method body not found"
    text = text.replace(old, new)

    # linear_attn_model_spec
    old = (
        "    @property\n"
        "    def linear_attn_model_spec(self):\n"
        "        result = self._get_linear_attn_registry_result()\n"
        "        return result[0] if result else None\n"
    )
    new = (
        "    @property\n"
        "    def linear_attn_model_spec(self):\n"
        "        return get_linear_attn_model_spec(self.model_config)\n"
    )
    assert old in text, "linear_attn_model_spec property body not found"
    text = text.replace(old, new)

    # mambaish_config
    old = (
        "    @property\n"
        "    def mambaish_config(self):\n"
        "        existing = (\n"
        "            self.mamba2_config\n"
        "            or self.hybrid_gdn_config\n"
        "            or self.kimi_linear_config\n"
        "            or self.hybrid_lightning_config\n"
        "        )\n"
        "        if existing:\n"
        "            return existing\n"
        "        result = self._get_linear_attn_registry_result()\n"
        "        return result[1] if result else None\n"
    )
    new = (
        "    @property\n"
        "    def mambaish_config(self):\n"
        "        return get_mambaish_config(self.model_config, is_draft_worker=self.is_draft_worker)\n"
    )
    assert old in text, "mambaish_config property body not found"
    text = text.replace(old, new)

    # Add the imports for the new free functions. Anchor on a stable nearby
    # import (sibling configs.* import) — at /33 the model_runner imports
    # `linear_attn_model_registry` and several config types.
    old_import = (
        "from sglang.srt.configs.linear_attn_model_registry import get_linear_attn_config\n"
    )
    new_import = (
        "from sglang.srt.configs.linear_attn_model_registry import get_linear_attn_config\n"
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
