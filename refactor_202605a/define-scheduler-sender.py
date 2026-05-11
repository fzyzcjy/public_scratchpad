#!/usr/bin/env python3
"""Define a SchedulerSender Protocol in a new managers/scheduler_sender.py
module. No edits to existing files — the Protocol is defined up front so
subsequent owner-class commits can type-hint their send_to_scheduler field.
"""

# /// script
# requires-python = ">=3.10"
# dependencies = ["typer"]
# ///

import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from _runner import run_pr

ID = "define-scheduler-sender"
SUBJECT = "Define SchedulerSender Protocol in managers/scheduler_sender.py"
BODY = """\
Add a Protocol that explicitly captures the duck-typed contract used by
TokenizerManager.send_to_scheduler (zmq.asyncio.Socket in single-worker
mode; SenderWrapper in multi-worker mode). Subsequent owner-class commits
will use this Protocol as the type for their send_to_scheduler field.
No code changes outside the new file.
"""
AREA = "mech_tokenizer_manager"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


CONTENT = '''from __future__ import annotations

from typing import Any, Protocol


class SchedulerSender(Protocol):
    """Type for the tokenizer-process side of the tokenizer->scheduler IPC.

    Single-worker mode: zmq.asyncio.Socket directly.
    Multi-HTTP-worker mode: SenderWrapper (multi_tokenizer_mixin.py) which
    wraps the socket and stamps http_worker_ipcs onto BaseBatchReq objects.
    Both satisfy this Protocol.
    """

    def send_pyobj(self, obj: Any) -> None: ...
'''


def transform(wt: Path) -> None:
    sender_file = wt / "python/sglang/srt/managers/scheduler_sender.py"
    sender_file.write_text(CONTENT)


if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        area_branch=AREA_BRANCH,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
