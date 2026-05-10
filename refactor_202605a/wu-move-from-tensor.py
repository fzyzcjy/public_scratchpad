#!/usr/bin/env python3
"""Move ``update_weights_from_tensor`` + helpers onto ``WeightUpdater``.

- ``update_weights_from_tensor`` and ``_update_weights_from_flattened_bucket``
  cut from ModelRunner and pasted (still as instance methods) onto
  WeightUpdater. Bodies rewrite ``self.<ModelRunner-field>`` ->
  ``self._mr.<...>`` (``model``, ``device``, ``server_args``); ``self.tp_rank``
  stays as is -- WeightUpdater has its own ``tp_rank`` field.
- Module-level helpers ``_unwrap_tensor`` / ``_model_load_weights_direct`` and
  the ``LocalSerializedTensor`` dataclass also cut from
  ``model_runner.py`` and re-homed in ``weight_updater.py`` as module-level
  free fns / class (they're stateless utilities).
- ``test/registered/rl/test_update_weights_from_tensor.py`` references
  ``sglang.srt.model_executor.model_runner._model_load_weights_direct`` via a
  dotted-path string for ``custom_weight_loader``; rewrite the path to
  ``sglang.srt.model_executor.weight_updater._model_load_weights_direct``.
- ``tp_worker.py`` caller rewritten to
  ``self.model_runner.weight_updater.update_weights_from_tensor(...)``.

Usage:
    uv run --python 3.12 wu-move-from-tensor.py run
    uv run --python 3.12 wu-move-from-tensor.py verify
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
    find_class_lines,
    find_function_lines,
    find_method_lines,
    insert_after,
    replace_call_site,
)
from _runner import run_pr

ID = "wu-move-from-tensor"
SUBJECT = "Move update_weights_from_tensor and helpers onto WeightUpdater"
BODY = ""
AREA = "mech_model_runner"
BASE = "tom_refactor_202605a/primary/mech_model_runner/wu-move-from-distributed"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


def _rewrite_self(method_text: str) -> str:
    """``update_weights_from_tensor`` body reads multiple ModelRunner fields
    (``model``, ``device``, ``server_args``); WeightUpdater itself owns
    ``tp_rank``. Apply the substitutions in an order that does not
    accidentally re-rewrite ``self._mr.X`` strings.
    """
    method_text = method_text.replace("self.model.load_weights", "self._mr.model.load_weights")
    method_text = method_text.replace("self.model,", "self._mr.model,")
    method_text = method_text.replace("self.device", "self._mr.device")
    method_text = method_text.replace(
        "self.server_args.custom_weight_loader",
        "self._mr.server_args.custom_weight_loader",
    )
    return method_text


def transform(wt: Path) -> None:
    mr = wt / "python/sglang/srt/model_executor/model_runner.py"
    wu = wt / "python/sglang/srt/model_executor/weight_updater.py"
    tw = wt / "python/sglang/srt/managers/tp_worker.py"

    # Cut bottom-up so earlier line ranges stay valid.
    s, e = find_class_lines(mr.read_text(), class_name="LocalSerializedTensor")
    cls_text = cut_lines(mr, s, e)

    s, e = find_function_lines(mr.read_text(), function_name="_unwrap_tensor")
    unwrap_text = cut_lines(mr, s, e)

    s, e = find_function_lines(mr.read_text(), function_name="_model_load_weights_direct")
    direct_text = cut_lines(mr, s, e)

    s, e = find_method_lines(
        mr.read_text(),
        class_name="ModelRunner",
        method_name="_update_weights_from_flattened_bucket",
    )
    fb_text = _rewrite_self(cut_lines(mr, s, e))

    s, e = find_method_lines(
        mr.read_text(),
        class_name="ModelRunner",
        method_name="update_weights_from_tensor",
    )
    uwt_text = _rewrite_self(cut_lines(mr, s, e))

    # weight_updater.py: imports needed by helpers and the new methods.
    # Consolidate the existing single-symbol ``FlattenedTensorBucket`` import
    # with ``FlattenedTensorMetadata`` so isort doesn't have to merge them.
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
    # Pre-commit's isort merged the two `from sglang.srt.utils` lines into
    # one combined alphabetical import; anchor on that.
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

    # Append the two methods to the class first (still at 4-space indent).
    append_to_file(
        wu,
        uwt_text.rstrip() + "\n\n" + fb_text.rstrip() + "\n",
        separator="\n",
    )
    # Append module-level helpers / dataclass after the class.
    append_to_file(
        wu,
        direct_text.rstrip() + "\n\n\n" + unwrap_text.rstrip() + "\n\n\n" + cls_text.rstrip() + "\n",
        separator="\n\n",
    )

    # tp_worker.py: rewrite caller.
    text = tw.read_text()
    text = replace_call_site(
        text,
        old="        success, message = self.model_runner.update_weights_from_tensor(\n",
        new="        success, message = self.model_runner.weight_updater.update_weights_from_tensor(\n",
    )
    tw.write_text(text)

    # Test file references the helper via dotted-path string; update it.
    test_uwt = wt / "test/registered/rl/test_update_weights_from_tensor.py"
    text = test_uwt.read_text()
    text = replace_call_site(
        text,
        old="sglang.srt.model_executor.model_runner._model_load_weights_direct",
        new="sglang.srt.model_executor.weight_updater._model_load_weights_direct",
    )
    test_uwt.write_text(text)

    # weight_sync/utils.py imports the dataclass from the old home — rewire.
    ws_utils = wt / "python/sglang/srt/weight_sync/utils.py"
    text = ws_utils.read_text()
    text = replace_call_site(
        text,
        old="from sglang.srt.model_executor.model_runner import LocalSerializedTensor\n",
        new="from sglang.srt.model_executor.weight_updater import LocalSerializedTensor\n",
    )
    ws_utils.write_text(text)

    # SafeUnpickler's allowlist gates pickle deserialization (CVE-2025-10164).
    # ``LocalSerializedTensor`` ships across the IPC boundary; after the move
    # the new module path needs to be allowed too.
    common = wt / "python/sglang/srt/utils/common.py"
    text = common.read_text()
    text = replace_call_site(
        text,
        old='        "sglang.srt.model_executor.model_runner.",\n',
        new=(
            '        "sglang.srt.model_executor.model_runner.",\n'
            '        "sglang.srt.model_executor.weight_updater.",\n'
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
