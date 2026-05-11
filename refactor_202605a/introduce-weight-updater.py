#!/usr/bin/env python3
"""Introduce ``WeightUpdater`` owner class and migrate the two
weight-update-group lifecycle methods.

- New file ``python/sglang/srt/model_executor/model_runner_components/weight_updater.py`` with class
  ``WeightUpdater``. Owns the ``_model_update_group: dict`` formerly on
  ModelRunner (Ch1 item 5: lifecycle-cohesive fields move to owner).
- Methods ``init_weights_update_group`` and ``destroy_weights_update_group``
  cut from ModelRunner and pasted (still as instance methods) into
  ``WeightUpdater``. Bodies are byte-identical -- ``self._model_update_group``
  / ``self.tp_rank`` retained as field accesses (these are now WeightUpdater
  fields).
- ModelRunner gains ``self.weight_updater = WeightUpdater(tp_rank=self.tp_rank)``
  in ``__init__`` and the ``self._model_update_group = {}`` initialization is
  removed (the dict lives on WeightUpdater).
- Other ModelRunner methods that still read ``self._model_update_group``
  (``update_weights_from_distributed`` / ``_update_bucketed_weights_from_distributed``
  -- moved out in /26) are updated in place to ``self.weight_updater._model_update_group``
  so the chain stays compilable.
- Caller in ``tp_worker.py`` rewritten to
  ``self.model_runner.weight_updater.init_weights_update_group(...)`` (positional
  args preserved -- WeightUpdater method signature mirrors the old ModelRunner
  signature).

Usage:
    uv run --python 3.12 introduce-weight-updater.py run
    uv run --python 3.12 introduce-weight-updater.py verify
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

ID = "introduce-weight-updater"
SUBJECT = "Introduce WeightUpdater and move weights update group lifecycle methods"
BODY = ""
AREA = "mech_model_runner"
BASE = "tom_refactor_202605a/primary/mech_model_runner/extract-kv-cache-dtype"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


HEADER = '''from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import torch

from sglang.srt.utils import init_custom_process_group
from sglang.srt.utils.network import NetworkAddress

logger = logging.getLogger(__name__)


# Mutable ``_model_update_group`` dict prevents ``frozen=True``; explicit
# Rule-5 exception per the dataclass-defaults sprint-wide rule.
@dataclass(slots=True, kw_only=True)
class WeightUpdater:
    tp_rank: int
    _mr: Any  # ModelRunner — kept untyped to avoid TYPE_CHECKING import here
    _model_update_group: dict = field(default_factory=dict)

'''


def transform(wt: Path) -> None:
    mr = wt / "python/sglang/srt/model_executor/model_runner.py"
    wu = wt / "python/sglang/srt/model_executor/model_runner_components/weight_updater.py"
    tw = wt / "python/sglang/srt/managers/tp_worker.py"

    # Cut bottom-up so earlier line ranges stay valid.
    s, e = find_method_lines(
        mr.read_text(), class_name="ModelRunner", method_name="destroy_weights_update_group"
    )
    destroy_text = cut_lines(mr, s, e)

    s, e = find_method_lines(
        mr.read_text(), class_name="ModelRunner", method_name="init_weights_update_group"
    )
    init_text = cut_lines(mr, s, e)

    # Methods stay indented at 4 spaces (instance methods on WeightUpdater).
    # Bodies reference ``self._model_update_group`` and ``self.tp_rank`` --
    # both fields exist on WeightUpdater, so no rewrite needed.
    wu.write_text(HEADER + init_text + destroy_text.rstrip() + "\n")

    # ModelRunner: remove the moved field, instantiate WeightUpdater, fix the
    # remaining ``self._model_update_group`` references in methods that have
    # not been moved yet (they're moved in /26).
    text = mr.read_text()
    text = insert_after(
        text,
        anchor="from sglang.srt.model_executor.cpu_graph_runner import CPUGraphRunner\n",
        addition="from sglang.srt.model_executor.model_runner_components.weight_updater import WeightUpdater\n",
    )
    text = replace_call_site(
        text,
        old=(
            "        # For weight updates\n"
            "        self._model_update_group = {}\n"
            "        self._weights_send_group = {}\n"
        ),
        new=(
            "        # For weight updates\n"
            "        self.weight_updater = WeightUpdater(tp_rank=self.tp_rank, _mr=self)\n"
            "        self._weights_send_group = {}\n"
        ),
    )
    # Methods staying on ModelRunner that still read the moved dict.
    text = text.replace(
        "self._model_update_group", "self.weight_updater._model_update_group"
    )
    mr.write_text(text)

    # tp_worker.py: rewrite both call sites to go through weight_updater.
    text = tw.read_text()
    text = replace_call_site(
        text,
        old="        success, message = self.model_runner.init_weights_update_group(\n",
        new="        success, message = self.model_runner.weight_updater.init_weights_update_group(\n",
    )
    text = replace_call_site(
        text,
        old="        success, message = self.model_runner.destroy_weights_update_group(\n",
        new="        success, message = self.model_runner.weight_updater.destroy_weights_update_group(\n",
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
