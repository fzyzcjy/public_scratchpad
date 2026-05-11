#!/usr/bin/env python3
"""Mechanical move for ``introduce-scheduler-request-receiver``: cut 3
@staticmethods from Scheduler, paste them into the ``SchedulerRequestReceiver``
class body. Drop ``@staticmethod`` decorators, simplify
``def foo(self: "SchedulerRequestReceiver", ...)`` → ``def foo(self, ...)``,
rewrite callers ``self.recv_requests(self.request_receiver, ...)`` →
``self.request_receiver.recv_requests(...)``.
"""

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

ID = "introduce-scheduler-request-receiver-move"
SUBJECT = "Hand request ingress over to SchedulerRequestReceiver"
BODY = """\
Mechanical cut + paste for the ``introduce-scheduler-request-receiver``
mech move.

Cut ``recv_requests`` / ``recv_limit_reached`` /
``_split_work_and_control_reqs`` (@staticmethods after prep) from
Scheduler and paste them into the ``SchedulerRequestReceiver`` class body
in ``scheduler_components/request_receiver.py``.

Drop ``@staticmethod`` decorators; simplify ``self: SchedulerRequestReceiver``
type annotation to bare ``self`` (in class context the type is implicit).
Method bodies otherwise byte-identical.

All callers updated:
  ``self.recv_requests(self.request_receiver, last_forward_mode=...)`` →
  ``self.request_receiver.recv_requests(last_forward_mode=...)``
(pure prefix transformation).
"""
AREA = "mech_scheduler"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


def _strip_staticmethod_typeflip(method_text: str, *, target_class: str) -> str:
    """Drop @staticmethod and the ``self: TargetClass`` annotation."""
    text = method_text.replace("    @staticmethod\n", "", 1)
    text = text.replace(
        f"self: \"{target_class}\"",
        "self",
    )
    return text


def transform(wt: Path) -> None:
    sched = wt / "python/sglang/srt/managers/scheduler.py"
    pp_mixin = wt / "python/sglang/srt/managers/scheduler_pp_mixin.py"
    receiver = wt / "python/sglang/srt/managers/scheduler_components/request_receiver.py"

    # Cut 3 methods bottom-up.
    method_blocks = []
    for name in [
        "_split_work_and_control_reqs",
        "recv_requests",
        "recv_limit_reached",
    ]:
        s, e = find_method_lines(
            sched.read_text(),
            class_name="Scheduler",
            method_name=name,
        )
        block = cut_lines(sched, s, e)
        block = _strip_staticmethod_typeflip(block, target_class="SchedulerRequestReceiver")
        method_blocks.append(block)

    # Reverse to restore source order: recv_limit_reached, recv_requests, _split_work_and_control_reqs.
    method_blocks.reverse()

    # Append into receiver class body. The existing class header ends with
    # ``self.stream_output = stream_output\n``; append after that (the methods
    # already have 4-space indent matching class body).
    rtext = receiver.read_text()
    rtext = rtext.rstrip() + "\n\n" + "".join(method_blocks).rstrip() + "\n"
    receiver.write_text(rtext)

    # Caller rewrites: pure prefix transformation.
    for f in [
        sched,
        pp_mixin,
        wt / "python/sglang/srt/disaggregation/decode.py",
        wt / "python/sglang/srt/disaggregation/prefill.py",
        wt / "python/sglang/srt/hardware_backend/mlx/scheduler_mixin.py",
        wt / "python/sglang/srt/multiplex/multiplexing_mixin.py",
    ]:
        text = f.read_text()
        # Match ``self.recv_requests(\n<indent>    self.request_receiver,\n<indent>    last_forward_mode=<expr>,\n<indent>)``
        # and collapse to ``self.request_receiver.recv_requests(\n<indent>    last_forward_mode=<expr>,\n<indent>)``.
        # We rely on the prep step having emitted these forms verbatim.
        for indent in ("            ", "                ", "                    "):
            text = text.replace(
                f"{indent}recv_reqs = self.recv_requests(\n"
                f"{indent}    self.request_receiver,\n"
                f"{indent}    last_forward_mode=last_forward_mode,\n"
                f"{indent})\n",
                f"{indent}recv_reqs = self.request_receiver.recv_requests(\n"
                f"{indent}    last_forward_mode=last_forward_mode,\n"
                f"{indent})\n",
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
