#!/usr/bin/env python3
"""Prep stage for we-move-save-get (MECH_COMMIT_SPLIT §"拆 class 场景"):

Reshape 3 ModelRunner methods toward becoming ``WeightExporter`` methods:
``save_remote_model``, ``save_sharded_model``, ``get_weights_by_name``. Each
becomes ``@staticmethod`` with ``self: WeightExporter`` first param; body
``self.model`` → ``self._mr.model``.

External call sites in ``tp_worker.py`` / ``scheduler_update_weights_mixin.py``
switch to class-qualified ``ModelRunner.<method>(<we>, ...)``. Those files
have ``ModelRunner`` only under ``TYPE_CHECKING`` (the codebase avoids a
``model_runner.py`` ↔ caller top-level cycle), so the qualified form is
unbound at runtime. Fix: a **local** import on the line above each callsite —
the import is lazy, both modules are fully loaded when the function actually
runs, no cycle. The ``-move`` commit drops both the qualifier and the local
import.
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

ID = "we-move-save-get-prep"
SUBJECT = "Prep weight save / get_weights_by_name for move onto WeightExporter"
BODY = ""
AREA = "mech_model_runner"
BASE = "tom_refactor_202605a/primary/mech_model_runner/introduce-weight-exporter"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


_METHOD_NAMES = ("save_remote_model", "save_sharded_model", "get_weights_by_name")


def _reshape_one(text: str, *, method_name: str) -> str:
    start, end = find_method_lines(text, class_name="ModelRunner", method_name=method_name)
    lines = text.splitlines(keepends=True)
    method = "".join(lines[start:end])
    if f"    def {method_name}(self, " in method:
        method = method.replace(
            f"    def {method_name}(self, ",
            f"    @staticmethod\n    def {method_name}(self: \"WeightExporter\", ",
            1,
        )
    else:
        method = method.replace(
            f"    def {method_name}(\n        self, ",
            f"    @staticmethod\n    def {method_name}(\n        self: \"WeightExporter\", ",
            1,
        )
    method = method.replace("self.model", "self._mr.model")
    return "".join(lines[:start]) + method + "".join(lines[end:])


def transform(wt: Path) -> None:
    mr = wt / "python/sglang/srt/model_executor/model_runner.py"
    tw = wt / "python/sglang/srt/managers/tp_worker.py"
    sm = wt / "python/sglang/srt/managers/scheduler_update_weights_mixin.py"

    # Reshape the 3 methods (still in ModelRunner). WeightExporter already
    # has ``_mr`` (and other fields) from ``introduce-weight-exporter``.
    text = mr.read_text()
    for name in _METHOD_NAMES:
        text = _reshape_one(text, method_name=name)
    mr.write_text(text)

    # tp_worker.py: local import + qualified call.
    text = tw.read_text()
    text = replace_call_site(
        text,
        old="        parameter = self.model_runner.get_weights_by_name(\n",
        new=(
            "        from sglang.srt.model_executor.model_runner import ModelRunner\n"
            "\n"
            "        parameter = ModelRunner.get_weights_by_name(\n"
            "            self.model_runner.weight_exporter,\n"
        ),
    )
    tw.write_text(text)

    # scheduler_update_weights_mixin.py: 3 callers, each with its own local import.
    text = sm.read_text()
    text = replace_call_site(
        text,
        old="        self.tp_worker.model_runner.save_remote_model(url)\n",
        new=(
            "        from sglang.srt.model_executor.model_runner import ModelRunner\n"
            "\n"
            "        ModelRunner.save_remote_model(\n"
            "            self.tp_worker.model_runner.weight_exporter, url\n"
            "        )\n"
        ),
    )
    text = replace_call_site(
        text,
        old="            self.draft_worker.model_runner.save_remote_model(draft_url)\n",
        new=(
            "            from sglang.srt.model_executor.model_runner import ModelRunner\n"
            "\n"
            "            ModelRunner.save_remote_model(\n"
            "                self.draft_worker.model_runner.weight_exporter, draft_url\n"
            "            )\n"
        ),
    )
    text = replace_call_site(
        text,
        old="        self.tp_worker.model_runner.save_sharded_model(\n",
        new=(
            "        from sglang.srt.model_executor.model_runner import ModelRunner\n"
            "\n"
            "        ModelRunner.save_sharded_model(\n"
            "            self.tp_worker.model_runner.weight_exporter,\n"
        ),
    )
    sm.write_text(text)


if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        area_branch=AREA_BRANCH,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
