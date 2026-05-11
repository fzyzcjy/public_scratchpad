#!/usr/bin/env python3
"""Prep stage for wu-move-from-distributed (MECH_COMMIT_SPLIT §"拆 class 场景"):

Reshape ``update_weights_from_distributed`` + its private helper
``_update_bucketed_weights_from_distributed`` toward becoming
``WeightUpdater`` methods. Body subs follow the original mech script:
- ``self.weight_updater._model_update_group`` → ``self._model_update_group``
  (the dict is already a WeightUpdater field — pre-existing forward-ref
  that introduce-weight-updater stubbed)
- ``self.model.load_weights`` → ``self._mr.model.load_weights``
- ``self.device`` → ``self._mr.device``

The inner call ``self._update_bucketed_weights_from_distributed(...)`` becomes
class-qualified ``ModelRunner._update_bucketed_weights_from_distributed(self, ...)``
since both methods are still ``@staticmethod`` on ModelRunner at prep stage.

External caller in tp_worker.py: local import + class-qualified call.
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

ID = "wu-move-from-distributed-prep"
SUBJECT = "Prep update_weights_from_distributed for move onto WeightUpdater"
BODY = ""
AREA = "mech_model_runner"
BASE = "tom_refactor_202605a/primary/mech_model_runner/wu-move-from-disk-move"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


def _reshape(text: str, *, method_name: str) -> str:
    start, end = find_method_lines(text, class_name="ModelRunner", method_name=method_name)
    lines = text.splitlines(keepends=True)
    method = "".join(lines[start:end])
    # Two possible signatures: ``def name(\n        self,\n`` (one-arg-per-line)
    # or ``def name(\n        self, names, dtypes, ...`` (all on one line).
    if f"    def {method_name}(\n        self,\n" in method:
        method = method.replace(
            f"    def {method_name}(\n        self,\n",
            f"    @staticmethod\n    def {method_name}(\n        self: \"WeightUpdater\",\n",
            1,
        )
    else:
        method = method.replace(
            f"    def {method_name}(\n        self, ",
            f"    @staticmethod\n    def {method_name}(\n        self: \"WeightUpdater\", ",
            1,
        )
    # Body subs — order: longest-prefix-first so substring replacements
    # don't half-rewrite the longer one.
    method = method.replace(
        "self.weight_updater._model_update_group", "self._model_update_group"
    )
    method = method.replace("self.model.load_weights", "self._mr.model.load_weights")
    method = method.replace("self.device", "self._mr.device")
    return "".join(lines[:start]) + method + "".join(lines[end:])


def transform(wt: Path) -> None:
    mr = wt / "python/sglang/srt/model_executor/model_runner.py"
    tw = wt / "python/sglang/srt/managers/tp_worker.py"

    text = mr.read_text()
    text = _reshape(text, method_name="_update_bucketed_weights_from_distributed")
    text = _reshape(text, method_name="update_weights_from_distributed")
    # Internal cross-method call inside update_weights_from_distributed.
    text = replace_call_site(
        text,
        old="self._update_bucketed_weights_from_distributed(",
        new="ModelRunner._update_bucketed_weights_from_distributed(self, ",
    )
    mr.write_text(text)

    text = tw.read_text()
    text = replace_call_site(
        text,
        old="        success, message = self.model_runner.update_weights_from_distributed(\n",
        new=(
            "        from sglang.srt.model_executor.model_runner import ModelRunner\n"
            "\n"
            "        success, message = ModelRunner.update_weights_from_distributed(\n"
            "            self.model_runner.weight_updater,\n"
        ),
    )
    tw.write_text(text)


if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        area_branch=AREA_BRANCH,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
