#!/usr/bin/env python3
"""Cut `apply_torch_tp` from ModelRunner; paste as a free function in
`layers/model_parallel.py`.
"""

import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.append(str(HERE))
sys.path.append(".claude/skills/mechanical-refactor-verify")
from _helpers import (
    append_to_file,
    cut_lines,
    dedent_method_to_function,
    find_method_lines,
)
from mechanical_refactor_verify_utils import (
    git_add_and_commit,
    verify_mechanical_refactor,
)

BASE_COMMIT = "tom_refactor/18"
TARGET_COMMIT = "tom_refactor/19"


def transform(dir_root: Path) -> None:
    mr = dir_root / "python/sglang/srt/model_executor/model_runner.py"
    mp = dir_root / "python/sglang/srt/layers/model_parallel.py"

    start, end = find_method_lines(
        mr.read_text(), class_name="ModelRunner", method_name="apply_torch_tp"
    )
    method_text = cut_lines(mr, start, end)
    function_text = dedent_method_to_function(method_text)
    function_text = function_text.replace(
        "def apply_torch_tp(self):\n",
        "def apply_torch_tp(\n    *,\n    model: nn.Module,\n    device: str,\n    tp_size: int,\n):\n",
    )
    function_text = function_text.replace("self.tp_size", "tp_size")
    function_text = function_text.replace("self.device", "device")
    function_text = function_text.replace("self.model", "model")

    mp_text = mp.read_text()
    if "logger = logging.getLogger(__name__)" not in mp_text:
        mp_text = mp_text.replace(
            "from typing import Optional, Sequence\n",
            "import logging\nfrom typing import Optional, Sequence\n",
        )
        mp_text = mp_text.replace(
            "from torch.distributed.device_mesh import DeviceMesh\n",
            "from torch.distributed.device_mesh import DeviceMesh\n\nlogger = logging.getLogger(__name__)\n",
        )
        mp.write_text(mp_text)
    append_to_file(mp, function_text)

    text = mr.read_text()
    text = text.replace(
        "self.apply_torch_tp()",
        "apply_torch_tp(model=self.model, device=self.device, tp_size=self.tp_size)",
    )
    text = text.replace(
        "from sglang.srt.layers.logits_processor import LogitsProcessorOutput\n",
        "from sglang.srt.layers.logits_processor import LogitsProcessorOutput\n"
        "from sglang.srt.layers.model_parallel import apply_torch_tp\n",
    )
    mr.write_text(text)

    git_add_and_commit(
        "Extract apply_torch_tp to free function in layers.model_parallel",
        cwd=str(dir_root),
    )


if __name__ == "__main__":
    verify_mechanical_refactor(
        base_commit=BASE_COMMIT,
        target_commit=TARGET_COMMIT,
        transform=transform,
    )
