#!/usr/bin/env python3
"""Delete the 7 hybrid-arch property delegates left behind by /34 on
ModelRunner; ripple all consumers to call the free functions in
`configs.hybrid_arch` directly.

Each hybrid_arch function takes `model_config: ModelConfig`; `mamba2_config`
and `mambaish_config` additionally need `is_draft_worker: bool` kwarg.

Per Ch1 rule "**不留 1 行 delegate**", drop the delegates as soon as consumers
are updated.

Usage:
    uv run --python 3.12 drop-hybrid-arch-delegates.py run
    uv run --python 3.12 drop-hybrid-arch-delegates.py verify
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

ID = "drop-hybrid-arch-delegates"
SUBJECT = "Drop hybrid-arch property delegates from ModelRunner; update consumers"
BODY = ""
AREA = "mech_model_runner"
BASE = "tom_refactor_202605a/primary/mech_model_runner/extract-hybrid-arch-props"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


# Functions that take `model_config` (no extra kwarg).
_MODEL_CONFIG = {
    "qwen3_next_config",
    "hybrid_lightning_config",
    "hybrid_gdn_config",
    "kimi_linear_config",
    "linear_attn_model_spec",
}
# Functions that take `model_config` plus `is_draft_worker` kwarg.
_MODEL_CONFIG_WITH_DRAFT = {
    "mamba2_config",
    "mambaish_config",
}


def _rewrite_accesses(text: str, *, accessor: str, function_names: list[str]) -> str:
    """Rewrite `<accessor>.<name>` access into a bare `<name>(...)` call.

    Per category:
    - `_MODEL_CONFIG`: `<name>(<accessor>.model_config)`.
    - `_MODEL_CONFIG_WITH_DRAFT`: `<name>(<accessor>.model_config, is_draft_worker=<accessor>.is_draft_worker)`.

    Names are imported via `from sglang.srt.configs.hybrid_arch import ...` —
    bare-call form, NOT module-qualified `hybrid_arch.<name>(...)`. The
    function names already carry their semantic ("qwen3_next_config",
    "mambaish_config" etc) and are domain-specific enough that the
    `hybrid_arch.` prefix is noise at consumer sites.
    """
    for name in function_names:
        if name in _MODEL_CONFIG_WITH_DRAFT:
            replacement = (
                f"{name}("
                f"{accessor}.model_config, "
                f"is_draft_worker={accessor}.is_draft_worker"
                f")"
            )
        else:
            replacement = f"{name}({accessor}.model_config)"
        text = text.replace(f"{accessor}.{name}", replacement)
    return text


def _import_block(function_names: list[str]) -> str:
    """`from sglang.srt.configs.hybrid_arch import a, b, c\n` for the given names."""
    sorted_names = sorted(set(function_names))
    if len(sorted_names) == 1:
        return f"from sglang.srt.configs.hybrid_arch import {sorted_names[0]}\n"
    body = ",\n".join(f"    {n}" for n in sorted_names)
    return f"from sglang.srt.configs.hybrid_arch import (\n{body},\n)\n"


def _patch_file(
    path: Path,
    *,
    accessor: str,
    function_names: list[str],
    import_anchor: str,
) -> None:
    text = path.read_text()
    text = _rewrite_accesses(text, accessor=accessor, function_names=function_names)
    import_line = _import_block(function_names)
    if import_line not in text:
        text = text.replace(import_anchor, import_line + import_anchor)
    path.write_text(text)


def transform(wt: Path) -> None:
    mr = wt / "python/sglang/srt/model_executor/model_runner.py"

    # Delete each delegate method on ModelRunner.
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

    # Drop the hybrid_arch module import from ModelRunner — after delegates are
    # gone, ModelRunner has no remaining hybrid_arch.* call.
    text = mr.read_text()
    text = text.replace("from sglang.srt.configs import hybrid_arch\n", "")
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
    hla_import = _import_block(["mamba2_config"])
    if hla_import not in hla_text:
        hla_text = hla_text.replace(attn_anchor, hla_import + attn_anchor)
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

    # Test fake fix: pool_configurator's test mocks `mr.mambaish_config = None`
    # directly on a MagicMock. After this commit, consumers call
    # hybrid_arch.mambaish_config(mr.model_config, is_draft_worker=...). The
    # function traverses ``mc.hf_config.get_text_config()`` — stub it to
    # return mc.hf_config so the traversal succeeds and falls back to None.
    test_pc = wt / "test/registered/unit/model_executor/test_pool_configurator.py"
    text = test_pc.read_text()
    text = text.replace(
        '    mc.hf_config = SimpleNamespace(architectures=["LlamaForCausalLM"])\n',
        '    mc.hf_config = SimpleNamespace(architectures=["LlamaForCausalLM"])\n'
        '    mc.hf_config.get_text_config = lambda: mc.hf_config\n',
    )
    test_pc.write_text(text)

if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        area_branch=AREA_BRANCH,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
