#!/usr/bin/env python3
"""Extract `ModelRunnerKVCacheMixin.calculate_mla_kv_cache_dim` to a free
function in new file `python/sglang/srt/mem_cache/kv_cache_dim.py`.

Per ch3.2 spec — narrow kwargs (`model_config`, `kv_cache_dtype`,
`server_args`), independently reusable, no configurator state.

Cut the method body from the mixin via ``find_method_lines``, dedent
4 spaces, swap the ``self`` reads (``self.kv_cache_dtype``,
``self.model_config``, ``self.server_args``) for the matching kwarg
names, replace the signature, and paste under the module imports. No
literal copy of the body lives in this script — what's running is the
exact mixin source minus the ``self`` substitution.

Two internal callers in the mixin (`init_memory_pool` /
`_apply_memory_pool_config` paths) switch from
``self.calculate_mla_kv_cache_dim()`` to module-qualified
``kv_cache_dim.calculate_mla_kv_cache_dim(...)``. Mixin keeps the method
stub for now — actual deletion happens in `kvc-migrate-method-bodies`
along with the other mixin methods.

Usage:
    uv run --python 3.12 kvc-extract-mla-dim.py run
    uv run --python 3.12 kvc-extract-mla-dim.py verify
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
    dedent_method_to_function,
    find_method_lines,
    insert_after,
    replace_call_site,
)
from _runner import run_pr

ID = "kvc-extract-mla-dim"
SUBJECT = "Extract calculate_mla_kv_cache_dim to free function in mem_cache.kv_cache_dim"
BODY = ""
AREA = "nonmech_model_runner"
BASE = "tom_refactor_202605a/primary/mech_model_runner"
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

    # ---- Cut the method out of the mixin source ----
    mixin_text = mixin.read_text()
    s, e = find_method_lines(
        mixin_text,
        class_name="ModelRunnerKVCacheMixin",
        method_name="calculate_mla_kv_cache_dim",
    )
    method_text = "".join(mixin_text.splitlines(keepends=True)[s:e])
    body_text = dedent_method_to_function(method_text)

    # ---- Substitute self-reads for the matching kwarg names ----
    # Signature swap: method form → free function with explicit kwargs.
    body_text = body_text.replace(
        "def calculate_mla_kv_cache_dim(self: ModelRunner) -> int:\n",
        "def calculate_mla_kv_cache_dim(\n"
        "    *,\n"
        "    model_config: ModelConfig,\n"
        "    kv_cache_dtype: torch.dtype,\n"
        "    server_args: ServerArgs,\n"
        ") -> int:\n",
    )
    # Bare-ref reads on the 3 self attrs become bare kwarg names.
    body_text = body_text.replace("self.kv_cache_dtype", "kv_cache_dtype")
    body_text = body_text.replace("self.model_config", "model_config")
    body_text = body_text.replace("self.server_args", "server_args")

    # ---- Paste into the target module under the imports ----
    target.write_text(_MODULE_HEADER + body_text)

    # ---- Update mixin's two internal callers ----
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
