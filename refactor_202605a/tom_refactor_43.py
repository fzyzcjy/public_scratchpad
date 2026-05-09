#!/usr/bin/env python3
"""Reproducible transform: migrate `_publish_modelexpress_metadata`,
`_build_transfer_engine_worker_metadata`, and `_build_nixl_worker_metadata`
from `ModelRunner` to `RemoteInstanceWeightTransport`.

The two `_build_*` helpers are referenced only from
`_publish_modelexpress_metadata`, so they are deleted from `ModelRunner`
without leaving delegates. `_publish_modelexpress_metadata` is still called
from the `load_model` body, so it remains on `ModelRunner` as a 1-line
delegate.

Inside the transport class, `self.remote_instance_weight_transport.X` -> `self.X`
(R6 — only allowed mechanical fix).
"""

import sys
from pathlib import Path

sys.path.append(".claude/skills/mechanical-refactor-verify")
from mechanical_refactor_verify_utils import (
    verify_mechanical_refactor,
    git_add_and_commit,
)

BASE_COMMIT = "tom_refactor/42"
TARGET_COMMIT = "tom_refactor/43"


def transform(dir_root: Path) -> None:
    # ---- Update transport class: append the 3 migrated methods + needed imports ----
    transport = (
        dir_root
        / "python/sglang/srt/model_executor/remote_instance_weight_transport.py"
    )
    text = transport.read_text()

    # Add `import uuid` and `import torch` near the top (used by migrated bodies).
    old_top = (
        "import logging\n"
        "from typing import TYPE_CHECKING\n"
    )
    new_top = (
        "import logging\n"
        "import uuid\n"
        "from typing import TYPE_CHECKING\n"
        "\n"
        "import torch\n"
    )
    assert old_top in text
    text = text.replace(old_top, new_top)

    new_methods = (
        "\n"
        "    def _publish_modelexpress_metadata(self):\n"
        '        """Publish metadata to ModelExpress server (seed mode).\n'
        "\n"
        "        Supports two transport backends:\n"
        "        - transfer_engine: publishes TransferEngine session_id (Mooncake)\n"
        "        - nixl: creates NIXL agent, registers tensors, publishes nixl_metadata\n"
        '        """\n'
        "        try:\n"
        "            from modelexpress import p2p_pb2\n"
        "            from modelexpress.client import MxClient\n"
        "        except ImportError as exc:\n"
        "            raise ImportError(\n"
        '                "ModelExpress support requires the \'modelexpress\' package. "\n'
        '                "Install it with: pip install modelexpress"\n'
        "            ) from exc\n"
        "\n"
        "        model_name = (\n"
        "            self.server_args.modelexpress_model_name or self.server_args.model_path\n"
        "        )\n"
        "        mx_url = self.server_args.modelexpress_url\n"
        "        transport = self.server_args.modelexpress_transport\n"
        "\n"
        "        # Build SourceIdentity for this instance\n"
        "        identity = p2p_pb2.SourceIdentity(\n"
        "            model_name=model_name,\n"
        "            backend_framework=p2p_pb2.BACKEND_FRAMEWORK_SGLANG,\n"
        "            tensor_parallel_size=self.server_args.tp_size,\n"
        "            pipeline_parallel_size=self.server_args.pp_size,\n"
        "            expert_parallel_size=self.server_args.ep_size,\n"
        '            dtype=self.server_args.dtype or "",\n'
        '            quantization=self.server_args.quantization or "",\n'
        "        )\n"
        "\n"
        '        if transport == "nixl":\n'
        "            worker, tensor_count = self._build_nixl_worker_metadata(p2p_pb2)\n"
        "        else:\n"
        "            worker, tensor_count = self._build_transfer_engine_worker_metadata(p2p_pb2)\n"
        "            if worker is None:\n"
        "                return\n"
        "\n"
        "        # Generate a unique worker_id for this running instance\n"
        "        worker_id = str(uuid.uuid4())\n"
        "\n"
        "        mx_client = MxClient(server_url=mx_url)\n"
        "        try:\n"
        "            logger.info(\n"
        '                "ModelExpress source [%s]: publishing metadata for model=%s, "\n'
        '                "tp_rank=%d, %d tensors, worker_id=%s",\n'
        "                transport,\n"
        "                model_name,\n"
        "                self.tp_rank,\n"
        "                tensor_count,\n"
        "                worker_id,\n"
        "            )\n"
        "            mx_source_id = mx_client.publish_metadata(identity, worker, worker_id)\n"
        "            mx_client.update_status(\n"
        "                mx_source_id=mx_source_id,\n"
        "                worker_id=worker_id,\n"
        "                worker_rank=self.tp_rank,\n"
        "                status=p2p_pb2.SOURCE_STATUS_READY,\n"
        "            )\n"
        "            logger.info(\n"
        '                "ModelExpress source: published ready for model=%s, "\n'
        '                "tp_rank=%d, mx_source_id=%s",\n'
        "                model_name,\n"
        "                self.tp_rank,\n"
        "                mx_source_id,\n"
        "            )\n"
        "        finally:\n"
        "            mx_client.close()\n"
        "\n"
        "    def _build_transfer_engine_worker_metadata(self, p2p_pb2):\n"
        '        """Build WorkerMetadata using TransferEngine session_id."""\n'
        "        session_id = self.session_id\n"
        "        weight_info = self.weight_info\n"
        "\n"
        "        if not session_id or weight_info is None:\n"
        "            logger.warning(\n"
        '                "ModelExpress source: skipping publish -- "\n'
        '                "TransferEngine not initialized or no weight info"\n'
        "            )\n"
        "            return None, 0\n"
        "\n"
        "        tensors = []\n"
        "        for name, (addr, numel, element_size) in weight_info.items():\n"
        "            tensors.append(\n"
        "                p2p_pb2.TensorDescriptor(\n"
        "                    name=name,\n"
        "                    addr=addr,\n"
        "                    size=numel * element_size,\n"
        "                    device_id=self.gpu_id,\n"
        "                )\n"
        "            )\n"
        "\n"
        "        worker = p2p_pb2.WorkerMetadata(\n"
        "            worker_rank=self.tp_rank,\n"
        "            transfer_engine_session_id=session_id,\n"
        "            tensors=tensors,\n"
        "        )\n"
        "        return worker, len(tensors)\n"
        "\n"
        "    def _build_nixl_worker_metadata(self, p2p_pb2):\n"
        '        """Build WorkerMetadata using NIXL agent for RDMA transfers."""\n'
        "        from modelexpress.nixl_transfer import NixlTransferManager\n"
        "\n"
        '        agent_name = f"sglang-seed-rank{self.tp_rank}-{uuid.uuid4().hex[:8]}"\n'
        "        nixl_mgr = NixlTransferManager(agent_name, self.gpu_id)\n"
        "        nixl_mgr.initialize()\n"
        "\n"
        "        # Collect model tensors for NIXL registration\n"
        "        model_tensors = {}\n"
        "        for name, param in self.model_ref.named_parameters():\n"
        "            t = param.data\n"
        "            if t.is_contiguous():\n"
        "                model_tensors[name] = t\n"
        "            else:\n"
        "                # Non-contiguous tensors: register underlying storage as byte view\n"
        "                sv = torch.empty(0, dtype=torch.uint8, device=t.device).set_(\n"
        "                    t.untyped_storage()\n"
        "                )\n"
        "                if sv.data_ptr() not in {v.data_ptr() for v in model_tensors.values()}:\n"
        '                    model_tensors[f"{name}.__storage"] = sv\n'
        "\n"
        "        nixl_metadata = nixl_mgr.register_tensors(model_tensors)\n"
        "\n"
        "        # Build tensor descriptors from registered tensors\n"
        "        tensors = []\n"
        "        for td in nixl_mgr.tensor_descriptors:\n"
        "            tensors.append(\n"
        "                p2p_pb2.TensorDescriptor(\n"
        "                    name=td.name,\n"
        "                    addr=td.addr,\n"
        "                    size=td.size,\n"
        "                    device_id=td.device_id,\n"
        "                    dtype=td.dtype,\n"
        "                )\n"
        "            )\n"
        "\n"
        "        worker = p2p_pb2.WorkerMetadata(\n"
        "            worker_rank=self.tp_rank,\n"
        "            nixl_metadata=nixl_metadata,\n"
        "            tensors=tensors,\n"
        "        )\n"
        "\n"
        "        # Keep reference alive so NIXL agent isn't garbage collected\n"
        "        self._nixl_manager = nixl_mgr\n"
        "\n"
        "        return worker, len(tensors)\n"
    )
    text = text.rstrip() + "\n" + new_methods
    transport.write_text(text)

    # ---- Update model_runner.py: delegate publish, delete the two helpers ----
    mr = dir_root / "python/sglang/srt/model_executor/model_runner.py"
    text = mr.read_text()

    # Replace the 3 methods (publish + two builders) with a single 1-line
    # delegate for `_publish_modelexpress_metadata`. The two builders are
    # only referenced from publish, which now lives on the transport class,
    # so they are dropped from ModelRunner entirely.
    old_block = (
        "    def _publish_modelexpress_metadata(self):\n"
        '        """Publish metadata to ModelExpress server (seed mode).\n'
        "\n"
        "        Supports two transport backends:\n"
        "        - transfer_engine: publishes TransferEngine session_id (Mooncake)\n"
        "        - nixl: creates NIXL agent, registers tensors, publishes nixl_metadata\n"
        '        """\n'
        "        try:\n"
        "            from modelexpress import p2p_pb2\n"
        "            from modelexpress.client import MxClient\n"
        "        except ImportError as exc:\n"
        "            raise ImportError(\n"
        '                "ModelExpress support requires the \'modelexpress\' package. "\n'
        '                "Install it with: pip install modelexpress"\n'
        "            ) from exc\n"
        "\n"
        "        model_name = (\n"
        "            self.server_args.modelexpress_model_name or self.server_args.model_path\n"
        "        )\n"
        "        mx_url = self.server_args.modelexpress_url\n"
        "        transport = self.server_args.modelexpress_transport\n"
        "\n"
        "        # Build SourceIdentity for this instance\n"
        "        identity = p2p_pb2.SourceIdentity(\n"
        "            model_name=model_name,\n"
        "            backend_framework=p2p_pb2.BACKEND_FRAMEWORK_SGLANG,\n"
        "            tensor_parallel_size=self.server_args.tp_size,\n"
        "            pipeline_parallel_size=self.server_args.pp_size,\n"
        "            expert_parallel_size=self.server_args.ep_size,\n"
        '            dtype=self.server_args.dtype or "",\n'
        '            quantization=self.server_args.quantization or "",\n'
        "        )\n"
        "\n"
        '        if transport == "nixl":\n'
        "            worker, tensor_count = self._build_nixl_worker_metadata(p2p_pb2)\n"
        "        else:\n"
        "            worker, tensor_count = self._build_transfer_engine_worker_metadata(p2p_pb2)\n"
        "            if worker is None:\n"
        "                return\n"
        "\n"
        "        # Generate a unique worker_id for this running instance\n"
        "        worker_id = str(uuid.uuid4())\n"
        "\n"
        "        mx_client = MxClient(server_url=mx_url)\n"
        "        try:\n"
        "            logger.info(\n"
        '                "ModelExpress source [%s]: publishing metadata for model=%s, "\n'
        '                "tp_rank=%d, %d tensors, worker_id=%s",\n'
        "                transport,\n"
        "                model_name,\n"
        "                self.tp_rank,\n"
        "                tensor_count,\n"
        "                worker_id,\n"
        "            )\n"
        "            mx_source_id = mx_client.publish_metadata(identity, worker, worker_id)\n"
        "            mx_client.update_status(\n"
        "                mx_source_id=mx_source_id,\n"
        "                worker_id=worker_id,\n"
        "                worker_rank=self.tp_rank,\n"
        "                status=p2p_pb2.SOURCE_STATUS_READY,\n"
        "            )\n"
        "            logger.info(\n"
        '                "ModelExpress source: published ready for model=%s, "\n'
        '                "tp_rank=%d, mx_source_id=%s",\n'
        "                model_name,\n"
        "                self.tp_rank,\n"
        "                mx_source_id,\n"
        "            )\n"
        "        finally:\n"
        "            mx_client.close()\n"
        "\n"
        "    def _build_transfer_engine_worker_metadata(self, p2p_pb2):\n"
        '        """Build WorkerMetadata using TransferEngine session_id."""\n'
        "        session_id = self.remote_instance_weight_transport.session_id\n"
        "        weight_info = self.remote_instance_weight_transport.weight_info\n"
        "\n"
        "        if not session_id or weight_info is None:\n"
        "            logger.warning(\n"
        '                "ModelExpress source: skipping publish -- "\n'
        '                "TransferEngine not initialized or no weight info"\n'
        "            )\n"
        "            return None, 0\n"
        "\n"
        "        tensors = []\n"
        "        for name, (addr, numel, element_size) in weight_info.items():\n"
        "            tensors.append(\n"
        "                p2p_pb2.TensorDescriptor(\n"
        "                    name=name,\n"
        "                    addr=addr,\n"
        "                    size=numel * element_size,\n"
        "                    device_id=self.gpu_id,\n"
        "                )\n"
        "            )\n"
        "\n"
        "        worker = p2p_pb2.WorkerMetadata(\n"
        "            worker_rank=self.tp_rank,\n"
        "            transfer_engine_session_id=session_id,\n"
        "            tensors=tensors,\n"
        "        )\n"
        "        return worker, len(tensors)\n"
        "\n"
        "    def _build_nixl_worker_metadata(self, p2p_pb2):\n"
        '        """Build WorkerMetadata using NIXL agent for RDMA transfers."""\n'
        "        from modelexpress.nixl_transfer import NixlTransferManager\n"
        "\n"
        '        agent_name = f"sglang-seed-rank{self.tp_rank}-{uuid.uuid4().hex[:8]}"\n'
        "        nixl_mgr = NixlTransferManager(agent_name, self.gpu_id)\n"
        "        nixl_mgr.initialize()\n"
        "\n"
        "        # Collect model tensors for NIXL registration\n"
        "        model_tensors = {}\n"
        "        for name, param in self.remote_instance_weight_transport.model_ref.named_parameters():\n"
        "            t = param.data\n"
        "            if t.is_contiguous():\n"
        "                model_tensors[name] = t\n"
        "            else:\n"
        "                # Non-contiguous tensors: register underlying storage as byte view\n"
        "                sv = torch.empty(0, dtype=torch.uint8, device=t.device).set_(\n"
        "                    t.untyped_storage()\n"
        "                )\n"
        "                if sv.data_ptr() not in {v.data_ptr() for v in model_tensors.values()}:\n"
        '                    model_tensors[f"{name}.__storage"] = sv\n'
        "\n"
        "        nixl_metadata = nixl_mgr.register_tensors(model_tensors)\n"
        "\n"
        "        # Build tensor descriptors from registered tensors\n"
        "        tensors = []\n"
        "        for td in nixl_mgr.tensor_descriptors:\n"
        "            tensors.append(\n"
        "                p2p_pb2.TensorDescriptor(\n"
        "                    name=td.name,\n"
        "                    addr=td.addr,\n"
        "                    size=td.size,\n"
        "                    device_id=td.device_id,\n"
        "                    dtype=td.dtype,\n"
        "                )\n"
        "            )\n"
        "\n"
        "        worker = p2p_pb2.WorkerMetadata(\n"
        "            worker_rank=self.tp_rank,\n"
        "            nixl_metadata=nixl_metadata,\n"
        "            tensors=tensors,\n"
        "        )\n"
        "\n"
        "        # Keep reference alive so NIXL agent isn't garbage collected\n"
        "        self.remote_instance_weight_transport._nixl_manager = nixl_mgr\n"
        "\n"
        "        return worker, len(tensors)\n"
    )
    new_block = (
        "    def _publish_modelexpress_metadata(self):\n"
        "        return self.remote_instance_weight_transport._publish_modelexpress_metadata()\n"
    )
    assert old_block in text, "old modelexpress methods block not found"
    text = text.replace(old_block, new_block)

    mr.write_text(text)

    git_add_and_commit(
        "Migrate ModelExpress metadata publishing to RemoteInstanceWeightTransport",
        cwd=str(dir_root),
    )


if __name__ == "__main__":
    verify_mechanical_refactor(
        base_commit=BASE_COMMIT,
        target_commit=TARGET_COMMIT,
        transform=transform,
    )
