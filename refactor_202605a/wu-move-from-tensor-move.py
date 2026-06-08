#!/usr/bin/env python3
"""Move stage for wu-move-from-tensor (MECH_COMMIT_SPLIT §"split-class scenario"):

Cut the 2 prep'd staticmethods to ``WeightUpdater``. Bodies byte-equivalent
(prep already applied ``self.X`` → ``self._mr.X``). Cut module-level helpers
(``_unwrap_tensor``, ``_model_load_weights_direct``) and the dataclass
``LocalSerializedTensor`` to ``weight_updater.py``. Rewire:
- ``weight_sync/utils.py`` LocalSerializedTensor import path
- ``utils/common.py`` SafeUnpickler ALLOWED_MODULE_PREFIXES (CVE-2025-10164)
- ``test_update_weights_from_tensor.py`` dotted-path string
- tp_worker.py: drop local import, collapse caller
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
    find_class_lines,
    find_function_lines,
    find_method_lines,
    insert_after,
    replace_call_site,
)
from _runner import run_pr

ID = "wu-move-from-tensor-move"
SUBJECT = "Move update_weights_from_tensor + helpers onto WeightUpdater (cut+paste)"
BODY = ""
AREA = "mech_model_runner"
BASE = "tom_refactor_202605a/primary/mech_model_runner/wu-move-from-tensor-prep"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


def _cut_method(mr: Path, method_name: str) -> str:
    s, e = find_method_lines(mr.read_text(), class_name="ModelRunner", method_name=method_name)
    method_text = cut_lines(mr, s, e)
    lines = method_text.splitlines(keepends=True)
    assert lines[0].strip() == "@staticmethod"
    body = "".join(lines[1:])
    body = body.replace('        self: "WeightUpdater",\n', "        self,\n")
    # Collapse cross-method call (now both methods in WU). Pre-commit may
    # line-wrap the long call.
    import re
    body = re.sub(
        r"ModelRunner\._update_weights_from_flattened_bucket\(\s*self,\s*",
        "self._update_weights_from_flattened_bucket(",
        body,
    )
    return body


def transform(wt: Path) -> None:
    mr = wt / "python/sglang/srt/model_executor/model_runner.py"
    wu = wt / "python/sglang/srt/model_executor/model_runner_components/weight_updater.py"
    tw = wt / "python/sglang/srt/managers/tp_worker.py"

    # Cut bottom-up so earlier line ranges stay valid: class, then 2 free
    # functions, then 2 methods.
    s, e = find_class_lines(mr.read_text(), class_name="LocalSerializedTensor")
    cls_text = cut_lines(mr, s, e)

    s, e = find_function_lines(mr.read_text(), function_name="_unwrap_tensor")
    unwrap_text = cut_lines(mr, s, e)

    s, e = find_function_lines(mr.read_text(), function_name="_model_load_weights_direct")
    direct_text = cut_lines(mr, s, e)

    fb_body = _cut_method(mr, "_update_weights_from_flattened_bucket")
    uwt_body = _cut_method(mr, "update_weights_from_tensor")

    # weight_updater.py: imports + class methods + module-level helpers + dataclass.
    text = wu.read_text()
    text = replace_call_site(
        text,
        old="from sglang.srt.weight_sync.tensor_bucket import FlattenedTensorBucket\n",
        new=(
            "from sglang.srt.weight_sync.tensor_bucket import (\n"
            "    FlattenedTensorBucket,\n"
            "    FlattenedTensorMetadata,\n"
            ")\n"
        ),
    )
    text = insert_after(
        text,
        anchor="from sglang.srt.utils import get_available_gpu_memory, init_custom_process_group\n",
        addition=(
            "from dataclasses import dataclass\n"
            "from typing import List, Tuple, Union\n\n"
            "from sglang.srt.model_loader.weight_utils import default_weight_loader\n"
            "from sglang.srt.utils import MultiprocessingSerializer, dynamic_import\n"
            "from sglang.srt.utils.patch_torch import monkey_patch_torch_reductions\n"
        ),
    )
    wu.write_text(text)

    append_to_file(
        wu,
        uwt_body.rstrip() + "\n\n" + fb_body.rstrip() + "\n",
        separator="\n",
    )
    append_to_file(
        wu,
        direct_text.rstrip() + "\n\n\n" + unwrap_text.rstrip() + "\n\n\n" + cls_text.rstrip() + "\n",
        separator="\n\n",
    )

    # tp_worker.py: collapse paired ``local_import + qualified_call``.
    text = tw.read_text()
    text = re.sub(
        r"[ \t]*from sglang\.srt\.model_executor\.model_runner import ModelRunner\n\n"
        r"([ \t]*)success, message = ModelRunner\.update_weights_from_tensor\(\s*self\.model_runner\.weight_updater,\s*",
        r"\1success, message = self.model_runner.weight_updater.update_weights_from_tensor(",
        text,
    )
    tw.write_text(text)

    # Test file: dotted-path string.
    test_uwt = wt / "test/registered/rl/test_update_weights_from_tensor.py"
    text = test_uwt.read_text()
    text = replace_call_site(
        text,
        old="sglang.srt.model_executor.model_runner._model_load_weights_direct",
        new="sglang.srt.model_executor.model_runner_components.weight_updater._model_load_weights_direct",
    )
    test_uwt.write_text(text)

    # weight_sync/utils.py LocalSerializedTensor import.
    ws_utils = wt / "python/sglang/srt/weight_sync/utils.py"
    text = ws_utils.read_text()
    text = replace_call_site(
        text,
        old="from sglang.srt.model_executor.model_runner import LocalSerializedTensor\n",
        new="from sglang.srt.model_executor.model_runner_components.weight_updater import LocalSerializedTensor\n",
    )
    ws_utils.write_text(text)

    # SafeUnpickler allowlist (CVE-2025-10164) — add new module prefix.
    common = wt / "python/sglang/srt/utils/common.py"
    text = common.read_text()
    text = replace_call_site(
        text,
        old='        "sglang.srt.model_executor.model_runner.",\n',
        new=(
            '        "sglang.srt.model_executor.model_runner.",\n'
            '        "sglang.srt.model_executor.model_runner_components.weight_updater.",\n'
        ),
    )
    common.write_text(text)


if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        area_branch=AREA_BRANCH,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
