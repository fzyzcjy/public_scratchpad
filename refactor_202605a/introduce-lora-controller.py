#!/usr/bin/env python3
"""Introduce LoraController owner class."""

# /// script
# requires-python = ">=3.10"
# dependencies = ["typer"]
# ///

import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from _helpers import (
    cut_lines,
    find_method_lines,
    insert_after,
    replace_call_site,
)
from _runner import run_pr

ID = "introduce-lora-controller"
SUBJECT = "Introduce LoraController and move lora load/unload methods"
BODY = """\
Move 7 lora-related methods (init_lora's field setup +
load_lora_adapter, load_lora_adapter_from_tensors, unload_lora_adapter,
_unload_lora_adapter_locked, _validate_and_resolve_lora,
_resolve_lora_path) from TokenizerManager + TokenizerControlMixin into a
new @dataclass(slots=True, kw_only=True) LoraController in
managers/control/lora_controller.py.

frozen=False because lora_ref_cache mutates over the lifecycle.
update_lora_adapter_communicator is injected from facade post-init.

Per md ch3.1: method names retained; LRU evict helper extraction is Ch2 PR2;
release_for_request public API is Ch2 PR3; method renames are Ch2 PR4.
"""
AREA = "mech_tokenizer_manager"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


HEADER = '''from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional, Union

import fastapi

from sglang.srt.lora.lora_registry import LoRARef, LoRARegistry
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
from sglang.srt.server_args import ServerArgs

logger = logging.getLogger(__name__)


@dataclass(slots=True, kw_only=True)
class LoraControllerConfig:
    enable_lora: bool
    max_loaded_loras: Optional[int]
    dp_size: int
    initial_lora_paths: Optional[list]


@dataclass(slots=True, kw_only=True)
class LoraController:
    """LoRA load/unload/LRU + per-request acquire/release."""

    server_args: ServerArgs
    auto_create_handle_loop: Callable[[], None]
    update_lora_adapter_communicator: Any = None  # set after facade.init_communicators
    config: LoraControllerConfig = None  # type: ignore[assignment]
    lora_registry: LoRARegistry = None  # type: ignore[assignment]
    lora_update_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    lora_ref_cache: Dict[str, LoRARef] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.lora_registry = LoRARegistry(self.server_args.lora_paths)
        if self.server_args.lora_paths is not None:
            for lora_ref in self.server_args.lora_paths:
                self.lora_ref_cache[lora_ref.lora_name] = lora_ref

'''


def transform(wt: Path) -> None:
    tm = wt / "python/sglang/srt/managers/tokenizer_manager.py"
    control_mixin = wt / "python/sglang/srt/managers/tokenizer_control_mixin.py"
    new = wt / "python/sglang/srt/managers/control/lora_controller.py"

    # Cut from tokenizer_manager: init_lora, _validate_and_resolve_lora, _resolve_lora_path.
    # bottom-up.
    tm_methods = ("init_lora", "_validate_and_resolve_lora", "_resolve_lora_path")
    name_to_range = {}
    for n in tm_methods:
        s, e = find_method_lines(tm.read_text(), class_name="TokenizerManager", method_name=n)
        name_to_range[n] = (s, e)
    cut_blocks_tm = {}
    for n in sorted(tm_methods, key=lambda nn: -name_to_range[nn][0]):
        s, e = find_method_lines(tm.read_text(), class_name="TokenizerManager", method_name=n)
        cut_blocks_tm[n] = cut_lines(tm, s, e)

    # Cut from control_mixin: 4 methods.
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

    # Strip ``self: TokenizerManager`` -> ``self`` in moved control_mixin bodies.
    def strip_typehint(body: str) -> str:
        return body.replace("self: TokenizerManager,", "self,").replace(
            "self: TokenizerManager\n", "self\n"
        )

    # init_lora body becomes part of __post_init__ already in HEADER -- discard the cut.
    bodies = []
    bodies.append(strip_typehint(cut_blocks_cm["load_lora_adapter"]))
    bodies.append(strip_typehint(cut_blocks_cm["load_lora_adapter_from_tensors"]))
    bodies.append(strip_typehint(cut_blocks_cm["unload_lora_adapter"]))
    bodies.append(strip_typehint(cut_blocks_cm["_unload_lora_adapter_locked"]))
    bodies.append(cut_blocks_tm["_validate_and_resolve_lora"])
    bodies.append(cut_blocks_tm["_resolve_lora_path"])
    new.write_text(HEADER + "\n\n".join(b.rstrip() for b in bodies) + "\n")

    # ===== Update tokenizer_manager.py =====
    text = tm.read_text()

    text = insert_after(
        text,
        anchor="from sglang.srt.managers.tokenizer_control_mixin import TokenizerControlMixin\n",
        addition=(
            "from sglang.srt.managers.control.lora_controller import (\n"
            "    LoraController,\n"
            "    LoraControllerConfig,\n"
            ")\n"
        ),
    )

    # Wire construction (after weight_disk_update_controller).
    text = replace_call_site(
        text,
        old=(
            "        # Session controller\n"
            "        self.session_controller = SessionController(\n"
        ),
        new=(
            "        # Lora controller\n"
            "        self.lora_controller = LoraController(\n"
            "            server_args=self.server_args,\n"
            "            auto_create_handle_loop=self.auto_create_handle_loop,\n"
            "            update_lora_adapter_communicator=self.update_lora_adapter_communicator,\n"
            "            config=LoraControllerConfig(\n"
            "                enable_lora=bool(self.server_args.lora_paths),\n"
            "                max_loaded_loras=self.server_args.max_loaded_loras,\n"
            "                dp_size=self.server_args.dp_size,\n"
            "                initial_lora_paths=self.server_args.lora_paths,\n"
            "            ),\n"
            "        )\n"
            "\n"
            "        # Session controller\n"
            "        self.session_controller = SessionController(\n"
        ),
    )

    # Drop the now-orphaned ``self.init_lora()`` call from facade __init__
    # (the method body lives in LoraController.__post_init__ now).
    text = text.replace(
        "        # Init LoRA status\n"
        "        self.init_lora()\n"
        "\n",
        "",
    )

    # Caller updates inside facade.
    import re as _re
    text = text.replace(
        "self._validate_and_resolve_lora(",
        "self.lora_controller._validate_and_resolve_lora(",
    )
    text = text.replace(
        "self._resolve_lora_path(",
        "self.lora_controller._resolve_lora_path(",
    )
    text = _re.sub(r"\bself\.lora_registry\b", "self.lora_controller.lora_registry", text)
    text = _re.sub(r"\bself\.lora_update_lock\b", "self.lora_controller.lora_update_lock", text)
    text = _re.sub(r"\bself\.lora_ref_cache\b", "self.lora_controller.lora_ref_cache", text)

    tm.write_text(text)

    # ===== entrypoint callers =====
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
        # tokenizer_manager.lora_registry attribute access -> via lora_controller
        text = _re.sub(
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
