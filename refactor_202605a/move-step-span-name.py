#!/usr/bin/env python3
"""Move ``_build_step_span_name`` free function from ``model_runner.py`` to
``utils/profile_utils.py``.

Per `module_level.md`, profile-trace span naming is not a ModelRunner
responsibility. ``utils/profile_utils.py`` is the appropriate home (it
already groups profiler-related helpers and imports ``ForwardMode`` from
``forward_batch_info`` -- the exact dep this function needs).

Privacy flip exception (allowed by Ch1 when a private helper becomes the new
module's public API): ``_build_step_span_name`` -> ``build_step_span_name``.
The leading underscore made sense as a model_runner-internal helper; in the
new module it is the public API.

- Cut the function via ``find_function_lines`` + ``cut_lines``.
- Append to ``utils/profile_utils.py``; rename in the function definition
  and at the call site in ``model_runner.py``.
- ``model_runner.py``: add a top-level import for the renamed function and
  rewrite the sole call site (inside ``forward_with_profile``) to use it.

Usage:
    uv run --python 3.12 move-step-span-name.py run
    uv run --python 3.12 move-step-span-name.py verify
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
    find_function_lines,
    insert_after,
    replace_call_site,
)
from _runner import run_pr

ID = "move-step-span-name"
SUBJECT = "Move _build_step_span_name from model_runner.py to utils/profile_utils.py"
BODY = ""
AREA = "mech_model_runner"
BASE = "tom_refactor_202605a/raw/mech_model_runner/move-resolve-language-model"
TARGET = f"tom_refactor_202605a/raw/{AREA}/{ID}"


def transform(wt: Path) -> None:
    mr = wt / "python/sglang/srt/model_executor/model_runner.py"
    profile_utils = wt / "python/sglang/srt/utils/profile_utils.py"

    s, e = find_function_lines(mr.read_text(), function_name="_build_step_span_name")
    func_text = cut_lines(mr, s, e)

    # Privacy flip on the def line. The underscore prefix served as a "this
    # is internal to model_runner.py" marker; on the new public-utils module
    # it is the module's exported API.
    func_text = func_text.replace(
        "def _build_step_span_name(",
        "def build_step_span_name(",
    )

    # The signature uses `forward_batch: ForwardBatch` annotation; ensure the
    # import lands at the top of profile_utils.py (TYPE_CHECKING is fine but
    # global import is simpler since profile_utils already has runtime imports
    # from forward_batch_info).
    pu_text = profile_utils.read_text()
    if "from sglang.srt.model_executor.forward_batch_info import ForwardBatch" not in pu_text:
        # Anchor on an existing import in profile_utils that we know exists.
        if "from sglang.srt.model_executor.forward_batch_info import ForwardMode\n" in pu_text:
            pu_text = pu_text.replace(
                "from sglang.srt.model_executor.forward_batch_info import ForwardMode\n",
                "from sglang.srt.model_executor.forward_batch_info import ForwardBatch, ForwardMode\n",
            )
        else:
            # Fallback: insert at top after any logging import.
            pu_text = insert_after(
                pu_text,
                anchor="import logging\n",
                addition="from sglang.srt.model_executor.forward_batch_info import ForwardBatch\n",
            )
        profile_utils.write_text(pu_text)

    append_to_file(profile_utils, func_text.rstrip() + "\n")

    # Update model_runner.py: add import, rewrite call site.
    text = mr.read_text()
    text = insert_after(
        text,
        anchor="from sglang.srt.constants import GPU_MEMORY_TYPE_WEIGHTS\n",
        addition=(
            "from sglang.srt.utils.profile_utils import build_step_span_name\n"
        ),
    )
    text = replace_call_site(
        text,
        old="_build_step_span_name(forward_batch)",
        new="build_step_span_name(forward_batch)",
    )
    mr.write_text(text)

if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        target=TARGET,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
