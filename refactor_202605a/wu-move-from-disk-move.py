#!/usr/bin/env python3
"""Move stage for wu-move-from-disk (MECH_COMMIT_SPLIT §"拆 class 场景"):

Pure cut+paste of the prep'd staticmethod onto ``WeightUpdater``. Body
byte-equivalent. Call sites collapse qualified form back to instance form;
the local ``import ModelRunner`` lines from prep are dropped.
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

ID = "wu-move-from-disk-move"
SUBJECT = "Move update_weights_from_disk onto WeightUpdater (cut+paste)"
BODY = ""
AREA = "mech_model_runner"
BASE = "tom_refactor_202605a/primary/mech_model_runner/wu-move-from-disk-prep"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


def transform(wt: Path) -> None:
    mr = wt / "python/sglang/srt/model_executor/model_runner.py"
    wu = wt / "python/sglang/srt/model_executor/model_runner_components/weight_updater.py"
    tw = wt / "python/sglang/srt/managers/tp_worker.py"
    ew = wt / "python/sglang/srt/speculative/eagle_worker_v2.py"

    # 1) Cut staticmethod from ModelRunner.
    s, e = find_method_lines(
        mr.read_text(), class_name="ModelRunner", method_name="update_weights_from_disk"
    )
    method_text = cut_lines(mr, s, e)

    # 2) Drop @staticmethod + normalize typed-self.
    lines = method_text.splitlines(keepends=True)
    assert lines[0].strip() == "@staticmethod"
    method_text = "".join(lines[1:])
    method_text = method_text.replace('        self: "WeightUpdater",\n', "        self,\n")

    # 3) Append to WeightUpdater + bring in imports the body needs.
    text = wu.read_text()
    text = insert_after(
        text,
        anchor="import logging\n",
        addition=(
            "import gc\n"
            "from typing import Callable, Optional\n"
        ),
    )
    # Expand the existing single-symbol utils import + add the rest.
    text = replace_call_site(
        text,
        old="from sglang.srt.utils import init_custom_process_group\n",
        new=(
            "from sglang.srt.utils import get_available_gpu_memory, init_custom_process_group\n"
            "from sglang.srt.configs.load_config import LoadConfig\n"
            "from sglang.srt.model_loader.loader import DefaultModelLoader, get_model_loader\n"
            "from sglang.srt.model_loader.utils import set_default_torch_dtype\n"
            "from sglang.srt.platforms import current_platform\n"
        ),
    )
    wu.write_text(text)
    append_to_file(wu, method_text.rstrip() + "\n", separator="\n")

    # 4) ModelRunner internal caller: collapse.
    text = mr.read_text()
    text = replace_call_site(
        text,
        old=(
            "                ModelRunner.update_weights_from_disk(\n"
            "                    self.weight_updater,\n"
        ),
        new="                self.weight_updater.update_weights_from_disk(\n",
    )
    mr.write_text(text)

    # 5) External callers: collapse paired ``local_import + qualified_call``
    # blocks back to bare instance calls (paired form preserves unrelated
    # local ``ModelRunner`` imports in the same file).
    text = tw.read_text()
    text = re.sub(
        r"[ \t]*from sglang\.srt\.model_executor\.model_runner import ModelRunner\n\n"
        r"([ \t]*)success, message = ModelRunner\.update_weights_from_disk\(\s*self\.model_runner\.weight_updater,\s*",
        r"\1success, message = self.model_runner.weight_updater.update_weights_from_disk(",
        text,
    )
    tw.write_text(text)

    text = ew.read_text()
    text = re.sub(
        r"[ \t]*from sglang\.srt\.model_executor\.model_runner import ModelRunner\n\n"
        r"([ \t]*)success, message = ModelRunner\.update_weights_from_disk\(\s*self\._draft_worker\.draft_runner\.weight_updater,\s*",
        r"\1success, message = self._draft_worker.draft_runner.weight_updater.update_weights_from_disk(",
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
