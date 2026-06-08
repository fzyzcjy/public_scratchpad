#!/usr/bin/env python3
"""Move stage for nem-migrate-maybe-prepare (MECH_COMMIT_SPLIT §"split-class scenario"):

Cut prep'd staticmethod from Scheduler to NgramEmbeddingManager. Body
byte-equivalent. Add manager-side imports the body needs. Collapse caller +
test mock back to instance form.
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

ID = "nem-migrate-maybe-prepare-move"
SUBJECT = "Move prepare_for_forward onto NgramEmbeddingManager (cut+paste)"
BODY = ""
AREA = "mech_model_runner"
BASE = "tom_refactor_202605a/primary/mech_model_runner/nem-migrate-maybe-prepare-prep"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


def transform(wt: Path) -> None:
    sched = wt / "python/sglang/srt/managers/scheduler.py"
    manager = wt / "python/sglang/srt/layers/n_gram_embedding_manager.py"

    # Cut from Scheduler.
    s, e = find_method_lines(sched.read_text(), class_name="Scheduler", method_name="prepare_for_forward")
    method_text = cut_lines(sched, s, e)
    lines = method_text.splitlines(keepends=True)
    assert lines[0].strip() == "@staticmethod"
    body = "".join(lines[1:])
    body = body.replace('        self: "NgramEmbeddingManager", batch: Optional[ScheduleBatch]\n', "        self, batch: Optional[ScheduleBatch]\n")

    # Manager-side imports the body needs.
    text = manager.read_text()
    if ", Optional" not in text and "from typing import TYPE_CHECKING\n" in text:
        text = text.replace(
            "from typing import TYPE_CHECKING\n",
            "from typing import TYPE_CHECKING, Optional\n",
        )
    if "from sglang.srt.managers.schedule_batch import ForwardMode\n" not in text:
        text = insert_after(
            text,
            anchor="from sglang.jit_kernel.ngram_embedding import update_token_table\n",
            addition="from sglang.srt.managers.schedule_batch import ForwardMode\n",
        )
    if "    from sglang.srt.managers.schedule_batch import ScheduleBatch\n" not in text:
        text = insert_after(
            text,
            anchor="if TYPE_CHECKING:\n",
            addition="    from sglang.srt.managers.schedule_batch import ScheduleBatch\n",
        )
    manager.write_text(text)

    append_to_file(manager, body.rstrip() + "\n")

    # Scheduler caller collapse.
    text = sched.read_text()
    text = replace_call_site(
        text,
        old="Scheduler.prepare_for_forward(self.ngram_embedding_manager, ",
        new="self.ngram_embedding_manager.prepare_for_forward(",
    )
    sched.write_text(text)


if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        area_branch=AREA_BRANCH,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
