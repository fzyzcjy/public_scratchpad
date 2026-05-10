#!/usr/bin/env python3
"""Cut 7 hybrid-arch ModelRunner properties to free functions in new file
`configs/hybrid_arch.py`. Each function takes `model_config: ModelConfig` (and
`is_draft_worker: bool` kwarg for `mamba2_config` / `mambaish_config`) — per
component md 3.2 spec.

ModelRunner keeps a 1-line property delegate per name (no Ch1 rename); the
delegate calls `hybrid_arch.<name>(self.model_config[, is_draft_worker=...])`.
Delegate deletion + consumer ripple happens in /35.

Also deletes ModelRunner.`_get_linear_attn_registry_result` helper and the
`_linear_attn_registry_cache` field + `_UNSET` sentinel (per component md
item 4: "8 个 property 删除（含 `_get_linear_attn_registry_result` 私有
helper）；`_linear_attn_registry_cache` 字段删除"). The cache logic is
inlined into the relevant hybrid_arch functions as a direct registry call
(no caching, per md note "零 caching").

Usage:
    uv run --python 3.12 extract-hybrid-arch-props.py run
    uv run --python 3.12 extract-hybrid-arch-props.py verify
"""

# /// script
# requires-python = ">=3.10"
# dependencies = ["typer"]
# ///

import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from _helpers import (
    find_method_lines,
    insert_after,
    replace_call_site,
)
from _runner import run_pr

ID = "extract-hybrid-arch-props"
SUBJECT = "Extract 7 hybrid-arch properties to free functions in configs.hybrid_arch"
BODY = ""
AREA = "mech_model_runner"
BASE = "tom_refactor_202605a/primary/mech_model_runner/extract-piecewise-cuda-graphs"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


_HEADER = '''from __future__ import annotations

from typing import Any, Optional, Union

from sglang.srt.configs import (
    BailingHybridConfig,
    FalconH1Config,
    GraniteMoeHybridConfig,
    JetNemotronConfig,
    JetVLMConfig,
    KimiLinearConfig,
    Lfm2Config,
    Lfm2MoeConfig,
    Lfm2VlConfig,
    NemotronH_Nano_VL_V2_Config,
    NemotronHConfig,
    Qwen3_5Config,
    Qwen3_5MoeConfig,
    Qwen3NextConfig,
)
from sglang.srt.configs.linear_attn_model_registry import get_linear_attn_config
from sglang.srt.configs.model_config import ModelConfig


def qwen3_next_config(model_config: ModelConfig) -> Optional[Qwen3NextConfig]:
    config = model_config.hf_config
    if isinstance(config, Qwen3NextConfig):
        return config
    return None


def hybrid_lightning_config(model_config: ModelConfig) -> Optional[BailingHybridConfig]:
    config = model_config.hf_config
    if isinstance(config, BailingHybridConfig):
        return config
    return None


def hybrid_gdn_config(
    model_config: ModelConfig,
) -> Optional[
    Union[
        Qwen3NextConfig,
        Qwen3_5Config,
        Qwen3_5MoeConfig,
        JetNemotronConfig,
        JetVLMConfig,
    ]
]:
    config = model_config.hf_config.get_text_config()
    if isinstance(
        config,
        Qwen3NextConfig
        | Qwen3_5Config
        | Qwen3_5MoeConfig
        | JetNemotronConfig
        | JetVLMConfig,
    ):
        return config
    return None


def mamba2_config(
    model_config: ModelConfig,
    *,
    is_draft_worker: bool,
) -> Optional[
    Union[
        FalconH1Config,
        NemotronHConfig,
        Lfm2Config,
        Lfm2MoeConfig,
        Lfm2VlConfig,
        NemotronH_Nano_VL_V2_Config,
        GraniteMoeHybridConfig,
    ]
]:
    config = model_config.hf_config
    if isinstance(config, NemotronHConfig) and is_draft_worker:
        # NemotronH MTP draft models have no Mamba layers (pattern like "*E")
        # so they shouldn't use HybridLinearAttnBackend
        pattern = getattr(config, "mtp_hybrid_override_pattern", None)
        if pattern is not None and "M" not in pattern:
            return None
    if isinstance(
        config,
        FalconH1Config | NemotronHConfig | Lfm2Config | Lfm2MoeConfig | Lfm2VlConfig,
    ):
        return config
    if isinstance(config, NemotronH_Nano_VL_V2_Config):
        return config.llm_config

    if isinstance(config, GraniteMoeHybridConfig):
        has_mamba = any(
            layer_type == "mamba" for layer_type in getattr(config, "layer_types", [])
        )
        if not has_mamba:
            return None
        else:
            return config

    return None


def kimi_linear_config(model_config: ModelConfig) -> Optional[KimiLinearConfig]:
    config = model_config.hf_config
    if isinstance(config, KimiLinearConfig):
        return config
    return None


def linear_attn_model_spec(model_config: ModelConfig) -> Optional[Any]:
    result = get_linear_attn_config(model_config.hf_config)
    return result[0] if result else None


def mambaish_config(
    model_config: ModelConfig,
    *,
    is_draft_worker: bool,
) -> Optional[Any]:
    existing = (
        mamba2_config(model_config, is_draft_worker=is_draft_worker)
        or hybrid_gdn_config(model_config)
        or kimi_linear_config(model_config)
        or hybrid_lightning_config(model_config)
    )
    if existing:
        return existing
    result = get_linear_attn_config(model_config.hf_config)
    return result[1] if result else None
'''

# 7 properties; the 2 needing is_draft_worker call with that kwarg.
_PROPS_NO_KWARG = [
    "qwen3_next_config",
    "hybrid_lightning_config",
    "hybrid_gdn_config",
    "kimi_linear_config",
    "linear_attn_model_spec",
]
_PROPS_WITH_DRAFT = [
    "mamba2_config",
    "mambaish_config",
]


def _delegate(name: str, with_draft: bool) -> str:
    if with_draft:
        body = (
            f"        return hybrid_arch.{name}(\n"
            "            self.model_config, is_draft_worker=self.is_draft_worker\n"
            "        )\n"
        )
    else:
        body = f"        return hybrid_arch.{name}(self.model_config)\n"
    return f"    @property\n    def {name}(self):\n{body}\n"


def transform(wt: Path) -> None:
    mr = wt / "python/sglang/srt/model_executor/model_runner.py"
    ha = wt / "python/sglang/srt/configs/hybrid_arch.py"

    ha.write_text(_HEADER)

    text = mr.read_text()

    # Replace each original @property with a 1-line delegate that forwards to
    # the new free function in hybrid_arch.
    for name in _PROPS_NO_KWARG + _PROPS_WITH_DRAFT:
        s, e = find_method_lines(text, class_name="ModelRunner", method_name=name)
        src = text.splitlines(keepends=True)
        delegate = _delegate(name, with_draft=(name in _PROPS_WITH_DRAFT))
        text = "".join(src[:s] + [delegate] + src[e:])

    # Delete _get_linear_attn_registry_result helper (no longer used; cache
    # logic now inline in hybrid_arch.linear_attn_model_spec / mambaish_config).
    s, e = find_method_lines(
        text, class_name="ModelRunner", method_name="_get_linear_attn_registry_result"
    )
    src = text.splitlines(keepends=True)
    text = "".join(src[:s] + src[e:])

    # Delete the `_linear_attn_registry_cache` field init in ModelRunner.__init__
    # (and its 2-line preceding comment).
    text = replace_call_site(
        text,
        old=(
            "        # Linear-attn registry result is computed lazily; _UNSET distinguishes\n"
            '        # "not yet computed" from "computed and got None".\n'
            "        self._linear_attn_registry_cache: Any = _UNSET\n"
            "\n"
        ),
        new="",
    )

    # Delete the module-level _UNSET sentinel + its comment.
    text = replace_call_site(
        text,
        old=(
            "# Sentinel distinct from None so the linear-attn registry cache can store\n"
            "# None as a real result (see _get_linear_attn_registry_result).\n"
            "# Rust analogue: OnceCell<Option<...>>.\n"
            "_UNSET: Any = object()\n"
            "\n"
            "\n"
        ),
        new="",
    )

    # ---- Update model_runner.py imports. ----
    # The 14 hybrid/linear-attn config classes are no longer referenced on
    # ModelRunner (isinstance checks moved into hybrid_arch.py). Drop the
    # grouped configs import block.
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

    # `get_linear_attn_config` is no longer called from ModelRunner.
    text = replace_call_site(
        text,
        old="from sglang.srt.configs.linear_attn_model_registry import get_linear_attn_config\n",
        new="",
    )

    # Insert the new module-qualified hybrid_arch import.
    text = insert_after(
        text,
        anchor="from sglang.srt.configs.device_config import DeviceConfig\n",
        addition="from sglang.srt.configs import hybrid_arch\n",
    )

    mr.write_text(text)

if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        area_branch=AREA_BRANCH,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
