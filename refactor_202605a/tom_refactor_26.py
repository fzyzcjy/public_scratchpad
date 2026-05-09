#!/usr/bin/env python3
"""Cut `update_weights_from_distributed` and the private helper
`_update_bucketed_weights_from_distributed` from ModelRunner; paste both into
`weight_updater.py` as free functions. Update sole caller in `tp_worker.py`.

Usage:
    uv run --python 3.12 tom_refactor_26.py run
    uv run --python 3.12 tom_refactor_26.py verify
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
    dedent_method_to_function,
    find_method_lines,
    insert_after,
    replace_call_site,
)
from _runner import run_pr

BASE = "tom_refactor/25"
TARGET = "tom_refactor/26"


def transform(wt: Path) -> None:
    sys.path.insert(0, str(wt / ".claude/skills/mechanical-refactor-verify"))
    from mechanical_refactor_verify_utils import git_add_and_commit

    mr = wt / "python/sglang/srt/model_executor/model_runner.py"
    wu = wt / "python/sglang/srt/model_executor/weight_updater.py"
    tw = wt / "python/sglang/srt/managers/tp_worker.py"

    # Cut from bottom to top so earlier line ranges stay valid.
    s, e = find_method_lines(
        mr.read_text(),
        class_name="ModelRunner",
        method_name="_update_bucketed_weights_from_distributed",
    )
    bucketed_text = (
        dedent_method_to_function(cut_lines(mr, s, e))
        .replace(
            "def _update_bucketed_weights_from_distributed(\n"
            "    self, names, dtypes, shapes, group_name\n"
            "):",
            "def _update_bucketed_weights_from_distributed(\n"
            "    *, model, _model_update_group, device, names, dtypes, shapes, group_name\n"
            "):",
        )
        .replace("self.device", "device")
        .replace("self._model_update_group", "_model_update_group")
        .replace("self.model.load_weights", "model.load_weights")
    )

    s, e = find_method_lines(
        mr.read_text(),
        class_name="ModelRunner",
        method_name="update_weights_from_distributed",
    )
    uwd_text = (
        dedent_method_to_function(cut_lines(mr, s, e))
        .replace(
            "def update_weights_from_distributed(\n"
            "    self,\n"
            "    names,\n"
            "    dtypes,\n"
            "    shapes,\n"
            "    group_name,\n"
            "    load_format: Optional[str] = None,\n"
            "):",
            "def update_weights_from_distributed(\n"
            "    *,\n"
            "    model,\n"
            "    _model_update_group,\n"
            "    device,\n"
            "    names,\n"
            "    dtypes,\n"
            "    shapes,\n"
            "    group_name,\n"
            "    load_format: Optional[str] = None,\n"
            "):",
        )
        .replace("self.device", "device")
        .replace("self._model_update_group", "_model_update_group")
        .replace("self.model.load_weights", "model.load_weights")
        .replace(
            '    if load_format == "flattened_bucket":\n'
            "        return self._update_bucketed_weights_from_distributed(\n"
            "            names, dtypes, shapes, group_name\n"
            "        )",
            '    if load_format == "flattened_bucket":\n'
            "        return _update_bucketed_weights_from_distributed(\n"
            "            model=model,\n"
            "            _model_update_group=_model_update_group,\n"
            "            device=device,\n"
            "            names=names,\n"
            "            dtypes=dtypes,\n"
            "            shapes=shapes,\n"
            "            group_name=group_name,\n"
            "        )",
        )
    )

    text = wu.read_text()
    text = insert_after(
        text,
        anchor="import logging\n",
        addition="from typing import Optional\n",
    )
    wu.write_text(text)
    appended = (
        "\nfrom sglang.srt.weight_sync.tensor_bucket import FlattenedTensorBucket\n\n\n"
        + uwd_text
        + "\n"
        + bucketed_text
    )
    append_to_file(wu, appended)

    # No model_runner.py import needed — model_runner doesn't reference
    # `_free_update_weights_from_distributed`; only tp_worker does. Adding an
    # unused import would be stripped by pre-commit (ruff F401), breaking
    # downstream anchors that rely on the import being present.

    text = tw.read_text()
    text = insert_after(
        text,
        anchor="from sglang.srt.model_executor.forward_batch_info import ForwardBatch, PPProxyTensors\n",
        addition=(
            "from sglang.srt.model_executor.weight_updater import (\n"
            "    update_weights_from_distributed as _free_update_weights_from_distributed,\n"
            ")\n"
        ),
    )
    text = replace_call_site(
        text,
        old=(
            "        success, message = self.model_runner.update_weights_from_distributed(\n"
            "            recv_req.names,\n"
            "            recv_req.dtypes,\n"
            "            recv_req.shapes,\n"
            "            recv_req.group_name,\n"
            "            recv_req.load_format,\n"
            "        )\n"
        ),
        new=(
            "        success, message = _free_update_weights_from_distributed(\n"
            "            model=self.model_runner.model,\n"
            "            _model_update_group=self.model_runner._model_update_group,\n"
            "            device=self.model_runner.device,\n"
            "            names=recv_req.names,\n"
            "            dtypes=recv_req.dtypes,\n"
            "            shapes=recv_req.shapes,\n"
            "            group_name=recv_req.group_name,\n"
            "            load_format=recv_req.load_format,\n"
            "        )\n"
        ),
    )
    tw.write_text(text)

    git_add_and_commit(
        "Extract update_weights_from_distributed to free function in weight_updater",
        cwd=str(wt),
    )


if __name__ == "__main__":
    run_pr(transform=transform, base=BASE, target=TARGET)
