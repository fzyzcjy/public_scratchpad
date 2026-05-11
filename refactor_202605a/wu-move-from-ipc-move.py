#!/usr/bin/env python3
"""Move stage for wu-move-from-ipc (MECH_COMMIT_SPLIT §"拆 class 场景"):

Cut prep'd staticmethod onto WeightUpdater (before the module-level helpers
section). Body byte-equivalent. Drop local imports + collapse external callers.
"""

# /// script
# requires-python = ">=3.10"
# dependencies = ["typer"]
# ///

import re
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

ID = "wu-move-from-ipc-move"
SUBJECT = "Move update_weights_from_ipc onto WeightUpdater (cut+paste)"
BODY = ""
AREA = "mech_model_runner"
BASE = "tom_refactor_202605a/primary/mech_model_runner/wu-move-from-ipc-prep"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


def transform(wt: Path) -> None:
    mr = wt / "python/sglang/srt/model_executor/model_runner.py"
    wu = wt / "python/sglang/srt/model_executor/weight_updater.py"
    tw = wt / "python/sglang/srt/managers/tp_worker.py"
    ew = wt / "python/sglang/srt/speculative/eagle_worker_v2.py"

    s, e = find_method_lines(mr.read_text(), class_name="ModelRunner", method_name="update_weights_from_ipc")
    method_text = cut_lines(mr, s, e)
    lines = method_text.splitlines(keepends=True)
    assert lines[0].strip() == "@staticmethod"
    method_text = "".join(lines[1:])
    method_text = method_text.replace('        self: "WeightUpdater",\n', "        self,\n")
    method_text = method_text.replace('(self: "WeightUpdater", ', "(self, ")

    # Splice before sentinel _model_load_weights_direct (module-level helper
    # from wu-move-from-tensor). Keep method inside the class.
    text = wu.read_text()
    sentinel = "\ndef _model_load_weights_direct("
    if sentinel not in text:
        raise RuntimeError("Sentinel missing — has wu-move-from-tensor run?")
    text = text.replace(sentinel, "\n" + method_text.rstrip() + "\n\n" + sentinel, 1)
    wu.write_text(text)

    # Lenient regex tolerates pre-commit line joins/splits.
    for path in (tw, ew):
        text = path.read_text()
        text = re.sub(
            r"^[ \t]*from sglang\.srt\.model_executor\.model_runner import ModelRunner\n\n",
            "",
            text,
            flags=re.MULTILINE,
        )
        path.write_text(text)

    text = tw.read_text()
    text = re.sub(
        r"ModelRunner\.update_weights_from_ipc\(\s*self\.model_runner\.weight_updater,\s*recv_req\s*\)",
        "self.model_runner.weight_updater.update_weights_from_ipc(recv_req)",
        text,
    )
    tw.write_text(text)

    text = ew.read_text()
    text = re.sub(
        r"ModelRunner\.update_weights_from_ipc\(\s*self\._draft_worker\.draft_runner\.weight_updater,\s*",
        "self._draft_worker.draft_runner.weight_updater.update_weights_from_ipc(",
        text,
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
