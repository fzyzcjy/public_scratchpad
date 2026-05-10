#!/usr/bin/env python3
"""Introduce ``WeightExporter`` owner class and migrate the two
weights-send-group methods.

- New file ``python/sglang/srt/model_executor/weight_exporter.py`` with class
  ``WeightExporter``. Owns the ``_weights_send_group: dict`` formerly on
  ModelRunner (Ch1 item 5: lifecycle-cohesive fields move to owner).
- Methods ``init_weights_send_group_for_remote_instance`` and
  ``send_weights_to_remote_instance`` cut from ModelRunner and pasted (still
  as instance methods) into ``WeightExporter``. Bodies rewrite
  ``self.model.named_parameters`` -> ``self._mr.model.named_parameters``;
  ``self.tp_rank`` / ``self.tp_size`` / ``self.gpu_id`` /
  ``self._weights_send_group`` stay as is (all WeightExporter fields).
- ModelRunner gains ``self.weight_exporter = WeightExporter(...)`` in
  ``__init__`` and the ``self._weights_send_group = {}`` initialization is
  removed (the dict lives on WeightExporter).
- Caller in ``tp_worker.py`` rewritten to
  ``self.model_runner.weight_exporter.<method>(...)`` (positional args
  preserved -- WeightExporter method signatures mirror the old ModelRunner
  signatures).

Usage:
    uv run --python 3.12 tom_refactor_29.py run
    uv run --python 3.12 tom_refactor_29.py verify
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
    cut_lines,
    find_method_lines,
    insert_after,
    replace_call_site,
)
from _runner import run_pr

BASE = "tom_refactor/28"
TARGET = "tom_refactor/29"


HEADER = '''from __future__ import annotations

import logging

import torch
import torch.distributed as dist

from sglang.srt.utils import init_custom_process_group
from sglang.srt.utils.network import NetworkAddress

logger = logging.getLogger(__name__)


class WeightExporter:

    def __init__(
        self,
        *,
        tp_rank: int,
        tp_size: int,
        gpu_id: int,
        model_runner_ref,
    ):
        self.tp_rank = tp_rank
        self.tp_size = tp_size
        self.gpu_id = gpu_id
        self._weights_send_group: dict = {}
        self._mr = model_runner_ref

'''


def transform(wt: Path) -> None:
    sys.path.insert(0, str(wt / ".claude/skills/mechanical-refactor-verify"))
    from mechanical_refactor_verify_utils import git_add_and_commit

    mr = wt / "python/sglang/srt/model_executor/model_runner.py"
    we = wt / "python/sglang/srt/model_executor/weight_exporter.py"
    tw = wt / "python/sglang/srt/managers/tp_worker.py"

    # Cut bottom-up so earlier line ranges stay valid.
    s, e = find_method_lines(
        mr.read_text(),
        class_name="ModelRunner",
        method_name="send_weights_to_remote_instance",
    )
    send_text = cut_lines(mr, s, e).replace(
        "self.model.named_parameters", "self._mr.model.named_parameters"
    )

    s, e = find_method_lines(
        mr.read_text(),
        class_name="ModelRunner",
        method_name="init_weights_send_group_for_remote_instance",
    )
    # Body has no ModelRunner-only field references that need rewriting --
    # ``self.tp_rank`` / ``self.tp_size`` / ``self.gpu_id`` /
    # ``self._weights_send_group`` are all WeightExporter fields.
    init_text = cut_lines(mr, s, e)

    we.write_text(HEADER + init_text + "\n" + send_text.rstrip() + "\n")

    # ModelRunner: instantiate WeightExporter; remove the moved field.
    text = mr.read_text()
    text = insert_after(
        text,
        anchor="from sglang.srt.model_executor.weight_updater import WeightUpdater\n",
        addition="from sglang.srt.model_executor.weight_exporter import WeightExporter\n",
    )
    text = replace_call_site(
        text,
        old=(
            "        self.weight_updater = WeightUpdater(tp_rank=self.tp_rank, model_runner_ref=self)\n"
            "        self._weights_send_group = {}\n"
        ),
        new=(
            "        self.weight_updater = WeightUpdater(tp_rank=self.tp_rank, model_runner_ref=self)\n"
            "        self.weight_exporter = WeightExporter(\n"
            "            tp_rank=self.tp_rank,\n"
            "            tp_size=self.tp_size,\n"
            "            gpu_id=self.gpu_id,\n"
            "            model_runner_ref=self,\n"
            "        )\n"
        ),
    )
    mr.write_text(text)

    # tp_worker.py: rewrite both call sites.
    text = tw.read_text()
    text = replace_call_site(
        text,
        old=(
            "        success, message = (\n"
            "            self.model_runner.init_weights_send_group_for_remote_instance(\n"
        ),
        new=(
            "        success, message = (\n"
            "            self.model_runner.weight_exporter.init_weights_send_group_for_remote_instance(\n"
        ),
    )
    text = replace_call_site(
        text,
        old="        success, message = self.model_runner.send_weights_to_remote_instance(\n",
        new="        success, message = self.model_runner.weight_exporter.send_weights_to_remote_instance(\n",
    )
    tw.write_text(text)

    git_add_and_commit(
        "Introduce WeightExporter and move weights send group methods",
        cwd=str(wt),
    )


if __name__ == "__main__":
    run_pr(transform=transform, base=BASE, target=TARGET)
