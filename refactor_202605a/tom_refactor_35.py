#!/usr/bin/env python3
"""Delete the 7 hybrid-arch property delegates left behind by /34 on
ModelRunner; ripple all consumers to call the free functions in
`configs.hybrid_arch` directly.

Per Ch1 rule "**不留 1 行 delegate**", drop the delegates as soon as consumers
are updated to call the free function. The `_get_linear_attn_registry_result`
helper (and the `_UNSET` sentinel + `_linear_attn_registry_cache` field) stay
on ModelRunner — that helper writes back to per-instance cache state, so it
isn't a property delegate.
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
    cut_lines,
    find_method_lines,
)
from _runner import run_pr

BASE = "tom_refactor/34"
TARGET = "tom_refactor/35"

def _import_block(names: list[str]) -> str:
    names = sorted(set(names))
    if len(names) == 1:
        return f"from sglang.srt.configs.hybrid_arch import {names[0]}\n"
    body = "".join(f"    {n},\n" for n in names)
    return f"from sglang.srt.configs.hybrid_arch import (\n{body})\n"


def _rewrite_accesses(text: str, *, accessor: str, function_names: list[str]) -> str:
    """Each free function takes a single `model_runner_ref` kwarg (R4 unified
    approach in /34); rewrite `<accessor>.<name>` -> `<name>(model_runner_ref=<accessor>)`."""
    for name in function_names:
        text = text.replace(
            f"{accessor}.{name}",
            f"{name}(model_runner_ref={accessor})",
        )
    return text


def _patch_file(
    path: Path,
    *,
    accessor: str,
    function_names: list[str],
    import_anchor: str,
) -> None:
    text = path.read_text()
    text = _rewrite_accesses(text, accessor=accessor, function_names=function_names)
    text = text.replace(import_anchor, _import_block(function_names) + import_anchor)
    path.write_text(text)


def transform(wt: Path) -> None:
    sys.path.insert(0, str(wt / ".claude/skills/mechanical-refactor-verify"))
    from mechanical_refactor_verify_utils import git_add_and_commit

    mr = wt / "python/sglang/srt/model_executor/model_runner.py"

    # ---- Delete each delegate method on ModelRunner. ----
    delegate_methods = [
        "qwen3_next_config",
        "hybrid_lightning_config",
        "hybrid_gdn_config",
        "mamba2_config",
        "kimi_linear_config",
        "linear_attn_model_spec",
        "mambaish_config",
    ]
    for name in delegate_methods:
        s, e = find_method_lines(mr.read_text(), class_name="ModelRunner", method_name=name)
        cut_lines(mr, s, e)

    # ---- Drop the alias-import block introduced by /34. ----
    text = mr.read_text()
    # Pre-commit (isort/ruff) splits the 7-symbol grouped import into a mix of
    # single-line `import X as Y` and 1-symbol `(\n    X as Y,\n)` blocks based
    # on line-length. Strip both forms for each of the 7 symbols.
    for name in (
        "hybrid_gdn_config",
        "hybrid_lightning_config",
        "kimi_linear_config",
        "linear_attn_model_spec",
        "mamba2_config",
        "mambaish_config",
        "qwen3_next_config",
    ):
        single_line = f"from sglang.srt.configs.hybrid_arch import {name} as _free_{name}\n"
        block = (
            "from sglang.srt.configs.hybrid_arch import (\n"
            f"    {name} as _free_{name},\n"
            ")\n"
        )
        if single_line in text:
            text = text.replace(single_line, "")
        elif block in text:
            text = text.replace(block, "")
        else:
            raise AssertionError(f"alias import for {name} not found in expected forms")
    mr.write_text(text)

    # ---- Ripple consumers ----
    spec_anchor = "from sglang.srt.speculative.spec_info import SpeculativeAlgorithm\n"
    attn_anchor = "from sglang.srt.layers.attention.base_attn_backend import AttentionBackend\n"

    _patch_file(
        wt / "python/sglang/srt/managers/scheduler.py",
        accessor="self.tp_worker.model_runner",
        function_names=["hybrid_gdn_config", "linear_attn_model_spec", "mamba2_config"],
        import_anchor="from sglang.srt.managers.io_struct import",
    )
    _patch_file(
        wt / "python/sglang/srt/layers/attention/triton_backend.py",
        accessor="model_runner",
        function_names=["hybrid_gdn_config", "kimi_linear_config", "linear_attn_model_spec"],
        import_anchor=attn_anchor,
    )

    hla = wt / "python/sglang/srt/layers/attention/hybrid_linear_attn_backend.py"
    hla_text = hla.read_text()
    hla_text = _rewrite_accesses(
        hla_text, accessor="model_runner", function_names=["mamba2_config"]
    )
    hla_text = hla_text.replace(attn_anchor, _import_block(["mamba2_config"]) + attn_anchor)
    hla.write_text(hla_text)

    _patch_file(
        wt / "python/sglang/srt/layers/attention/attention_registry.py",
        accessor="runner",
        function_names=[
            "hybrid_gdn_config",
            "hybrid_lightning_config",
            "kimi_linear_config",
            "mamba2_config",
            "mambaish_config",
        ],
        import_anchor="from sglang.srt.utils import get_device_capability, is_musa\n",
    )

    _patch_file(
        wt / "python/sglang/srt/model_executor/pool_configurator.py",
        accessor="mr",
        function_names=["mambaish_config"],
        import_anchor="from sglang.srt.environ import envs\n",
    )

    _patch_file(
        wt / "python/sglang/srt/model_executor/model_runner_kv_cache_mixin.py",
        accessor="self",
        function_names=["hybrid_gdn_config", "mambaish_config"],
        import_anchor="from sglang.srt.distributed.parallel_state import get_world_group\n",
    )

    target_prefix = "self.target_worker.model_runner"
    spec_consumer_files = [
        ("eagle_worker.py", ["hybrid_gdn_config", "mamba2_config", "hybrid_lightning_config"]),
        ("eagle_worker_v2.py", ["hybrid_gdn_config", "mamba2_config"]),
        ("multi_layer_eagle_worker.py", ["hybrid_gdn_config"]),
        ("frozen_kv_mtp_worker.py", ["hybrid_gdn_config", "mamba2_config", "hybrid_lightning_config"]),
    ]
    for fname, fns in spec_consumer_files:
        _patch_file(
            wt / "python/sglang/srt/speculative" / fname,
            accessor=target_prefix,
            function_names=fns,
            import_anchor=spec_anchor,
        )

    git_add_and_commit(
        "Drop hybrid-arch property delegates from ModelRunner; update consumers",
        cwd=str(wt),
    )


if __name__ == "__main__":
    run_pr(transform=transform, base=BASE, target=TARGET)
