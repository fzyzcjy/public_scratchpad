#!/usr/bin/env python3
"""Cut `init_weights_update_group` and `destroy_weights_update_group` from
ModelRunner; paste as free functions in new file `model_executor/weight_updater.py`.
Updates tp_worker.py callers directly (methods are deleted).
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

BASE = "tom_refactor/23"
TARGET = "tom_refactor/24"

NEW_HEADER = (
    "from __future__ import annotations\n\nimport logging\n\nimport torch\n\n"
    "from sglang.srt.utils import init_custom_process_group\n"
    "from sglang.srt.utils.network import NetworkAddress\n\n"
    "logger = logging.getLogger(__name__)\n"
)


def transform(wt: Path) -> None:
    sys.path.insert(0, str(wt / ".claude/skills/mechanical-refactor-verify"))
    from mechanical_refactor_verify_utils import git_add_and_commit

    mr = wt / "python/sglang/srt/model_executor/model_runner.py"
    new_file = wt / "python/sglang/srt/model_executor/weight_updater.py"
    new_file.write_text(NEW_HEADER)

    for name in ("init_weights_update_group", "destroy_weights_update_group"):
        s, e = find_method_lines(mr.read_text(), class_name="ModelRunner", method_name=name)
        method_text = cut_lines(mr, s, e)
        fn = dedent_method_to_function(method_text)
        if name == "init_weights_update_group":
            fn = fn.replace(
                "def init_weights_update_group(\n    self,\n",
                "def init_weights_update_group(\n    *,\n    _model_update_group,\n    tp_rank,\n",
            )
            fn = fn.replace("self.tp_rank", "tp_rank")
            fn = fn.replace("self._model_update_group", "_model_update_group")
        else:
            fn = fn.replace(
                "def destroy_weights_update_group(self, group_name):\n",
                "def destroy_weights_update_group(*, _model_update_group, group_name):\n",
            )
            fn = fn.replace("self._model_update_group", "_model_update_group")
        append_to_file(new_file, fn)

    text = mr.read_text()
    text = insert_after(
        text,
        anchor="from sglang.srt.model_executor.cpu_graph_runner import CPUGraphRunner\n",
        addition=(
            "from sglang.srt.model_executor.weight_updater import (\n"
            "    destroy_weights_update_group,\n    init_weights_update_group,\n)\n"
        ),
    )
    mr.write_text(text)

    tp = wt / "python/sglang/srt/managers/tp_worker.py"
    text = tp.read_text()
    text = replace_call_site(
        text,
        old=(
            "        success, message = self.model_runner.init_weights_update_group(\n"
            "            recv_req.master_address,\n            recv_req.master_port,\n"
            "            recv_req.rank_offset,\n            recv_req.world_size,\n"
            "            recv_req.group_name,\n            recv_req.backend,\n        )\n"
        ),
        new=(
            "        success, message = init_weights_update_group(\n"
            "            _model_update_group=self.model_runner._model_update_group,\n"
            "            tp_rank=self.model_runner.tp_rank,\n"
            "            master_address=recv_req.master_address,\n"
            "            master_port=recv_req.master_port,\n"
            "            rank_offset=recv_req.rank_offset,\n"
            "            world_size=recv_req.world_size,\n"
            "            group_name=recv_req.group_name,\n"
            "            backend=recv_req.backend,\n        )\n"
        ),
    )
    text = replace_call_site(
        text,
        old=(
            "        success, message = self.model_runner.destroy_weights_update_group(\n"
            "            recv_req.group_name,\n        )\n"
        ),
        new=(
            "        success, message = destroy_weights_update_group(\n"
            "            _model_update_group=self.model_runner._model_update_group,\n"
            "            group_name=recv_req.group_name,\n        )\n"
        ),
    )
    text = replace_call_site(
        text,
        old="from sglang.srt.managers.io_struct import (\n",
        new=(
            "from sglang.srt.model_executor.weight_updater import (\n"
            "    destroy_weights_update_group,\n    init_weights_update_group,\n)\n"
            "from sglang.srt.managers.io_struct import (\n"
        ),
    )
    tp.write_text(text)

    git_add_and_commit(
        "Extract weights update group lifecycle to free functions in weight_updater",
        cwd=str(wt),
    )


if __name__ == "__main__":
    run_pr(transform=transform, base=BASE, target=TARGET)
