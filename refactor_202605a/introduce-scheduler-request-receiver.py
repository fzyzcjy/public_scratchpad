#!/usr/bin/env python3
"""Introduce ``SchedulerRequestReceiver`` and move ``recv_requests`` /
``recv_limit_reached`` / ``_split_work_and_control_reqs`` off Scheduler.

- New file ``scheduler_components/ingress/request_receiver.py``.
- Ctor accepts ``narrow kwargs`` per CLAUDE.md ch4 (no ``scheduler_ref``):
  16 协作者/配置 + 1 Callable (``stream_output``). The Callable is needed
  because ``stream_output`` lives on ``SchedulerOutputProcessorMixin`` until
  the ``introduce-output-streamer`` commit moves it; that follow-up commit
  swaps the Callable kwarg for a sister ``output_streamer`` injection.
- ``recv_requests`` gains a per-call ``last_forward_mode`` keyword (R4 kwarg
  add per EXECUTION_GUIDE item 2). The original two-line block computing
  ``last_forward_mode`` from ``self.last_batch`` is removed.
- 5 callsites updated: ``scheduler.py`` (2) + ``scheduler_pp_mixin.py`` (3).

Usage:
    uv run --python 3.12 introduce-scheduler-request-receiver.py run
    uv run --python 3.12 introduce-scheduler-request-receiver.py verify
"""

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

ID = "introduce-scheduler-request-receiver"
SUBJECT = (
    "Introduce SchedulerRequestReceiver and move recv_requests + 2 helpers"
)
BODY = """\
Move ``recv_requests`` (~157 LOC), ``recv_limit_reached`` (~5 LOC) and
``_split_work_and_control_reqs`` (~29 LOC) off Scheduler into a new owner
class ``SchedulerRequestReceiver`` in
``scheduler_components/ingress/request_receiver.py``.

The ctor uses narrow typed kwargs per CLAUDE.md ch4 (no ``scheduler_ref``
back-reference): 16 collaborators / configs + 1 ``stream_output: Callable``.
The Callable is a transitional shim because ``stream_output`` still lives on
``SchedulerOutputProcessorMixin``; it will be replaced by a sister
``output_streamer`` injection when ``introduce-output-streamer`` lands.

``recv_requests`` gains a per-call ``last_forward_mode`` kwarg (R4 kwarg add)
replacing the inline ``self.last_batch.forward_mode if ...`` computation.
Callers (``Scheduler.event_loop_normal`` / ``event_loop_overlap`` and 3 in
``scheduler_pp_mixin.py``) extract ``last_forward_mode`` and pass it.

No method renames / privacy flips. Method bodies byte-identical apart from
the ``last_forward_mode`` block removal in ``recv_requests``.

No behavior change.
"""
AREA = "mech_scheduler"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


# Block to STRIP from ``recv_requests`` body (after dedent to 4-space).
LAST_FORWARD_MODE_BLOCK = """\
        if self.recv_skipper is not None:
            last_forward_mode = (
                self.last_batch.forward_mode if self.last_batch is not None else None
            )
            if not self.recv_skipper.handle(last_forward_mode):
                return []

"""


# Replacement (the receiver still wants the recv_skipper gate, just keyed on
# the per-call kwarg instead of a self.X read).
LAST_FORWARD_MODE_REPLACEMENT = """\
        if self.recv_skipper is not None:
            if not self.recv_skipper.handle(last_forward_mode):
                return []

"""


# Header for the new file.
RECEIVER_HEADER = '''from __future__ import annotations

from http import HTTPStatus
from typing import Any, Callable, List, Optional, Union

import zmq
from torch.distributed import barrier

from sglang.srt.disaggregation.utils import prepare_abort
from sglang.srt.managers.io_struct import (
    BatchTokenizedEmbeddingReqInput,
    BatchTokenizedGenerateReqInput,
    TokenizedEmbeddingReqInput,
    TokenizedGenerateReqInput,
)
from sglang.srt.managers.mm_utils import has_shm_features, unwrap_shm_features
from sglang.srt.utils import broadcast_pyobj, point_to_point_pyobj


class SchedulerRequestReceiver:
    """Wire-level request receiver: pulls ``recv_req`` lists from zmq /
    pipeline upstream, applies recv_skipper / input_blocker guards, broadcasts
    across TP/DP/CP groups, runs MM-receiver pre-processing, and unwraps shm
    features. Owns no mutable state."""

    def __init__(
        self,
        *,
        recv_from_tokenizer,
        recv_from_rpc,
        recv_skipper,
        input_blocker,
        mm_receiver,
        ps,
        tp_group,
        tp_cpu_group,
        attn_tp_group,
        attn_tp_cpu_group,
        attn_cp_group,
        attn_cp_cpu_group,
        world_group,
        server_args,
        model_config,
        max_recv_per_poll: int,
        stream_output: Callable[..., None],
    ) -> None:
        self.recv_from_tokenizer = recv_from_tokenizer
        self.recv_from_rpc = recv_from_rpc
        self.recv_skipper = recv_skipper
        self.input_blocker = input_blocker
        self.mm_receiver = mm_receiver
        self.ps = ps
        self.tp_group = tp_group
        self.tp_cpu_group = tp_cpu_group
        self.attn_tp_group = attn_tp_group
        self.attn_tp_cpu_group = attn_tp_cpu_group
        self.attn_cp_group = attn_cp_group
        self.attn_cp_cpu_group = attn_cp_cpu_group
        self.world_group = world_group
        self.server_args = server_args
        self.model_config = model_config
        self.max_recv_per_poll = max_recv_per_poll
        self.stream_output = stream_output

'''


# Construction snippet for Scheduler.__init__. Inserted just before
# ``self.is_initializing = False``.
INIT_INSERT = '''        self.request_receiver = SchedulerRequestReceiver(
            recv_from_tokenizer=self.recv_from_tokenizer,
            recv_from_rpc=self.recv_from_rpc,
            recv_skipper=self.recv_skipper,
            input_blocker=self.input_blocker,
            mm_receiver=getattr(self, "mm_receiver", None),
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
        )

'''


def _transform_recv_requests(method_text: str) -> str:
    """Strip the ``last_forward_mode`` computation block + add per-call kwarg
    to the signature."""
    if LAST_FORWARD_MODE_BLOCK not in method_text:
        raise RuntimeError(
            "last_forward_mode block anchor mismatch — recv_requests body shape changed"
        )
    text = method_text.replace(LAST_FORWARD_MODE_BLOCK, LAST_FORWARD_MODE_REPLACEMENT)

    # Add the per-call kwarg to the signature.
    text = text.replace(
        "    def recv_requests(\n        self,\n    ) -> List[",
        "    def recv_requests(\n"
        "        self,\n"
        "        *,\n"
        "        last_forward_mode,\n"
        "    ) -> List[",
    )
    return text


def _make_caller_replacement(target: str) -> str:
    """Build the call-site replacement: extract ``last_forward_mode`` from
    ``self.last_batch`` then dispatch to ``self.request_receiver.recv_requests``."""
    return (
        f"            last_forward_mode = (\n"
        f"                self.last_batch.forward_mode if self.last_batch is not None else None\n"
        f"            )\n"
        f"            recv_reqs = self.request_receiver.recv_requests(\n"
        f"                last_forward_mode=last_forward_mode,\n"
        f"            )\n"
    )


def transform(wt: Path) -> None:
    sched = wt / "python/sglang/srt/managers/scheduler.py"
    pp_mixin = wt / "python/sglang/srt/managers/scheduler_pp_mixin.py"
    pkg_init = wt / "python/sglang/srt/managers/scheduler_components/ingress/__init__.py"
    receiver = wt / "python/sglang/srt/managers/scheduler_components/ingress/request_receiver.py"

    pkg_init.parent.mkdir(parents=True, exist_ok=True)
    pkg_init.write_text("")

    # Cut bottom-up so earlier line ranges stay valid.
    s, e = find_method_lines(
        sched.read_text(),
        class_name="Scheduler",
        method_name="_split_work_and_control_reqs",
    )
    split_text = cut_lines(sched, s, e)

    s, e = find_method_lines(
        sched.read_text(),
        class_name="Scheduler",
        method_name="recv_requests",
    )
    recv_text = cut_lines(sched, s, e)
    recv_text = _transform_recv_requests(recv_text)

    s, e = find_method_lines(
        sched.read_text(),
        class_name="Scheduler",
        method_name="recv_limit_reached",
    )
    limit_text = cut_lines(sched, s, e)

    # Method bodies retain 4-space indentation — they slot directly into the
    # new class body. Order: limit_reached, recv_requests, _split_w_a_c_reqs.
    receiver.write_text(
        RECEIVER_HEADER + limit_text + recv_text + split_text.rstrip() + "\n"
    )

    # Update Scheduler: import + ctor instantiation + 2 callsite rewrites.
    text = sched.read_text()
    text = insert_after(
        text,
        anchor="from sglang.srt.managers.scheduler_components.setup import kv_cache\n",
        addition=(
            "from sglang.srt.managers.scheduler_components.ingress.request_receiver import (\n"
            "    SchedulerRequestReceiver,\n"
            ")\n"
        ),
    )
    # Insert ctor instantiation just before ``self.is_initializing = False``.
    text = replace_call_site(
        text,
        old="        self.is_initializing = False\n",
        new=INIT_INSERT + "        self.is_initializing = False\n",
    )
    # 2 callsite rewrites in scheduler.py.
    caller_replacement = _make_caller_replacement("scheduler.py")
    text = text.replace(
        "            recv_reqs = self.recv_requests()\n",
        caller_replacement,
    )
    sched.write_text(text)

    # 3 callsite rewrites in scheduler_pp_mixin.py.
    text = pp_mixin.read_text()
    text = text.replace(
        "                    recv_reqs = self.recv_requests()\n",
        "                    last_forward_mode = (\n"
        "                        self.last_batch.forward_mode if self.last_batch is not None else None\n"
        "                    )\n"
        "                    recv_reqs = self.request_receiver.recv_requests(\n"
        "                        last_forward_mode=last_forward_mode,\n"
        "                    )\n",
    )
    text = text.replace(
        "                recv_reqs = self.recv_requests()\n",
        "                last_forward_mode = (\n"
        "                    self.last_batch.forward_mode if self.last_batch is not None else None\n"
        "                )\n"
        "                recv_reqs = self.request_receiver.recv_requests(\n"
        "                    last_forward_mode=last_forward_mode,\n"
        "                )\n",
    )
    pp_mixin.write_text(text)

    # Additional callsites: disaggregation/decode.py, disaggregation/prefill.py,
    # hardware_backend/mlx/scheduler_mixin.py, multiplex/multiplexing_mixin.py.
    # NOTE: anchor OLD strings with a leading newline so the 12-space pattern
    # cannot match as a substring of a 16-space-indented line.
    for f in [
        wt / "python/sglang/srt/disaggregation/decode.py",
        wt / "python/sglang/srt/disaggregation/prefill.py",
        wt / "python/sglang/srt/hardware_backend/mlx/scheduler_mixin.py",
        wt / "python/sglang/srt/multiplex/multiplexing_mixin.py",
    ]:
        ftext = f.read_text()
        ftext = ftext.replace(
            "\n            recv_reqs = self.recv_requests()\n",
            "\n            last_forward_mode = (\n"
            "                self.last_batch.forward_mode if self.last_batch is not None else None\n"
            "            )\n"
            "            recv_reqs = self.request_receiver.recv_requests(\n"
            "                last_forward_mode=last_forward_mode,\n"
            "            )\n",
        )
        # multiplex_mixin uses 16-space indent.
        ftext = ftext.replace(
            "\n                recv_reqs = self.recv_requests()\n",
            "\n                last_forward_mode = (\n"
            "                    self.last_batch.forward_mode if self.last_batch is not None else None\n"
            "                )\n"
            "                recv_reqs = self.request_receiver.recv_requests(\n"
            "                    last_forward_mode=last_forward_mode,\n"
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
