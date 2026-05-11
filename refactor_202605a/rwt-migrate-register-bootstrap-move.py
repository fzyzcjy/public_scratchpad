#!/usr/bin/env python3
"""Move stage for rwt-migrate-register-bootstrap (MECH_COMMIT_SPLIT §"拆 class 场景"):

Pure cut+paste onto ``RemoteInstanceWeightTransport``. Body byte-equivalent.
Internal caller collapses qualified form back to instance call.
"""

# /// script
# requires-python = ">=3.10"
# dependencies = ["typer"]
# ///

import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from _helpers import append_to_file, cut_lines, find_method_lines, replace_call_site
from _runner import run_pr

ID = "rwt-migrate-register-bootstrap-move"
SUBJECT = "Move _register_to_engine_info_bootstrap onto RemoteInstanceWeightTransport (cut+paste)"
BODY = ""
AREA = "mech_model_runner"
BASE = "tom_refactor_202605a/primary/mech_model_runner/rwt-migrate-register-bootstrap-prep"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


def transform(wt: Path) -> None:
    mr = wt / "python/sglang/srt/model_executor/model_runner.py"
    transport = wt / "python/sglang/srt/model_executor/remote_instance_weight_transport.py"

    s, e = find_method_lines(mr.read_text(), class_name="ModelRunner", method_name="_register_to_engine_info_bootstrap")
    method_text = cut_lines(mr, s, e)
    lines = method_text.splitlines(keepends=True)
    assert lines[0].strip() == "@staticmethod"
    body = "".join(lines[1:])
    body = body.replace('        self: "RemoteInstanceWeightTransport",\n', "        self,\n")
    body = body.replace('(self: "RemoteInstanceWeightTransport"', "(self")
    append_to_file(transport, body.rstrip() + "\n")

    text = mr.read_text()
    # Pre-commit may wrap the qualified call across lines. Use a regex that
    # tolerates both inline and wrapped forms.
    import re
    text = re.sub(
        r"ModelRunner\._register_to_engine_info_bootstrap\(\s*self\.remote_instance_weight_transport\s*\)",
        "self.remote_instance_weight_transport._register_to_engine_info_bootstrap()",
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
