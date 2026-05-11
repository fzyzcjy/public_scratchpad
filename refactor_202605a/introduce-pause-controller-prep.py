#!/usr/bin/env python3
"""Inplace prep for ``introduce-pause-controller``: create the
``PauseController`` class skeleton (dataclass + fields + ``__post_init__``)
in ``managers/pause_controller.py``, instantiate
``self.pause_controller = PauseController(...)`` in TokenizerManager.__init__,
convert 4 methods (``pause_generation`` / ``continue_generation`` /
``abort_request`` / ``_handle_abort_req``) to ``@staticmethod`` with
``self: "PauseController"`` type annotation, rewrite callers to
``TokenizerManager.<method>(self.pause_controller, ...)`` form.

Body byte-identical wrt the post-move state, modulo:
  - 5 field rewrites that retarget moved attributes onto PauseController
    (``self.enable_metrics`` -> ``self.config.enable_metrics``, etc.)
  - inter-method calls within the 4-method cluster get class-qualified
    (``self.abort_request(...)`` -> ``TokenizerManager.abort_request(self, ...)``)
    so they remain reachable while the bodies still live inside TM;
    the move commit reverses this back to ``self.abort_request(...)``.

Both kinds of body edits are stable across prep/move (the move commit does
not touch them again).
"""

# /// script
# requires-python = ">=3.10"
# dependencies = ["typer"]
# ///

import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from _helpers import find_method_lines, insert_after, replace_call_site
from _runner import run_pr

ID = "introduce-pause-controller-prep"
SUBJECT = "Build PauseController skeleton + @staticmethod prep (prep for move)"
BODY = """\
Inplace prep for the ``introduce-pause-controller`` mech move.

- Create ``managers/pause_controller.py`` with ``PauseControllerConfig``
  and ``PauseController`` (``@dataclass(slots=True, kw_only=True)``;
  ``frozen=False`` because ``is_pause`` mutates). Fields: ``send_to_scheduler``,
  ``dispatcher``, ``rid_to_state``, ``model_update_lock``,
  ``metrics_collector``, ``tokenizer``, ``config``, ``is_pause``,
  ``is_pause_cond``. No methods yet (other than ``__post_init__`` which
  registers AbortReq on the dispatcher via a forwarding lambda to
  ``TokenizerManager._handle_abort_req`` during prep).
- Instantiate ``self.pause_controller = PauseController(...)`` in
  ``TokenizerManager.__init__`` just before the SessionController block.
- Drop ``self.is_pause = False`` / ``self.is_pause_cond = ...`` from TM
  init (these fields now live on PauseController).
- In TM, convert 4 methods (``pause_generation`` / ``continue_generation``
  / ``abort_request`` / ``_handle_abort_req``) to ``@staticmethod`` with
  ``self: "PauseController"`` type annotation. Body rewrites in place:
    - ``self.enable_metrics``                  -> ``self.config.enable_metrics``
    - ``self.server_args.weight_version``      -> ``self.config.weight_version``
    - ``self.server_args.skip_tokenizer_init`` -> ``self.config.skip_tokenizer_init``
    - ``self.raw_tokenizer_wrapper.tokenizer`` -> ``self.tokenizer``
    - ``self.request_metrics_recorder.metrics_collector`` -> ``self.metrics_collector``
  Inter-method calls inside the 4 bodies get class-qualified
  (``self.abort_request(...)`` -> ``TokenizerManager.abort_request(self, ...)``);
  the move commit reverses these back to ``self.abort_request(...)``.
- Caller rewires (TM + tokenizer_control_mixin + multi_tokenizer_mixin):
    ``self.is_pause``         -> ``self.pause_controller.is_pause``
    ``self.is_pause_cond``    -> ``self.pause_controller.is_pause_cond``
    ``self.abort_request(``   -> ``TokenizerManager.abort_request(self.pause_controller, ``
    ``self.pause_generation(``    -> ``TokenizerManager.pause_generation(self.pause_controller, ``
    ``self.continue_generation(`` -> ``TokenizerManager.continue_generation(self.pause_controller, ``
- Entrypoints callers (under ``entrypoints/``):
    ``tokenizer_manager.abort_request(``      -> ``TokenizerManager.abort_request(tokenizer_manager.pause_controller, ``
    ``tokenizer_manager.pause_generation(``   -> ``TokenizerManager.pause_generation(tokenizer_manager.pause_controller, ``
    ``tokenizer_manager.continue_generation(``-> ``TokenizerManager.continue_generation(tokenizer_manager.pause_controller, ``

The 4 methods stay inside TokenizerManager in this commit; physical cut +
paste into PauseController body happens in ``introduce-pause-controller-move``.
"""
AREA = "mech_tokenizer_manager"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


PAUSE_CONTROLLER_HEADER = '''from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from sglang.srt.managers import logprob_ops
from sglang.srt.managers.io_struct import (
    AbortReq,
    ContinueGenerationReqInput,
    PauseGenerationReqInput,
)
from sglang.srt.managers.request_state import ReqState
from sglang.srt.managers.scheduler import is_health_check_generate_req
from sglang.srt.utils.aio_rwlock import RWLock
from sglang.utils import TypeBasedDispatcher

logger = logging.getLogger(__name__)


@dataclass(slots=True, kw_only=True)
class PauseControllerConfig:
    enable_metrics: bool
    skip_tokenizer_init: bool
    weight_version: Optional[str]


@dataclass(slots=True, kw_only=True)
class PauseController:
    """Pause / resume / abort state machine + AbortReq dispatcher handler."""

    send_to_scheduler: Any
    dispatcher: TypeBasedDispatcher
    rid_to_state: Dict[str, ReqState]
    model_update_lock: RWLock
    metrics_collector: Optional[Any]
    tokenizer: Optional[Any]
    config: PauseControllerConfig
    is_pause: bool = False
    is_pause_cond: asyncio.Condition = field(default_factory=asyncio.Condition)

    def __post_init__(self) -> None:
        # During prep, ``_handle_abort_req`` still lives on TokenizerManager
        # as a @staticmethod with ``self: PauseController``; forward through it
        # via a lambda. The move commit replaces this with
        # ``self.dispatcher._mapping[AbortReq] = self._handle_abort_req``.
        from sglang.srt.managers.tokenizer_manager import TokenizerManager

        self.dispatcher._mapping[AbortReq] = (
            lambda recv_obj: TokenizerManager._handle_abort_req(self, recv_obj)
        )
'''


INIT_INSERT = '''        # Pause controller
        self.pause_controller = PauseController(
            send_to_scheduler=self.send_to_scheduler,
            dispatcher=self._result_dispatcher,
            rid_to_state=self.rid_to_state,
            model_update_lock=self.model_update_lock,
            metrics_collector=self.request_metrics_recorder.metrics_collector,
            tokenizer=self.raw_tokenizer_wrapper.tokenizer,
            config=PauseControllerConfig(
                enable_metrics=self.enable_metrics,
                skip_tokenizer_init=self.server_args.skip_tokenizer_init,
                weight_version=self.server_args.weight_version,
            ),
        )

'''


# Methods moved as a cluster — inter-method calls inside their bodies get
# class-qualified during prep and stripped back during move.
CLUSTER_METHODS = (
    "pause_generation",
    "continue_generation",
    "abort_request",
    "_handle_abort_req",
)


def _rewrite_body(body: str) -> str:
    """Field-access rewrites that retarget moved attributes onto PauseController.

    These edits stay identical across prep/move; the move commit cuts the
    block byte-for-byte and pastes it into PauseController's class body.
    """
    body = body.replace("self.enable_metrics", "self.config.enable_metrics")
    body = body.replace("self.server_args.weight_version", "self.config.weight_version")
    body = body.replace(
        "self.server_args.skip_tokenizer_init",
        "self.config.skip_tokenizer_init",
    )
    body = body.replace(
        "self.raw_tokenizer_wrapper.tokenizer", "self.tokenizer"
    )
    body = body.replace(
        "self.request_metrics_recorder.metrics_collector",
        "self.metrics_collector",
    )
    return body


def _rewrite_intercluster_calls(body: str) -> str:
    """Within method bodies, rewrite ``self.<cluster_method>(`` ->
    ``TokenizerManager.<cluster_method>(self, ``. Reversed by the move commit
    (pure prefix transform back to ``self.<method>(``)."""
    for name in CLUSTER_METHODS:
        body = re.sub(
            r"\bself\." + re.escape(name) + r"\(",
            f"TokenizerManager.{name}(self, ",
            body,
        )
    return body


def _staticmethodize(method_text: str) -> str:
    """Convert ``    def foo(self`` -> ``    @staticmethod\\n    def foo(self: "PauseController"``.

    Only touches the def header line; body untouched here.
    """
    # The method signature may be ``def foo(self):``, ``def foo(self, ...):``,
    # ``def foo(\n        self,\n        ...\n    ):``, async etc. Cover both
    # single-line and multi-line headers by anchoring on ``def <name>(self``.
    lines = method_text.splitlines(keepends=True)
    out = []
    inserted_decorator = False
    for line in lines:
        if not inserted_decorator and re.match(r"^(    )(async )?def \w+\(self\b", line):
            out.append("    @staticmethod\n")
            inserted_decorator = True
            # Retype the ``self`` param. Two forms:
            #   1) ``def foo(self`` followed immediately by ``)`` or ``,`` or ``:`` (single-line head)
            #   2) ``def foo(\n        self,\n        ...`` — but our regex above
            #      requires ``self`` on the def line, so only form (1) applies.
            new_line = re.sub(
                r"def (\w+)\(self\b",
                lambda m: f'def {m.group(1)}(self: "PauseController"',
                line,
                count=1,
            )
            out.append(new_line)
        else:
            out.append(line)
    if not inserted_decorator:
        raise RuntimeError(
            f"could not find ``def NAME(self`` header in:\n{method_text[:200]}"
        )
    return "".join(out)


def _retype_multiline_self(method_text: str) -> str:
    """For methods whose signature spans multiple lines (``def foo(\\n        self,``),
    retype ``self`` -> ``self: "PauseController"`` on its own line."""
    return re.sub(
        r"^(        )self,$",
        r'\1self: "PauseController",',
        method_text,
        count=1,
        flags=re.MULTILINE,
    )


def _ensure_staticmethod(method_text: str) -> str:
    """Idempotently add @staticmethod + retype self, covering both single-line
    and multi-line def headers."""
    if "@staticmethod" in method_text.splitlines()[0:2][0] if method_text.splitlines() else False:
        return method_text
    # Try single-line header first.
    if re.search(r"^    (async )?def \w+\(self\b", method_text, re.MULTILINE):
        return _staticmethodize(method_text)
    # Multi-line header: ``def foo(\n        self,\n        ...``.
    lines = method_text.splitlines(keepends=True)
    out = []
    inserted = False
    for i, line in enumerate(lines):
        if not inserted and re.match(r"^    (async )?def \w+\($", line.rstrip("\n")):
            out.append("    @staticmethod\n")
            inserted = True
        out.append(line)
    if not inserted:
        raise RuntimeError(
            f"could not find def header (single- or multi-line) in:\n{method_text[:200]}"
        )
    body = "".join(out)
    body = _retype_multiline_self(body)
    return body


def transform(wt: Path) -> None:
    tm = wt / "python/sglang/srt/managers/tokenizer_manager.py"
    control_mixin = wt / "python/sglang/srt/managers/tokenizer_control_mixin.py"
    multi_mixin = wt / "python/sglang/srt/managers/multi_tokenizer_mixin.py"
    pause_file = wt / "python/sglang/srt/managers/pause_controller.py"

    # 1. Create pause_controller.py with class skeleton only.
    pause_file.write_text(PAUSE_CONTROLLER_HEADER)

    # 2. In TM, convert each cluster method to @staticmethod inplace with
    #    body rewrites (field retarget + inter-method class-qualify).
    for name in CLUSTER_METHODS:
        text = tm.read_text()
        s, e = find_method_lines(text, class_name="TokenizerManager", method_name=name)
        lines = text.splitlines(keepends=True)
        method_text = "".join(lines[s:e])

        method_text = _ensure_staticmethod(method_text)
        method_text = _rewrite_body(method_text)
        method_text = _rewrite_intercluster_calls(method_text)

        new_text = "".join(lines[:s]) + method_text + "".join(lines[e:])
        tm.write_text(new_text)

    # 3. Drop is_pause / is_pause_cond field init from TM (now PauseController fields).
    text = tm.read_text()
    text = replace_call_site(
        text,
        old=(
            "        self.is_pause = False\n"
            "        self.is_pause_cond = asyncio.Condition()\n"
        ),
        new="",
    )

    # 4. Add import.
    text = insert_after(
        text,
        anchor="from sglang.srt.managers.tokenizer_control_mixin import TokenizerControlMixin\n",
        addition=(
            "from sglang.srt.managers.pause_controller import (\n"
            "    PauseController,\n"
            "    PauseControllerConfig,\n"
            ")\n"
        ),
    )

    # 5. Wire construction (just before SessionController block).
    text = replace_call_site(
        text,
        old=(
            "        # Session controller\n"
            "        self.session_controller = SessionController(\n"
        ),
        new=(
            INIT_INSERT
            + "        # Session controller\n"
            "        self.session_controller = SessionController(\n"
        ),
    )

    # 6. Caller substitutions (residual references after methods are still in TM
    #    but conceptually owned by PauseController). Done across TM and mixins.
    def rewire(t: str) -> str:
        t = re.sub(r"\bself\.is_pause_cond\b", "self.pause_controller.is_pause_cond", t)
        t = re.sub(r"\bself\.is_pause\b", "self.pause_controller.is_pause", t)
        t = re.sub(
            r"\bself\.abort_request\(",
            "TokenizerManager.abort_request(self.pause_controller, ",
            t,
        )
        t = re.sub(
            r"\bself\.pause_generation\(",
            "TokenizerManager.pause_generation(self.pause_controller, ",
            t,
        )
        t = re.sub(
            r"\bself\.continue_generation\(",
            "TokenizerManager.continue_generation(self.pause_controller, ",
            t,
        )
        return t

    text = rewire(text)
    tm.write_text(text)

    for f in (control_mixin, multi_mixin):
        t = f.read_text()
        t = rewire(t)
        f.write_text(t)

    # 7. Entrypoints — external callers via ``tokenizer_manager.<X>(...)``.
    import glob

    for fpath in glob.glob(str(wt / "python/sglang/srt/entrypoints/**/*.py"), recursive=True):
        f = Path(fpath)
        t = f.read_text()
        t = re.sub(
            r"\btokenizer_manager\.abort_request\(",
            "TokenizerManager.abort_request(tokenizer_manager.pause_controller, ",
            t,
        )
        t = re.sub(
            r"\btokenizer_manager\.pause_generation\(",
            "TokenizerManager.pause_generation(tokenizer_manager.pause_controller, ",
            t,
        )
        t = re.sub(
            r"\btokenizer_manager\.continue_generation\(",
            "TokenizerManager.continue_generation(tokenizer_manager.pause_controller, ",
            t,
        )
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
