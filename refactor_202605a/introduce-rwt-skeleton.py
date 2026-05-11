#!/usr/bin/env python3
"""Cut `remote_instance_init_transfer_engine` from ModelRunner; introduce a
new `RemoteInstanceWeightTransport` class that owns the 4 lifecycle fields
(``remote_instance_transfer_engine`` / ``_session_id`` / ``_weight_info`` /
``_nixl_manager``) and that one method. Update callers to delegate via
``self.remote_instance_weight_transport``. Field names on the new class match
the original ModelRunner field names byte-for-byte.

This is PR 1/3 of the RemoteInstanceWeightTransport extraction; PRs 2 and 3
migrate the remaining 4 methods.

Usage:
    uv run --python 3.12 introduce-rwt-skeleton.py run
    uv run --python 3.12 introduce-rwt-skeleton.py verify
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

ID = "introduce-rwt-skeleton"
SUBJECT = "Extract RemoteInstanceWeightTransport skeleton with remote_instance_init_transfer_engine"
BODY = ""
AREA = "mech_model_runner"
BASE = "tom_refactor_202605a/primary/mech_model_runner/init-dist"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"

# New file holding the transport class. Field names mirror the original
# ModelRunner field names; ``model`` is bound late (after load_model in
# ModelRunner) because the body only consults it from /42's _build_nixl_*.
TRANSPORT_HEADER = '''from __future__ import annotations

import logging
from typing import Callable

import torch

from sglang.srt.environ import envs
from sglang.srt.server_args import ServerArgs
from sglang.srt.utils.network import NetworkAddress, get_local_ip_auto

logger = logging.getLogger(__name__)


class RemoteInstanceWeightTransport:

    def __init__(
        self,
        *,
        server_args: ServerArgs,
        get_model: Callable[[], torch.nn.Module],
        tp_rank: int,
        gpu_id: int,
    ):
        self.server_args = server_args
        self.get_model = get_model
        self.tp_rank = tp_rank
        self.gpu_id = gpu_id
        self.remote_instance_transfer_engine = None
        self.remote_instance_transfer_engine_session_id = ""
        self.remote_instance_transfer_engine_weight_info = None
        self._nixl_manager = None

    @property
    def model(self) -> torch.nn.Module:
        # Always read through the getter — ModelRunner may swap ``self.model``
        # during weight reload, so a captured object reference would go stale.
        return self.get_model()

'''


def transform(wt: Path) -> None:
    mr = wt / "python/sglang/srt/model_executor/model_runner.py"
    transport = wt / "python/sglang/srt/model_executor/model_runner_components/remote_instance_weight_transport.py"

    # ---- Cut remote_instance_init_transfer_engine; body refs original fields, ----
    # ---- so it pastes onto the transport class verbatim (just leading indent).  ----
    start, end = find_method_lines(
        mr.read_text(),
        class_name="ModelRunner",
        method_name="remote_instance_init_transfer_engine",
    )
    method_text = cut_lines(mr, start, end)
    transport.write_text(TRANSPORT_HEADER + method_text.rstrip() + "\n")

    # ---- Update ModelRunner: import, replace 3 init lines, rewrite callers ----
    text = mr.read_text()

    text = insert_after(
        text,
        anchor="from sglang.srt.model_executor.model_runner_components.pool_configurator import MemoryPoolConfig\n",
        addition=(
            "from sglang.srt.model_executor.model_runner_components.remote_instance_weight_transport import (\n"
            "    RemoteInstanceWeightTransport,\n"
            ")\n"
        ),
    )

    # Replace the 3 init-time field assignments with a call to a fresh
    # ``init_remote_instance_weight_transport`` helper (per MECH_COMMIT_SPLIT
    # "长 ctor → init_X" rule — the ctor is a multi-line kwarg call, so it
    # lives in its own method instead of inlined in ``__init__``).
    text = replace_call_site(
        text,
        old=(
            "        self.remote_instance_transfer_engine = None\n"
            '        self.remote_instance_transfer_engine_session_id = ""\n'
            "        self.remote_instance_transfer_engine_weight_info = None\n"
        ),
        new="        self.init_remote_instance_weight_transport()\n",
    )
    # Insert the new init helper method just before ``_build_model_config``.
    # ``model`` is a Callable getter so the transport always sees ModelRunner's
    # current model (weight reload paths may replace ``self.model``).
    helper_method = (
        "    def init_remote_instance_weight_transport(self):\n"
        "        self.remote_instance_weight_transport = RemoteInstanceWeightTransport(\n"
        "            server_args=self.server_args,\n"
        "            get_model=lambda: self.model,\n"
        "            tp_rank=self.tp_rank,\n"
        "            gpu_id=self.gpu_id,\n"
        "        )\n"
        "\n"
    )
    text = text.replace(
        "    def _build_model_config(",
        helper_method + "    def _build_model_config(",
        1,
    )

    # Sole call-site of remote_instance_init_transfer_engine.
    text = replace_call_site(
        text,
        old="self.remote_instance_init_transfer_engine()",
        new="self.remote_instance_weight_transport.remote_instance_init_transfer_engine()",
    )

    # All remaining references to the 3 lifecycle fields move onto the transport.
    text = text.replace(
        "self.remote_instance_transfer_engine_session_id",
        "self.remote_instance_weight_transport.remote_instance_transfer_engine_session_id",
    )
    text = text.replace(
        "self.remote_instance_transfer_engine_weight_info",
        "self.remote_instance_weight_transport.remote_instance_transfer_engine_weight_info",
    )
    text = text.replace(
        "self.remote_instance_transfer_engine",
        "self.remote_instance_weight_transport.remote_instance_transfer_engine",
    )
    # `_nixl_manager` is only ever written by _build_nixl_worker_metadata
    # (migrated in /42). Reroute the would-be write site preemptively so /42
    # does not need to re-touch this file.
    text = text.replace(
        "self._nixl_manager",
        "self.remote_instance_weight_transport._nixl_manager",
    )
    mr.write_text(text)

    # Absorbed from rwt-mech-rename + rwt-mech-slots: shorter names (class
    # name carries ``RemoteInstance`` semantic) and ``@dataclass(slots,
    # kw_only)`` form. Not frozen — engine/session_id/weight_info/_nixl_manager
    # are lifecycle fields written across multiple methods after construction.
    _rename_and_slot_transport(wt)


_INSIDE_RWT_SUBS = [
    # field renames (longest first so suffix subs do not half-rewrite the longer)
    ("self.remote_instance_transfer_engine_session_id", "self.session_id"),
    ("self.remote_instance_transfer_engine_weight_info", "self.weight_info"),
    ("self.remote_instance_transfer_engine", "self.engine"),
    # method def lines
    ("def remote_instance_init_transfer_engine", "def init_engine"),
    ("def _register_to_engine_info_bootstrap", "def register_to_bootstrap"),
    ("def _publish_modelexpress_metadata", "def publish_to_modelexpress"),
    # internal method calls
    ("self.remote_instance_init_transfer_engine(", "self.init_engine("),
    ("self._register_to_engine_info_bootstrap(", "self.register_to_bootstrap("),
    ("self._publish_modelexpress_metadata(", "self.publish_to_modelexpress("),
]


_OUTSIDE_RWT_SUBS = [
    (
        "remote_instance_weight_transport.remote_instance_transfer_engine_session_id",
        "remote_instance_weight_transport.session_id",
    ),
    (
        "remote_instance_weight_transport.remote_instance_transfer_engine_weight_info",
        "remote_instance_weight_transport.weight_info",
    ),
    (
        "remote_instance_weight_transport.remote_instance_init_transfer_engine",
        "remote_instance_weight_transport.init_engine",
    ),
    (
        "remote_instance_weight_transport.remote_instance_transfer_engine",
        "remote_instance_weight_transport.engine",
    ),
    (
        "remote_instance_weight_transport._register_to_engine_info_bootstrap",
        "remote_instance_weight_transport.register_to_bootstrap",
    ),
    (
        "remote_instance_weight_transport._publish_modelexpress_metadata",
        "remote_instance_weight_transport.publish_to_modelexpress",
    ),
]


def _rename_and_slot_transport(wt: Path) -> None:
    src = wt / "python/sglang/srt/model_executor/model_runner_components/remote_instance_weight_transport.py"
    text = src.read_text()
    for old, new in _INSIDE_RWT_SUBS:
        text = text.replace(old, new)
    # Apply rwt-mech-slots: replace handwritten __init__ with dataclass form.
    text = insert_after(
        text,
        anchor="from sglang.srt.utils.network import NetworkAddress, get_local_ip_auto\n",
        addition=(
            "from dataclasses import dataclass\n"
            "from typing import Any, Callable, Optional\n"
        ),
    )
    text = replace_call_site(
        text,
        old=(
            "class RemoteInstanceWeightTransport:\n"
            "\n"
            "    def __init__(\n"
            "        self,\n"
            "        *,\n"
            "        server_args: ServerArgs,\n"
            "        get_model: Callable[[], torch.nn.Module],\n"
            "        tp_rank: int,\n"
            "        gpu_id: int,\n"
            "    ):\n"
            "        self.server_args = server_args\n"
            "        self.get_model = get_model\n"
            "        self.tp_rank = tp_rank\n"
            "        self.gpu_id = gpu_id\n"
            "        self.engine = None\n"
            "        self.session_id = \"\"\n"
            "        self.weight_info = None\n"
            "        self._nixl_manager = None\n"
            "\n"
            "    @property\n"
            "    def model(self) -> torch.nn.Module:\n"
            "        # Always read through the getter — ModelRunner may swap ``self.model``\n"
            "        # during weight reload, so a captured object reference would go stale.\n"
            "        return self.get_model()\n"
        ),
        new=(
            "# Lifecycle fields (engine / session_id / weight_info / _nixl_manager)\n"
            "# are written across multiple methods after construction — explicit R5\n"
            "# exception, hence `slots=True, kw_only=True` without `frozen=True`.\n"
            "@dataclass(slots=True, kw_only=True)\n"
            "class RemoteInstanceWeightTransport:\n"
            "    server_args: ServerArgs\n"
            "    get_model: Callable[[], torch.nn.Module]\n"
            "    tp_rank: int\n"
            "    gpu_id: int\n"
            "    engine: Optional[Any] = None\n"
            '    session_id: str = ""\n'
            "    weight_info: Optional[dict[str, tuple[int, int, int]]] = None\n"
            "    _nixl_manager: Optional[Any] = None\n"
            "\n"
            "    @property\n"
            "    def model(self) -> torch.nn.Module:\n"
            "        # Always read through the getter — ModelRunner may swap ``self.model``\n"
            "        # during weight reload, so a captured object reference would go stale.\n"
            "        return self.get_model()\n"
        ),
    )
    src.write_text(text)

    mr = wt / "python/sglang/srt/model_executor/model_runner.py"
    text = mr.read_text()
    for old, new in _OUTSIDE_RWT_SUBS:
        text = text.replace(old, new)
    mr.write_text(text)


if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        area_branch=AREA_BRANCH,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
