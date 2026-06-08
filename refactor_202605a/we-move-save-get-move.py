#!/usr/bin/env python3
"""Move stage for we-move-save-get (MECH_COMMIT_SPLIT §"split-class scenario"):

Pure cut+paste onto ``WeightExporter``. Bodies byte-equivalent. Call sites
collapse qualified form back to instance-method form; the local
``import ModelRunner`` lines introduced in prep are dropped.
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
    append_to_file,
    cut_lines,
    find_method_lines,
    insert_after,
    replace_call_site,
)
from _runner import run_pr

ID = "we-move-save-get-move"
SUBJECT = "Move weight save / get_weights_by_name onto WeightExporter (cut+paste)"
BODY = ""
AREA = "mech_model_runner"
BASE = "tom_refactor_202605a/primary/mech_model_runner/we-move-save-get-prep"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


_METHOD_NAMES = ("save_remote_model", "save_sharded_model", "get_weights_by_name")


def transform(wt: Path) -> None:
    mr = wt / "python/sglang/srt/model_executor/model_runner.py"
    we = wt / "python/sglang/srt/model_executor/model_runner_components/weight_exporter.py"
    tw = wt / "python/sglang/srt/managers/tp_worker.py"
    sm = wt / "python/sglang/srt/managers/scheduler_update_weights_mixin.py"

    # Add Optional import for the signatures.
    text = we.read_text()
    if "from typing import Optional\n" not in text:
        text = insert_after(
            text,
            anchor="import logging\n",
            addition="from typing import Optional\n",
        )
        we.write_text(text)

    # Cut all three methods, paste onto WeightExporter (still 4-space indent).
    cut_methods = []
    for name in _METHOD_NAMES:
        s, e = find_method_lines(mr.read_text(), class_name="ModelRunner", method_name=name)
        method_text = cut_lines(mr, s, e)
        lines = method_text.splitlines(keepends=True)
        assert lines[0].strip() == "@staticmethod"
        body = "".join(lines[1:])
        # Normalize the typed-self back to plain self (both single- and multi-line forms).
        body = body.replace(f'    def {name}(self: "WeightExporter", ', f'    def {name}(self, ')
        body = body.replace('        self: "WeightExporter",', '        self,')
        cut_methods.append(body)

    append_to_file(we, "\n\n".join(m.rstrip() for m in cut_methods) + "\n", separator="\n")

    # Collapse the paired ``local_import + qualified_call`` blocks back to
    # bare instance calls. Pre-commit may wrap; tolerate whitespace. The
    # paired form precludes accidentally stripping other unrelated local
    # ``ModelRunner`` imports in the same file.
    text = tw.read_text()
    text = re.sub(
        r"[ \t]*from sglang\.srt\.model_executor\.model_runner import ModelRunner\n\n"
        r"([ \t]*)parameter = ModelRunner\.get_weights_by_name\(\s*self\.model_runner\.weight_exporter,\s*",
        r"\1parameter = self.model_runner.weight_exporter.get_weights_by_name(",
        text,
    )
    tw.write_text(text)

    text = sm.read_text()
    text = re.sub(
        r"[ \t]*from sglang\.srt\.model_executor\.model_runner import ModelRunner\n\n"
        r"([ \t]*)ModelRunner\.save_remote_model\(\s*self\.tp_worker\.model_runner\.weight_exporter,\s*url\s*\)",
        r"\1self.tp_worker.model_runner.weight_exporter.save_remote_model(url)",
        text,
    )
    text = re.sub(
        r"[ \t]*from sglang\.srt\.model_executor\.model_runner import ModelRunner\n\n"
        r"([ \t]*)ModelRunner\.save_remote_model\(\s*self\.draft_worker\.model_runner\.weight_exporter,\s*draft_url\s*\)",
        r"\1self.draft_worker.model_runner.weight_exporter.save_remote_model(draft_url)",
        text,
    )
    text = re.sub(
        r"[ \t]*from sglang\.srt\.model_executor\.model_runner import ModelRunner\n\n"
        r"([ \t]*)ModelRunner\.save_sharded_model\(\s*self\.tp_worker\.model_runner\.weight_exporter,\s*",
        r"\1self.tp_worker.model_runner.weight_exporter.save_sharded_model(",
        text,
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
