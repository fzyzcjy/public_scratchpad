#!/usr/bin/env python3
"""Delete 7 hybrid-arch property delegates from ModelRunner; update consumers."""
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.append(str(HERE))
sys.path.append(".claude/skills/mechanical-refactor-verify")
from _helpers import cut_lines, find_method_lines
from mechanical_refactor_verify_utils import git_add_and_commit, verify_mechanical_refactor

BASE_COMMIT = "tom_refactor/34"
TARGET_COMMIT = "tom_refactor/35"

_SHORT = {"get_hybrid_gdn_config": "hybrid_gdn_config", "get_kimi_linear_config": "kimi_linear_config",
          "get_linear_attn_model_spec": "linear_attn_model_spec", "get_hybrid_lightning_config": "hybrid_lightning_config"}

def _imp(names):
    names = sorted(set(names))
    if len(names) == 1:
        return f"from sglang.srt.configs.hybrid_arch import {names[0]}\n"
    return "from sglang.srt.configs.hybrid_arch import (\n" + "".join(f"    {n},\n" for n in names) + ")\n"


def _patch(path: Path, prefix: str, fns: list, anchor: str) -> None:
    t = path.read_text()
    for full in fns:
        if full in _SHORT:
            t = t.replace(f"{prefix}.{_SHORT[full]}", f"{full}({prefix}.model_config)")
    if "get_mamba2_config" in fns:
        t = t.replace(f"            or {prefix}.mamba2_config is not None\n",
            f"            or get_mamba2_config(\n                {prefix}.model_config,\n"
            f"                is_draft_worker={prefix}.is_draft_worker,\n            ) is not None\n")
    path.write_text(t.replace(anchor, _imp(fns) + anchor))


def transform(dir_root: Path) -> None:
    mr = dir_root / "python/sglang/srt/model_executor/model_runner.py"
    for n in ("mambaish_config", "linear_attn_model_spec", "_get_linear_attn_registry_result",
              "kimi_linear_config", "mamba2_config", "hybrid_gdn_config",
              "hybrid_lightning_config", "qwen3_next_config"):
        s, e = find_method_lines(mr.read_text(), class_name="ModelRunner", method_name=n)
        cut_lines(mr, s, e)
    t = mr.read_text().replace(
        "        # Linear-attn registry result is computed lazily; _UNSET distinguishes\n"
        '        # "not yet computed" from "computed and got None".\n'
        "        self._linear_attn_registry_cache: Any = _UNSET\n\n", "").replace(
        "# Sentinel distinct from None so the linear-attn registry cache can store\n"
        "# None as a real result (see _get_linear_attn_registry_result).\n"
        "# Rust analogue: OnceCell<Option<...>>.\n_UNSET: Any = object()\n\n\n", "").replace(
        "    _get_linear_attn_registry_result,\n", "")
    mr.write_text(t)

    AB = "from sglang.srt.layers.attention.base_attn_backend import AttentionBackend\n"
    SI = "from sglang.srt.speculative.spec_info import SpeculativeAlgorithm\n"
    _patch(dir_root / "python/sglang/srt/managers/scheduler.py", "self.tp_worker.model_runner",
           ["get_hybrid_gdn_config", "get_linear_attn_model_spec", "get_mamba2_config"],
           "from sglang.srt.managers.io_struct import")
    _patch(dir_root / "python/sglang/srt/layers/attention/triton_backend.py", "model_runner",
           ["get_hybrid_gdn_config", "get_kimi_linear_config", "get_linear_attn_model_spec"], AB)

    hla = dir_root / "python/sglang/srt/layers/attention/hybrid_linear_attn_backend.py"
    h = hla.read_text().replace(
        "        config = model_runner.mamba2_config\n",
        "        config = get_mamba2_config(\n            model_runner.model_config,\n"
        "            is_draft_worker=model_runner.is_draft_worker,\n        )\n")
    hla.write_text(h.replace(AB, _imp(["get_mamba2_config"]) + AB))

    pp = "self.target_worker.model_runner"
    G, M, L = "get_hybrid_gdn_config", "get_mamba2_config", "get_hybrid_lightning_config"
    for fname, fns in (("eagle_worker.py", [G, M, L]), ("eagle_worker_v2.py", [G, M]),
                       ("multi_layer_eagle_worker.py", [G]), ("frozen_kv_mtp_worker.py", [G, M, L])):
        _patch(dir_root / "python/sglang/srt/speculative" / fname, pp, fns, SI)

    git_add_and_commit("Drop hybrid-arch property delegates from ModelRunner; update consumers", cwd=str(dir_root))


if __name__ == "__main__":
    verify_mechanical_refactor(base_commit=BASE_COMMIT, target_commit=TARGET_COMMIT, transform=transform)
