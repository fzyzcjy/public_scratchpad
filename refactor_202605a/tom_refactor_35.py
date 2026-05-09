#!/usr/bin/env python3
"""Reproducible transform: delete the 7 hybrid-arch property delegates from
ModelRunner (now redundant after /34) and update consumer call sites to call
the free functions directly. Also drops the now-unused
`_linear_attn_registry_cache` field and the `_UNSET` sentinel.

Consumers updated (per /17 layout):
  - python/sglang/srt/managers/scheduler.py
  - python/sglang/srt/layers/attention/triton_backend.py
  - python/sglang/srt/layers/attention/hybrid_linear_attn_backend.py
  - python/sglang/srt/speculative/eagle_worker.py
  - python/sglang/srt/speculative/eagle_worker_v2.py
  - python/sglang/srt/speculative/multi_layer_eagle_worker.py
  - python/sglang/srt/speculative/frozen_kv_mtp_worker.py
"""

import sys
from pathlib import Path

sys.path.append(".claude/skills/mechanical-refactor-verify")
from mechanical_refactor_verify_utils import (
    verify_mechanical_refactor,
    git_add_and_commit,
)

BASE_COMMIT = "tom_refactor/34"
TARGET_COMMIT = "tom_refactor/35"


def transform(dir_root: Path) -> None:
    # ---- Delete the 7 property delegates + _get_linear_attn_registry_result helper ----
    mr = dir_root / "python/sglang/srt/model_executor/model_runner.py"
    text = mr.read_text()

    delegate_blocks = [
        # qwen3_next_config
        (
            "    @property\n"
            "    def qwen3_next_config(self):\n"
            "        return get_qwen3_next_config(self.model_config)\n"
            "\n"
        ),
        # hybrid_lightning_config
        (
            "    @property\n"
            "    def hybrid_lightning_config(self):\n"
            "        return get_hybrid_lightning_config(self.model_config)\n"
            "\n"
        ),
        # hybrid_gdn_config
        (
            "    @property\n"
            "    def hybrid_gdn_config(self):\n"
            "        return get_hybrid_gdn_config(self.model_config)\n"
            "\n"
        ),
        # mamba2_config
        (
            "    @property\n"
            "    def mamba2_config(self):\n"
            "        return get_mamba2_config(self.model_config, is_draft_worker=self.is_draft_worker)\n"
            "\n"
        ),
        # kimi_linear_config
        (
            "    @property\n"
            "    def kimi_linear_config(self):\n"
            "        return get_kimi_linear_config(self.model_config)\n"
            "\n"
        ),
        # _get_linear_attn_registry_result helper
        (
            "    def _get_linear_attn_registry_result(self):\n"
            "        return _get_linear_attn_registry_result(self.model_config)\n"
            "\n"
        ),
        # linear_attn_model_spec
        (
            "    @property\n"
            "    def linear_attn_model_spec(self):\n"
            "        return get_linear_attn_model_spec(self.model_config)\n"
            "\n"
        ),
        # mambaish_config
        (
            "    @property\n"
            "    def mambaish_config(self):\n"
            "        return get_mambaish_config(self.model_config, is_draft_worker=self.is_draft_worker)\n"
            "\n"
        ),
    ]
    for block in delegate_blocks:
        assert block in text, f"delegate block not found: {block!r}"
        text = text.replace(block, "")

    # Drop the `_linear_attn_registry_cache` field + comment.
    cache_block = (
        "        # Linear-attn registry result is computed lazily; _UNSET distinguishes\n"
        '        # "not yet computed" from "computed and got None".\n'
        "        self._linear_attn_registry_cache: Any = _UNSET\n"
        "\n"
    )
    assert cache_block in text, "_linear_attn_registry_cache assignment not found"
    text = text.replace(cache_block, "")

    # Drop the _UNSET sentinel and its comment block.
    unset_block = (
        "# Sentinel distinct from None so the linear-attn registry cache can store\n"
        "# None as a real result (see _get_linear_attn_registry_result).\n"
        "# Rust analogue: OnceCell<Option<...>>.\n"
        "_UNSET: Any = object()\n"
        "\n"
        "\n"
    )
    assert unset_block in text, "_UNSET sentinel block not found"
    text = text.replace(unset_block, "")

    # The `_get_linear_attn_registry_result` symbol is no longer referenced
    # inside model_runner.py; drop it from the hybrid_arch import.
    text = text.replace(
        "from sglang.srt.configs.hybrid_arch import (\n"
        "    _get_linear_attn_registry_result,\n"
        "    get_hybrid_gdn_config,\n"
        "    get_hybrid_lightning_config,\n"
        "    get_kimi_linear_config,\n"
        "    get_linear_attn_model_spec,\n"
        "    get_mamba2_config,\n"
        "    get_mambaish_config,\n"
        "    get_qwen3_next_config,\n"
        ")\n",
        "from sglang.srt.configs.hybrid_arch import (\n"
        "    get_hybrid_gdn_config,\n"
        "    get_hybrid_lightning_config,\n"
        "    get_kimi_linear_config,\n"
        "    get_linear_attn_model_spec,\n"
        "    get_mamba2_config,\n"
        "    get_mambaish_config,\n"
        "    get_qwen3_next_config,\n"
        ")\n",
    )

    mr.write_text(text)

    # ---- Consumer ripple ----
    # All call sites switch from `<runner>.X_config` (or `linear_attn_model_spec`,
    # `mambaish_config`) to the free function form, passing `model_config` and
    # — for mamba2/mambaish — `is_draft_worker`.

    # scheduler.py
    sched = dir_root / "python/sglang/srt/managers/scheduler.py"
    s = sched.read_text()
    s = s.replace(
        "        _spec = self.tp_worker.model_runner.linear_attn_model_spec\n",
        "        _spec = get_linear_attn_model_spec(self.tp_worker.model_runner.model_config)\n",
    )
    s = s.replace(
        "        self.is_hybrid_ssm = (\n"
        "            self.tp_worker.model_runner.hybrid_gdn_config is not None\n"
        "            or self.tp_worker.model_runner.mamba2_config is not None\n"
        "            or _registry_needs_mamba\n"
        "        )\n",
        "        self.is_hybrid_ssm = (\n"
        "            get_hybrid_gdn_config(self.tp_worker.model_runner.model_config) is not None\n"
        "            or get_mamba2_config(\n"
        "                self.tp_worker.model_runner.model_config,\n"
        "                is_draft_worker=self.tp_worker.model_runner.is_draft_worker,\n"
        "            ) is not None\n"
        "            or _registry_needs_mamba\n"
        "        )\n",
    )
    # Add the import (anchor on an existing sglang.srt.configs.* import if any,
    # else top-of-file after stdlib imports).
    s = s.replace(
        "from sglang.srt.managers.io_struct import",
        "from sglang.srt.configs.hybrid_arch import (\n"
        "    get_hybrid_gdn_config,\n"
        "    get_linear_attn_model_spec,\n"
        "    get_mamba2_config,\n"
        ")\n"
        "from sglang.srt.managers.io_struct import",
    )
    sched.write_text(s)

    # triton_backend.py
    tri = dir_root / "python/sglang/srt/layers/attention/triton_backend.py"
    t = tri.read_text()
    t = t.replace(
        "        elif (\n"
        "            model_runner.hybrid_gdn_config is not None\n"
        "            or model_runner.kimi_linear_config is not None\n"
        "            or model_runner.linear_attn_model_spec is not None\n"
        "        ):\n",
        "        elif (\n"
        "            get_hybrid_gdn_config(model_runner.model_config) is not None\n"
        "            or get_kimi_linear_config(model_runner.model_config) is not None\n"
        "            or get_linear_attn_model_spec(model_runner.model_config) is not None\n"
        "        ):\n",
    )
    # Insert import; anchor on an existing relative-stable sglang.srt import.
    t = t.replace(
        "from sglang.srt.layers.attention.base_attn_backend import AttentionBackend\n",
        "from sglang.srt.configs.hybrid_arch import (\n"
        "    get_hybrid_gdn_config,\n"
        "    get_kimi_linear_config,\n"
        "    get_linear_attn_model_spec,\n"
        ")\n"
        "from sglang.srt.layers.attention.base_attn_backend import AttentionBackend\n",
    )
    tri.write_text(t)

    # hybrid_linear_attn_backend.py
    hla = dir_root / "python/sglang/srt/layers/attention/hybrid_linear_attn_backend.py"
    h = hla.read_text()
    h = h.replace(
        "        config = model_runner.mamba2_config\n",
        "        config = get_mamba2_config(\n"
        "            model_runner.model_config,\n"
        "            is_draft_worker=model_runner.is_draft_worker,\n"
        "        )\n",
    )
    h = h.replace(
        "from sglang.srt.layers.attention.base_attn_backend import AttentionBackend\n",
        "from sglang.srt.configs.hybrid_arch import get_mamba2_config\n"
        "from sglang.srt.layers.attention.base_attn_backend import AttentionBackend\n",
    )
    hla.write_text(h)

    # eagle_worker.py
    ew = dir_root / "python/sglang/srt/speculative/eagle_worker.py"
    e = ew.read_text()
    e = e.replace(
        "        if (\n"
        "            self.target_worker.model_runner.hybrid_gdn_config is not None\n"
        "            or self.target_worker.model_runner.mamba2_config is not None\n"
        "            or self.target_worker.model_runner.hybrid_lightning_config is not None\n"
        "        ):\n",
        "        if (\n"
        "            get_hybrid_gdn_config(self.target_worker.model_runner.model_config) is not None\n"
        "            or get_mamba2_config(\n"
        "                self.target_worker.model_runner.model_config,\n"
        "                is_draft_worker=self.target_worker.model_runner.is_draft_worker,\n"
        "            ) is not None\n"
        "            or get_hybrid_lightning_config(self.target_worker.model_runner.model_config) is not None\n"
        "        ):\n",
    )
    e = e.replace(
        "from sglang.srt.speculative.spec_info import SpeculativeAlgorithm\n",
        "from sglang.srt.configs.hybrid_arch import (\n"
        "    get_hybrid_gdn_config,\n"
        "    get_hybrid_lightning_config,\n"
        "    get_mamba2_config,\n"
        ")\n"
        "from sglang.srt.speculative.spec_info import SpeculativeAlgorithm\n",
    )
    ew.write_text(e)

    # eagle_worker_v2.py
    ew2 = dir_root / "python/sglang/srt/speculative/eagle_worker_v2.py"
    e2 = ew2.read_text()
    e2 = e2.replace(
        "        if (\n"
        "            self.target_worker.model_runner.hybrid_gdn_config is not None\n"
        "            or self.target_worker.model_runner.mamba2_config is not None\n"
        "        ):\n",
        "        if (\n"
        "            get_hybrid_gdn_config(self.target_worker.model_runner.model_config) is not None\n"
        "            or get_mamba2_config(\n"
        "                self.target_worker.model_runner.model_config,\n"
        "                is_draft_worker=self.target_worker.model_runner.is_draft_worker,\n"
        "            ) is not None\n"
        "        ):\n",
    )
    e2 = e2.replace(
        "from sglang.srt.speculative.spec_info import SpeculativeAlgorithm\n",
        "from sglang.srt.configs.hybrid_arch import (\n"
        "    get_hybrid_gdn_config,\n"
        "    get_mamba2_config,\n"
        ")\n"
        "from sglang.srt.speculative.spec_info import SpeculativeAlgorithm\n",
    )
    ew2.write_text(e2)

    # multi_layer_eagle_worker.py
    mle = dir_root / "python/sglang/srt/speculative/multi_layer_eagle_worker.py"
    m = mle.read_text()
    m = m.replace(
        "        if self.target_worker.model_runner.hybrid_gdn_config is not None:\n",
        "        if get_hybrid_gdn_config(self.target_worker.model_runner.model_config) is not None:\n",
    )
    m = m.replace(
        "from sglang.srt.speculative.spec_info import SpeculativeAlgorithm\n",
        "from sglang.srt.configs.hybrid_arch import get_hybrid_gdn_config\n"
        "from sglang.srt.speculative.spec_info import SpeculativeAlgorithm\n",
    )
    mle.write_text(m)

    # frozen_kv_mtp_worker.py
    fkv = dir_root / "python/sglang/srt/speculative/frozen_kv_mtp_worker.py"
    f = fkv.read_text()
    f = f.replace(
        "        if (\n"
        "            self.target_worker.model_runner.hybrid_gdn_config is not None\n"
        "            or self.target_worker.model_runner.mamba2_config is not None\n"
        "            or self.target_worker.model_runner.hybrid_lightning_config is not None\n"
        "        ):\n",
        "        if (\n"
        "            get_hybrid_gdn_config(self.target_worker.model_runner.model_config) is not None\n"
        "            or get_mamba2_config(\n"
        "                self.target_worker.model_runner.model_config,\n"
        "                is_draft_worker=self.target_worker.model_runner.is_draft_worker,\n"
        "            ) is not None\n"
        "            or get_hybrid_lightning_config(self.target_worker.model_runner.model_config) is not None\n"
        "        ):\n",
    )
    f = f.replace(
        "from sglang.srt.speculative.spec_info import SpeculativeAlgorithm\n",
        "from sglang.srt.configs.hybrid_arch import (\n"
        "    get_hybrid_gdn_config,\n"
        "    get_hybrid_lightning_config,\n"
        "    get_mamba2_config,\n"
        ")\n"
        "from sglang.srt.speculative.spec_info import SpeculativeAlgorithm\n",
    )
    fkv.write_text(f)

    git_add_and_commit(
        "Drop hybrid-arch property delegates from ModelRunner; update consumers",
        cwd=str(dir_root),
    )


if __name__ == "__main__":
    verify_mechanical_refactor(
        base_commit=BASE_COMMIT,
        target_commit=TARGET_COMMIT,
        transform=transform,
    )
