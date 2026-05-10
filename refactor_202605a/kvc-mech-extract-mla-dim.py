#!/usr/bin/env python3
"""Extract `ModelRunnerKVCacheMixin.calculate_mla_kv_cache_dim` to a free
function in new file `python/sglang/srt/mem_cache/kv_cache_dim.py`.

Per the mech_model_runner TODO doc, this is the only KVCacheConfigurator
mech commit — all the broader configurator work (skeleton +
method-body migration + drop-inheritance) is non-mechanical and lives
in Ch2.

Cut the method body from the mixin via ``find_method_lines``, dedent
4 spaces, swap the 3 ``self`` reads (``self.kv_cache_dtype``,
``self.model_config``, ``self.server_args``) for matching kwarg names,
replace the signature, and write the new module. Mixin's same-named
method is **deleted** (this is a move). The two internal callers in
the mixin (``init_memory_pool`` / ``_apply_memory_pool_config`` paths)
switch from ``self.calculate_mla_kv_cache_dim()`` to a module-qualified
``kv_cache_dim.calculate_mla_kv_cache_dim(...)``.

Usage:
    uv run --python 3.12 kvc-mech-extract-mla-dim.py run
    uv run --python 3.12 kvc-mech-extract-mla-dim.py verify
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
    dedent_method_to_function,
    find_method_lines,
    insert_after,
    replace_call_site,
)
from _runner import run_pr

ID = "kvc-mech-extract-mla-dim"
SUBJECT = "Extract calculate_mla_kv_cache_dim to free function in mem_cache.kv_cache_dim"
BODY = ""
AREA = "mech_model_runner"
BASE = "tom_refactor_202605a/primary/mech_model_runner/move-step-span-name"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


_MODULE_HEADER = '''\
from __future__ import annotations

import torch

from sglang.srt.configs.model_config import ModelConfig, is_deepseek_nsa
from sglang.srt.mem_cache.memory_pool import NSATokenToKVPool
from sglang.srt.server_args import ServerArgs
from sglang.srt.utils.common import is_hip

_is_hip = is_hip()


'''


def transform(wt: Path) -> None:
    mixin = wt / "python/sglang/srt/model_executor/model_runner_kv_cache_mixin.py"
    target = wt / "python/sglang/srt/mem_cache/kv_cache_dim.py"

    # ---- Cut method out of the mixin (real move, not copy) ----
    mixin_text = mixin.read_text()
    s, e = find_method_lines(
        mixin_text,
        class_name="ModelRunnerKVCacheMixin",
        method_name="calculate_mla_kv_cache_dim",
    )
    method_text = "".join(mixin_text.splitlines(keepends=True)[s:e])
    body_text = dedent_method_to_function(method_text)
    cut_lines(mixin, s, e)

    # ---- Substitute self-reads for kwarg names + swap signature ----
    body_text = body_text.replace(
        "def calculate_mla_kv_cache_dim(self: ModelRunner) -> int:\n",
        "def calculate_mla_kv_cache_dim(\n"
        "    *,\n"
        "    model_config: ModelConfig,\n"
        "    kv_cache_dtype: torch.dtype,\n"
        "    server_args: ServerArgs,\n"
        ") -> int:\n",
    )
    body_text = body_text.replace("self.kv_cache_dtype", "kv_cache_dtype")
    body_text = body_text.replace("self.model_config", "model_config")
    body_text = body_text.replace("self.server_args", "server_args")

    # ---- Write the new module ----
    target.write_text(_MODULE_HEADER + body_text)

    # ---- Update mixin: import + 2 internal call-site rewrites ----
    text = mixin.read_text()
    if "from sglang.srt.mem_cache import kv_cache_dim\n" not in text:
        text = insert_after(
            text,
            anchor="from sglang.srt.environ import envs\n",
            addition="from sglang.srt.mem_cache import kv_cache_dim\n",
        )
    text = replace_call_site(
        text,
        old="                    kv_cache_dim=self.calculate_mla_kv_cache_dim(),\n",
        new=(
            "                    kv_cache_dim=kv_cache_dim.calculate_mla_kv_cache_dim(\n"
            "                        model_config=self.model_config,\n"
            "                        kv_cache_dtype=self.kv_cache_dtype,\n"
            "                        server_args=self.server_args,\n"
            "                    ),\n"
        ),
    )
    text = replace_call_site(
        text,
        old="                kv_cache_dim=self.calculate_mla_kv_cache_dim(),\n",
        new=(
            "                kv_cache_dim=kv_cache_dim.calculate_mla_kv_cache_dim(\n"
            "                    model_config=self.model_config,\n"
            "                    kv_cache_dtype=self.kv_cache_dtype,\n"
            "                    server_args=self.server_args,\n"
            "                ),\n"
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
