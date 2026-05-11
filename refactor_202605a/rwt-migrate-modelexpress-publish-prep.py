#!/usr/bin/env python3
"""Prep stage for rwt-migrate-modelexpress-publish (MECH_COMMIT_SPLIT §"拆 class 场景"):

Reshape 3 methods (``_publish_modelexpress_metadata``,
``_build_transfer_engine_worker_metadata``, ``_build_nixl_worker_metadata``)
toward becoming ``RemoteInstanceWeightTransport`` methods.
- ``@staticmethod`` + ``self: RemoteInstanceWeightTransport``.
- Body: ``self.remote_instance_weight_transport.X`` → ``self.X``.
- Inner cross-method calls in ``_publish_modelexpress_metadata`` become
  class-qualified ``ModelRunner._build_X(self, ...)``.
- External caller becomes ``ModelRunner._publish_modelexpress_metadata(
  self.remote_instance_weight_transport)``.
"""

# /// script
# requires-python = ">=3.10"
# dependencies = ["typer"]
# ///

import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from _helpers import find_method_lines, replace_call_site
from _runner import run_pr

ID = "rwt-migrate-modelexpress-publish-prep"
SUBJECT = "Prep ModelExpress publish methods for move onto RemoteInstanceWeightTransport"
BODY = ""
AREA = "mech_model_runner"
BASE = "tom_refactor_202605a/primary/mech_model_runner/rwt-migrate-register-bootstrap-move"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


_METHODS = (
    "_publish_modelexpress_metadata",
    "_build_transfer_engine_worker_metadata",
    "_build_nixl_worker_metadata",
)


def _reshape(text: str, *, method_name: str) -> str:
    start, end = find_method_lines(text, class_name="ModelRunner", method_name=method_name)
    lines = text.splitlines(keepends=True)
    method = "".join(lines[start:end])
    # Signature swap.
    if f"    def {method_name}(\n        self,\n" in method:
        method = method.replace(
            f"    def {method_name}(\n        self,\n",
            f"    @staticmethod\n    def {method_name}(\n        self: \"RemoteInstanceWeightTransport\",\n",
            1,
        )
    else:
        method = method.replace(
            f"    def {method_name}(self",
            f"    @staticmethod\n    def {method_name}(self: \"RemoteInstanceWeightTransport\"",
            1,
        )
    method = method.replace("self.remote_instance_weight_transport.", "self.")
    return "".join(lines[:start]) + method + "".join(lines[end:])


def transform(wt: Path) -> None:
    mr = wt / "python/sglang/srt/model_executor/model_runner.py"
    text = mr.read_text()
    for name in _METHODS:
        text = _reshape(text, method_name=name)
    # Inner cross-method calls inside _publish_modelexpress_metadata body.
    text = replace_call_site(
        text,
        old="self._build_nixl_worker_metadata(p2p_pb2)",
        new="ModelRunner._build_nixl_worker_metadata(self, p2p_pb2)",
    )
    text = replace_call_site(
        text,
        old="self._build_transfer_engine_worker_metadata(p2p_pb2)",
        new="ModelRunner._build_transfer_engine_worker_metadata(self, p2p_pb2)",
    )
    # External caller (same file).
    text = replace_call_site(
        text,
        old="self._publish_modelexpress_metadata()",
        new="ModelRunner._publish_modelexpress_metadata(self.remote_instance_weight_transport)",
    )
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
