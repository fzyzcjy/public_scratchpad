#!/usr/bin/env python3
"""Move (pure cut/paste): RequestMetricsRecorder methods relocate from TM to target class."""

# /// script
# requires-python = ">=3.10"
# dependencies = ["typer"]
# ///

import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from _helpers import cut_lines, find_method_lines
from _runner import run_pr

ID = "introduce-request-metrics-recorder-move"
SUBJECT = "Hand per-request metrics over to RequestMetricsRecorder"
BODY = """\
Pure physical move per MECH_COMMIT_SPLIT. Cut @staticmethod
collect_metrics + _request_has_grammar from TokenizerManager; paste into
RequestMetricsRecorder (drop @staticmethod, replace
``self: "RequestMetricsRecorder"`` → plain ``self``). Caller prefix
replacement: ``TokenizerManager.collect_metrics(self.request_metrics_recorder, ...)``
→ ``self.request_metrics_recorder.collect_metrics(...)``.
"""
AREA = "mech_tokenizer_manager"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


EXTRA_IMPORTS = '''from sglang.srt.managers.io_struct import (
    BatchStrOutput,
    GenerateReqInput,
)
from sglang.srt.managers.tokenizer_manager_components.request_state import ReqState
'''


def transform(wt: Path) -> None:
    tm = wt / "python/sglang/srt/managers/tokenizer_manager.py"
    rmr = wt / "python/sglang/srt/managers/tokenizer_manager_components/request_metrics_recorder.py"

    # Cut bottom-up.
    s, e = find_method_lines(tm.read_text(), class_name="TokenizerManager", method_name="collect_metrics")
    collect_text = cut_lines(tm, s, e)
    s, e = find_method_lines(tm.read_text(), class_name="TokenizerManager", method_name="_request_has_grammar")
    has_grammar_text = cut_lines(tm, s, e)

    # Strip @staticmethod + restore plain self.
    collect_text = collect_text.replace("    @staticmethod\n", "", 1)
    collect_text = collect_text.replace('self: "RequestMetricsRecorder", ', "")
    has_grammar_text = has_grammar_text.replace("    @staticmethod\n", "", 1)
    has_grammar_text = has_grammar_text.replace('self: "RequestMetricsRecorder", ', "")

    rmr_text = rmr.read_text()
    rmr_text = rmr_text.replace(
        "from dataclasses import dataclass\n",
        "from dataclasses import dataclass\n\n" + EXTRA_IMPORTS,
    )
    rmr.write_text(
        rmr_text.rstrip() + "\n\n" + has_grammar_text.rstrip() + "\n\n" + collect_text.rstrip() + "\n"
    )

    # Caller prefix replacement.
    text = tm.read_text()
    text = text.replace(
        "TokenizerManager.collect_metrics(\n                    self.request_metrics_recorder, ",
        "self.request_metrics_recorder.collect_metrics(\n                    ",
    )
    tm.write_text(text)


if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        area_branch=AREA_BRANCH,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
