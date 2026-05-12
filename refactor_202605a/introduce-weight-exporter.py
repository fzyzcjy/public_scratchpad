#!/usr/bin/env python3
"""Introduce ``WeightExporter`` owner class and migrate the two
weights-send-group methods.

- New file ``python/sglang/srt/model_executor/model_runner_components/weight_exporter.py`` with class
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
    uv run --python 3.12 introduce-weight-exporter.py run
    uv run --python 3.12 introduce-weight-exporter.py verify
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

ID = "introduce-weight-exporter"
SUBJECT = "Introduce WeightExporter and move weights send group methods"
BODY = ""
AREA = "mech_model_runner"
BASE = "tom_refactor_202605a/primary/mech_model_runner/wu-move-from-ipc"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


HEADER = '''from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import torch
import torch.distributed as dist

from sglang.srt.utils import init_custom_process_group
from sglang.srt.utils.network import NetworkAddress

logger = logging.getLogger(__name__)


# Mutable ``_weights_send_group`` dict prevents ``frozen=True``; explicit
# Rule-5 exception per the dataclass-defaults sprint-wide rule.
# tp_rank / tp_size / gpu_id read via ``self._mr`` (consistent with
# WeightUpdater) — no redundant storage.
@dataclass(slots=True, kw_only=True)
class WeightExporter:
    _mr: Any  # ModelRunner — kept untyped to avoid TYPE_CHECKING import here
    _weights_send_group: dict = field(default_factory=dict)

'''


def transform(wt: Path) -> None:
    mr = wt / "python/sglang/srt/model_executor/model_runner.py"
    we = wt / "python/sglang/srt/model_executor/model_runner_components/weight_exporter.py"
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
    init_text = cut_lines(mr, s, e)

    # Route ``tp_rank`` / ``tp_size`` / ``gpu_id`` through ``self._mr`` --
    # WeightExporter no longer stores them locally (mirror of WeightUpdater).
    for body_field in ("tp_rank", "tp_size", "gpu_id"):
        init_text = init_text.replace(f"self.{body_field}", f"self._mr.{body_field}")
        send_text = send_text.replace(f"self.{body_field}", f"self._mr.{body_field}")

    we.write_text(HEADER + init_text + "\n" + send_text.rstrip() + "\n")

    # ModelRunner: instantiate WeightExporter; remove the moved field.
    text = mr.read_text()
    text = insert_after(
        text,
        anchor=(
            "from sglang.srt.model_executor.model_runner_components.weight_updater import (\n"
            "    WeightUpdater,\n"
            ")\n"
        ),
        addition="from sglang.srt.model_executor.model_runner_components.weight_exporter import WeightExporter\n",
    )
    # Per MECH_COMMIT_SPLIT "长 ctor → init_X" rule, the multi-line ctor
    # lives in its own helper method.
    text = replace_call_site(
        text,
        old=(
            "        self.weight_updater = WeightUpdater(tp_rank=self.tp_rank, _mr=self)\n"
            "        self._weights_send_group = {}\n"
        ),
        new=(
            "        self.weight_updater = WeightUpdater(tp_rank=self.tp_rank, _mr=self)\n"
            "        self.init_weight_exporter()\n"
        ),
    )
    helper_method = (
        "    def init_weight_exporter(self):\n"
        "        self.weight_exporter = WeightExporter(_mr=self)\n"
        "\n"
    )
    text = text.replace(
        "    def init_msprobe(",
        helper_method + "    def init_msprobe(",
        1,
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

if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        area_branch=AREA_BRANCH,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
