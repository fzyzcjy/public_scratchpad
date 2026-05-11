#!/usr/bin/env python3
"""Mechanical move for ``introduce-logprob-computer``: cut 9 @staticmethods
from ``SchedulerOutputProcessorMixin``, paste them into the
``SchedulerLogprobComputer`` class body. Drop ``@staticmethod`` decorators,
simplify ``self: "SchedulerLogprobComputer"`` → bare ``self``, rewrite
callers ``self.<m>(self.logprob_computer, ...)`` →
``self.logprob_computer.<m>(...)``.
"""

# /// script
# requires-python = ">=3.10"
# dependencies = ["typer"]
# ///

import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from _helpers import cut_lines, find_method_lines, rewrite_method_call_site
from _runner import run_pr

ID = "introduce-logprob-computer-move"
SUBJECT = "Hand logprob assembly over to SchedulerLogprobComputer"
BODY = """\
Mechanical cut + paste for the ``introduce-logprob-computer`` mech move.

Cut the 9 logprob @staticmethods (after prep) from
``SchedulerOutputProcessorMixin`` and paste them into
``SchedulerLogprobComputer`` body in
``scheduler_components/logprob_computer.py``.

Drop ``@staticmethod`` decorators; simplify
``self: "SchedulerLogprobComputer"`` → bare ``self`` (in class context
the type is implicit). Method bodies otherwise byte-identical.

All callers updated:
  ``self.<m>(self.logprob_computer, ...)`` →
  ``self.logprob_computer.<m>(...)``
(pure prefix transformation).
"""
AREA = "mech_scheduler"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


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


def _strip_staticmethod_typeflip(method_text: str, *, target_class: str) -> str:
    """Drop @staticmethod and the ``self: "TargetClass"`` annotation."""
    text = method_text.replace("    @staticmethod\n", "", 1)
    text = text.replace(f"self: \"{target_class}\"", "self")
    import re
    text = re.sub(
        r"self\.(\w+)\(\s*self\.logprob_computer\s*(?:,\s*)?",
        r"self.\1(",
        text,
        flags=re.DOTALL,
    )
    return text


def transform(wt: Path) -> None:
    mixin = wt / "python/sglang/srt/managers/scheduler_output_processor_mixin.py"
    sched = wt / "python/sglang/srt/managers/scheduler.py"
    target = wt / "python/sglang/srt/managers/scheduler_components/logprob_computer.py"

    # Locate then cut each method bottom-up (re-parse each time since line
    # numbers shift after each cut).
    method_blocks = []
    # Sort methods by their current line number, descending — so we cut the
    # bottom-most first to keep upstream line numbers valid for the next
    # find. The set of methods is the union; ordering is reflected in the
    # final concat (we restore source order by reversing the cut order).
    src_text = mixin.read_text()
    located = []
    for name in METHODS:
        s, e = find_method_lines(
            src_text,
            class_name="SchedulerOutputProcessorMixin",
            method_name=name,
        )
        located.append((s, e, name))
    located.sort(key=lambda t: t[0], reverse=True)

    for _, _, name in located:
        s, e = find_method_lines(
            mixin.read_text(),
            class_name="SchedulerOutputProcessorMixin",
            method_name=name,
        )
        block = cut_lines(mixin, s, e)
        block = _strip_staticmethod_typeflip(
            block, target_class="SchedulerLogprobComputer"
        )
        method_blocks.append((name, block))

    # Restore source order (we cut bottom-up, so reverse).
    method_blocks.reverse()
    methods_text = "".join(b for _, b in method_blocks)

    # Append into target class body. Existing skeleton ends with
    # ``self.model_config = model_config\n``; append after that with a blank
    # separator.
    rtext = target.read_text()
    rtext = rtext.rstrip() + "\n\n" + methods_text.rstrip() + "\n"
    target.write_text(rtext)

    # Caller rewrites — use the robust helper (handles single-line and
    # multi-line black-formatted calls alike).
    callsite_methods = [
        "add_logprob_return_values",
        "add_input_logprob_return_values",
        "calculate_num_input_logprobs",
    ]
    for f in [
        mixin,
        sched,
        wt / "python/sglang/srt/disaggregation/prefill.py",
    ]:
        ftext = f.read_text()
        for m in callsite_methods:
            try:
                ftext = rewrite_method_call_site(
                    ftext, method_name=m, target_attr="logprob_computer"
                )
            except ValueError:
                pass  # not all methods called in every file
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
