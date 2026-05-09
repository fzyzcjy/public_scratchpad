#!/usr/bin/env python3
"""Reproducible transform: extract `ModelRunner.apply_torch_tp` to a free
function in `sglang.srt.layers.model_parallel`. Adds the module-level logger.

Run from the repo root:
    python3 /tmp/transform_apply_torch_tp.py
"""

import sys
from pathlib import Path

sys.path.append(".claude/skills/mechanical-refactor-verify")
from mechanical_refactor_verify_utils import (
    verify_mechanical_refactor,
    git_add_and_commit,
)

BASE_COMMIT = "tom_refactor/18"
TARGET_COMMIT = "tom_refactor/19"


def transform(dir_root: Path) -> None:
    mp = dir_root / "python/sglang/srt/layers/model_parallel.py"
    text = mp.read_text()
    text = text.replace(
        '"""\nCommon utilities for torch model parallelism.\n"""\n\nfrom typing import Optional, Sequence\n\nimport torch\nimport torch.nn as nn\nfrom torch.distributed.device_mesh import DeviceMesh',
        '"""\nCommon utilities for torch model parallelism.\n"""\n\nimport logging\nfrom typing import Optional, Sequence\n\nimport torch\nimport torch.nn as nn\nfrom torch.distributed.device_mesh import DeviceMesh\n\nlogger = logging.getLogger(__name__)',
    )
    text = text.rstrip() + (
        "\n\n\ndef apply_torch_tp(\n"
        "    *,\n"
        "    model: nn.Module,\n"
        "    device: str,\n"
        "    tp_size: int,\n"
        ") -> None:\n"
        '    logger.info(f"Enabling torch tensor parallelism on {tp_size} devices.")\n'
        "    device_mesh = torch.distributed.init_device_mesh(device, (tp_size,))\n"
        "    tensor_parallel(model, device_mesh)\n"
    )
    mp.write_text(text)

    mr = dir_root / "python/sglang/srt/model_executor/model_runner.py"
    text = mr.read_text()
    old_method = (
        "    def apply_torch_tp(self):\n"
        '        logger.info(f"Enabling torch tensor parallelism on {self.tp_size} devices.")\n'
        "        from sglang.srt.layers.model_parallel import tensor_parallel\n\n"
        "        device_mesh = torch.distributed.init_device_mesh(self.device, (self.tp_size,))\n"
        "        tensor_parallel(self.model, device_mesh)\n\n"
    )
    assert old_method in text, "apply_torch_tp method not found"
    text = text.replace(old_method, "")
    text = text.replace(
        '        if self.tp_size > 1 and supports_torch_tp:\n            self.apply_torch_tp()',
        '        if self.tp_size > 1 and supports_torch_tp:\n            apply_torch_tp(model=self.model, device=self.device, tp_size=self.tp_size)',
    )
    text = text.replace(
        "from sglang.srt.layers.logits_processor import LogitsProcessorOutput\n",
        "from sglang.srt.layers.logits_processor import LogitsProcessorOutput\nfrom sglang.srt.layers.model_parallel import apply_torch_tp\n",
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
