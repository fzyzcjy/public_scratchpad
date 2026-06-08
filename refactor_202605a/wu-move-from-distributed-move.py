#!/usr/bin/env python3
"""Move stage for wu-move-from-distributed (MECH_COMMIT_SPLIT §"split-class scenario"):

Cut both staticmethods to WeightUpdater. Bodies byte-equivalent. Collapse
inner cross-method call and external caller; drop the local
``import ModelRunner`` lines from prep.
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

ID = "wu-move-from-distributed-move"
SUBJECT = "Move update_weights_from_distributed onto WeightUpdater (cut+paste)"
BODY = ""
AREA = "mech_model_runner"
BASE = "tom_refactor_202605a/primary/mech_model_runner/wu-move-from-distributed-prep"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


def _cut(mr: Path, method_name: str) -> str:
    s, e = find_method_lines(mr.read_text(), class_name="ModelRunner", method_name=method_name)
    method_text = cut_lines(mr, s, e)
    lines = method_text.splitlines(keepends=True)
    assert lines[0].strip() == "@staticmethod"
    body = "".join(lines[1:])
    # Handle both signature forms.
    body = body.replace('        self: "WeightUpdater",\n', "        self,\n")
    body = body.replace('        self: "WeightUpdater", ', "        self, ")
    return body


def transform(wt: Path) -> None:
    mr = wt / "python/sglang/srt/model_executor/model_runner.py"
    wu = wt / "python/sglang/srt/model_executor/model_runner_components/weight_updater.py"
    tw = wt / "python/sglang/srt/managers/tp_worker.py"

    # Cut bottom-up so earlier line ranges stay valid.
    bucketed = _cut(mr, "_update_bucketed_weights_from_distributed")
    uwd = _cut(mr, "update_weights_from_distributed")

    # Collapse the inner cross-method call (now living in WeightUpdater).
    # Pre-commit may line-wrap the long call; use regex to tolerate both forms.
    import re
    uwd = re.sub(
        r"ModelRunner\._update_bucketed_weights_from_distributed\(\s*self,\s*",
        "self._update_bucketed_weights_from_distributed(",
        uwd,
    )

    # Bring in FlattenedTensorBucket for the body.
    text = wu.read_text()
    text = insert_after(
        text,
        anchor="from sglang.srt.utils import get_available_gpu_memory, init_custom_process_group\n",
        addition="from sglang.srt.weight_sync.tensor_bucket import FlattenedTensorBucket\n",
    )
    wu.write_text(text)
    append_to_file(wu, uwd.rstrip() + "\n\n" + bucketed.rstrip() + "\n", separator="\n")

    # External caller: collapse paired ``local_import + qualified_call``.
    text = tw.read_text()
    text = re.sub(
        r"[ \t]*from sglang\.srt\.model_executor\.model_runner import ModelRunner\n\n"
        r"([ \t]*)success, message = ModelRunner\.update_weights_from_distributed\(\s*self\.model_runner\.weight_updater,\s*",
        r"\1success, message = self.model_runner.weight_updater.update_weights_from_distributed(",
        text,
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
