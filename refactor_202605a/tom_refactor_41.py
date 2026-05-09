#!/usr/bin/env python3
"""Cut `remote_instance_init_transfer_engine` from ModelRunner; introduce
`RemoteInstanceWeightTransport` skeleton class with that one method. Update
caller and ripple-rename remaining `self.remote_instance_transfer_engine*`
fields to live on the new transport object.
"""

import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.append(str(HERE))
sys.path.append(".claude/skills/mechanical-refactor-verify")
from _helpers import cut_lines, find_method_lines
from mechanical_refactor_verify_utils import git_add_and_commit, verify_mechanical_refactor

BASE_COMMIT = "tom_refactor/40"
TARGET_COMMIT = "tom_refactor/41"

TRANSPORT_HEADER = '''from __future__ import annotations

import logging

from sglang.srt.environ import envs
from sglang.srt.utils.network import NetworkAddress, get_local_ip_auto

logger = logging.getLogger(__name__)


class RemoteInstanceWeightTransport:

    def __init__(self, *, server_args, model_ref, tp_rank, gpu_id):
        self.server_args = server_args
        self.model_ref = model_ref
        self.tp_rank = tp_rank
        self.gpu_id = gpu_id
        self.engine = None
        self.session_id = ""
        self.weight_info = None
        self._nixl_manager = None

'''


def transform(dir_root: Path) -> None:
    mr = dir_root / "python/sglang/srt/model_executor/model_runner.py"
    transport = dir_root / "python/sglang/srt/model_executor/remote_instance_weight_transport.py"

    start, end = find_method_lines(mr.read_text(), class_name="ModelRunner", method_name="remote_instance_init_transfer_engine")
    method_text = cut_lines(mr, start, end)
    method_text = method_text.replace("self.remote_instance_transfer_engine_session_id", "self.session_id")
    method_text = method_text.replace("self.remote_instance_transfer_engine", "self.engine")
    transport.write_text(TRANSPORT_HEADER + method_text.rstrip() + "\n")

    text = mr.read_text()
    text = text.replace(
        "from sglang.srt.model_executor.kv_cache_configurator import KVCacheConfigurator\n",
        "from sglang.srt.model_executor.kv_cache_configurator import KVCacheConfigurator\n"
        "from sglang.srt.model_executor.remote_instance_weight_transport import RemoteInstanceWeightTransport\n",
    )
    text = text.replace(
        "        self.remote_instance_transfer_engine = None\n"
        '        self.remote_instance_transfer_engine_session_id = ""\n'
        "        self.remote_instance_transfer_engine_weight_info = None\n",
        "        self.remote_instance_weight_transport = RemoteInstanceWeightTransport(\n"
        "            server_args=server_args, model_ref=None, tp_rank=self.tp_rank, gpu_id=self.gpu_id,\n"
        "        )\n",
    )
    text = text.replace(
        "            self.model = self.loader.load_model(\n"
        "                model_config=self.model_config,\n"
        "                device_config=DeviceConfig(self.device, self.gpu_id),\n"
        "            )\n",
        "            self.model = self.loader.load_model(\n"
        "                model_config=self.model_config,\n"
        "                device_config=DeviceConfig(self.device, self.gpu_id),\n"
        "            )\n"
        "            self.remote_instance_weight_transport.model_ref = self.model\n",
    )
    text = text.replace(
        "self.remote_instance_init_transfer_engine()",
        "self.remote_instance_weight_transport.remote_instance_init_transfer_engine()",
    )
    text = text.replace(
        "self.remote_instance_transfer_engine_session_id",
        "self.remote_instance_weight_transport.session_id",
    )
    text = text.replace(
        "self.remote_instance_transfer_engine_weight_info",
        "self.remote_instance_weight_transport.weight_info",
    )
    text = text.replace(
        "self.remote_instance_transfer_engine",
        "self.remote_instance_weight_transport.engine",
    )
    text = text.replace(
        "self._nixl_manager",
        "self.remote_instance_weight_transport._nixl_manager",
    )
    mr.write_text(text)

    git_add_and_commit(
        "Extract RemoteInstanceWeightTransport skeleton with remote_instance_init_transfer_engine",
        cwd=str(dir_root),
    )


if __name__ == "__main__":
    verify_mechanical_refactor(base_commit=BASE_COMMIT, target_commit=TARGET_COMMIT, transform=transform)
