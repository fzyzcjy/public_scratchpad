#!/usr/bin/env python3
"""Convert ``RemoteInstanceWeightTransport`` to
``@dataclass(slots=True, kw_only=True)`` (no ``frozen``).

Why no frozen: ``engine`` / ``session_id`` / ``weight_info`` /
``_nixl_manager`` are *lifecycle* fields written across multiple
methods (``init_engine`` writes engine + session_id;
``model_runner.initialize`` writes weight_info; nixl manager set up
in ``publish_to_modelexpress``). ``frozen=True`` would block those
writes — explicit R5 exception.

Replace the handwritten ``__init__`` (4 narrow kwargs + 4 lifecycle
default-inits) with the dataclass-generated form. Lifecycle fields
take their original ``None`` / ``""`` defaults.

Usage:
    uv run --python 3.12 rwt-mech-slots.py run
    uv run --python 3.12 rwt-mech-slots.py verify
"""

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

ID = "rwt-mech-slots"
SUBJECT = "RemoteInstanceWeightTransport: @dataclass(slots, kw_only)"
BODY = ""
AREA = "mech_model_runner"
BASE = "tom_refactor_202605a/primary/mech_model_runner/rwt-mech-rename"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


def transform(wt: Path) -> None:
    src = wt / "python/sglang/srt/model_executor/remote_instance_weight_transport.py"
    text = src.read_text()
    if "from dataclasses import dataclass" not in text:
        text = insert_after(
            text,
            anchor="from sglang.srt.utils.network import NetworkAddress, get_local_ip_auto\n",
            addition=(
                "from dataclasses import dataclass\n"
                "from typing import Any, Optional\n"
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
            "        model: torch.nn.Module,\n"
            "        tp_rank: int,\n"
            "        gpu_id: int,\n"
            "    ):\n"
            "        self.server_args = server_args\n"
            "        self.model = model\n"
            "        self.tp_rank = tp_rank\n"
            "        self.gpu_id = gpu_id\n"
            "        self.engine = None\n"
            "        self.session_id = \"\"\n"
            "        self.weight_info = None\n"
            "        self._nixl_manager = None\n"
        ),
        new=(
            "# Lifecycle fields (engine / session_id / weight_info / _nixl_manager)\n"
            "# are written across multiple methods after construction — explicit R5\n"
            "# exception, hence `slots=True, kw_only=True` without `frozen=True`.\n"
            "@dataclass(slots=True, kw_only=True)\n"
            "class RemoteInstanceWeightTransport:\n"
            "    server_args: ServerArgs\n"
            "    model: torch.nn.Module\n"
            "    tp_rank: int\n"
            "    gpu_id: int\n"
            "    engine: Optional[Any] = None\n"
            '    session_id: str = ""\n'
            "    weight_info: Optional[dict[str, tuple[int, int, int]]] = None\n"
            "    _nixl_manager: Optional[Any] = None\n"
        ),
    )
    src.write_text(text)


if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        area_branch=AREA_BRANCH,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
