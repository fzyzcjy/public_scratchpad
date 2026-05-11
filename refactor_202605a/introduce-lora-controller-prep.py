#!/usr/bin/env python3
"""Prep: LoraController skeleton + composition wiring."""

# /// script
# requires-python = ">=3.10"
# dependencies = ["typer"]
# ///

import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from _helpers import insert_after, replace_call_site
from _runner import run_pr

ID = "introduce-lora-controller-prep"
SUBJECT = "Prep LoraController: skeleton + composition wiring"
BODY = "Per MECH_COMMIT_SPLIT: skeleton + composition only."
AREA = "mech_tokenizer_manager"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


SKELETON = '''from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional

from sglang.srt.lora.lora_registry import LoRARef, LoRARegistry
from sglang.srt.server_args import ServerArgs


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
    new = wt / "python/sglang/srt/managers/lora_controller.py"
    new.write_text(SKELETON)

    text = tm.read_text()
    text = insert_after(
        text,
        anchor="from sglang.srt.managers.tokenizer_control_mixin import TokenizerControlMixin\n",
        addition=(
            "from sglang.srt.managers.lora_controller import (\n"
            "    LoraController,\n"
            "    LoraControllerConfig,\n"
            ")\n"
        ),
    )
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
            "                enable_lora=self.server_args.enable_lora,\n"
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
    # Drop init_lora() call from facade (skeleton's __post_init__ handles it).
    text = text.replace(
        "        # Init LoRA status\n"
        "        self.init_lora()\n"
        "\n",
        "",
    )
    tm.write_text(text)


if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        area_branch=AREA_BRANCH,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
