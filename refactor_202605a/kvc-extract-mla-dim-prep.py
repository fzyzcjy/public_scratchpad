#!/usr/bin/env python3
"""Prep stage for kvc-extract-mla-dim (MECH_COMMIT_SPLIT §"二段式"):

Reshape ``ModelRunnerKVCacheMixin.calculate_mla_kv_cache_dim`` toward
free-function form. ``@staticmethod`` + kwarg-only signature; ``self.X`` →
kwargs. Both in-class callers switch to class-qualified form.
"""

# /// script
# requires-python = ">=3.10"
# dependencies = ["typer"]
# ///

import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from _helpers import find_method_lines, replace_call_site
from _runner import run_pr

ID = "kvc-extract-mla-dim-prep"
SUBJECT = "Prep calculate_mla_kv_cache_dim for extraction"
BODY = ""
AREA = "mech_model_runner"
BASE = "tom_refactor_202605a/primary/mech_model_runner/kvc-introduce-skeleton"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


def transform(wt: Path) -> None:
    mixin = wt / "python/sglang/srt/model_executor/model_runner_kv_cache_mixin.py"
    text = mixin.read_text()

    start, end = find_method_lines(
        text,
        class_name="ModelRunnerKVCacheMixin",
        method_name="calculate_mla_kv_cache_dim",
    )
    lines = text.splitlines(keepends=True)
    method = "".join(lines[start:end])
    method = method.replace(
        "    def calculate_mla_kv_cache_dim(self: ModelRunner) -> int:\n",
        "    @staticmethod\n"
        "    def calculate_mla_kv_cache_dim(\n"
        "        *,\n"
        "        model_config: ModelConfig,\n"
        "        kv_cache_dtype: torch.dtype,\n"
        "        server_args: ServerArgs,\n"
        "    ) -> int:\n",
        1,
    )
    method = method.replace("self.kv_cache_dtype", "kv_cache_dtype")
    method = method.replace("self.model_config", "model_config")
    method = method.replace("self.server_args", "server_args")
    text = "".join(lines[:start]) + method + "".join(lines[end:])

    # Two in-class callers: ``self.calculate_mla_kv_cache_dim()`` → class-qualified.
    text = replace_call_site(
        text,
        old="                    kv_cache_dim=self.calculate_mla_kv_cache_dim(),\n",
        new=(
            "                    kv_cache_dim=ModelRunnerKVCacheMixin.calculate_mla_kv_cache_dim(\n"
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
            "                kv_cache_dim=ModelRunnerKVCacheMixin.calculate_mla_kv_cache_dim(\n"
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
