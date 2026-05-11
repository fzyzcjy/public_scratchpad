#!/usr/bin/env python3
"""Prep stage for rwt-migrate-register-bootstrap (MECH_COMMIT_SPLIT §"拆 class 场景"):

Reshape ``_register_to_engine_info_bootstrap`` toward becoming a
``RemoteInstanceWeightTransport`` method. ``@staticmethod`` + ``self:
RemoteInstanceWeightTransport``; body sub ``self.remote_instance_weight_transport.X``
→ ``self.X`` (the path collapses because ``self`` IS the transport now).
Internal caller becomes class-qualified.
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

ID = "rwt-migrate-register-bootstrap-prep"
SUBJECT = "Prep _register_to_engine_info_bootstrap for move onto RemoteInstanceWeightTransport"
BODY = ""
AREA = "mech_model_runner"
BASE = "tom_refactor_202605a/primary/mech_model_runner/introduce-rwt-skeleton"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


def transform(wt: Path) -> None:
    mr = wt / "python/sglang/srt/model_executor/model_runner.py"
    text = mr.read_text()

    start, end = find_method_lines(
        text, class_name="ModelRunner", method_name="_register_to_engine_info_bootstrap"
    )
    lines = text.splitlines(keepends=True)
    method = "".join(lines[start:end])
    # Signature swap (multi-line or single-line).
    if "    def _register_to_engine_info_bootstrap(\n        self,\n" in method:
        method = method.replace(
            "    def _register_to_engine_info_bootstrap(\n        self,\n",
            "    @staticmethod\n    def _register_to_engine_info_bootstrap(\n        self: \"RemoteInstanceWeightTransport\",\n",
            1,
        )
    else:
        method = method.replace(
            "    def _register_to_engine_info_bootstrap(self",
            "    @staticmethod\n    def _register_to_engine_info_bootstrap(self: \"RemoteInstanceWeightTransport\"",
            1,
        )
    # Body collapse: self.remote_instance_weight_transport.X → self.X.
    method = method.replace("self.remote_instance_weight_transport.", "self.")
    text = "".join(lines[:start]) + method + "".join(lines[end:])

    # Internal caller — same file, so ``ModelRunner`` is in scope.
    text = replace_call_site(
        text,
        old="self._register_to_engine_info_bootstrap()",
        new="ModelRunner._register_to_engine_info_bootstrap(self.remote_instance_weight_transport)",
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
