#!/usr/bin/env python3
"""Inplace prep for ``introduce-scheduler-request-receiver``: create the
empty ``SchedulerRequestReceiver`` class skeleton, instantiate in
Scheduler.__init__, convert 3 methods to @staticmethod with
``self: SchedulerRequestReceiver``, rewrite callers to
``Scheduler.<method>(self.request_receiver, ...)``.

Body bytes byte-identical wrt the post-move state (modulo decorator + the
``def foo(self: SchedulerRequestReceiver, ...)`` → ``def foo(self, ...)``
signature simplification in the move commit).
"""

# /// script
# requires-python = ">=3.10"
# dependencies = ["typer"]
# ///

import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from _helpers import find_method_lines, insert_after, replace_call_site
from _runner import run_pr

ID = "introduce-scheduler-request-receiver-prep"
SUBJECT = "Add SchedulerRequestReceiver and route request-ingress state through it"
BODY = """\
Inplace prep for the ``introduce-scheduler-request-receiver`` mech move.

- Create ``scheduler_components/request_receiver.py`` with an empty
  ``SchedulerRequestReceiver`` class (collaborator / config fields +
  ``stream_output`` Callable, enumerated in the dataclass body below).
  No methods yet.
- Instantiate ``self.request_receiver = SchedulerRequestReceiver(...)`` in
  ``Scheduler.__init__`` just before ``self.is_initializing = False``.
- In Scheduler, convert the receiver methods (``recv_requests`` /
  ``recv_limit_reached`` / ``_split_work_and_control_reqs``) to
  ``@staticmethod`` with ``self: SchedulerRequestReceiver`` type annotation.
  Body bytes unchanged.
- In ``recv_requests``, strip the inline ``last_forward_mode`` computation
  block and add ``last_forward_mode`` as a keyword-only parameter
  (pragmatic deviation; documented).
- Callers in scheduler.py, scheduler_pp_mixin.py, and the disagg / mlx /
  multiplex mixins are rewritten to
  ``self.recv_requests(self.request_receiver, last_forward_mode=...)``.

On the block-move audit: the ``last_forward_mode`` block-move is
intentionally **not** extracted into a separate ``-pre-prep`` commit.
Hoisting the block out to callers without simultaneously turning
``last_forward_mode`` into a kwarg on ``recv_requests`` would leave the
method body referencing an undefined name, producing a runtime
``NameError`` mid-chain. The hoist and the signature redesign are
semantically inseparable here, so both stay in this prep commit.

The receiver methods stay inside Scheduler in this commit; physical cut +
paste to ``SchedulerRequestReceiver`` body happens in
``introduce-scheduler-request-receiver-move``.
"""
AREA = "mech_scheduler"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


RECEIVER_HEADER = '''from __future__ import annotations  # noqa: F401

from dataclasses import dataclass
from http import HTTPStatus  # noqa: F401
from typing import Any, Callable, List, Optional, Union  # noqa: F401

import zmq  # noqa: F401
from torch.distributed import barrier  # noqa: F401

from sglang.srt.disaggregation.utils import prepare_abort  # noqa: F401
from sglang.srt.managers.io_struct import (  # noqa: F401
    BatchTokenizedEmbeddingReqInput,
    BatchTokenizedGenerateReqInput,
    TokenizedEmbeddingReqInput,
    TokenizedGenerateReqInput,
)
from sglang.srt.managers.mm_utils import has_shm_features, unwrap_shm_features  # noqa: F401
from sglang.srt.utils import broadcast_pyobj, point_to_point_pyobj  # noqa: F401


@dataclass(kw_only=True, slots=True, frozen=True)
class SchedulerRequestReceiver:
    """Wire-level request receiver: pulls ``recv_req`` lists from zmq /
    pipeline upstream, applies recv_skipper / input_blocker guards, broadcasts
    across TP/DP/CP groups, runs MM-receiver pre-processing, and unwraps shm
    features. Owns no mutable state."""

    recv_from_tokenizer: Any
    recv_from_rpc: Any
    recv_skipper: Any
    input_blocker: Any
    mm_receiver: Any
    ps: Any
    tp_group: Any
    tp_cpu_group: Any
    attn_tp_group: Any
    attn_tp_cpu_group: Any
    attn_cp_group: Any
    attn_cp_cpu_group: Any
    world_group: Any
    server_args: Any
    model_config: Any
    max_recv_per_poll: int
    stream_output: Callable[..., None]
    get_last_forward_mode: Callable[[], Any]
'''


INIT_INSERT = '''        self.request_receiver = SchedulerRequestReceiver(
            recv_from_tokenizer=self.recv_from_tokenizer,
            recv_from_rpc=self.recv_from_rpc,
            recv_skipper=self.recv_skipper,
            input_blocker=self.input_blocker,
            mm_receiver=self.mm_receiver,
            ps=self.ps,
            tp_group=self.tp_group,
            tp_cpu_group=self.tp_cpu_group,
            attn_tp_group=self.attn_tp_group,
            attn_tp_cpu_group=self.attn_tp_cpu_group,
            attn_cp_group=self.attn_cp_group,
            attn_cp_cpu_group=self.attn_cp_cpu_group,
            world_group=self.world_group,
            server_args=self.server_args,
            model_config=self.model_config,
            max_recv_per_poll=self.max_recv_per_poll,
            stream_output=self.stream_output,
            get_last_forward_mode=lambda: self.last_batch.forward_mode if self.last_batch is not None else None,
        )

'''


LAST_FORWARD_MODE_BLOCK = """\
        if self.recv_skipper is not None:
            last_forward_mode = (
                self.last_batch.forward_mode if self.last_batch is not None else None
            )
            if not self.recv_skipper.handle(last_forward_mode):
                return []

"""


LAST_FORWARD_MODE_REPLACEMENT = """\
        if self.recv_skipper is not None:
            if not self.recv_skipper.handle(self.get_last_forward_mode()):
                return []

"""


def _make_caller_replacement_4space() -> str:
    return (
        "            recv_reqs = self.recv_requests(\n"
        "                self.request_receiver,\n"
        "            )\n"
    )


def transform(wt: Path) -> None:
    sched = wt / "python/sglang/srt/managers/scheduler.py"
    pp_mixin = wt / "python/sglang/srt/managers/scheduler_pp_mixin.py"
    receiver = wt / "python/sglang/srt/managers/scheduler_components/request_receiver.py"

    # 1. Create new file with empty class.
    receiver.parent.mkdir(parents=True, exist_ok=True)
    receiver.write_text(RECEIVER_HEADER)

    # 2. In Scheduler, convert 3 methods to @staticmethod inplace.
    text = sched.read_text()

    # recv_requests — add @staticmethod, type-flip self, strip last_forward_mode block, add kwarg.
    s, e = find_method_lines(text, class_name="Scheduler", method_name="recv_requests")
    lines = text.splitlines(keepends=True)
    method_text = "".join(lines[s:e])

    new_method = method_text.replace(
        "    def recv_requests(\n        self,\n    ) -> List[",
        "    @staticmethod\n"
        "    def recv_requests(\n"
        "        self: \"SchedulerRequestReceiver\",\n"
        "    ) -> List[",
    )
    if LAST_FORWARD_MODE_BLOCK not in new_method:
        raise RuntimeError("last_forward_mode block anchor mismatch")
    new_method = new_method.replace(LAST_FORWARD_MODE_BLOCK, LAST_FORWARD_MODE_REPLACEMENT)
    text = "".join(lines[:s]) + new_method + "".join(lines[e:])

    # recv_limit_reached — add @staticmethod, type-flip self.
    # Original signature: ``def recv_limit_reached(self, num_recv_reqs: int) -> bool:``.
    s, e = find_method_lines(text, class_name="Scheduler", method_name="recv_limit_reached")
    lines = text.splitlines(keepends=True)
    method_text = "".join(lines[s:e])
    if "    def recv_limit_reached(self, " not in method_text:
        raise RuntimeError("recv_limit_reached signature shape unexpected")
    new_method = method_text.replace(
        "    def recv_limit_reached(self, ",
        "    @staticmethod\n    def recv_limit_reached(self: \"SchedulerRequestReceiver\", ",
    )
    text = "".join(lines[:s]) + new_method + "".join(lines[e:])

    # _split_work_and_control_reqs — add @staticmethod, type-flip self.
    # Original signature: ``def _split_work_and_control_reqs(self, recv_reqs: List):``.
    s, e = find_method_lines(text, class_name="Scheduler", method_name="_split_work_and_control_reqs")
    lines = text.splitlines(keepends=True)
    method_text = "".join(lines[s:e])
    if "    def _split_work_and_control_reqs(self, " not in method_text:
        raise RuntimeError("_split_work_and_control_reqs signature shape unexpected")
    new_method = method_text.replace(
        "    def _split_work_and_control_reqs(self, ",
        "    @staticmethod\n    def _split_work_and_control_reqs(self: \"SchedulerRequestReceiver\", ",
    )
    text = "".join(lines[:s]) + new_method + "".join(lines[e:])

    # 3. Add import + ctor instantiation.
    text = insert_after(
        text,
        anchor="from sglang.srt.mem_cache import kv_cache_builder\n",
        addition=(
            "from sglang.srt.managers.scheduler_components.request_receiver import (\n"
            "    SchedulerRequestReceiver,\n"
            ")\n"
        ),
    )
    text = replace_call_site(
        text,
        old="        self.is_initializing = False\n",
        new=INIT_INSERT + "        self.is_initializing = False\n",
    )

    # 4. Callsite rewrites in scheduler.py (2 sites).
    text = text.replace(
        "            recv_reqs = self.recv_requests()\n",
        _make_caller_replacement_4space(),
    )

    sched.write_text(text)

    # 5. Callsite rewrites in scheduler_pp_mixin.py (3 sites).
    text = pp_mixin.read_text()
    text = text.replace(
        "                    recv_reqs = self.recv_requests()\n",
        "                    recv_reqs = self.recv_requests(\n"
        "                        self.request_receiver,\n"
        "                    )\n",
    )
    text = text.replace(
        "                recv_reqs = self.recv_requests()\n",
        "                recv_reqs = self.recv_requests(\n"
        "                    self.request_receiver,\n"
        "                )\n",
    )
    pp_mixin.write_text(text)

    # 6. Callsite rewrites in disagg / mlx / multiplex mixins.
    for f, indent16 in [
        (wt / "python/sglang/srt/disaggregation/decode.py", False),
        (wt / "python/sglang/srt/disaggregation/prefill.py", False),
        (wt / "python/sglang/srt/hardware_backend/mlx/scheduler_mixin.py", False),
        (wt / "python/sglang/srt/multiplex/multiplexing_mixin.py", True),
    ]:
        ftext = f.read_text()
        ftext = ftext.replace(
            "\n            recv_reqs = self.recv_requests()\n",
            "\n            recv_reqs = self.recv_requests(\n"
            "                self.request_receiver,\n"
            "            )\n",
        )
        ftext = ftext.replace(
            "\n                recv_reqs = self.recv_requests()\n",
            "\n                recv_reqs = self.recv_requests(\n"
            "                    self.request_receiver,\n"
            "                )\n",
        )
        f.write_text(ftext)


if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        area_branch=AREA_BRANCH,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
