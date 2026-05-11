#!/usr/bin/env python3
"""Move lora load/unload methods to LoraController."""

# /// script
# requires-python = ">=3.10"
# dependencies = ["typer"]
# ///

import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from _helpers import cut_lines, find_method_lines
from _runner import run_pr

ID = "introduce-lora-controller-move"
SUBJECT = "Move lora methods to LoraController"
BODY = """\
Cut 6 lora methods (init_lora discarded as already in __post_init__):
load_lora_adapter, load_lora_adapter_from_tensors, unload_lora_adapter,
_unload_lora_adapter_locked, _validate_and_resolve_lora, _resolve_lora_path.

Callers in TM + entrypoints rewired through self.lora_controller.<X>.
"""
AREA = "mech_tokenizer_manager"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


EXTRA_IMPORTS = '''import logging
from typing import Union

import fastapi

from sglang.srt.managers.io_struct import (
    EmbeddingReqInput,
    GenerateReqInput,
    LoadLoRAAdapterFromTensorsReqInput,
    LoadLoRAAdapterFromTensorsReqOutput,
    LoadLoRAAdapterReqInput,
    LoadLoRAAdapterReqOutput,
    UnloadLoRAAdapterReqInput,
    UnloadLoRAAdapterReqOutput,
)

logger = logging.getLogger(__name__)
'''


def transform(wt: Path) -> None:
    tm = wt / "python/sglang/srt/managers/tokenizer_manager.py"
    control_mixin = wt / "python/sglang/srt/managers/tokenizer_control_mixin.py"
    lc = wt / "python/sglang/srt/managers/lora_controller.py"

    # Cut init_lora + 2 helpers from TM.
    tm_methods = ("init_lora", "_validate_and_resolve_lora", "_resolve_lora_path")
    name_to_range = {}
    for n in tm_methods:
        s, e = find_method_lines(tm.read_text(), class_name="TokenizerManager", method_name=n)
        name_to_range[n] = (s, e)
    cut_blocks_tm = {}
    for n in sorted(tm_methods, key=lambda nn: -name_to_range[nn][0]):
        s, e = find_method_lines(tm.read_text(), class_name="TokenizerManager", method_name=n)
        cut_blocks_tm[n] = cut_lines(tm, s, e)

    # Cut 4 methods from control_mixin.
    cm_methods = (
        "_unload_lora_adapter_locked",
        "load_lora_adapter",
        "load_lora_adapter_from_tensors",
        "unload_lora_adapter",
    )
    name_to_range_cm = {}
    for n in cm_methods:
        s, e = find_method_lines(
            control_mixin.read_text(),
            class_name="TokenizerControlMixin",
            method_name=n,
        )
        name_to_range_cm[n] = (s, e)
    cut_blocks_cm = {}
    for n in sorted(cm_methods, key=lambda nn: -name_to_range_cm[nn][0]):
        s, e = find_method_lines(
            control_mixin.read_text(),
            class_name="TokenizerControlMixin",
            method_name=n,
        )
        cut_blocks_cm[n] = cut_lines(control_mixin, s, e)

    def strip_typehint(body: str) -> str:
        return body.replace("self: TokenizerManager,", "self,").replace(
            "self: TokenizerManager\n", "self\n"
        )

    bodies = [
        strip_typehint(cut_blocks_cm["load_lora_adapter"]),
        strip_typehint(cut_blocks_cm["load_lora_adapter_from_tensors"]),
        strip_typehint(cut_blocks_cm["unload_lora_adapter"]),
        strip_typehint(cut_blocks_cm["_unload_lora_adapter_locked"]),
        cut_blocks_tm["_validate_and_resolve_lora"],
        cut_blocks_tm["_resolve_lora_path"],
    ]

    lc_text = lc.read_text()
    lc_text = lc_text.replace(
        "from dataclasses import dataclass, field\n",
        "from dataclasses import dataclass, field\n\n" + EXTRA_IMPORTS,
    )
    lc.write_text(lc_text.rstrip() + "\n\n" + "\n\n".join(b.rstrip() for b in bodies) + "\n")

    # Caller updates.
    text = tm.read_text()
    text = text.replace(
        "self._validate_and_resolve_lora(",
        "self.lora_controller._validate_and_resolve_lora(",
    )
    text = text.replace(
        "self._resolve_lora_path(",
        "self.lora_controller._resolve_lora_path(",
    )
    text = re.sub(r"\bself\.lora_registry\b", "self.lora_controller.lora_registry", text)
    text = re.sub(r"\bself\.lora_update_lock\b", "self.lora_controller.lora_update_lock", text)
    text = re.sub(r"\bself\.lora_ref_cache\b", "self.lora_controller.lora_ref_cache", text)
    tm.write_text(text)

    # Entrypoint callers.
    engine = wt / "python/sglang/srt/entrypoints/engine.py"
    http_server = wt / "python/sglang/srt/entrypoints/http_server.py"
    for f in [engine, http_server]:
        text = f.read_text()
        text = text.replace(
            "tokenizer_manager.load_lora_adapter_from_tensors(",
            "tokenizer_manager.lora_controller.load_lora_adapter_from_tensors(",
        )
        text = text.replace(
            "tokenizer_manager.load_lora_adapter(",
            "tokenizer_manager.lora_controller.load_lora_adapter(",
        )
        text = text.replace(
            "tokenizer_manager.unload_lora_adapter(",
            "tokenizer_manager.lora_controller.unload_lora_adapter(",
        )
        text = re.sub(
            r"\btokenizer_manager\.lora_registry\b",
            "tokenizer_manager.lora_controller.lora_registry",
            text,
        )
        f.write_text(text)


if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        area_branch=AREA_BRANCH,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
