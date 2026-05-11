#!/usr/bin/env python3
"""Prep stage for extract-kv-cache-dtype (MECH_COMMIT_SPLIT §"二段式"):

In-place reshape of ``ModelRunner.configure_kv_cache_dtype``:
- Add ``@staticmethod`` + kwarg-only signature taking ``server_args``,
  ``model``, ``model_dtype``.
- Replace ``self.server_args.kv_cache_dtype`` with a local
  ``server_args_kv_cache_dtype`` (so the body never mutates kwarg-passed state).
- Replace remaining ``self.X`` reads with kwargs / locals.
- Turn the ``self.kv_cache_dtype = ...`` write into a local + 2-tuple return.

Call site rewritten to ``self.server_args.kv_cache_dtype, self.kv_cache_dtype =
ModelRunner.configure_kv_cache_dtype(...)``.

The module-level ``TORCH_DTYPE_TO_KV_CACHE_STR`` constant stays in place; the
``-move`` commit cuts it together with the method.
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

ID = "extract-kv-cache-dtype-prep"
SUBJECT = "Prep configure_kv_cache_dtype for extraction: @staticmethod + kwargs + 2-tuple return"
BODY = ""
AREA = "mech_model_runner"
BASE = "tom_refactor_202605a/primary/mech_model_runner/extract-prealloc-symm-pool-move"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


def transform(wt: Path) -> None:
    mr = wt / "python/sglang/srt/model_executor/model_runner.py"
    text = mr.read_text()

    start, end = find_method_lines(
        text, class_name="ModelRunner", method_name="configure_kv_cache_dtype"
    )
    lines = text.splitlines(keepends=True)
    method = "".join(lines[start:end])
    new_method = (
        method
        .replace(
            "    def configure_kv_cache_dtype(self):\n",
            "    @staticmethod\n"
            "    def configure_kv_cache_dtype(\n"
            "        *,\n"
            "        server_args: ServerArgs,\n"
            "        model: nn.Module,\n"
            "        model_dtype: torch.dtype,\n"
            "    ) -> tuple[str, torch.dtype]:\n"
            "        server_args_kv_cache_dtype = server_args.kv_cache_dtype\n",
        )
        # Specific first so server_args.kv_cache_dtype reads/writes land on the local.
        .replace("self.server_args.kv_cache_dtype", "server_args_kv_cache_dtype")
        .replace("self.server_args", "server_args")
        .replace("self.model", "model")
        .replace("self.kv_cache_dtype = ", "kv_cache_dtype = ")
        .replace("self.kv_cache_dtype", "kv_cache_dtype")
        .replace("self.dtype", "model_dtype")
    )
    new_method = new_method.rstrip() + "\n        return server_args_kv_cache_dtype, kv_cache_dtype\n\n"
    text = "".join(lines[:start]) + new_method + "".join(lines[end:])

    text = replace_call_site(
        text,
        old="        self.configure_kv_cache_dtype()\n",
        new=(
            "        self.server_args.kv_cache_dtype, self.kv_cache_dtype = (\n"
            "            ModelRunner.configure_kv_cache_dtype(\n"
            "                server_args=self.server_args,\n"
            "                model=self.model,\n"
            "                model_dtype=self.dtype,\n"
            "            )\n"
            "        )\n"
        ),
    )
    mr.write_text(text)


if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        area_branch=AREA_BRANCH,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
