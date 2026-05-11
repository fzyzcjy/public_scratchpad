#!/usr/bin/env python3
"""Prep stage for wu-move-from-disk (MECH_COMMIT_SPLIT §"拆 class 场景"):

Reshape ``ModelRunner.update_weights_from_disk`` toward becoming a
``WeightUpdater`` method:

- Signature: ``@staticmethod`` + ``self: WeightUpdater`` first param.
- Body: ``self.X`` → ``self._mr.X`` (WeightUpdater only exposes
  ``tp_rank`` / ``_model_update_group`` at this point, neither in body).
- ``WeightUpdater``: add ``model_runner_ref`` ctor kwarg + ``_mr`` field.
- ``ModelRunner.__init__``: pass ``model_runner_ref=self``.
- Internal caller (inside update_expert_location, same file): class-qualified.
- External callers (tp_worker.py, eagle_worker_v2.py): class-qualified, with
  a local ``import ModelRunner`` on the line above to dodge the
  TYPE_CHECKING-only top-level import.
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

ID = "wu-move-from-disk-prep"
SUBJECT = "Prep update_weights_from_disk for move onto WeightUpdater"
BODY = ""
AREA = "mech_model_runner"
BASE = "tom_refactor_202605a/primary/mech_model_runner/introduce-weight-updater"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


def transform(wt: Path) -> None:
    mr = wt / "python/sglang/srt/model_executor/model_runner.py"
    wu = wt / "python/sglang/srt/model_executor/weight_updater.py"
    tw = wt / "python/sglang/srt/managers/tp_worker.py"
    ew = wt / "python/sglang/srt/speculative/eagle_worker_v2.py"

    # 1) Body rewrite + signature swap inside ModelRunner.
    text = mr.read_text()
    start, end = find_method_lines(text, class_name="ModelRunner", method_name="update_weights_from_disk")
    lines = text.splitlines(keepends=True)
    method = "".join(lines[start:end])
    # Order matters: signature swap first.
    method = method.replace(
        "    def update_weights_from_disk(\n        self,\n",
        "    @staticmethod\n    def update_weights_from_disk(\n        self: \"WeightUpdater\",\n",
    )
    # Blanket self.X → self._mr.X in body. WeightUpdater exposes only
    # tp_rank / _model_update_group at this point; neither appears here.
    method = method.replace("self.", "self._mr.")
    text = "".join(lines[:start]) + method + "".join(lines[end:])
    mr.write_text(text)

    # 2) WeightUpdater ctor: add model_runner_ref + _mr.
    text = wu.read_text()
    text = replace_call_site(
        text,
        old=(
            "    def __init__(self, *, tp_rank: int):\n"
            "        self.tp_rank = tp_rank\n"
            "        self._model_update_group: dict = {}\n"
        ),
        new=(
            "    def __init__(self, *, tp_rank: int, model_runner_ref):\n"
            "        self.tp_rank = tp_rank\n"
            "        self._model_update_group: dict = {}\n"
            "        self._mr = model_runner_ref\n"
        ),
    )
    wu.write_text(text)

    # 3) ModelRunner ctor: pass model_runner_ref=self + rewrite the inline
    # internal caller (still inside ModelRunner — no local import needed).
    text = mr.read_text()
    text = replace_call_site(
        text,
        old="        self.weight_updater = WeightUpdater(tp_rank=self.tp_rank)\n",
        new="        self.weight_updater = WeightUpdater(tp_rank=self.tp_rank, model_runner_ref=self)\n",
    )
    text = replace_call_site(
        text,
        old=(
            "                self.update_weights_from_disk(\n"
            "                    get_global_server_args().model_path,\n"
            "                    get_global_server_args().load_format,\n"
            "                    weight_name_filter=weight_name_filter,\n"
            "                )\n"
        ),
        new=(
            "                ModelRunner.update_weights_from_disk(\n"
            "                    self.weight_updater,\n"
            "                    get_global_server_args().model_path,\n"
            "                    get_global_server_args().load_format,\n"
            "                    weight_name_filter=weight_name_filter,\n"
            "                )\n"
        ),
    )
    mr.write_text(text)

    # 4) External callers: local import + class-qualified call.
    text = tw.read_text()
    text = replace_call_site(
        text,
        old="        success, message = self.model_runner.update_weights_from_disk(\n",
        new=(
            "        from sglang.srt.model_executor.model_runner import ModelRunner\n"
            "\n"
            "        success, message = ModelRunner.update_weights_from_disk(\n"
            "            self.model_runner.weight_updater,\n"
        ),
    )
    tw.write_text(text)

    text = ew.read_text()
    text = replace_call_site(
        text,
        old="        success, message = self._draft_worker.draft_runner.update_weights_from_disk(\n",
        new=(
            "        from sglang.srt.model_executor.model_runner import ModelRunner\n"
            "\n"
            "        success, message = ModelRunner.update_weights_from_disk(\n"
            "            self._draft_worker.draft_runner.weight_updater,\n"
        ),
    )
    ew.write_text(text)


if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        area_branch=AREA_BRANCH,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
