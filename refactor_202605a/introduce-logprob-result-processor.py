#!/usr/bin/env python3
"""1:N split #1 of ``SchedulerOutputProcessorMixin``: 9 logprob methods move
to ``SchedulerLogprobResultProcessor`` at
``scheduler_components/logprob_result_processor.py``.

Ctor narrow kwargs: ``server_args``, ``model_config`` (2 only — logprob is
near-stateless).

1 privacy flip: ``_calculate_num_input_logprobs`` →
``calculate_num_input_logprobs`` (sister API for the upcoming
BatchResultProcessor). Internal cross-method callsites updated in the same
move.

The remaining 19 methods stay on ``SchedulerOutputProcessorMixin`` until
``introduce-output-streamer`` and ``introduce-batch-result-processor``
finish the split.
"""

# /// script
# requires-python = ">=3.10"
# dependencies = ["typer"]
# ///

import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from _helpers import find_method_lines, insert_after, replace_call_site
from _runner import run_pr

ID = "introduce-logprob-result-processor"
SUBJECT = "Introduce SchedulerLogprobResultProcessor (split #1 of output_processor mixin)"
BODY = """\
Pull 9 logprob methods out of ``SchedulerOutputProcessorMixin`` into a new
``SchedulerLogprobResultProcessor`` class at
``scheduler_components/logprob_result_processor.py``. Scheduler holds it as
``self.logprob_result_processor``.

Ctor narrow kwargs (per CLAUDE.md ch4): ``server_args`` + ``model_config``
(2 only — these methods are near-stateless apart from server_args /
model_config reads).

1 privacy flip: ``_calculate_num_input_logprobs`` →
``calculate_num_input_logprobs`` (drop ``_`` — public sister API for the
upcoming BatchResultProcessor split).

Body byte-identical apart from:
- ``: Scheduler`` annotations dropped
- 1 privacy flip cross-method callsite (``self._calculate_num_input_logprobs``
  → ``self.calculate_num_input_logprobs``)

The output_processor mixin remains in place; OutputStreamer +
BatchResultProcessor finish the 1:N split next.
"""
AREA = "mech_scheduler"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


NEW_CLASS_HEADER = '''\
class SchedulerLogprobResultProcessor:
    """Pure-compute logprob accumulator helpers. Composition target on
    Scheduler (``self.logprob_result_processor``)."""

    def __init__(self, *, server_args, model_config) -> None:
        self.server_args = server_args
        self.model_config = model_config

'''


TARGET_FILE_HEADER = '''\
from __future__ import annotations

from typing import List, Optional, Tuple

import torch

from sglang.srt.layers.logits_processor import LogitsProcessorOutput
from sglang.srt.managers.schedule_batch import Req
from sglang.srt.server_args import MIS_DELIMITER_TOKEN_ID


'''


SCHEDULER_INIT_INSERT = """\
        self.logprob_result_processor = SchedulerLogprobResultProcessor(
            server_args=self.server_args,
            model_config=self.model_config,
        )

"""


def transform(wt: Path) -> None:
    src = wt / "python/sglang/srt/managers/scheduler_output_processor_mixin.py"
    sched = wt / "python/sglang/srt/managers/scheduler.py"
    target = wt / "python/sglang/srt/managers/scheduler_components/logprob_result_processor.py"

    pkg_init = wt / "python/sglang/srt/managers/scheduler_components/__init__.py"
    pkg_init.parent.mkdir(parents=True, exist_ok=True)
    pkg_init.write_text("")

    src_text = src.read_text()

    # Cut 9 logprob methods bottom-up.
    method_blocks = []
    for name in [
        "_initialize_empty_logprob_containers",
        "add_logprob_return_values",
        "add_input_logprob_return_values",
        "_is_multi_item_scoring",
        "_calculate_num_input_logprobs",
        "_calculate_relevant_tokens_len",
        "_process_input_token_ids_logprobs",
        "_process_input_top_logprobs",
        "_process_input_token_logprobs",
    ]:
        s, e = find_method_lines(
            src_text, class_name="SchedulerOutputProcessorMixin", method_name=name
        )
        block = "".join(src_text.splitlines(keepends=True)[s:e])
        method_blocks.append((name, block))
        lines = src_text.splitlines(keepends=True)
        del lines[s:e]
        src_text = "".join(lines)

    src.write_text(src_text)

    # Reverse order to restore source-file order.
    method_blocks.reverse()
    methods_text = "".join(b for _, b in method_blocks)

    # Drop ``: Scheduler`` annotations.
    methods_text = methods_text.replace("self: Scheduler", "self")

    # Privacy flip definition + internal callsites.
    methods_text = methods_text.replace(
        "    def _calculate_num_input_logprobs(",
        "    def calculate_num_input_logprobs(",
    )
    methods_text = methods_text.replace(
        "self._calculate_num_input_logprobs(",
        "self.calculate_num_input_logprobs(",
    )

    target.write_text(TARGET_FILE_HEADER + NEW_CLASS_HEADER + methods_text)

    # Update Scheduler: import + ctor.
    text = sched.read_text()
    text = insert_after(
        text,
        anchor="from sglang.srt.managers.scheduler_components.pool_stats_observer import (\n    SchedulerPoolStatsObserver,\n)\n",
        addition=(
            "from sglang.srt.managers.scheduler_components.logprob_result_processor import (\n"
            "    SchedulerLogprobResultProcessor,\n"
            ")\n"
        ),
    )
    text = replace_call_site(
        text,
        old="        self.is_initializing = False\n",
        new=SCHEDULER_INIT_INSERT + "        self.is_initializing = False\n",
    )
    sched.write_text(text)

    # The remaining output_processor mixin (still in place) calls these
    # methods — update its body to use ``self.logprob_result_processor.X`` form.
    # Also update external callers (disaggregation/prefill.py) that invoke
    # the methods directly on Scheduler.
    for f in [
        src,
        wt / "python/sglang/srt/disaggregation/prefill.py",
    ]:
        text = f.read_text()
        text = text.replace(
            "self.add_logprob_return_values(",
            "self.logprob_result_processor.add_logprob_return_values(",
        )
        text = text.replace(
            "self.add_input_logprob_return_values(",
            "self.logprob_result_processor.add_input_logprob_return_values(",
        )
        text = text.replace(
            "self._calculate_num_input_logprobs(",
            "self.logprob_result_processor.calculate_num_input_logprobs(",
        )
        f.write_text(text)


if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        area_branch=AREA_BRANCH,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
