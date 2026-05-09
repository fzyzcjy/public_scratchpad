#!/usr/bin/env python3
"""Cut `_publish_modelexpress_metadata`, `_build_transfer_engine_worker_metadata`,
and `_build_nixl_worker_metadata` from `ModelRunner`; append all three to
`RemoteInstanceWeightTransport`. Update the sole external caller of
`_publish_modelexpress_metadata` to delegate via the transport.
"""

import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.append(str(HERE))
sys.path.append(".claude/skills/mechanical-refactor-verify")
from _helpers import (
    append_to_file,
    cut_lines,
    find_method_lines,
    insert_after,
    replace_call_site,
)
from mechanical_refactor_verify_utils import (
    git_add_and_commit,
    verify_mechanical_refactor,
)

BASE_COMMIT = "tom_refactor/41"
TARGET_COMMIT = "tom_refactor/42"


def transform(dir_root: Path) -> None:
    mr = dir_root / "python/sglang/srt/model_executor/model_runner.py"
    transport = dir_root / "python/sglang/srt/model_executor/remote_instance_weight_transport.py"

    # The migrated bodies use uuid (worker_id, agent_name) and torch
    # (untyped_storage byte view); add those imports to the transport module.
    text = transport.read_text()
    text = insert_after(
        text,
        anchor="import logging\n",
        addition="import uuid\n\nimport torch\n",
    )
    transport.write_text(text)

    # Cut the three methods one at a time, re-finding line ranges after each
    # cut so the AST sees the latest file. Substitutions per the migration:
    # the bodies were already partially-rewritten in /41 to reference
    # `self.remote_instance_weight_transport.X` from outside; once the methods
    # live INSIDE the transport class, those become `self.X`. The NIXL builder
    # additionally references the model via `self.model.named_parameters()`,
    # which becomes `self.model_ref.named_parameters()` on the transport.
    cuts = []
    for method_name in (
        "_publish_modelexpress_metadata",
        "_build_transfer_engine_worker_metadata",
        "_build_nixl_worker_metadata",
    ):
        start, end = find_method_lines(mr.read_text(), class_name="ModelRunner", method_name=method_name)
        method_text = cut_lines(mr, start, end)
        method_text = method_text.replace(
            "self.remote_instance_weight_transport.", "self."
        )
        method_text = method_text.replace(
            "self.model.named_parameters()", "self.model_ref.named_parameters()"
        )
        cuts.append(method_text)

    for method_text in cuts:
        append_to_file(transport, method_text.rstrip() + "\n", separator="\n")

    text = mr.read_text()
    text = replace_call_site(
        text,
        old="self._publish_modelexpress_metadata()",
        new="self.remote_instance_weight_transport._publish_modelexpress_metadata()",
    )
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
