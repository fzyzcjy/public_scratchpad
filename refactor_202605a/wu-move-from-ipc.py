#!/usr/bin/env python3
"""Move ``update_weights_from_ipc`` onto ``WeightUpdater``.

- Method cut from ModelRunner and pasted (still as instance method) onto
  WeightUpdater. The body's
  ``SGLangCheckpointEngineWorkerExtensionImpl(self)`` is rewritten to
  ``SGLangCheckpointEngineWorkerExtensionImpl(self._mr)`` (the extension
  expects a ``ModelRunner`` reference).
- Method deleted from ModelRunner.
- ``tp_worker.py`` caller rewritten to
  ``self.model_runner.weight_updater.update_weights_from_ipc(recv_req)``.

Usage:
    uv run --python 3.12 wu-move-from-ipc.py run
    uv run --python 3.12 wu-move-from-ipc.py verify
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
    replace_call_site,
)
from _runner import run_pr

ID = "wu-move-from-ipc"
SUBJECT = "Move update_weights_from_ipc onto WeightUpdater"
BODY = ""
AREA = "mech_model_runner"
BASE = "tom_refactor_202605a/raw/mech_model_runner/wu-move-from-tensor"
TARGET = f"tom_refactor_202605a/raw/{AREA}/{ID}"


def transform(wt: Path) -> None:
    mr = wt / "python/sglang/srt/model_executor/model_runner.py"
    wu = wt / "python/sglang/srt/model_executor/weight_updater.py"
    tw = wt / "python/sglang/srt/managers/tp_worker.py"
    ew = wt / "python/sglang/srt/speculative/eagle_worker_v2.py"

    s, e = find_method_lines(
        mr.read_text(),
        class_name="ModelRunner",
        method_name="update_weights_from_ipc",
    )
    method_text = cut_lines(mr, s, e).replace(
        "SGLangCheckpointEngineWorkerExtensionImpl(self)",
        "SGLangCheckpointEngineWorkerExtensionImpl(self._mr)",
    )

    # Splice the new method into ``WeightUpdater``: insert immediately before
    # the module-level helpers section (sentinel = the trailing
    # ``def _model_load_weights_direct(...)`` block added in /27).
    text = wu.read_text()
    sentinel = "\ndef _model_load_weights_direct("
    if sentinel not in text:
        raise RuntimeError(
            "Expected ``_model_load_weights_direct`` in weight_updater.py "
            "(added in /27). Has the chain run?"
        )
    text = text.replace(
        sentinel,
        "\n" + method_text.rstrip() + "\n\n" + sentinel,
        1,
    )
    wu.write_text(text)

    # tp_worker.py: rewrite caller.
    text = tw.read_text()
    text = replace_call_site(
        text,
        old="        success, message = self.model_runner.update_weights_from_ipc(recv_req)\n",
        new="        success, message = self.model_runner.weight_updater.update_weights_from_ipc(recv_req)\n",
    )
    tw.write_text(text)

    # eagle_worker_v2.py: rewrite caller.
    text = ew.read_text()
    text = replace_call_site(
        text,
        old="        success, message = self._draft_worker.draft_runner.update_weights_from_ipc(\n",
        new="        success, message = self._draft_worker.draft_runner.weight_updater.update_weights_from_ipc(\n",
    )
    ew.write_text(text)

if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        target=TARGET,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
