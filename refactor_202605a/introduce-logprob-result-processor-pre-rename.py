#!/usr/bin/env python3
"""Pre-rename for ``introduce-logprob-result-processor``: privacy-flip
``_calculate_num_input_logprobs`` → ``calculate_num_input_logprobs`` on
``SchedulerOutputProcessorMixin`` and update its 2 intra-mixin callsites.

Body unchanged. No structural moves. This commit lets the subsequent
``-prep`` + ``-move`` commits keep method bodies byte-identical (the
renamed identifier is the only thing that differs between the original
single-shot ``introduce-logprob-result-processor.py`` script and the split path).
"""

# /// script
# requires-python = ">=3.10"
# dependencies = ["typer"]
# ///

import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from _helpers import replace_call_site
from _runner import run_pr

ID = "introduce-logprob-result-processor-pre-rename"
SUBJECT = "Drop underscore from _calculate_num_input_logprobs (pre-rename for introduce-logprob-result-processor)"
BODY = """\
Privacy flip ``_calculate_num_input_logprobs`` →
``calculate_num_input_logprobs`` inside
``SchedulerOutputProcessorMixin``. The renamed method becomes the public
sister API consumed by the upcoming ``SchedulerBatchResultProcessor``
split.

- Definition line renamed (drop leading ``_``).
- Intra-mixin callers updated (inside ``add_input_logprob_return_values``).

Method body byte-identical. No callers outside the mixin file
(``grep`` confirmed: only the mixin uses this method).

Absorbed early per ``MECH_COMMIT_SPLIT.md`` so the follow-up
``introduce-logprob-result-processor-prep`` + ``-move`` pair can keep all moved
method bodies byte-identical.
"""
AREA = "mech_scheduler"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


def transform(wt: Path) -> None:
    src = wt / "python/sglang/srt/managers/scheduler_output_processor_mixin.py"

    text = src.read_text()
    text = replace_call_site(
        text,
        old="    def _calculate_num_input_logprobs(",
        new="    def calculate_num_input_logprobs(",
    )
    text = text.replace(
        "self._calculate_num_input_logprobs(",
        "self.calculate_num_input_logprobs(",
    )
    src.write_text(text)


if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        area_branch=AREA_BRANCH,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
