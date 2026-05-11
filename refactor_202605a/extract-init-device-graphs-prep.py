#!/usr/bin/env python3
"""Prep stage for extract-init-device-graphs (MECH_COMMIT_SPLIT §"二段式"):

Reshape ``ModelRunner.init_device_graphs`` to a free-function-ready form:
- Add ``@staticmethod`` + rename to ``create_device_graphs`` (factory naming,
  dg-mech-rename absorption).
- Body: ``self.X`` → ``model_runner.X``.
- Three call sites (3 in ModelRunner.initialize + 1 in WeightUpdater) become
  class-qualified ``ModelRunner.create_device_graphs(<runner>)``.
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

ID = "extract-init-device-graphs-prep"
SUBJECT = "Prep init_device_graphs → create_device_graphs for extraction"
BODY = ""
AREA = "mech_model_runner"
BASE = "tom_refactor_202605a/primary/mech_model_runner/extract-update-expert-location-move"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


def transform(wt: Path) -> None:
    mr = wt / "python/sglang/srt/model_executor/model_runner.py"
    wu = wt / "python/sglang/srt/model_executor/weight_updater.py"

    # Reshape: rename + @staticmethod + signature + body subs.
    text = mr.read_text()
    start, end = find_method_lines(text, class_name="ModelRunner", method_name="init_device_graphs")
    lines = text.splitlines(keepends=True)
    method = "".join(lines[start:end])
    method = method.replace(
        "    def init_device_graphs(self):\n",
        "    @staticmethod\n"
        "    def create_device_graphs(model_runner: \"ModelRunner\") -> tuple[object, float]:\n",
        1,
    )
    method = method.replace("self.", "model_runner.")
    text = "".join(lines[:start]) + method + "".join(lines[end:])

    # Three ``self.init_device_graphs()`` call sites in initialize() — all share
    # the same substring; single replace covers all.
    text = replace_call_site(
        text,
        old="self.init_device_graphs()",
        new="ModelRunner.create_device_graphs(self)",
    )
    mr.write_text(text)

    # WeightUpdater recapture-path caller.
    wu_text = wu.read_text()
    wu_text = replace_call_site(
        wu_text,
        old="self._mr.init_device_graphs()",
        new="ModelRunner.create_device_graphs(self._mr)",
    )
    # ``ModelRunner`` not imported in weight_updater.py — add a temp import for
    # the qualified call. ``-move`` drops this and switches to the free fn.
    if "from sglang.srt.model_executor.model_runner import ModelRunner\n" not in wu_text:
        wu_text = wu_text.replace(
            "from sglang.srt.utils import",
            "from sglang.srt.model_executor.model_runner import ModelRunner\n"
            "from sglang.srt.utils import",
            1,
        )
    wu.write_text(wu_text)


if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        area_branch=AREA_BRANCH,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
