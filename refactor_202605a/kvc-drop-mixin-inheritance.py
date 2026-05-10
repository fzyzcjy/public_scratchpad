#!/usr/bin/env python3
"""Drop ``ModelRunnerKVCacheMixin`` inheritance.

3 textual rewrites + 1 file delete:

1. ``class ModelRunner(ModelRunnerKVCacheMixin):`` → ``class ModelRunner:``
2. Remove the ``model_runner_kv_cache_mixin`` import.
3. Replace ``self.init_memory_pool(pre_model_load_memory)`` in
   ``ModelRunner.initialize`` with the explicit 8-field writeback block
   per ch3.2.
4. Delete ``python/sglang/srt/model_executor/model_runner_kv_cache_mixin.py``.

After this commit ``grep -r ModelRunnerKVCacheMixin python/`` is zero.

Usage:
    uv run --python 3.12 kvc-drop-mixin-inheritance.py run
    uv run --python 3.12 kvc-drop-mixin-inheritance.py verify
"""

# /// script
# requires-python = ">=3.10"
# dependencies = ["typer"]
# ///

import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from _helpers import replace_call_site
from _runner import run_pr

ID = "kvc-drop-mixin-inheritance"
SUBJECT = "Drop ModelRunnerKVCacheMixin inheritance; ModelRunner uses KVCacheConfigurator directly"
BODY = ""
AREA = "nonmech_model_runner"
BASE = "tom_refactor_202605a/primary/nonmech_model_runner/kvc-migrate-method-bodies"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


_WRITEBACK_BLOCK = '''\
        result = self.kv_cache_configurator.configure(
            pre_model_load_memory=pre_model_load_memory
        )
        self.max_total_num_tokens = result.max_total_num_tokens
        self.max_running_requests = result.max_running_requests
        self.req_to_token_pool = result.req_to_token_pool
        self.token_to_kv_pool = result.token_to_kv_pool
        self.token_to_kv_pool_allocator = result.token_to_kv_pool_allocator
        self.memory_pool_config = result.memory_pool_config
        if self.is_hybrid_swa:
            self.full_max_total_num_tokens = result.full_max_total_num_tokens
            self.swa_max_total_num_tokens = result.swa_max_total_num_tokens
'''


def transform(wt: Path) -> None:
    mr = wt / "python/sglang/srt/model_executor/model_runner.py"
    mixin = wt / "python/sglang/srt/model_executor/model_runner_kv_cache_mixin.py"

    text = mr.read_text()

    text = replace_call_site(
        text,
        old="class ModelRunner(ModelRunnerKVCacheMixin):",
        new="class ModelRunner:",
    )
    text = replace_call_site(
        text,
        old=(
            "from sglang.srt.model_executor.model_runner_kv_cache_mixin import (\n"
            "    ModelRunnerKVCacheMixin,\n"
            ")\n"
        ),
        new="",
    )
    text = replace_call_site(
        text,
        old="        self.init_memory_pool(pre_model_load_memory)\n",
        new=_WRITEBACK_BLOCK,
    )

    mr.write_text(text)

    if mixin.exists():
        mixin.unlink()


if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        area_branch=AREA_BRANCH,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
