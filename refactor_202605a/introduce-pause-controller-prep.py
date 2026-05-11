#!/usr/bin/env python3
"""Prep: PauseController skeleton + composition wiring + in-place staticmethod conversion + caller rewrites."""

# /// script
# requires-python = ">=3.10"
# dependencies = ["typer"]
# ///

import ast
import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from _helpers import insert_after, replace_call_site
from _runner import run_pr

ID = "introduce-pause-controller-prep"
SUBJECT = "Stage generation pause/abort for handoff to PauseController"
BODY = """\
Per MECH_COMMIT_SPLIT §"拆 class 场景": prep does ALL semantic work.

Builds PauseController skeleton; wires composition in TM.__init__; drops
is_pause / is_pause_cond field initialization from TM (those fields live on
PauseController). Converts 4 methods (pause_generation,
continue_generation, abort_request, _handle_abort_req) to @staticmethod
with ``self: "PauseController"`` annotation in TM; applies body rewrites
(self.enable_metrics -> self.config.enable_metrics, etc.). Adds
__post_init__ that registers AbortReq via a lambda forwarding back to
TokenizerManager._handle_abort_req(self, x) (since the method is still on
TM in this commit). Removes the (AbortReq, self._handle_abort_req) entry
from TM.init_request_dispatcher (registration is now PauseController's
responsibility).

Rewrites every caller to class-qualified form:
- in-class cross-calls inside the 4 methods: ``self.abort_request(...)``
  -> ``TokenizerManager.abort_request(self, ...)``
- TM-internal callers: ``self.is_pause`` -> ``self.pause_controller.is_pause``,
  ``self.abort_request(...)`` ->
  ``TokenizerManager.abort_request(self.pause_controller, ...)``, etc.
- tokenizer_control_mixin.py / multi_tokenizer_mixin.py: same residual rewires.
- entrypoints: ``tokenizer_manager.abort_request(...)`` ->
  ``TokenizerManager.abort_request(tokenizer_manager.pause_controller, ...)``.

Method bodies stay in TM in this commit; the next commit's pure cut/paste
+ caller prefix replacement completes the move.
"""
AREA = "mech_tokenizer_manager"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


SKELETON = '''from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from sglang.srt.managers.io_struct import AbortReq  # noqa: F401  (used in handler signature once method moves in)
from sglang.srt.managers.tokenizer_manager_components.request_state import ReqState
from sglang.srt.utils.aio_rwlock import RWLock


@dataclass(slots=True, kw_only=True)
class PauseControllerConfig:
    enable_metrics: bool
    skip_tokenizer_init: bool
    weight_version: Optional[str]


@dataclass(slots=True, kw_only=True)
class PauseController:
    """Pause / resume / abort state machine + AbortReq dispatcher handler."""

    send_to_scheduler: Any
    rid_to_state: Dict[str, ReqState]
    model_update_lock: RWLock
    metrics_collector: Optional[Any]
    tokenizer: Optional[Any]
    config: PauseControllerConfig
    is_pause: bool = False
    is_pause_cond: asyncio.Condition = field(default_factory=asyncio.Condition)
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


# Replacement headers for each method: @staticmethod + self: "PauseController" typing.
# Async-ness is preserved.
NEW_HEADERS = {
    "abort_request": (
        '    @staticmethod\n'
        '    def abort_request(self: "PauseController", rid: str = "", abort_all: bool = False):\n'
    ),
    "pause_generation": (
        '    @staticmethod\n'
        '    async def pause_generation(self: "PauseController", obj: PauseGenerationReqInput):\n'
    ),
    "continue_generation": (
        '    @staticmethod\n'
        '    async def continue_generation(self: "PauseController", obj: ContinueGenerationReqInput):\n'
    ),
    "_handle_abort_req": (
        '    @staticmethod\n'
        '    def handle_abort_req(self: "PauseController", recv_obj: AbortReq):\n'
    ),
}


def _rewrite_body(body: str) -> str:
    """Body rewrites: TM-attribute access -> PauseController-attribute access."""
    body = body.replace("self.enable_metrics", "self.config.enable_metrics")
    body = body.replace("self.server_args.weight_version", "self.config.weight_version")
    body = body.replace(
        "self.server_args.skip_tokenizer_init", "self.config.skip_tokenizer_init"
    )
    body = body.replace(
        "self.request_metrics_recorder.metrics_collector", "self.metrics_collector"
    )
    # Cross-calls inside the 4-method cluster: in this commit, methods are
    # @staticmethod on TM, so siblings are reached as class-qualified calls
    # with the staticmethod's ``self`` (a PauseController) threaded through.
    body = body.replace(
        "self.abort_request(", "TokenizerManager.abort_request(self, "
    )
    return body


def transform(wt: Path) -> None:
    tm = wt / "python/sglang/srt/managers/tokenizer_manager.py"
    control_mixin = wt / "python/sglang/srt/managers/tokenizer_control_mixin.py"
    multi_mixin = wt / "python/sglang/srt/managers/multi_tokenizer_mixin.py"
    new = wt / "python/sglang/srt/managers/tokenizer_manager_components/pause_controller.py"

    new.write_text(SKELETON)

    text = tm.read_text()

    # Drop is_pause / is_pause_cond from TM.__init__ (they live on PauseController now).
    text = replace_call_site(
        text,
        old=(
            "        self.is_pause = False\n"
            "        self.is_pause_cond = asyncio.Condition()\n"
        ),
        new="",
    )

    # Import PauseController / PauseControllerConfig into TM.
    text = insert_after(
        text,
        anchor="from sglang.srt.managers.tokenizer_control_mixin import TokenizerControlMixin\n",
        addition=(
            "from sglang.srt.managers.tokenizer_manager_components.pause_controller import (\n"
            "    PauseController,\n"
            "    PauseControllerConfig,\n"
            ")\n"
        ),
    )

    # Composition wiring.
    text = replace_call_site(
        text,
        old=(
            "        # Session controller\n"
            "        self.session_controller = SessionController(\n"
        ),
        new=(
            "        # Pause controller\n"
            "        self.pause_controller = PauseController(\n"
            "            send_to_scheduler=self.send_to_scheduler,\n"
            "            rid_to_state=self.rid_to_state,\n"
            "            model_update_lock=self.model_update_lock,\n"
            "            metrics_collector=self.request_metrics_recorder.metrics_collector,\n"
            "            tokenizer=self.tokenizer,\n"
            "            config=PauseControllerConfig(\n"
            "                enable_metrics=self.enable_metrics,\n"
            "                skip_tokenizer_init=self.server_args.skip_tokenizer_init,\n"
            "                weight_version=self.server_args.weight_version,\n"
            "            ),\n"
            "        )\n"
            "\n"
            "        # Session controller\n"
            "        self.session_controller = SessionController(\n"
        ),
    )

    # Rewrite the AbortReq entry in TM's init_request_dispatcher in place: route
    # through a lambda forwarder that calls the @staticmethod (still on TM) with
    # self.pause_controller as the self arg. -move flips this to a direct ref.
    text = replace_call_site(
        text,
        old="                (AbortReq, self._handle_abort_req),\n",
        new=(
            "                (\n"
            "                    AbortReq,\n"
            "                    lambda x: TokenizerManager.handle_abort_req(\n"
            "                        self.pause_controller, x\n"
            "                    ),\n"
            "                ),\n"
        ),
    )

    # Convert the 4 methods to @staticmethod with self: "PauseController" typing.
    # Apply body rewrites in-place. Body stays in TM class. Iterate bottom-up so
    # earlier line numbers stay valid; recompute ranges on each pass since text
    # mutates between iterations.
    for method_name in ("_handle_abort_req", "continue_generation", "pause_generation", "abort_request"):
        s, body_s, e = _method_ranges(text, "TokenizerManager", method_name)
        lines = text.splitlines(keepends=True)
        body_text = "".join(lines[body_s:e])
        body_text = _rewrite_body(body_text)
        new_method = NEW_HEADERS[method_name] + body_text
        text = "".join(lines[:s]) + new_method + "".join(lines[e:])

    # TM-internal callers OUTSIDE the 4-method cluster: rewire self.is_pause /
    # self.is_pause_cond -> via self.pause_controller; self.abort_request(...) ->
    # TokenizerManager.abort_request(self.pause_controller, ...).
    def rewire_external(t: str) -> str:
        t = re.sub(r"\bself\.is_pause_cond\b", "self.pause_controller.is_pause_cond", t)
        t = re.sub(r"\bself\.is_pause\b", "self.pause_controller.is_pause", t)
        t = re.sub(
            r"\bself\.abort_request\(",
            "TokenizerManager.abort_request(self.pause_controller, ",
            t,
        )
        return t

    # Split TM into "inside the 4 retyped methods" vs "everything else"; only the
    # latter gets external-style rewires. The retyped methods already had their
    # in-class cross-calls handled by _rewrite_body.
    tm_lines = text.splitlines(keepends=True)
    retyped_ranges = []
    # NEW_HEADERS keys are pre-rename method names; `_handle_abort_req` was
    # privacy-flipped to `handle_abort_req` by the retype loop above.
    _renamed = {"_handle_abort_req": "handle_abort_req"}
    for method_name in NEW_HEADERS:
        final_name = _renamed.get(method_name, method_name)
        s, _body_s, e = _method_ranges(text, "TokenizerManager", final_name)
        retyped_ranges.append((s, e))
    retyped_ranges.sort()

    out_parts = []
    cursor = 0
    for s, e in retyped_ranges:
        out_parts.append(rewire_external("".join(tm_lines[cursor:s])))
        out_parts.append("".join(tm_lines[s:e]))  # untouched (already _rewrite_body'd)
        cursor = e
    out_parts.append(rewire_external("".join(tm_lines[cursor:])))
    text = "".join(out_parts)

    tm.write_text(text)

    # Mixin files: rewire is_pause / is_pause_cond / abort_request the same way.
    for f in (control_mixin, multi_mixin):
        f.write_text(rewire_external(f.read_text()))

    # External callers in entrypoints: ``tokenizer_manager.<method>(...)`` ->
    # ``TokenizerManager.<method>(tokenizer_manager.pause_controller, ...)``.
    import glob

    for fpath in glob.glob(str(wt / "python/sglang/srt/entrypoints/**/*.py"), recursive=True):
        f = Path(fpath)
        t = f.read_text()
        original = t
        # Capture the `<prefix>.tokenizer_manager.<method>(` form so the rewrite
        # keeps the prefix intact: <prefix>.tokenizer_manager.<method>(args)
        # -> TokenizerManager.<method>(<prefix>.tokenizer_manager.pause_controller, args)
        for method in ("abort_request", "pause_generation", "continue_generation"):
            t = re.sub(
                rf"(\b[\w.]+\.)tokenizer_manager\.{method}\(",
                lambda m, _meth=method: f"TokenizerManager.{_meth}({m.group(1)}tokenizer_manager.pause_controller, ",
                t,
            )
            # Bare `tokenizer_manager.<method>(` form (no prefix).
            t = re.sub(
                rf"(?<![\w.])tokenizer_manager\.{method}\(",
                f"TokenizerManager.{method}(tokenizer_manager.pause_controller, ",
                t,
            )
        if t != original:
            # Make sure TokenizerManager is imported.
            if "from sglang.srt.managers.tokenizer_manager import" not in t:
                t = "from sglang.srt.managers.tokenizer_manager import TokenizerManager\n" + t
            f.write_text(t)


if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        area_branch=AREA_BRANCH,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
