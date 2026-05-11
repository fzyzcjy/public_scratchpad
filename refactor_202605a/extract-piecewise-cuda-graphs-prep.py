#!/usr/bin/env python3
"""Prep stage for extract-piecewise-cuda-graphs (MECH_COMMIT_SPLIT §"二段式"):

Reshape ``ModelRunner.init_piecewise_cuda_graphs`` to a free-function-ready
form. Add ``@staticmethod`` + rename to ``create_piecewise_cuda_graphs``
(factory naming, dg-mech-rename absorption). Body: ``self.X`` →
``model_runner.X``. Call site becomes class-qualified.
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

ID = "extract-piecewise-cuda-graphs-prep"
SUBJECT = "Prep init_piecewise_cuda_graphs → create_piecewise_cuda_graphs for extraction"
BODY = ""
AREA = "mech_model_runner"
BASE = "tom_refactor_202605a/primary/mech_model_runner/extract-init-device-graphs-move"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


def transform(wt: Path) -> None:
    mr = wt / "python/sglang/srt/model_executor/model_runner.py"
    text = mr.read_text()

    start, end = find_method_lines(
        text, class_name="ModelRunner", method_name="init_piecewise_cuda_graphs"
    )
    lines = text.splitlines(keepends=True)
    method = "".join(lines[start:end])
    method = method.replace(
        "    def init_piecewise_cuda_graphs(self):\n",
        "    @staticmethod\n"
        "    def create_piecewise_cuda_graphs(model_runner: \"ModelRunner\"):\n",
        1,
    )
    # Body: convert the runner write to a local + return-form. The
    # ``attention_layers`` / ``moe_layers`` / ``moe_fusions`` writes stay as
    # side-effects (downstream runner ctors read them off ``model_runner``,
    # per the original method's documented side-effect contract).
    method = method.replace("self.piecewise_cuda_graph_runner = ", "piecewise_cuda_graph_runner = ")
    method = method.replace("self.", "model_runner.")
    # Bare ``self`` (no dot) — passed as ctor arg to graph runner classes.
    method = method.replace("(self)", "(model_runner)")
    # Early bails (bare ``return``) → ``return None``.
    method = method.replace("            return\n", "            return None\n")
    method = method.replace("        return\n", "        return None\n")
    # Final fall-through gets an explicit return.
    method = method.rstrip("\n") + "\n        return piecewise_cuda_graph_runner\n\n"
    text = "".join(lines[:start]) + method + "".join(lines[end:])

    # Caller becomes a writeback ``self.piecewise_cuda_graph_runner = ...``.
    text = replace_call_site(
        text,
        old="self.init_piecewise_cuda_graphs()",
        new=(
            "self.piecewise_cuda_graph_runner = "
            "ModelRunner.create_piecewise_cuda_graphs(self)"
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
