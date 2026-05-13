#!/usr/bin/env python3
"""Inplace prep for ``introduce-logprob-result-processor``: create empty
``SchedulerLogprobResultProcessor`` class skeleton, instantiate on Scheduler,
convert 9 logprob methods on ``SchedulerOutputProcessorMixin`` to
``@staticmethod`` with ``self: "SchedulerLogprobResultProcessor"`` type annotation,
rewrite callers to ``self.<method>(self.logprob_result_processor, ...)``.

Method bodies byte-identical (modulo the ``: Scheduler`` annotation drop —
applied here as it's the minimal change needed to detach ``self`` from
``Scheduler``).
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

ID = "introduce-logprob-result-processor-prep"
SUBJECT = "Stage logprob assembly for handoff to SchedulerLogprobResultProcessor"
BODY = """\
Inplace prep for the ``introduce-logprob-result-processor`` mech move.

- Create ``scheduler_components/logprob_result_processor.py`` with an empty
  ``SchedulerLogprobResultProcessor`` class (ctor takes ``server_args`` +
  ``model_config`` — 2 narrow kwargs).
- Instantiate ``self.logprob_result_processor = SchedulerLogprobResultProcessor(...)``
  in ``Scheduler.__init__`` just before ``self.is_initializing = False``.
- In ``SchedulerOutputProcessorMixin``, convert 9 logprob methods
  (``_initialize_empty_logprob_containers``, ``add_logprob_return_values``,
  ``add_input_logprob_return_values``, ``_is_multi_item_scoring``,
  ``calculate_num_input_logprobs`` [renamed by ``-pre-rename`` already],
  ``_calculate_relevant_tokens_len``, ``_process_input_token_ids_logprobs``,
  ``_process_input_top_logprobs``, ``_process_input_token_logprobs``) to
  ``@staticmethod`` with ``self: "SchedulerLogprobResultProcessor"`` type annotation.
- Drop the original ``self: Scheduler`` annotation; otherwise method bodies
  byte-identical.
- Callers (3 callsites in ``scheduler_output_processor_mixin.py`` and 2
  in ``disaggregation/prefill.py``) rewritten to
  ``self.<method>(self.logprob_result_processor, ...)``.

The 9 methods stay inside the mixin in this commit; physical cut + paste
to ``SchedulerLogprobResultProcessor`` body happens in
``introduce-logprob-result-processor-move``.
"""
AREA = "mech_scheduler"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


TARGET_FILE_HEADER = '''\
from __future__ import annotations  # noqa: F401

from dataclasses import dataclass
from typing import Any, List, Optional, Tuple  # noqa: F401

import torch  # noqa: F401

from sglang.srt.layers.logits_processor import LogitsProcessorOutput  # noqa: F401
from sglang.srt.managers.schedule_batch import Req  # noqa: F401
from sglang.srt.server_args import MIS_DELIMITER_TOKEN_ID  # noqa: F401


@dataclass(kw_only=True, slots=True, frozen=True)
class SchedulerLogprobResultProcessor:
    """Pure-compute logprob accumulator helpers. Composition target on
    Scheduler (``self.logprob_result_processor``)."""

    server_args: Any
    model_config: Any
'''


SCHEDULER_INIT_INSERT = """\
        self.logprob_result_processor = SchedulerLogprobResultProcessor(
            server_args=self.server_args,
            model_config=self.model_config,
        )

"""


METHODS = [
    "_initialize_empty_logprob_containers",
    "add_logprob_return_values",
    "add_input_logprob_return_values",
    "_is_multi_item_scoring",
    "calculate_num_input_logprobs",
    "_calculate_relevant_tokens_len",
    "_process_input_token_ids_logprobs",
    "_process_input_top_logprobs",
    "_process_input_token_logprobs",
]


def transform(wt: Path) -> None:
    sched = wt / "python/sglang/srt/managers/scheduler.py"
    mixin = wt / "python/sglang/srt/managers/scheduler_output_processor_mixin.py"
    target = wt / "python/sglang/srt/managers/scheduler_components/logprob_result_processor.py"

    # 1. Create skeleton target file (class + ctor, no methods yet).
    target.parent.mkdir(parents=True, exist_ok=True)
    pkg_init = target.parent / "__init__.py"
    if not pkg_init.exists():
        pkg_init.write_text("")
    target.write_text(TARGET_FILE_HEADER)

    # 2. Convert 9 methods on the mixin to @staticmethod with
    #    type-flipped ``self: "SchedulerLogprobResultProcessor"``. Body unchanged
    #    apart from the ``: Scheduler`` → ``: "SchedulerLogprobResultProcessor"``
    #    annotation rewrite (achieved via a global replace at the end since
    #    only the 9 picked methods carry that annotation in their signature).
    text = mixin.read_text()

    for name in METHODS:
        s, e = find_method_lines(
            text,
            class_name="SchedulerOutputProcessorMixin",
            method_name=name,
        )
        lines = text.splitlines(keepends=True)
        method_text = "".join(lines[s:e])

        # Detect single-line vs multi-line signature.
        single_line_sig = f"    def {name}(self: Scheduler, "
        single_line_no_args = f"    def {name}(self: Scheduler)"
        multi_line_sig = f"    def {name}(\n        self: Scheduler,"

        if single_line_sig in method_text:
            new_method = method_text.replace(
                single_line_sig,
                f"    @staticmethod\n    def {name}(self: \"SchedulerLogprobResultProcessor\", ",
                1,
            )
        elif single_line_no_args in method_text:
            new_method = method_text.replace(
                single_line_no_args,
                f"    @staticmethod\n    def {name}(self: \"SchedulerLogprobResultProcessor\")",
                1,
            )
        elif multi_line_sig in method_text:
            new_method = method_text.replace(
                multi_line_sig,
                f"    @staticmethod\n    def {name}(\n        self: \"SchedulerLogprobResultProcessor\",",
                1,
            )
        else:
            raise RuntimeError(
                f"signature shape for {name} unrecognized; sample: {method_text[:200]!r}"
            )

        text = "".join(lines[:s]) + new_method + "".join(lines[e:])

    # Add TYPE_CHECKING import for the new TargetClass so the
    # ``self: "SchedulerLogprobResultProcessor"`` annotation resolves under pyflakes.
    if "from sglang.srt.managers.scheduler_components.logprob_result_processor import SchedulerLogprobResultProcessor" not in text:
        text = text.replace(
            "if TYPE_CHECKING:\n",
            "if TYPE_CHECKING:\n"
            "    from sglang.srt.managers.scheduler_components.logprob_result_processor import SchedulerLogprobResultProcessor\n",
            1,
        )

    mixin.write_text(text)

    # 3. Scheduler: add import + ctor instantiation.
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

    # 4. Callsite rewrites: mixin body (still in place) + external callers
    #    in disaggregation/prefill.py. Form is
    #    ``self.<method>(self.logprob_result_processor, <existing-args>)``.
    for f in [
        mixin,
        wt / "python/sglang/srt/disaggregation/prefill.py",
    ]:
        ftext = f.read_text()
        ftext = ftext.replace(
            "self.add_logprob_return_values(",
            "self.add_logprob_return_values(self.logprob_result_processor, ",
        )
        ftext = ftext.replace(
            "self.add_input_logprob_return_values(",
            "self.add_input_logprob_return_values(self.logprob_result_processor, ",
        )
        ftext = ftext.replace(
            "self.calculate_num_input_logprobs(",
            "self.calculate_num_input_logprobs(self.logprob_result_processor, ",
        )
        f.write_text(ftext)


if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        area_branch=AREA_BRANCH,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
