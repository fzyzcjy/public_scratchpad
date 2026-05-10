#!/usr/bin/env python3
"""Move ``save_remote_model`` / ``save_sharded_model`` /
``get_weights_by_name`` onto ``WeightExporter``.

- All three methods cut from ModelRunner and pasted (still as instance
  methods) onto WeightExporter. Bodies rewrite ``self.model`` ->
  ``self._mr.model`` and ``self.model_config`` -> ``self._mr.model_config``;
  ``self.tp_size`` stays as is (WeightExporter field).
- ``Optional`` import added to ``weight_exporter.py`` for the new method
  signatures.
- ``tp_worker.py`` and ``scheduler_update_weights_mixin.py`` callers updated
  to go through ``...weight_exporter.<method>(...)``.

Usage:
    uv run --python 3.12 we-move-save-get.py run
    uv run --python 3.12 we-move-save-get.py verify
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

ID = "we-move-save-get"
SUBJECT = "Move weight save and get_weights_by_name methods onto WeightExporter"
BODY = ""
AREA = "mech_model_runner"
BASE = "tom_refactor_202605a/primary/mech_model_runner/introduce-weight-exporter"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


def transform(wt: Path) -> None:
    mr = wt / "python/sglang/srt/model_executor/model_runner.py"
    we = wt / "python/sglang/srt/model_executor/weight_exporter.py"
    tw = wt / "python/sglang/srt/managers/tp_worker.py"
    sm = wt / "python/sglang/srt/managers/scheduler_update_weights_mixin.py"

    # Cut bottom-up so earlier line ranges stay valid. ``self.model`` is the
    # only ModelRunner-side prefix appearing in these three bodies (it covers
    # both ``self.model`` and ``self.model_config``); ``self.tp_size`` stays
    # because WeightExporter owns it.
    s, e = find_method_lines(
        mr.read_text(), class_name="ModelRunner", method_name="save_sharded_model"
    )
    sharded_text = cut_lines(mr, s, e).replace("self.model", "self._mr.model")

    s, e = find_method_lines(
        mr.read_text(), class_name="ModelRunner", method_name="save_remote_model"
    )
    remote_text = cut_lines(mr, s, e).replace("self.model", "self._mr.model")

    s, e = find_method_lines(
        mr.read_text(), class_name="ModelRunner", method_name="get_weights_by_name"
    )
    gwbn_text = cut_lines(mr, s, e).replace("self.model", "self._mr.model")

    # weight_exporter.py: add ``Optional`` import for the new signatures.
    text = we.read_text()
    if "from typing import Optional\n" not in text:
        text = insert_after(
            text,
            anchor="import logging\n",
            addition="from typing import Optional\n",
        )
        we.write_text(text)

    append_to_file(
        we,
        remote_text.rstrip() + "\n\n" + sharded_text.rstrip() + "\n\n" + gwbn_text.rstrip() + "\n",
        separator="\n",
    )

    # tp_worker.py: rewrite caller for ``get_weights_by_name``.
    text = tw.read_text()
    text = replace_call_site(
        text,
        old="        parameter = self.model_runner.get_weights_by_name(\n",
        new="        parameter = self.model_runner.weight_exporter.get_weights_by_name(\n",
    )
    tw.write_text(text)

    # scheduler_update_weights_mixin.py: rewrite ``save_remote_model`` /
    # ``save_sharded_model`` callers.
    text = sm.read_text()
    text = replace_call_site(
        text,
        old="        self.tp_worker.model_runner.save_remote_model(url)\n",
        new="        self.tp_worker.model_runner.weight_exporter.save_remote_model(url)\n",
    )
    text = replace_call_site(
        text,
        old="            self.draft_worker.model_runner.save_remote_model(draft_url)\n",
        new="            self.draft_worker.model_runner.weight_exporter.save_remote_model(draft_url)\n",
    )
    text = replace_call_site(
        text,
        old="        self.tp_worker.model_runner.save_sharded_model(\n",
        new="        self.tp_worker.model_runner.weight_exporter.save_sharded_model(\n",
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
