#!/usr/bin/env python3
"""Cut 7 hybrid-arch ModelRunner properties + 1 helper to free functions in a
new `configs/hybrid_arch.py`.

Free functions keep the original property/method names (no Ch1 rename). Each
free function takes `model_config` (and `is_draft_worker` where needed) as
kwargs in place of `self`. ModelRunner keeps a 1-line property delegate to
avoid a Ch1 cross-file rename ripple — the delegate calls the free function
via an aliased import (`as _free_X`). Delegate deletion happens in /35.
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
    append_to_file,
    cut_lines,
    dedent_method_to_function,
    find_method_lines,
)
from _runner import run_pr

BASE = "tom_refactor/33"
TARGET = "tom_refactor/34"


_HEADER = (
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
)


def _extract_property_to_function(
    mr_path: Path,
    *,
    method_name: str,
    new_signature: str,
    self_subs: dict[str, str],
    delegate_body: str,
    is_property: bool = True,
) -> str:
    """Cut a method from ModelRunner; replace with a 1-line delegate; return the
    free-function source built from the original method body."""
    text = mr_path.read_text()
    start, end = find_method_lines(text, class_name="ModelRunner", method_name=method_name)
    src = text.splitlines(keepends=True)
    method_text = "".join(src[start:end])
    delegate_lines = (
        ("    @property\n" if is_property else "")
        + f"    def {method_name}(self):\n"
        + f"        {delegate_body}\n"
        + "\n"
    )
    mr_path.write_text("".join(src[:start] + [delegate_lines] + src[end:]))

    func_text = dedent_method_to_function(method_text)
    func_text = func_text.replace("@property\n", "", 1)
    # Replace the original `def NAME(self):\n` with the new signature.
    old_sig = f"def {method_name}(self):\n"
    func_text = func_text.replace(old_sig, new_signature)
    for old, new in self_subs.items():
        func_text = func_text.replace(old, new)
    return func_text


def transform(wt: Path) -> None:
    sys.path.insert(0, str(wt / ".claude/skills/mechanical-refactor-verify"))
    from mechanical_refactor_verify_utils import git_add_and_commit

    mr = wt / "python/sglang/srt/model_executor/model_runner.py"
    ha = wt / "python/sglang/srt/configs/hybrid_arch.py"

    ha.write_text(_HEADER)

    mc = {"self.model_config": "model_config"}
    mc_idw = {**mc, "self.is_draft_worker": "is_draft_worker"}

    simple_properties = [
        ("qwen3_next_config", mc),
        ("hybrid_lightning_config", mc),
        ("hybrid_gdn_config", mc),
        ("kimi_linear_config", mc),
    ]
    for name, subs in simple_properties:
        fn = _extract_property_to_function(
            mr,
            method_name=name,
            new_signature=f"def {name}(model_config):\n",
            self_subs=subs,
            delegate_body=f"return _free_{name}(self.model_config)",
        )
        append_to_file(ha, fn)

    fn = _extract_property_to_function(
        mr,
        method_name="mamba2_config",
        new_signature="def mamba2_config(model_config, *, is_draft_worker):\n",
        self_subs=mc_idw,
        delegate_body="return _free_mamba2_config(self.model_config, is_draft_worker=self.is_draft_worker)",
    )
    append_to_file(ha, fn)

    fn = _extract_property_to_function(
        mr,
        method_name="_get_linear_attn_registry_result",
        new_signature="def _get_linear_attn_registry_result(model_config):\n",
        self_subs=mc,
        delegate_body="return _free__get_linear_attn_registry_result(self.model_config)",
        is_property=False,
    )
    append_to_file(ha, fn)

    fn = _extract_property_to_function(
        mr,
        method_name="linear_attn_model_spec",
        new_signature="def linear_attn_model_spec(model_config):\n",
        self_subs={
            **mc,
            "self._get_linear_attn_registry_result()": "_get_linear_attn_registry_result(model_config)",
        },
        delegate_body="return _free_linear_attn_model_spec(self.model_config)",
    )
    append_to_file(ha, fn)

    fn = _extract_property_to_function(
        mr,
        method_name="mambaish_config",
        new_signature="def mambaish_config(model_config, *, is_draft_worker):\n",
        self_subs={
            **mc_idw,
            "self.mamba2_config": "mamba2_config(model_config, is_draft_worker=is_draft_worker)",
            "self.hybrid_gdn_config": "hybrid_gdn_config(model_config)",
            "self.kimi_linear_config": "kimi_linear_config(model_config)",
            "self.hybrid_lightning_config": "hybrid_lightning_config(model_config)",
            "self._get_linear_attn_registry_result()": "_get_linear_attn_registry_result(model_config)",
        },
        delegate_body="return _free_mambaish_config(self.model_config, is_draft_worker=self.is_draft_worker)",
    )
    append_to_file(ha, fn)

    # ---- Update model_runner.py imports. ----
    text = mr.read_text()

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

    old_import = (
        "from sglang.srt.configs.linear_attn_model_registry import get_linear_attn_config\n"
    )
    new_import = (
        "from sglang.srt.configs.hybrid_arch import (\n"
        "    _get_linear_attn_registry_result as _free__get_linear_attn_registry_result,\n"
        "    hybrid_gdn_config as _free_hybrid_gdn_config,\n"
        "    hybrid_lightning_config as _free_hybrid_lightning_config,\n"
        "    kimi_linear_config as _free_kimi_linear_config,\n"
        "    linear_attn_model_spec as _free_linear_attn_model_spec,\n"
        "    mamba2_config as _free_mamba2_config,\n"
        "    mambaish_config as _free_mambaish_config,\n"
        "    qwen3_next_config as _free_qwen3_next_config,\n"
        ")\n"
    )
    assert old_import in text, "linear_attn_model_registry import not found"
    text = text.replace(old_import, new_import)

    mr.write_text(text)

    git_add_and_commit(
        "Extract 7 hybrid-arch properties to free functions in configs.hybrid_arch",
        cwd=str(wt),
    )


if __name__ == "__main__":
    run_pr(transform=transform, base=BASE, target=TARGET)
