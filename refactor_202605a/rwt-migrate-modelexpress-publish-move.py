#!/usr/bin/env python3
"""Move stage for rwt-migrate-modelexpress-publish (MECH_COMMIT_SPLIT §"拆 class 场景"):

Cut 3 staticmethods to ``RemoteInstanceWeightTransport``. Bodies byte-equivalent.
Add uuid + torch imports the bodies need. Collapse all qualified calls.
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

ID = "rwt-migrate-modelexpress-publish-move"
SUBJECT = "Move ModelExpress publish methods onto RemoteInstanceWeightTransport (cut+paste)"
BODY = ""
AREA = "mech_model_runner"
BASE = "tom_refactor_202605a/primary/mech_model_runner/rwt-migrate-modelexpress-publish-prep"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


_METHODS = (
    "_publish_modelexpress_metadata",
    "_build_transfer_engine_worker_metadata",
    "_build_nixl_worker_metadata",
)


def _cut(mr: Path, method_name: str) -> str:
    s, e = find_method_lines(mr.read_text(), class_name="ModelRunner", method_name=method_name)
    method_text = cut_lines(mr, s, e)
    lines = method_text.splitlines(keepends=True)
    assert lines[0].strip() == "@staticmethod"
    body = "".join(lines[1:])
    body = body.replace('        self: "RemoteInstanceWeightTransport",\n', "        self,\n")
    body = body.replace('(self: "RemoteInstanceWeightTransport"', "(self")
    # Inner cross-method calls: now in target class, collapse to self.X(...).
    body = body.replace(
        "ModelRunner._build_nixl_worker_metadata(self, ",
        "self._build_nixl_worker_metadata(",
    )
    body = body.replace(
        "ModelRunner._build_transfer_engine_worker_metadata(self, ",
        "self._build_transfer_engine_worker_metadata(",
    )
    return body


def transform(wt: Path) -> None:
    mr = wt / "python/sglang/srt/model_executor/model_runner.py"
    transport = wt / "python/sglang/srt/model_executor/remote_instance_weight_transport.py"

    # Add imports the bodies need.
    text = transport.read_text()
    text = insert_after(
        text,
        anchor="import logging\n",
        addition="import uuid\n\nimport torch\n",
    )
    transport.write_text(text)

    cuts = [_cut(mr, name) for name in _METHODS]
    for body in cuts:
        append_to_file(transport, body.rstrip() + "\n")

    # External caller collapse — regex to tolerate pre-commit line wrap.
    text = mr.read_text()
    import re
    text = re.sub(
        r"ModelRunner\._publish_modelexpress_metadata\(\s*self\.remote_instance_weight_transport\s*\)",
        "self.remote_instance_weight_transport._publish_modelexpress_metadata()",
        text,
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
