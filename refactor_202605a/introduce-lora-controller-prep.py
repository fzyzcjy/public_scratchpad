#!/usr/bin/env python3
"""Prep: LoraController skeleton + composition + in-place staticmethod conversion + caller rewrites."""

# /// script
# requires-python = ">=3.10"
# dependencies = ["typer"]
# ///

import ast
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from _helpers import insert_after, replace_call_site
from _runner import run_pr

ID = "introduce-lora-controller-prep"
SUBJECT = "Stage LoRA load/unload for handoff to LoraController"
BODY = """\
Per MECH_COMMIT_SPLIT §"拆 class 场景": prep does ALL semantic work.

Builds LoraController skeleton (with __post_init__ replacing init_lora);
wires composition in TM.__init__ + plugs update_lora_adapter_communicator
in after init_communicators; converts 6 lora methods to @staticmethod with
self: "LoraController" annotation in their source class (4 in
TokenizerControlMixin, 2 in TokenizerManager); rewrites cross-calls inside
the lora cluster (self.<other_lora>(...) → TokenizerManager.<other_lora>(self, ...));
rewrites TM facade callers + entrypoint callers to
``TokenizerManager.<method>(self.lora_controller, ...)`` form. Methods stay
on their source class in this commit; the next commit's pure cut/paste +
caller prefix replacement completes the move.
"""
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
class LoraController:
    """LoRA load/unload/LRU + per-request acquire/release."""

    server_args: ServerArgs
    auto_create_handle_loop: Callable[[], None]
    update_lora_adapter_communicator: Any = None  # set after facade.init_communicators
    lora_registry: LoRARegistry = None  # type: ignore[assignment]
    lora_update_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    lora_ref_cache: Dict[str, LoRARef] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Initialize the `LoRARegistry` with initial LoRA adapter paths provided in `server_args`.
        # The registry dynamically updates as adapters are loaded / unloaded during runtime. It
        # serves as the source of truth for available adapters and maps user-friendly LoRA names
        # to internally used unique LoRA IDs.
        self.lora_registry = LoRARegistry(self.server_args.lora_paths)
        # A cache for mapping the lora_name for LoRA adapters that have been loaded at any
        # point to their latest LoRARef objects, so that they can be
        # dynamically loaded if needed for inference.
        if self.server_args.lora_paths is not None:
            for lora_ref in self.server_args.lora_paths:
                self.lora_ref_cache[lora_ref.lora_name] = lora_ref
'''


def _method_ranges(text: str, class_name: str, method_name: str):
    tree = ast.parse(text)
    func_types = (ast.FunctionDef, ast.AsyncFunctionDef)
    for cls in ast.walk(tree):
        if isinstance(cls, ast.ClassDef) and cls.name == class_name:
            for i, node in enumerate(cls.body):
                if isinstance(node, func_types) and node.name == method_name:
                    start = node.lineno - 1
                    if node.decorator_list:
                        start = node.decorator_list[0].lineno - 1
                    body_start = node.body[0].lineno - 1
                    if i + 1 < len(cls.body):
                        end = cls.body[i + 1].lineno - 1
                        nxt = cls.body[i + 1]
                        if isinstance(nxt, func_types + (ast.ClassDef,)) and nxt.decorator_list:
                            end = nxt.decorator_list[0].lineno - 1
                    else:
                        end = node.end_lineno
                    return start, body_start, end
    raise ValueError(f"{class_name}.{method_name} not found")


# Replacement headers: @staticmethod + self: "LoraController" typing. Parameter list otherwise
# unchanged. Each header includes the original `async def` and full parameter signature.
NEW_HEADERS = {
    "_unload_lora_adapter_locked": '''    @staticmethod
    async def _unload_lora_adapter_locked(
        self: "LoraController",
        obj: UnloadLoRAAdapterReqInput,
    ) -> UnloadLoRAAdapterReqOutput:
''',
    "load_lora_adapter": '''    @staticmethod
    async def load_lora_adapter(
        self: "LoraController",
        obj: LoadLoRAAdapterReqInput,
        _: Optional[fastapi.Request] = None,
    ) -> LoadLoRAAdapterReqOutput:
''',
    "load_lora_adapter_from_tensors": '''    @staticmethod
    async def load_lora_adapter_from_tensors(
        self: "LoraController",
        obj: LoadLoRAAdapterFromTensorsReqInput,
        _: Optional[fastapi.Request] = None,
    ) -> LoadLoRAAdapterFromTensorsReqOutput:
''',
    "unload_lora_adapter": '''    @staticmethod
    async def unload_lora_adapter(
        self: "LoraController",
        obj: UnloadLoRAAdapterReqInput,
        _: Optional[fastapi.Request] = None,
    ) -> UnloadLoRAAdapterReqOutput:
''',
    "_validate_and_resolve_lora": '''    @staticmethod
    async def _validate_and_resolve_lora(
        self: "LoraController",
        obj: Union[GenerateReqInput, EmbeddingReqInput],
    ) -> None:
''',
    "_resolve_lora_path": '''    @staticmethod
    async def _resolve_lora_path(
        self: "LoraController",
        obj: Union[GenerateReqInput, EmbeddingReqInput],
    ):
''',
}


def _retype_method(text: str, class_name: str, method_name: str) -> str:
    """Replace a method's header with @staticmethod + self: "LoraController" typing.
    Body bytes preserved verbatim. Rewrites cross-calls between the 6 lora methods.
    """
    s, body_s, e = _method_ranges(text, class_name, method_name)
    lines = text.splitlines(keepends=True)
    body_text = "".join(lines[body_s:e])

    # Cross-call rewrites within the lora cluster: self.<other_lora>(...) on the
    # LoraController self → TokenizerManager.<other_lora>(self, ...). This is the
    # prep-stage "class-qualified call" pattern; commit 2 reduces them to
    # self.<other_lora>(...) (now an instance method of LoraController) via pure
    # prefix replacement.
    body_text = body_text.replace(
        "await self._unload_lora_adapter_locked(\n",
        "await TokenizerManager._unload_lora_adapter_locked(\n                            self,\n",
    )
    body_text = body_text.replace(
        "return await self._unload_lora_adapter_locked(obj)",
        "return await TokenizerManager._unload_lora_adapter_locked(self, obj)",
    )
    body_text = body_text.replace(
        "await self._resolve_lora_path(obj)",
        "await TokenizerManager._resolve_lora_path(self, obj)",
    )
    body_text = body_text.replace(
        "load_result = await self.load_lora_adapter(\n",
        "load_result = await TokenizerManager.load_lora_adapter(\n                self,\n",
    )

    return "".join(lines[:s]) + NEW_HEADERS[method_name] + body_text + "".join(lines[e:])


def transform(wt: Path) -> None:
    tm = wt / "python/sglang/srt/managers/tokenizer_manager.py"
    control_mixin = wt / "python/sglang/srt/managers/tokenizer_control_mixin.py"
    new = wt / "python/sglang/srt/managers/lora_controller.py"
    new.write_text(SKELETON)

    # ---- TM: import + composition wiring + init_lora removal + communicator plug-in ----
    text = tm.read_text()
    text = insert_after(
        text,
        anchor="from sglang.srt.managers.tokenizer_control_mixin import TokenizerControlMixin\n",
        addition="from sglang.srt.managers.lora_controller import LoraController\n",
    )

    # Composition wiring: replace init_lora() call with LoraController(...) construction
    # in the same slot (init_weight_update → here → init_disaggregation).
    text = replace_call_site(
        text,
        old=(
            "        # Init LoRA status\n"
            "        self.init_lora()\n"
        ),
        new=(
            "        # Init LoRA controller\n"
            "        self.lora_controller = LoraController(\n"
            "            server_args=self.server_args,\n"
            "            auto_create_handle_loop=self.auto_create_handle_loop,\n"
            "        )\n"
        ),
    )

    # Plug the communicator into the controller after init_communicators() has run.
    text = replace_call_site(
        text,
        old=(
            "        self.init_communicators(self.server_args)\n"
        ),
        new=(
            "        self.init_communicators(self.server_args)\n"
            "        self.lora_controller.update_lora_adapter_communicator = (\n"
            "            self.update_lora_adapter_communicator\n"
            "        )\n"
        ),
    )

    # Remove the now-dead init_lora method body from TM (LoraController.__post_init__ owns this).
    s, _, e = _method_ranges(text, "TokenizerManager", "init_lora")
    lines = text.splitlines(keepends=True)
    text = "".join(lines[:s]) + "".join(lines[e:])

    # Convert TM's 2 lora methods to @staticmethod with self: "LoraController" typing.
    text = _retype_method(text, "TokenizerManager", "_resolve_lora_path")
    text = _retype_method(text, "TokenizerManager", "_validate_and_resolve_lora")

    # Caller rewrites in TM facade.
    text = replace_call_site(
        text,
        old="            await self._validate_and_resolve_lora(obj)\n",
        new="            await TokenizerManager._validate_and_resolve_lora(self.lora_controller, obj)\n",
    )
    # External readers of LoraController fields (outside the 6 retyped methods) in TM:
    # both call sites read self.lora_registry.release(state.obj.lora_id) inside
    # _wait_one_response / handle_loop. Rewire to self.lora_controller.lora_registry.
    text = text.replace(
        "self.lora_registry.release(state.obj.lora_id)",
        "self.lora_controller.lora_registry.release(state.obj.lora_id)",
    )

    tm.write_text(text)

    # ---- TokenizerControlMixin: convert 4 lora methods ----
    cm_text = control_mixin.read_text()
    # Bottom-up: _unload_lora_adapter_locked (smallest line range) appears first; retype in any order
    # but each retype recomputes ranges from the freshly-read text, so safest is to do them one at a time.
    for name in (
        "_unload_lora_adapter_locked",
        "load_lora_adapter",
        "load_lora_adapter_from_tensors",
        "unload_lora_adapter",
    ):
        cm_text = _retype_method(cm_text, "TokenizerControlMixin", name)
    control_mixin.write_text(cm_text)

    # ---- Entrypoint callers: <prefix>.tokenizer_manager.<method>(...) ----
    # Prep: rewrite to class-qualified TokenizerManager.<method>(<prefix>.tokenizer_manager.lora_controller, ...).
    # Move step will reduce to <prefix>.tokenizer_manager.lora_controller.<method>(...).
    # Anchor on each owning-prefix to avoid clobbering the leading `<prefix>.`.
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
                f"{prefix}.{method}(",
                f"TokenizerManager.{method}({prefix}.lora_controller, ",
            )
        # External read of lora_registry in http_server's /v1/models lister.
        ep_text = ep_text.replace(
            f"{prefix}.lora_registry",
            f"{prefix}.lora_controller.lora_registry",
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
