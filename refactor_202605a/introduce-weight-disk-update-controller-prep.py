#!/usr/bin/env python3
"""Prep: WeightDiskUpdateController skeleton + composition + in-place staticmethod conversion + caller rewrites."""

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

ID = "introduce-weight-disk-update-controller-prep"
SUBJECT = "Stage disk-based weight reload for handoff to WeightDiskUpdateController"
BODY = """\
Per MECH_COMMIT_SPLIT §"拆 class 场景": prep does ALL semantic work.

Builds WeightDiskUpdateController skeleton (with __post_init__ that flips
initial_weights_loaded per config and registers a lambda forwarder for
UpdateWeightFromDiskReqOutput on the shared dispatcher). Wires composition
in TM.__init__; drops the facade fields ``initial_weights_loaded`` and
``model_update_result`` from ``init_weight_update`` (they now live on the
controller). Converts 4 TM methods (``update_weights_from_disk``,
``_update_model_path_info``, ``_wait_for_model_update_from_disk``,
``_handle_update_weights_from_disk_req_output``) and 1
TokenizerControlMixin method (``_update_weight_version_if_provided``) to
``@staticmethod`` with ``self: "WeightDiskUpdateController"`` annotation,
applying body rewrites (``self.server_args.dp_size`` →
``self.config.dp_size``; ``self.served_model_name=`` /
``self.model_path=`` re-routed through ``server_args``) and cross-call
rewrites (intra-controller calls become ``TokenizerManager.<m>(self, ...)``
/ ``TokenizerControlMixin._update_weight_version_if_provided(self, ...)``).
Rewires 3 sibling mixin callers (``update_weights_from_distributed`` /
``_tensor`` / ``_ipc``) and external entrypoints (engine.py /
http_server.py — both the ``update_weights_from_disk`` call and the
``initial_weights_loaded`` reads / writes) to the class-qualified form.
Methods stay on their source class in this commit; the next commit's
pure cut/paste + lambda → direct-ref flip + caller prefix replacement
completes the move.
"""
AREA = "mech_tokenizer_manager"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


SKELETON = '''from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, List, Optional

from sglang.srt.server_args import ServerArgs
from sglang.srt.utils.aio_rwlock import RWLock


@dataclass(slots=True, kw_only=True)
class WeightDiskUpdateController:
    """update_weights_from_disk endpoint + UpdateWeightFromDiskReqOutput dispatcher handler."""

    send_to_scheduler: Any
    abort_request: Callable[..., None]
    is_pause_getter: Callable[[], bool]
    is_pause_cond: asyncio.Condition
    model_update_lock: RWLock
    server_args: ServerArgs
    auto_create_handle_loop: Callable[[], None]
    initial_weights_loaded: bool = True
    model_update_result: Optional[Awaitable[Any]] = None
    model_update_tmp: List[Any] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.server_args.checkpoint_engine_wait_weights_before_ready:
            self.initial_weights_loaded = False
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


# Replacement headers: @staticmethod + self: "WeightDiskUpdateController" typing.
NEW_HEADERS = {
    "update_weights_from_disk": '''    @staticmethod
    async def update_weights_from_disk(
        self: "WeightDiskUpdateController",
        obj: UpdateWeightFromDiskReqInput,
        request: Optional[fastapi.Request] = None,
    ) -> Tuple[bool, str]:
''',
    "_update_model_path_info": '''    @staticmethod
    def _update_model_path_info(self: "WeightDiskUpdateController", model_path: str, load_format: str):
''',
    "_wait_for_model_update_from_disk": '''    @staticmethod
    async def _wait_for_model_update_from_disk(
        self: "WeightDiskUpdateController", obj: UpdateWeightFromDiskReqInput
    ) -> Tuple[bool, str]:
''',
    "_handle_update_weights_from_disk_req_output": '''    @staticmethod
    def handle_update_weights_from_disk_req_output(self: "WeightDiskUpdateController", recv_obj):
''',
    "_update_weight_version_if_provided": '''    @staticmethod
    def _update_weight_version_if_provided(
        self: "WeightDiskUpdateController", weight_version: Optional[str]
    ) -> None:
''',
}


def _rewrite_body(body_text: str) -> str:
    """Apply body rewrites: facade-field re-routing + intra-cluster cross-call class-qualification."""
    # Field re-routing onto server_args (controller has no served_model_name /
    # model_path attrs; ServerArgs owns them). server_args reads themselves stay.
    body_text = body_text.replace(
        "self.served_model_name = ", "self.server_args.served_model_name = "
    )
    body_text = body_text.replace(
        "self.model_path = model_path", "self.server_args.model_path = model_path"
    )

    # PauseController stayed unextracted (too coupled with other TM state to
    # be a clean independent class). The 3 fields ``abort_request`` /
    # ``is_pause`` / ``is_pause_cond`` that WDU needs are injected as Callable
    # kwargs / shared refs on WeightDiskUpdateController. Body forms:
    #   self.abort_request(abort_all=True)  →  self.abort_request(abort_all=True)
    #     (same call; ``abort_request`` is now a Callable field on WDU, not TM's method)
    #   self.is_pause                       →  self.is_pause_getter()
    #   self.is_pause_cond                  →  self.is_pause_cond (shared ref, same name)
    body_text = body_text.replace("self.is_pause_cond", "self.is_pause_cond")
    body_text = body_text.replace(
        "is_paused = self.is_pause", "is_paused = self.is_pause_getter()"
    )

    # Cross-call rewrites within the wd-controller cluster (4 TM methods + 1 mixin
    # method): self.<peer>(...) on the WeightDiskUpdateController self →
    # <SourceClass>.<peer>(self, ...). Move-step reduces these to self.<peer>(...)
    # (now an instance method of WeightDiskUpdateController) via pure prefix replace.
    body_text = body_text.replace(
        "await self._wait_for_model_update_from_disk(obj)",
        "await TokenizerManager._wait_for_model_update_from_disk(self, obj)",
    )
    body_text = body_text.replace(
        "self._update_model_path_info(obj.model_path, obj.load_format)",
        "TokenizerManager._update_model_path_info(self, obj.model_path, obj.load_format)",
    )
    body_text = body_text.replace(
        "self._update_weight_version_if_provided(obj.weight_version)",
        "TokenizerControlMixin._update_weight_version_if_provided(self, obj.weight_version)",
    )
    return body_text


def _retype_method(text: str, class_name: str, method_name: str) -> str:
    """Replace a method's header with @staticmethod + self: "WeightDiskUpdateController" typing.
    Applies _rewrite_body to body bytes.
    """
    s, body_s, e = _method_ranges(text, class_name, method_name)
    lines = text.splitlines(keepends=True)
    body_text = _rewrite_body("".join(lines[body_s:e]))
    return "".join(lines[:s]) + NEW_HEADERS[method_name] + body_text + "".join(lines[e:])


def transform(wt: Path) -> None:
    tm = wt / "python/sglang/srt/managers/tokenizer_manager.py"
    control_mixin = wt / "python/sglang/srt/managers/tokenizer_control_mixin.py"
    new = wt / "python/sglang/srt/managers/tokenizer_manager_components/weight_disk_update_controller.py"
    new.write_text(SKELETON)

    # ---- TM: drop facade fields + import + composition wiring ----
    text = tm.read_text()

    # Drop facade fields from init_weight_update. model_update_lock stays --
    # it was already wired into PauseController by introduce-pause-controller-prep,
    # so TM remains its canonical owner; WeightDiskUpdateController receives a
    # shared reference via composition.
    text = replace_call_site(
        text,
        old=(
            "    def init_weight_update(self):\n"
            "        # Initial weights status\n"
            "        self.initial_weights_loaded = True\n"
            "        if self.server_args.checkpoint_engine_wait_weights_before_ready:\n"
            "            self.initial_weights_loaded = False\n"
            "\n"
            "        # Weight updates\n"
            "        # The event to notify the weight sync is finished.\n"
            "        self.model_update_lock = RWLock()\n"
            "        self.model_update_result: Optional[Awaitable[UpdateWeightFromDiskReqOutput]] = (\n"
            "            None\n"
            "        )\n"
        ),
        new=(
            "    def init_weight_update(self):\n"
            "        # Lock guarding weight-sync updates against in-flight requests.\n"
            "        self.model_update_lock = RWLock()\n"
        ),
    )

    text = insert_after(
        text,
        anchor="from sglang.srt.managers.tokenizer_control_mixin import TokenizerControlMixin\n",
        addition=(
            "from sglang.srt.managers.tokenizer_manager_components.weight_disk_update_controller import (\n"
            "    WeightDiskUpdateController,\n"
            "    WeightDiskUpdateControllerConfig,\n"
            ")\n"
        ),
    )

    # Composition wiring. The controller's __post_init__ registers the dispatcher
    # forwarder, so no separate dispatcher-mutation line is needed here.
    text = replace_call_site(
        text,
        old=(
            "        # Session controller\n"
            "        self.session_controller = SessionController(\n"
        ),
        new=(
            "        # Weight disk update controller\n"
            "        self.weight_disk_update_controller = WeightDiskUpdateController(\n"
            "            send_to_scheduler=self.send_to_scheduler,\n"
            "            abort_request=self.abort_request,\n"
            "            is_pause_getter=lambda: self.is_pause,\n"
            "            is_pause_cond=self.is_pause_cond,\n"
            "            model_update_lock=self.model_update_lock,\n"
            "            server_args=self.server_args,\n"
            "            auto_create_handle_loop=self.auto_create_handle_loop,\n"
            "            config=WeightDiskUpdateControllerConfig(\n"
            "                dp_size=self.server_args.dp_size,\n"
            "                initial_load_format=self.server_args.load_format,\n"
            "                checkpoint_engine_wait_weights_before_ready=self.server_args.checkpoint_engine_wait_weights_before_ready,\n"
            "            ),\n"
            "        )\n"
            "\n"
            "        # Session controller\n"
            "        self.session_controller = SessionController(\n"
        ),
    )

    # Rewrite the UpdateWeightFromDiskReqOutput entry in init_request_dispatcher
    # in place: route through a lambda forwarder calling the @staticmethod
    # (still on TM) with self.weight_disk_update_controller as the self arg.
    # -move flips this to a direct method ref.
    text = replace_call_site(
        text,
        old="                (\n                    UpdateWeightFromDiskReqOutput,\n                    self._handle_update_weights_from_disk_req_output,\n                ),\n",
        new=(
            "                (\n"
            "                    UpdateWeightFromDiskReqOutput,\n"
            "                    lambda x: TokenizerManager.handle_update_weights_from_disk_req_output(\n"
            "                        self.weight_disk_update_controller, x\n"
            "                    ),\n"
            "                ),\n"
        ),
    )

    # ---- TM: convert 4 methods to @staticmethod with self: "WeightDiskUpdateController" typing ----
    for name in (
        "update_weights_from_disk",
        "_update_model_path_info",
        "_wait_for_model_update_from_disk",
        "_handle_update_weights_from_disk_req_output",
    ):
        text = _retype_method(text, "TokenizerManager", name)

    tm.write_text(text)

    # ---- TokenizerControlMixin: convert _update_weight_version_if_provided + rewrite 3 sibling callers ----
    cm_text = control_mixin.read_text()
    cm_text = _retype_method(cm_text, "TokenizerControlMixin", "_update_weight_version_if_provided")

    # The 3 sibling mixin methods (update_weights_from_distributed / _tensor / _ipc)
    # stay on the mixin but their `self._update_weight_version_if_provided(...)`
    # calls must be rewritten to the class-qualified form. Move-step reduces to
    # self.weight_disk_update_controller._update_weight_version_if_provided(...).
    cm_text = cm_text.replace(
        "self._update_weight_version_if_provided(obj.weight_version)",
        "TokenizerControlMixin._update_weight_version_if_provided(self.weight_disk_update_controller, obj.weight_version)",
    )
    control_mixin.write_text(cm_text)

    # ---- Entrypoint callers: tokenizer_manager.update_weights_from_disk(...) ----
    # Prep rewrites to class-qualified form; move flips prefix.
    engine = wt / "python/sglang/srt/entrypoints/engine.py"
    http_server = wt / "python/sglang/srt/entrypoints/http_server.py"

    text = engine.read_text()
    text = text.replace(
        "self.tokenizer_manager.update_weights_from_disk(",
        "TokenizerManager.update_weights_from_disk(self.tokenizer_manager.weight_disk_update_controller, ",
    )
    engine.write_text(text)

    text = http_server.read_text()
    text = text.replace(
        "_global_state.tokenizer_manager.update_weights_from_disk(",
        "TokenizerManager.update_weights_from_disk(_global_state.tokenizer_manager.weight_disk_update_controller, ",
    )
    # Facade-field reads / writes on http_server (initial_weights_loaded was
    # dropped from TM, now lives on the controller).
    text = text.replace(
        "_global_state.tokenizer_manager.initial_weights_loaded",
        "_global_state.tokenizer_manager.weight_disk_update_controller.initial_weights_loaded",
    )
    http_server.write_text(text)


if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        area_branch=AREA_BRANCH,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
