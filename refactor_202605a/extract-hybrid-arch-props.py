#!/usr/bin/env python3
"""Cut 7 hybrid-arch ModelRunner properties to free functions in new file
`configs/hybrid_arch.py`. Each function takes `model_config: ModelConfig` (and
`is_draft_worker: bool` kwarg for `mamba2_config`) — per component md 3.2 spec.

`linear_attn_model_spec` / `mambaish_config` need the lazy registry cache,
so they take `model_runner: ModelRunner` directly (per the new "passing
ModelRunner is fine" directive that items 3-4 adopted). The
`_get_linear_attn_registry_result` private helper moves to
`hybrid_arch.py` as a free function — body is a mechanical copy of the
original method, ``self`` → ``model_runner``.

The ``_UNSET`` sentinel (introduced in the preflight
``cache-linear-attn-registry`` commit) also moves to ``hybrid_arch.py``.
The ``self._linear_attn_registry_cache: Any = _UNSET`` field init in
``ModelRunner.__init__`` is **preserved** — the cache still lives on the
ModelRunner instance; only the helper's home and the sentinel definition
moved.

ModelRunner keeps a 1-line property delegate per name (no Ch1 rename); the
delegate calls `hybrid_arch.<name>(self.model_config[, is_draft_worker=...])`
or `hybrid_arch.<name>(self)` for the two cache-using ones. Delegate
deletion + consumer ripple happens in /35.

Usage:
    uv run --python 3.12 extract-hybrid-arch-props.py run
    uv run --python 3.12 extract-hybrid-arch-props.py verify
"""

# /// script
# requires-python = ">=3.10"
# dependencies = ["typer"]
# ///

import re
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
    InternS2PreviewConfig,
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


# Sentinel distinct from None so the linear-attn registry cache can store
# None as a real result (see _get_linear_attn_registry_result).
# Rust analogue: OnceCell<Option<...>>.
_UNSET: Any = object()

# Module-global lazy cache for `get_linear_attn_config(hf_config)`. Process
# only ever holds one ModelRunner / one model config, so a single global
# slot mirrors the original per-instance ``self._linear_attn_registry_cache``
# semantics with one less hop.
_linear_attn_registry_cache: Any = _UNSET


def _get_linear_attn_registry_result(model_config: ModelConfig) -> Any:
    global _linear_attn_registry_cache
    if _linear_attn_registry_cache is _UNSET:
        _linear_attn_registry_cache = get_linear_attn_config(model_config.hf_config)
    return _linear_attn_registry_cache


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
        InternS2PreviewConfig,
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
        | InternS2PreviewConfig
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
    result = _get_linear_attn_registry_result(model_config)
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
    result = _get_linear_attn_registry_result(model_config)
    return result[1] if result else None
'''


# 7 properties. All take `self.model_config`; the 2 with an extra
# `is_draft_worker` kwarg (`mamba2_config`, `mambaish_config`) call it
# explicitly. The cache for `linear_attn_model_spec` / `mambaish_config`
# now lives in a module-global var inside `hybrid_arch.py` — no per-instance
# state on ModelRunner.
_PROPS_MODEL_CONFIG = [
    "qwen3_next_config",
    "hybrid_lightning_config",
    "hybrid_gdn_config",
    "kimi_linear_config",
    "linear_attn_model_spec",
]
_PROPS_MODEL_CONFIG_WITH_DRAFT = [
    "mamba2_config",
    "mambaish_config",
]


def _delegate(name: str, *, kind: str) -> str:
    if kind == "model_config":
        body = f"        return hybrid_arch.{name}(self.model_config)\n"
    elif kind == "model_config_with_draft":
        body = (
            f"        return hybrid_arch.{name}(\n"
            "            self.model_config, is_draft_worker=self.is_draft_worker\n"
            "        )\n"
        )
    else:
        raise ValueError(f"unknown delegate kind: {kind}")
    return f"    @property\n    def {name}(self):\n{body}\n"


def transform(wt: Path) -> None:
    mr = wt / "python/sglang/srt/model_executor/model_runner.py"
    ha = wt / "python/sglang/srt/configs/hybrid_arch.py"

    ha.write_text(_HEADER)

    text = mr.read_text()

    # Replace each original @property with a 1-line delegate that forwards to
    # the new free function in hybrid_arch.
    for name in _PROPS_MODEL_CONFIG:
        s, e = find_method_lines(text, class_name="ModelRunner", method_name=name)
        src = text.splitlines(keepends=True)
        text = "".join(src[:s] + [_delegate(name, kind="model_config")] + src[e:])
    for name in _PROPS_MODEL_CONFIG_WITH_DRAFT:
        s, e = find_method_lines(text, class_name="ModelRunner", method_name=name)
        src = text.splitlines(keepends=True)
        text = "".join(
            src[:s] + [_delegate(name, kind="model_config_with_draft")] + src[e:]
        )

    # Delete `_get_linear_attn_registry_result` helper from ModelRunner — it
    # moved to hybrid_arch.py.
    s, e = find_method_lines(
        text, class_name="ModelRunner", method_name="_get_linear_attn_registry_result"
    )
    src = text.splitlines(keepends=True)
    text = "".join(src[:s] + src[e:])

    # Delete the module-level _UNSET sentinel + its 3-line comment — moved to
    # hybrid_arch.py. The cache itself is now a module-global in
    # hybrid_arch.py (not per-instance), so the
    # ``self._linear_attn_registry_cache: Any = _UNSET`` field init in
    # ModelRunner.__init__ goes away too.
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

    # ---- Update model_runner.py imports. ----
    # The 14 hybrid/linear-attn config classes are no longer referenced on
    # ModelRunner (isinstance checks moved into hybrid_arch.py). Drop the
    # grouped configs import block.
    old_configs_block = (
        "from sglang.srt.configs import (\n"
        "    BailingHybridConfig,\n"
        "    FalconH1Config,\n"
        "    GraniteMoeHybridConfig,\n"
        "    InternS2PreviewConfig,\n"
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

    # Absorbed from ha-mech-drop-is-draft-worker: the kwarg is reachable via
    # ``model_config.is_draft_model`` (already a ModelConfig field), so the
    # kwarg on ``mamba2_config`` / ``mambaish_config`` was redundant.
    _drop_is_draft_worker(wt)


def _drop_call_kwarg(text: str) -> str:
    """Inside every ``mamba2_config(...)`` / ``mambaish_config(...)`` call
    body, drop the ``, is_draft_worker=<expr>`` substring (handles both
    inline and black-wrapped multi-line forms)."""
    def repl(m: "re.Match") -> str:
        return re.sub(
            r",\s*is_draft_worker=[a-zA-Z0-9_.\[\]]+\s*",
            "",
            m.group(0),
        )

    return re.sub(
        r"\bmam(?:ba2|baish)_config\([^()]*\)",
        repl,
        text,
        flags=re.DOTALL,
    )


_FILES_DROP_KWARG = [
    "python/sglang/srt/configs/hybrid_arch.py",
    "python/sglang/srt/layers/attention/attention_registry.py",
    "python/sglang/srt/layers/attention/hybrid_linear_attn_backend.py",
    "python/sglang/srt/managers/scheduler.py",
    "python/sglang/srt/model_executor/model_runner.py",
    "python/sglang/srt/model_executor/model_runner_components/pool_configurator.py",
    "python/sglang/srt/model_executor/model_runner_kv_cache_mixin.py",
    "python/sglang/srt/speculative/eagle_worker.py",
    "python/sglang/srt/speculative/eagle_worker_v2.py",
    "python/sglang/srt/speculative/frozen_kv_mtp_worker.py",
]


def _drop_is_draft_worker(wt: Path) -> None:
    # 1) hybrid_arch.py: drop signature kwarg + replace body usage.
    ha = wt / "python/sglang/srt/configs/hybrid_arch.py"
    text = ha.read_text()
    text = text.replace("    *,\n    is_draft_worker: bool,\n", "")
    text = text.replace(
        "if isinstance(config, NemotronHConfig) and is_draft_worker:",
        "if isinstance(config, NemotronHConfig) and model_config.is_draft_model:",
    )
    text = _drop_call_kwarg(text)
    ha.write_text(text)

    # 2) Drop kwarg at every other caller. Skip files that may not exist on
    # the current chain (e.g. the mixin file deleted by
    # ``kvc-drop-mixin-inheritance``).
    for relpath in _FILES_DROP_KWARG:
        if relpath == "python/sglang/srt/configs/hybrid_arch.py":
            continue
        path = wt / relpath
        if not path.exists():
            continue
        path.write_text(_drop_call_kwarg(path.read_text()))


if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        area_branch=AREA_BRANCH,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
