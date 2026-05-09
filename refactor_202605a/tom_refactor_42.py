#!/usr/bin/env python3
"""Reproducible transform: migrate `_register_to_engine_info_bootstrap` from
`ModelRunner` to `RemoteInstanceWeightTransport`.

After /41, the body already references the transport's fields via
`self.remote_instance_weight_transport.<field>`. Lifting it into the transport
class is then byte-equivalent except for `self.remote_instance_weight_transport.X`
-> `self.X` (R6 — the only allowed mechanical fix on the migrated body).

The ModelRunner method becomes a 1-line delegate.
"""

import sys
from pathlib import Path

sys.path.append(".claude/skills/mechanical-refactor-verify")
from mechanical_refactor_verify_utils import (
    verify_mechanical_refactor,
    git_add_and_commit,
)

BASE_COMMIT = "tom_refactor/41"
TARGET_COMMIT = "tom_refactor/42"


def transform(dir_root: Path) -> None:
    # ---- Update transport class ----
    transport = (
        dir_root
        / "python/sglang/srt/model_executor/remote_instance_weight_transport.py"
    )
    text = transport.read_text()

    # Append the migrated method to the end of the class. The method body uses
    # `self.<field>` directly because it now lives on the transport.
    new_method = (
        "\n"
        "    def _register_to_engine_info_bootstrap(self):\n"
        '        """Register transfer engine info with the EngineInfoBootstrapServer via HTTP PUT.\n'
        "\n"
        "        The bootstrap server runs on node_rank==0. For multi-node setups, the\n"
        "        host is derived from dist_init_addr. For single-node, use 127.0.0.1.\n"
        '        """\n'
        "        import requests as http_requests\n"
        "\n"
        "        if self.server_args.dist_init_addr:\n"
        "            # Multi-node: bootstrap server is on the head node (node_rank==0).\n"
        "            # Derive host from dist_init_addr (shared across all nodes).\n"
        "            bootstrap_host = (\n"
        "                NetworkAddress.parse(self.server_args.dist_init_addr).resolved().host\n"
        "            )\n"
        "        else:\n"
        '            bootstrap_host = "127.0.0.1"\n'
        "\n"
        "        bootstrap_port = self.server_args.engine_info_bootstrap_port\n"
        "        bootstrap_na = NetworkAddress(bootstrap_host, bootstrap_port)\n"
        '        url = f"{bootstrap_na.to_url()}/register_transfer_engine_info"\n'
        "\n"
        "        payload = {\n"
        '            "tp_rank": self.tp_rank,\n'
        '            "transfer_engine_info": {\n'
        '                "session_id": self.session_id,\n'
        '                "weights_info_dict": self.weight_info,\n'
        "            },\n"
        "        }\n"
        "\n"
        "        try:\n"
        "            resp = http_requests.put(url, json=payload, timeout=5)\n"
        "            if resp.status_code == 200:\n"
        "                logger.info(\n"
        '                    f"Registered transfer engine info for tp_rank={self.tp_rank} "\n'
        '                    f"with bootstrap server at {bootstrap_na}"\n'
        "                )\n"
        "            else:\n"
        "                logger.error(\n"
        '                    f"Failed to register transfer engine info for tp_rank={self.tp_rank}: "\n'
        '                    f"{resp.status_code}, {resp.text}"\n'
        "                )\n"
        "        except Exception as e:\n"
        "            logger.error(\n"
        '                f"Failed to register transfer engine info for tp_rank={self.tp_rank}: {e}"\n'
        "            )\n"
    )
    text = text.rstrip() + "\n" + new_method
    transport.write_text(text)

    # ---- Replace ModelRunner method with a 1-line delegate ----
    mr = dir_root / "python/sglang/srt/model_executor/model_runner.py"
    text = mr.read_text()

    old_body = (
        "    def _register_to_engine_info_bootstrap(self):\n"
        '        """Register transfer engine info with the EngineInfoBootstrapServer via HTTP PUT.\n'
        "\n"
        "        The bootstrap server runs on node_rank==0. For multi-node setups, the\n"
        "        host is derived from dist_init_addr. For single-node, use 127.0.0.1.\n"
        '        """\n'
        "        import requests as http_requests\n"
        "\n"
        "        if self.server_args.dist_init_addr:\n"
        "            # Multi-node: bootstrap server is on the head node (node_rank==0).\n"
        "            # Derive host from dist_init_addr (shared across all nodes).\n"
        "            bootstrap_host = (\n"
        "                NetworkAddress.parse(self.server_args.dist_init_addr).resolved().host\n"
        "            )\n"
        "        else:\n"
        '            bootstrap_host = "127.0.0.1"\n'
        "\n"
        "        bootstrap_port = self.server_args.engine_info_bootstrap_port\n"
        "        bootstrap_na = NetworkAddress(bootstrap_host, bootstrap_port)\n"
        '        url = f"{bootstrap_na.to_url()}/register_transfer_engine_info"\n'
        "\n"
        "        payload = {\n"
        '            "tp_rank": self.tp_rank,\n'
        '            "transfer_engine_info": {\n'
        '                "session_id": self.remote_instance_weight_transport.session_id,\n'
        '                "weights_info_dict": self.remote_instance_weight_transport.weight_info,\n'
        "            },\n"
        "        }\n"
        "\n"
        "        try:\n"
        "            resp = http_requests.put(url, json=payload, timeout=5)\n"
        "            if resp.status_code == 200:\n"
        "                logger.info(\n"
        '                    f"Registered transfer engine info for tp_rank={self.tp_rank} "\n'
        '                    f"with bootstrap server at {bootstrap_na}"\n'
        "                )\n"
        "            else:\n"
        "                logger.error(\n"
        '                    f"Failed to register transfer engine info for tp_rank={self.tp_rank}: "\n'
        '                    f"{resp.status_code}, {resp.text}"\n'
        "                )\n"
        "        except Exception as e:\n"
        "            logger.error(\n"
        '                f"Failed to register transfer engine info for tp_rank={self.tp_rank}: {e}"\n'
        "            )\n"
    )
    new_body = (
        "    def _register_to_engine_info_bootstrap(self):\n"
        "        return self.remote_instance_weight_transport._register_to_engine_info_bootstrap()\n"
    )
    assert old_body in text, "old _register_to_engine_info_bootstrap body not found"
    text = text.replace(old_body, new_body)

    mr.write_text(text)

    git_add_and_commit(
        "Migrate _register_to_engine_info_bootstrap to RemoteInstanceWeightTransport",
        cwd=str(dir_root),
    )


if __name__ == "__main__":
    verify_mechanical_refactor(
        base_commit=BASE_COMMIT,
        target_commit=TARGET_COMMIT,
        transform=transform,
    )
