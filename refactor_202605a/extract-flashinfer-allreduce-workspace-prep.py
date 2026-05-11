#!/usr/bin/env python3
"""Prep stage for extract-flashinfer-allreduce-workspace (MECH_COMMIT_SPLIT §"二段式"):

In-place reshape of ``ModelRunner._pre_initialize_flashinfer_allreduce_workspace``
toward free-function form. Body reads 3 ``self.X`` fields → kwargs;
``@staticmethod`` + kwarg-only signature; sole call site becomes class-qualified.
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

ID = "extract-flashinfer-allreduce-workspace-prep"
SUBJECT = "Prep _pre_initialize_flashinfer_allreduce_workspace for extraction"
BODY = ""
AREA = "mech_model_runner"
BASE = "tom_refactor_202605a/primary/mech_model_runner/extract-lora-moe-buffers-move"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


def transform(wt: Path) -> None:
    mr = wt / "python/sglang/srt/model_executor/model_runner.py"
    text = mr.read_text()

    start, end = find_method_lines(
        text,
        class_name="ModelRunner",
        method_name="_pre_initialize_flashinfer_allreduce_workspace",
    )
    lines = text.splitlines(keepends=True)
    method = "".join(lines[start:end])
    method = method.replace(
        "    def _pre_initialize_flashinfer_allreduce_workspace(self):\n",
        "    @staticmethod\n"
        "    def _pre_initialize_flashinfer_allreduce_workspace(\n"
        "        *,\n"
        "        server_args: ServerArgs,\n"
        "        model_config: ModelConfig,\n"
        "        dtype: torch.dtype,\n"
        "    ):\n",
    )
    method = method.replace("self.server_args", "server_args")
    method = method.replace("self.model_config", "model_config")
    method = method.replace("self.dtype", "dtype")
    text = "".join(lines[:start]) + method + "".join(lines[end:])

    text = replace_call_site(
        text,
        old="            self._pre_initialize_flashinfer_allreduce_workspace()\n",
        new=(
            "            ModelRunner._pre_initialize_flashinfer_allreduce_workspace(\n"
            "                server_args=self.server_args,\n"
            "                model_config=self.model_config,\n"
            "                dtype=self.dtype,\n"
            "            )\n"
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
