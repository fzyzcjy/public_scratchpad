#!/usr/bin/env python3
"""Move (pure cut/paste): LoraController methods relocate from TM + ControlMixin to target class."""

# /// script
# requires-python = ">=3.10"
# dependencies = ["typer"]
# ///

import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from _helpers import cut_lines, find_method_lines
from _runner import run_pr

ID = "introduce-lora-controller-move"
SUBJECT = "Move LoraController methods: pure cut/paste + caller prefix replacement"
BODY = """\
Pure physical move per MECH_COMMIT_SPLIT. Cut the 6 @staticmethod lora
methods (4 from TokenizerControlMixin: load_lora_adapter,
load_lora_adapter_from_tensors, unload_lora_adapter,
_unload_lora_adapter_locked; 2 from TokenizerManager:
_validate_and_resolve_lora, _resolve_lora_path); paste into LoraController
(drop @staticmethod, replace ``self: "LoraController"`` → plain ``self``).
Caller prefix replacement:
``TokenizerManager.<method>(self.lora_controller, ...)`` →
``self.lora_controller.<method>(...)``; ditto entrypoints.
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


def _strip_static_prefix(body: str) -> str:
    """Remove @staticmethod decorator, replace ``self: "LoraController",`` → ``self,``,
    and rewrite intra-cluster cross-calls (``TokenizerManager.<m>(self, ...)`` → ``self.<m>(...)``).
    Both transforms are pure prefix replacement — body bytes are otherwise unchanged.
    """
    body = body.replace("    @staticmethod\n", "", 1)
    body = body.replace('self: "LoraController",', "self,")
    # Intra-cluster cross-call prefix replacement.
    body = body.replace(
        "await TokenizerManager._unload_lora_adapter_locked(\n                            self,\n",
        "await self._unload_lora_adapter_locked(\n",
    )
    body = body.replace(
        "return await TokenizerManager._unload_lora_adapter_locked(self, obj)",
        "return await self._unload_lora_adapter_locked(obj)",
    )
    body = body.replace(
        "await TokenizerManager._resolve_lora_path(self, obj)",
        "await self._resolve_lora_path(obj)",
    )
    body = body.replace(
        "load_result = await TokenizerManager.load_lora_adapter(\n                self,\n",
        "load_result = await self.load_lora_adapter(\n",
    )
    return body


def transform(wt: Path) -> None:
    tm = wt / "python/sglang/srt/managers/tokenizer_manager.py"
    control_mixin = wt / "python/sglang/srt/managers/tokenizer_control_mixin.py"
    lc = wt / "python/sglang/srt/managers/lora_controller.py"

    # Cut 2 methods from TM, bottom-up (highest start line first).
    tm_methods = ("_validate_and_resolve_lora", "_resolve_lora_path")
    name_to_range = {}
    for n in tm_methods:
        s, e = find_method_lines(tm.read_text(), class_name="TokenizerManager", method_name=n)
        name_to_range[n] = s
    cut_blocks_tm = {}
    for n in sorted(tm_methods, key=lambda nn: -name_to_range[nn]):
        s, e = find_method_lines(tm.read_text(), class_name="TokenizerManager", method_name=n)
        cut_blocks_tm[n] = cut_lines(tm, s, e)

    # Cut 4 methods from control_mixin, bottom-up.
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
        name_to_range_cm[n] = s
    cut_blocks_cm = {}
    for n in sorted(cm_methods, key=lambda nn: -name_to_range_cm[nn]):
        s, e = find_method_lines(
            control_mixin.read_text(),
            class_name="TokenizerControlMixin",
            method_name=n,
        )
        cut_blocks_cm[n] = cut_lines(control_mixin, s, e)

    # Assemble in canonical order. Body bytes unchanged except @staticmethod stripped + self typing.
    bodies = [
        _strip_static_prefix(cut_blocks_cm["load_lora_adapter"]),
        _strip_static_prefix(cut_blocks_cm["load_lora_adapter_from_tensors"]),
        _strip_static_prefix(cut_blocks_cm["unload_lora_adapter"]),
        _strip_static_prefix(cut_blocks_cm["_unload_lora_adapter_locked"]),
        _strip_static_prefix(cut_blocks_tm["_validate_and_resolve_lora"]),
        _strip_static_prefix(cut_blocks_tm["_resolve_lora_path"]),
    ]

    lc_text = lc.read_text()
    lc_text = lc_text.replace(
        "from dataclasses import dataclass, field\n",
        "from dataclasses import dataclass, field\n\n" + EXTRA_IMPORTS,
    )
    lc.write_text(lc_text.rstrip() + "\n\n" + "\n".join(b.rstrip() + "\n" for b in bodies))

    # ---- Caller prefix replacement in TM facade ----
    # TokenizerManager.<method>(self.lora_controller, ... ) → self.lora_controller.<method>(...)
    # Cross-call sites (now removed from TM) and the validate-and-resolve site at line 551 remain.
    text = tm.read_text()
    text = text.replace(
        "TokenizerManager._validate_and_resolve_lora(self.lora_controller, ",
        "self.lora_controller._validate_and_resolve_lora(",
    )
    tm.write_text(text)

    # ---- Caller prefix replacement in entrypoints ----
    entrypoint_specs = [
        (
            wt / "python/sglang/srt/entrypoints/engine.py",
            "self.tokenizer_manager",
        ),
        (
            wt / "python/sglang/srt/entrypoints/http_server.py",
            "_global_state.tokenizer_manager",
        ),
    ]
    for ep, prefix in entrypoint_specs:
        ep_text = ep.read_text()
        for method in (
            "load_lora_adapter_from_tensors",
            "load_lora_adapter",
            "unload_lora_adapter",
        ):
            ep_text = ep_text.replace(
                f"TokenizerManager.{method}({prefix}.lora_controller, ",
                f"{prefix}.lora_controller.{method}(",
            )
        ep.write_text(ep_text)



if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        area_branch=AREA_BRANCH,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
