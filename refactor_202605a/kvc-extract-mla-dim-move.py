#!/usr/bin/env python3
"""Move stage for kvc-extract-mla-dim (MECH_COMMIT_SPLIT §"二段式"):

Pure cut+paste to ``mem_cache/kv_cache_configurator.py``. Body byte-equivalent.
Call sites prefix-strip + adds the configurator-module-side imports for the
new free function.
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
    insert_after,
    replace_call_site,
)
from _runner import run_pr

ID = "kvc-extract-mla-dim-move"
SUBJECT = "Move calculate_mla_kv_cache_dim to mem_cache.kv_cache_configurator (cut+paste)"
BODY = ""
AREA = "mech_model_runner"
BASE = "tom_refactor_202605a/primary/mech_model_runner/kvc-extract-mla-dim-prep"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


_NSA_IMPORT_BLOCK = '''\
from sglang.srt.mem_cache.memory_pool import KVCache, NSATokenToKVPool, ReqToTokenPool
from sglang.srt.utils.common import is_hip

_is_hip = is_hip()
'''


def transform(wt: Path) -> None:
    mixin = wt / "python/sglang/srt/model_executor/model_runner_kv_cache_mixin.py"
    cfg = wt / "python/sglang/srt/mem_cache/kv_cache_configurator.py"

    s, e = find_method_lines(
        mixin.read_text(),
        class_name="ModelRunnerKVCacheMixin",
        method_name="calculate_mla_kv_cache_dim",
    )
    method_text = cut_lines(mixin, s, e)
    lines = method_text.splitlines(keepends=True)
    assert lines[0].strip() == "@staticmethod"
    function_text = dedent_method_to_function("".join(lines[1:]))

    # Configurator imports — extend model_config import + bring in NSA pool.
    cfg_text = cfg.read_text()
    cfg_text = replace_call_site(
        cfg_text,
        old="from sglang.srt.configs.model_config import ModelConfig\n",
        new="from sglang.srt.configs.model_config import ModelConfig, is_deepseek_nsa\n",
    )
    cfg_text = replace_call_site(
        cfg_text,
        old="from sglang.srt.mem_cache.memory_pool import KVCache, ReqToTokenPool\n",
        new="",
    )
    cfg_text = insert_after(
        cfg_text,
        anchor="from sglang.srt.mem_cache.allocator import BaseTokenToKVPoolAllocator\n",
        addition=_NSA_IMPORT_BLOCK,
    )
    cfg.write_text(cfg_text)
    append_to_file(cfg, function_text.rstrip() + "\n")

    # Mixin: prefix-strip + add import.
    text = mixin.read_text()
    text = replace_call_site(
        text,
        old="ModelRunnerKVCacheMixin.calculate_mla_kv_cache_dim(",
        new="calculate_mla_kv_cache_dim(",
    )
    if (
        "from sglang.srt.mem_cache.kv_cache_configurator import "
        "calculate_mla_kv_cache_dim\n"
    ) not in text:
        text = insert_after(
            text,
            anchor="from sglang.srt.environ import envs\n",
            addition=(
                "from sglang.srt.mem_cache.kv_cache_configurator import (\n"
                "    calculate_mla_kv_cache_dim,\n"
                ")\n"
            ),
        )
    mixin.write_text(text)


if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        area_branch=AREA_BRANCH,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
