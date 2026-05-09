#!/usr/bin/env python3
"""Reproducible transform: introduce `RemoteInstanceWeightTransport` skeleton
class with one migrated method (`remote_instance_init_transfer_engine`).

- Create `python/sglang/srt/model_executor/remote_instance_weight_transport.py`
  with the new class, its `__init__(*, server_args, tp_rank, gpu_id)`, the
  lifecycle fields (`engine`, `session_id`, `weight_info`, `_nixl_manager`,
  `model_ref`), and the migrated `remote_instance_init_transfer_engine` body.
- Delete the 3 lifecycle field assignments from `ModelRunner.__init__`
  (`remote_instance_transfer_engine`, `..._session_id`, `..._weight_info`),
  replaced by `self.remote_instance_weight_transport = ...`.
- Replace `ModelRunner.remote_instance_init_transfer_engine` with a 1-line
  delegate.
- Ripple-update every read/write of those 3 fields elsewhere in
  `model_runner.py` (load_model body, the still-on-ModelRunner methods
  `_register_to_engine_info_bootstrap` / `_publish_modelexpress_metadata` /
  `_build_transfer_engine_worker_metadata` / `_build_nixl_worker_metadata`)
  to use `self.remote_instance_weight_transport.<field>`.
- After `load_model`, assign `self.remote_instance_weight_transport.model_ref
  = self.model` so the metadata builders can iterate the live model.
"""

import sys
from pathlib import Path

sys.path.append(".claude/skills/mechanical-refactor-verify")
from mechanical_refactor_verify_utils import (
    verify_mechanical_refactor,
    git_add_and_commit,
)

BASE_COMMIT = "tom_refactor/40"
TARGET_COMMIT = "tom_refactor/41"


TRANSPORT_PY = '''
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from sglang.srt.environ import envs
from sglang.srt.utils.common import get_local_ip_auto
from sglang.srt.utils.network import NetworkAddress

if TYPE_CHECKING:
    from sglang.srt.model_executor.model_runner import ModelRunner  # noqa: F401

logger = logging.getLogger(__name__)


class RemoteInstanceWeightTransport:

    def __init__(
        self,
        *,
        server_args,
        tp_rank: int,
        gpu_id: int,
    ) -> None:
        self.server_args = server_args
        self.tp_rank = tp_rank
        self.gpu_id = gpu_id
        # Live model reference, wired in by ModelRunner after load_model.
        self.model_ref = None
        # Lifecycle state populated by the methods below.
        self.engine = None
        self.session_id: str = ""
        self.weight_info = None
        self._nixl_manager = None

    def remote_instance_init_transfer_engine(self):
        try:
            from mooncake.engine import TransferEngine
        except ImportError as e:
            logger.warning(
                "Please install mooncake for using remote instance transfer engine: pip install mooncake"
            )
            return
        self.engine = TransferEngine()
        local_ip = get_local_ip_auto()
        self.engine.initialize(
            local_ip, "P2PHANDSHAKE", "rdma", envs.MOONCAKE_DEVICE.get()
        )
        self.session_id = NetworkAddress(
            local_ip, self.engine.get_rpc_port()
        ).to_host_port_str()
'''


def transform(dir_root: Path) -> None:
    # ---- Create transport file ----
    transport = (
        dir_root
        / "python/sglang/srt/model_executor/remote_instance_weight_transport.py"
    )
    transport.write_text(TRANSPORT_PY)

    # ---- Update model_runner.py ----
    mr = dir_root / "python/sglang/srt/model_executor/model_runner.py"
    text = mr.read_text()

    # Add import.
    old_import_anchor = (
        "from sglang.srt.model_executor.kernel_warmup import kernel_warmup as _kernel_warmup\n"
        "from sglang.srt.model_executor.kv_cache_configurator import KVCacheConfigurator\n"
    )
    new_import_anchor = (
        "from sglang.srt.model_executor.kernel_warmup import kernel_warmup as _kernel_warmup\n"
        "from sglang.srt.model_executor.kv_cache_configurator import KVCacheConfigurator\n"
        "from sglang.srt.model_executor.remote_instance_weight_transport import (\n"
        "    RemoteInstanceWeightTransport,\n"
        ")\n"
    )
    assert old_import_anchor in text
    text = text.replace(old_import_anchor, new_import_anchor)

    # Replace the 3 explicit field assignments in __init__ with a single
    # transport construction.
    old_fields = (
        "        self.remote_instance_transfer_engine = None\n"
        '        self.remote_instance_transfer_engine_session_id = ""\n'
        "        self.remote_instance_transfer_engine_weight_info = None\n"
    )
    new_fields = (
        "        self.remote_instance_weight_transport = RemoteInstanceWeightTransport(\n"
        "            server_args=server_args,\n"
        "            tp_rank=self.tp_rank,\n"
        "            gpu_id=self.gpu_id,\n"
        "        )\n"
    )
    assert old_fields in text
    text = text.replace(old_fields, new_fields)

    # Replace remote_instance_init_transfer_engine body with a delegate.
    old_init_engine = (
        "    def remote_instance_init_transfer_engine(self):\n"
        "        try:\n"
        "            from mooncake.engine import TransferEngine\n"
        "        except ImportError as e:\n"
        "            logger.warning(\n"
        '                "Please install mooncake for using remote instance transfer engine: pip install mooncake"\n'
        "            )\n"
        "            return\n"
        "        self.remote_instance_transfer_engine = TransferEngine()\n"
        "        local_ip = get_local_ip_auto()\n"
        "        self.remote_instance_transfer_engine.initialize(\n"
        '            local_ip, "P2PHANDSHAKE", "rdma", envs.MOONCAKE_DEVICE.get()\n'
        "        )\n"
        "        self.remote_instance_transfer_engine_session_id = NetworkAddress(\n"
        "            local_ip, self.remote_instance_transfer_engine.get_rpc_port()\n"
        "        ).to_host_port_str()\n"
    )
    new_init_engine = (
        "    def remote_instance_init_transfer_engine(self):\n"
        "        return self.remote_instance_weight_transport.remote_instance_init_transfer_engine()\n"
    )
    assert old_init_engine in text
    text = text.replace(old_init_engine, new_init_engine)

    # Ripple-update remaining references.
    # NOTE: order matters: replace the longest names first so substrings
    # don't accidentally match the shorter prefix.
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

    # Wire the live model reference after load_model.
    old_after_load = (
        "            self.model = self.loader.load_model(\n"
        "                model_config=self.model_config,\n"
        "                device_config=DeviceConfig(self.device, self.gpu_id),\n"
        "            )\n"
        '            if hasattr(self.loader, "remote_instance_transfer_engine_weight_info"):\n'
    )
    new_after_load = (
        "            self.model = self.loader.load_model(\n"
        "                model_config=self.model_config,\n"
        "                device_config=DeviceConfig(self.device, self.gpu_id),\n"
        "            )\n"
        "            self.remote_instance_weight_transport.model_ref = self.model\n"
        '            if hasattr(self.loader, "remote_instance_transfer_engine_weight_info"):\n'
    )
    assert old_after_load in text
    text = text.replace(old_after_load, new_after_load)

    # `_build_nixl_worker_metadata` uses `self.model.named_parameters()`.
    # Switch it to `model_ref` so the body can later be lifted into the
    # transport class as-is (in /43).
    text = text.replace(
        "        for name, param in self.model.named_parameters():\n",
        "        for name, param in self.remote_instance_weight_transport.model_ref.named_parameters():\n",
    )

    mr.write_text(text)

    git_add_and_commit(
        "Extract RemoteInstanceWeightTransport skeleton with remote_instance_init_transfer_engine",
        cwd=str(dir_root),
    )


if __name__ == "__main__":
    verify_mechanical_refactor(
        base_commit=BASE_COMMIT,
        target_commit=TARGET_COMMIT,
        transform=transform,
    )
