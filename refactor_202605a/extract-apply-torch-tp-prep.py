#!/usr/bin/env python3
"""Prep stage for extract-apply-torch-tp (MECH_COMMIT_SPLIT §"二段式"):

In-place reshape of ``ModelRunner.apply_torch_tp`` to a free-function-ready
form. Adds ``@staticmethod`` + kwarg-only signature; replaces ``self.X``
reads with kwargs; drops the in-body self-import. Call site rewritten to
class-qualified ``ModelRunner.apply_torch_tp(model=..., device=..., tp_size=...)``.
The follow-up ``-move`` commit cuts the staticmethod byte-equivalently into
``layers/model_parallel.py``.
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

ID = "extract-apply-torch-tp-prep"
SUBJECT = "Prep apply_torch_tp for extraction: @staticmethod + kwarg-only + class-qualified call site"
BODY = ""
AREA = "mech_model_runner"
BASE = "tom_refactor_202605a/primary/mech_model_runner/extract-init-cublas-move"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


def transform(wt: Path) -> None:
    mr = wt / "python/sglang/srt/model_executor/model_runner.py"
    text = mr.read_text()

    start, end = find_method_lines(text, class_name="ModelRunner", method_name="apply_torch_tp")
    lines = text.splitlines(keepends=True)
    method = "".join(lines[start:end])
    new_method = (
        method
        .replace(
            "    def apply_torch_tp(self):\n",
            "    @staticmethod\n"
            "    def apply_torch_tp(\n"
            "        *,\n"
            "        model: nn.Module,\n"
            "        device: str,\n"
            "        tp_size: int,\n"
            "    ):\n",
        )
        .replace("self.tp_size", "tp_size")
        .replace("self.device", "device")
        .replace("self.model", "model")
        # Drop the same-file self-import (cycle-breaker for the future move).
        .replace(
            "        from sglang.srt.layers.model_parallel import tensor_parallel\n\n",
            "",
        )
    )
    text = "".join(lines[:start]) + new_method + "".join(lines[end:])

    text = replace_call_site(
        text,
        old="self.apply_torch_tp()",
        new="ModelRunner.apply_torch_tp(model=self.model, device=self.device, tp_size=self.tp_size)",
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
