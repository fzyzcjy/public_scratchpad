#!/usr/bin/env python3
"""Cut `_publish_modelexpress_metadata`, `_build_transfer_engine_worker_metadata`,
and `_build_nixl_worker_metadata` from ModelRunner; append all three to
`RemoteInstanceWeightTransport`. Update the sole external caller of
`_publish_modelexpress_metadata` to delegate via the transport.

The ``self.X`` references that were rewritten at /40's caller side (now
``self.remote_instance_weight_transport.X``) collapse back to ``self.X`` once
the methods live inside the transport class. ``self.model.named_parameters()``
in `_build_nixl_worker_metadata` keeps the original field name (``model`` on
the transport class).

Usage:
    uv run --python 3.12 rwt-migrate-modelexpress-publish.py run
    uv run --python 3.12 rwt-migrate-modelexpress-publish.py verify
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
    append_to_file,
    cut_lines,
    find_method_lines,
    insert_after,
    replace_call_site,
)
from _runner import run_pr

ID = "rwt-migrate-modelexpress-publish"
SUBJECT = "Migrate ModelExpress metadata publishing to RemoteInstanceWeightTransport"
BODY = ""
AREA = "mech_model_runner"
BASE = "tom_refactor_202605a/primary/mech_model_runner/rwt-migrate-register-bootstrap"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


def transform(wt: Path) -> None:
    mr = wt / "python/sglang/srt/model_executor/model_runner.py"
    transport = wt / "python/sglang/srt/model_executor/remote_instance_weight_transport.py"

    # Add imports needed by the migrated bodies (uuid for worker_id / agent_name,
    # torch for the storage byte-view fallback in the NIXL builder).
    text = transport.read_text()
    text = insert_after(
        text,
        anchor="import logging\n",
        addition="import uuid\n\nimport torch\n",
    )
    transport.write_text(text)

    # Cut the 3 methods one at a time, re-finding line ranges after each cut so
    # the AST sees the latest source text.
    cuts = []
    for method_name in (
        "_publish_modelexpress_metadata",
        "_build_transfer_engine_worker_metadata",
        "_build_nixl_worker_metadata",
    ):
        start, end = find_method_lines(
            mr.read_text(), class_name="ModelRunner", method_name=method_name
        )
        method_text = cut_lines(mr, start, end)
        method_text = method_text.replace(
            "self.remote_instance_weight_transport.", "self."
        )
        cuts.append(method_text)

    for method_text in cuts:
        append_to_file(transport, method_text.rstrip() + "\n")

    # The only external call-site is `self._publish_modelexpress_metadata()`.
    text = mr.read_text()
    text = replace_call_site(
        text,
        old="self._publish_modelexpress_metadata()",
        new="self.remote_instance_weight_transport._publish_modelexpress_metadata()",
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
