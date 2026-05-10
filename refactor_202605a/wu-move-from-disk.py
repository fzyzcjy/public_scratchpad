#!/usr/bin/env python3
"""Move ``update_weights_from_disk`` onto ``WeightUpdater``.

- WeightUpdater ctor gains a ``model_runner_ref`` kwarg (R4 concession). The
  back-reference (``self._mr``) is needed because the method body reads many
  ModelRunner fields (``model``, ``server_args``, ``model_config``, ``device``,
  ``gpu_id``, ``load_config``) and calls ``init_device_graphs()``.
- Method moves byte-identical except ``self.X`` -> ``self._mr.X`` for every
  field that lives on ModelRunner.
- ModelRunner: ctor now passes ``model_runner_ref=self`` to WeightUpdater;
  ``update_weights_from_disk`` is deleted from the class.
- Inline call inside ``update_expert_location`` (still on ModelRunner) is
  rewritten to ``self.weight_updater.update_weights_from_disk(...)``.
- ``tp_worker.py`` and ``eagle_worker_v2.py`` callers now go through
  ``self.model_runner.weight_updater.update_weights_from_disk(...)`` /
  ``self._draft_worker.draft_runner.weight_updater.update_weights_from_disk(...)``.

Usage:
    uv run --python 3.12 wu-move-from-disk.py run
    uv run --python 3.12 wu-move-from-disk.py verify
"""

# /// script
# requires-python = ">=3.10"
# dependencies = ["typer"]
# ///

import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from _helpers import (
    append_to_file,
    cut_lines,
    find_method_lines,
    insert_after,
    replace_call_site,
)
from _runner import run_pr

ID = "wu-move-from-disk"
SUBJECT = "Move update_weights_from_disk onto WeightUpdater"
BODY = ""
AREA = "mech_model_runner"
BASE = "tom_refactor_202605a/raw/mech_model_runner/introduce-weight-updater"
AREA_BRANCH = f"tom_refactor_202605a/raw/{AREA}"


def transform(wt: Path) -> None:
    mr = wt / "python/sglang/srt/model_executor/model_runner.py"
    wu = wt / "python/sglang/srt/model_executor/weight_updater.py"
    tw = wt / "python/sglang/srt/managers/tp_worker.py"
    ew = wt / "python/sglang/srt/speculative/eagle_worker_v2.py"

    # Cut update_weights_from_disk from ModelRunner.
    s, e = find_method_lines(
        mr.read_text(), class_name="ModelRunner", method_name="update_weights_from_disk"
    )
    method_text = cut_lines(mr, s, e)

    # Rewrite ``self.<fields-on-ModelRunner>`` -> ``self._mr.<...>``. The
    # fields read by this body (model, model_config, device, gpu_id,
    # server_args, load_config) and the method call (init_device_graphs)
    # all live on ModelRunner, so a blanket s/self./self._mr./ is safe --
    # WeightUpdater itself currently exposes only ``tp_rank`` /
    # ``_model_update_group``, neither of which appears in this body.
    method_text = method_text.replace("self.", "self._mr.")

    # Append the method to the WeightUpdater class. ``cut_lines`` preserved
    # the 4-space indentation, so it slots into the class body verbatim.
    append_to_file(wu, method_text.rstrip() + "\n", separator="\n")

    # Update WeightUpdater ctor: add ``model_runner_ref`` kwarg + ``_mr`` field.
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
    # Imports needed by the new method body.
    text = insert_after(
        text,
        anchor="import logging\n",
        addition=(
            "import gc\n"
            "from typing import Callable, Optional\n"
        ),
    )
    text = insert_after(
        text,
        anchor="from sglang.srt.utils import init_custom_process_group\n",
        addition=(
            "from sglang.srt.configs.load_config import LoadConfig\n"
            "from sglang.srt.model_loader.loader import DefaultModelLoader, get_model_loader\n"
            "from sglang.srt.model_loader.utils import set_default_torch_dtype\n"
            "from sglang.srt.platforms import current_platform\n"
            "from sglang.srt.utils import get_available_gpu_memory\n"
        ),
    )
    wu.write_text(text)

    # ModelRunner: pass ``model_runner_ref=self`` to WeightUpdater ctor;
    # rewrite the inline call inside ``update_expert_location``.
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
            "                self.weight_updater.update_weights_from_disk(\n"
            "                    get_global_server_args().model_path,\n"
            "                    get_global_server_args().load_format,\n"
            "                    weight_name_filter=weight_name_filter,\n"
            "                )\n"
        ),
    )
    mr.write_text(text)

    # tp_worker.py: rewrite caller (positional args preserved).
    text = tw.read_text()
    text = replace_call_site(
        text,
        old="        success, message = self.model_runner.update_weights_from_disk(\n",
        new="        success, message = self.model_runner.weight_updater.update_weights_from_disk(\n",
    )
    tw.write_text(text)

    # eagle_worker_v2.py: rewrite caller.
    text = ew.read_text()
    text = replace_call_site(
        text,
        old="        success, message = self._draft_worker.draft_runner.update_weights_from_disk(\n",
        new="        success, message = self._draft_worker.draft_runner.weight_updater.update_weights_from_disk(\n",
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
