#!/usr/bin/env python3
"""Cut `init_weights_update_group` and `destroy_weights_update_group` from
ModelRunner; paste as free functions in new file `model_executor/weight_updater.py`.
Updates tp_worker.py callers directly (methods are deleted).
"""

import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.append(str(HERE))
sys.path.append(".claude/skills/mechanical-refactor-verify")
from _helpers import append_to_file, cut_lines, dedent_method_to_function, find_method_lines
from mechanical_refactor_verify_utils import git_add_and_commit, verify_mechanical_refactor

BASE_COMMIT = "tom_refactor/23"
TARGET_COMMIT = "tom_refactor/24"

NEW_HEADER = (
    "from __future__ import annotations\n\nimport logging\n\nimport torch\n\n"
    "from sglang.srt.utils import init_custom_process_group\n"
    "from sglang.srt.utils.network import NetworkAddress\n\n"
    "logger = logging.getLogger(__name__)\n"
)


def transform(dir_root: Path) -> None:
    mr = dir_root / "python/sglang/srt/model_executor/model_runner.py"
    new_file = dir_root / "python/sglang/srt/model_executor/weight_updater.py"
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
    text = text.replace(
        "from sglang.srt.model_executor.cpu_graph_runner import CPUGraphRunner\n",
        "from sglang.srt.model_executor.cpu_graph_runner import CPUGraphRunner\n"
        "from sglang.srt.model_executor.weight_updater import (\n"
        "    destroy_weights_update_group,\n    init_weights_update_group,\n)\n",
    )
    mr.write_text(text)

    tp = dir_root / "python/sglang/srt/managers/tp_worker.py"
    text = tp.read_text()
    text = text.replace(
        "        success, message = self.model_runner.init_weights_update_group(\n"
        "            recv_req.master_address,\n            recv_req.master_port,\n"
        "            recv_req.rank_offset,\n            recv_req.world_size,\n"
        "            recv_req.group_name,\n            recv_req.backend,\n        )\n",
        "        success, message = init_weights_update_group(\n"
        "            _model_update_group=self.model_runner._model_update_group,\n"
        "            tp_rank=self.model_runner.tp_rank,\n"
        "            master_address=recv_req.master_address,\n"
        "            master_port=recv_req.master_port,\n"
        "            rank_offset=recv_req.rank_offset,\n"
        "            world_size=recv_req.world_size,\n"
        "            group_name=recv_req.group_name,\n"
        "            backend=recv_req.backend,\n        )\n",
    )
    text = text.replace(
        "        success, message = self.model_runner.destroy_weights_update_group(\n"
        "            recv_req.group_name,\n        )\n",
        "        success, message = destroy_weights_update_group(\n"
        "            _model_update_group=self.model_runner._model_update_group,\n"
        "            group_name=recv_req.group_name,\n        )\n",
    )
    text = text.replace(
        "from sglang.srt.managers.io_struct import (\n",
        "from sglang.srt.model_executor.weight_updater import (\n"
        "    destroy_weights_update_group,\n    init_weights_update_group,\n)\n"
        "from sglang.srt.managers.io_struct import (\n",
    )
    tp.write_text(text)

    git_add_and_commit(
        "Extract weights update group lifecycle to free functions in weight_updater",
        cwd=str(dir_root),
    )


if __name__ == "__main__":
    verify_mechanical_refactor(base_commit=BASE_COMMIT, target_commit=TARGET_COMMIT, transform=transform)
