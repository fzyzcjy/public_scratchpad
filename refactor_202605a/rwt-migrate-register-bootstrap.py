#!/usr/bin/env python3
"""Cut `_register_to_engine_info_bootstrap` from ModelRunner; append it to
`RemoteInstanceWeightTransport`. Update the sole caller to delegate via
``self.remote_instance_weight_transport``.

After /40 the body's references to the 3 lifecycle fields read
``self.remote_instance_weight_transport.X`` (because the field rename
happened at the caller side, not inside the method). When we move the body
into the transport class, those become bare ``self.X`` -- a single substring
substitution.

Usage:
    uv run --python 3.12 rwt-migrate-register-bootstrap.py run
    uv run --python 3.12 rwt-migrate-register-bootstrap.py verify
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

ID = "rwt-migrate-register-bootstrap"
SUBJECT = "Migrate _register_to_engine_info_bootstrap to RemoteInstanceWeightTransport"
BODY = ""
AREA = "mech_model_runner"
BASE = "tom_refactor_202605a/primary/mech_model_runner/introduce-rwt-skeleton"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


def transform(wt: Path) -> None:
    mr = wt / "python/sglang/srt/model_executor/model_runner.py"
    transport = wt / "python/sglang/srt/model_executor/remote_instance_weight_transport.py"

    start, end = find_method_lines(
        mr.read_text(),
        class_name="ModelRunner",
        method_name="_register_to_engine_info_bootstrap",
    )
    method_text = cut_lines(mr, start, end)
    method_text = method_text.replace(
        "self.remote_instance_weight_transport.", "self."
    )
    append_to_file(transport, method_text.rstrip() + "\n")

    text = mr.read_text()
    text = replace_call_site(
        text,
        old="self._register_to_engine_info_bootstrap()",
        new="self.remote_instance_weight_transport._register_to_engine_info_bootstrap()",
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
