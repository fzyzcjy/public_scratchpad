#!/usr/bin/env python3
"""Reproducible transform: extract `ModelRunner.apply_torch_tp` to a free
function in `sglang.srt.layers.model_parallel`. Strict-minimal mechanical move:
no docstring added, no rename, no type annotations beyond the originals
(parameters take whatever annotations align with the existing module-level
imports), and the body is byte-identical to the method body except for
`self.X` -> kwarg substitution.

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
    # --- Step 1: Append apply_torch_tp free function to layers.model_parallel ---
    mp = dir_root / "python/sglang/srt/layers/model_parallel.py"
    text = mp.read_text()

    # Add `import logging` and module-level logger near the top of the file.
    # This is necessary infrastructure: the original method called `logger.info`
    # via the model_runner module-level logger; the free function needs its own.
    old_top = (
        '"""\nCommon utilities for torch model parallelism.\n"""\n\n'
        "from typing import Optional, Sequence\n\n"
        "import torch\n"
        "import torch.nn as nn\n"
        "from torch.distributed.device_mesh import DeviceMesh"
    )
    new_top = (
        '"""\nCommon utilities for torch model parallelism.\n"""\n\n'
        "import logging\n"
        "from typing import Optional, Sequence\n\n"
        "import torch\n"
        "import torch.nn as nn\n"
        "from torch.distributed.device_mesh import DeviceMesh\n\n"
        "logger = logging.getLogger(__name__)"
    )
    assert old_top in text, "model_parallel.py top-of-file marker not found"
    text = text.replace(old_top, new_top)

    # Append the new free function. Body byte-identical to the method body with
    # self.tp_size -> tp_size, self.device -> device, self.model -> model.
    # Keep the inline `from sglang.srt.layers.model_parallel import tensor_parallel`
    # even though it's redundant inside this very module — strict byte-identical.
    text = text.rstrip() + (
        "\n\n\ndef apply_torch_tp(\n"
        "    *,\n"
        "    model: nn.Module,\n"
        "    device: str,\n"
        "    tp_size: int,\n"
        "):\n"
        '    logger.info(f"Enabling torch tensor parallelism on {tp_size} devices.")\n'
        "    from sglang.srt.layers.model_parallel import tensor_parallel\n\n"
        "    device_mesh = torch.distributed.init_device_mesh(device, (tp_size,))\n"
        "    tensor_parallel(model, device_mesh)\n"
    )
    mp.write_text(text)

    # --- Step 2: Update model_runner.py ---
    mr = dir_root / "python/sglang/srt/model_executor/model_runner.py"
    text = mr.read_text()

    # Delete method entirely + update sole caller in initialize() to call free function.
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
        "        if self.tp_size > 1 and supports_torch_tp:\n            self.apply_torch_tp()",
        "        if self.tp_size > 1 and supports_torch_tp:\n            apply_torch_tp(model=self.model, device=self.device, tp_size=self.tp_size)",
    )

    # Add import for the new free function (alphabetical position right after
    # logits_processor).
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
