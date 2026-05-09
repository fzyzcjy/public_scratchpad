#!/usr/bin/env python3
"""Cut 7 hybrid-arch ModelRunner properties to free functions in new file
`configs/hybrid_arch.py`.

R4 concession: each free function takes `model_runner_ref` (kwarg) — bodies
stay byte-identical modulo `self` -> `model_runner_ref`. The helper
`_get_linear_attn_registry_result` STAYS on ModelRunner (it writes back to
`self._linear_attn_registry_cache`); the two properties that call it
(`linear_attn_model_spec`, `mambaish_config`) reach it through
`model_runner_ref._get_linear_attn_registry_result()`.

ModelRunner keeps a 1-line property delegate per name (no Ch1 rename); the
delegate calls the aliased free function. Delegate deletion + consumer
ripple happens in /35.
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
)


def _extract_property_to_function(
    mr_path: Path,
    *,
    name: str,
    sibling_property_names: list[str],
) -> str:
    """Cut a @property from ModelRunner; replace with a 1-line delegate that
    forwards `self` to the free function via `model_runner_ref`. Return the
    free-function source. Body is R4 byte-identical modulo `self` ->
    `model_runner_ref`, except references to `self.<sibling>` (other extracted
    properties whose delegates will be deleted in /35) are rewired to call the
    free function directly."""
    text = mr_path.read_text()
    start, end = find_method_lines(text, class_name="ModelRunner", method_name=name)
    src = text.splitlines(keepends=True)
    method_text = "".join(src[start:end])
    delegate = (
        "    @property\n"
        f"    def {name}(self):\n"
        f"        return _free_{name}(model_runner_ref=self)\n"
        "\n"
    )
    mr_path.write_text("".join(src[:start] + [delegate] + src[end:]))

    fn = dedent_method_to_function(method_text)
    fn = fn.replace("@property\n", "", 1)
    fn = fn.replace(
        f"def {name}(self):\n",
        f"def {name}(*, model_runner_ref):\n",
    )
    # Rewire sibling property accesses BEFORE the global `self.` swap, so we
    # produce direct free-function calls instead of relying on (about-to-be-
    # deleted) delegates on ModelRunner.
    for sibling in sibling_property_names:
        fn = fn.replace(
            f"self.{sibling}",
            f"{sibling}(model_runner_ref=model_runner_ref)",
        )
    fn = fn.replace("self.", "model_runner_ref.")
    return fn


def transform(wt: Path) -> None:
    sys.path.insert(0, str(wt / ".claude/skills/mechanical-refactor-verify"))
    from mechanical_refactor_verify_utils import git_add_and_commit

    mr = wt / "python/sglang/srt/model_executor/model_runner.py"
    ha = wt / "python/sglang/srt/configs/hybrid_arch.py"

    ha.write_text(_HEADER)

    property_names = [
        "qwen3_next_config",
        "hybrid_lightning_config",
        "hybrid_gdn_config",
        "mamba2_config",
        "kimi_linear_config",
        "linear_attn_model_spec",
        "mambaish_config",
    ]
    for name in property_names:
        fn = _extract_property_to_function(
            mr,
            name=name,
            sibling_property_names=property_names,
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

    # Insert the new aliased hybrid_arch imports right where the configs
    # block used to live; placement uses the existing `linear_attn_model_registry`
    # import line as anchor.
    new_import = (
        "from sglang.srt.configs.hybrid_arch import (\n"
        "    hybrid_gdn_config as _free_hybrid_gdn_config,\n"
        "    hybrid_lightning_config as _free_hybrid_lightning_config,\n"
        "    kimi_linear_config as _free_kimi_linear_config,\n"
        "    linear_attn_model_spec as _free_linear_attn_model_spec,\n"
        "    mamba2_config as _free_mamba2_config,\n"
        "    mambaish_config as _free_mambaish_config,\n"
        "    qwen3_next_config as _free_qwen3_next_config,\n"
        ")\n"
    )
    anchor = (
        "from sglang.srt.configs.linear_attn_model_registry import get_linear_attn_config\n"
    )
    assert anchor in text, "linear_attn_model_registry import not found"
    text = text.replace(anchor, anchor + new_import)

    mr.write_text(text)

    git_add_and_commit(
        "Extract 7 hybrid-arch properties to free functions in configs.hybrid_arch",
        cwd=str(wt),
    )


if __name__ == "__main__":
    run_pr(transform=transform, base=BASE, target=TARGET)
