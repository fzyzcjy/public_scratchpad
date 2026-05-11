#!/usr/bin/env python3
"""Mechanical move for ``introduce-batch-result-processor``: cut the 11
remaining @staticmethods from ``SchedulerOutputProcessorMixin``, paste them
into the ``SchedulerBatchResultProcessor`` class body. Drop ``@staticmethod``
decorators, simplify ``self: "SchedulerBatchResultProcessor"`` → bare
``self``. Delete the now-empty mixin file and drop the inheritance entry +
import from ``Scheduler``. Rewrite callers
``self.<m>(self.batch_result_processor, ...)`` →
``self.batch_result_processor.<m>(...)``.

This is the FINAL extract from ``SchedulerOutputProcessorMixin`` — after
this commit the mixin file no longer exists.
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

ID = "introduce-batch-result-processor-move"
SUBJECT = "Move 11 methods into SchedulerBatchResultProcessor class body; delete output_processor mixin file"
BODY = """\
Mechanical cut + paste for the ``introduce-batch-result-processor`` mech
move (final extract from ``SchedulerOutputProcessorMixin``).

Cut the 11 remaining process/collect @staticmethods (after prep) from
``SchedulerOutputProcessorMixin`` and paste them into
``SchedulerBatchResultProcessor`` body in
``scheduler_components/batch_result_processor.py``.

Drop ``@staticmethod`` decorators; simplify
``self: "SchedulerBatchResultProcessor"`` → bare ``self``. Method bodies
byte-identical (all Callable / privacy / mutator substitutions happened in
prep so this step is pure mechanical cut+paste).

Delete the now-empty ``scheduler_output_processor_mixin.py`` file. Drop
the ``SchedulerOutputProcessorMixin`` import + inheritance entry from
``Scheduler``.

All callers updated:
  ``self.<m>(self.batch_result_processor, ...)`` →
  ``self.batch_result_processor.<m>(...)``
(pure prefix transformation).
"""
AREA = "mech_scheduler"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


# Methods listed in source order (with privacy-flipped names that prep
# wrote).
METHODS = [
    "process_batch_result_prebuilt",
    "_maybe_collect_routed_experts",   # prep flipped privacy
    "_maybe_collect_indexer_topk",     # prep flipped privacy
    "_maybe_collect_customized_info",  # prep flipped privacy
    "process_batch_result_prefill",
    "_resolve_spec_overlap_token_ids",
    "process_batch_result_idle",
    "process_batch_result_decode",
    "_handle_finished_req",
    "_maybe_update_reasoning_tokens",
    "_mamba_prefix_cache_update",
]


def _strip_staticmethod_typeflip(method_text: str, *, target_class: str) -> str:
    text = method_text.replace("    @staticmethod\n", "", 1)
    text = text.replace(f"self: \"{target_class}\"", "self")
    import re
    text = re.sub(
        r"self\.(\w+)\(\s*self\.batch_result_processor\s*(?:,\s*)?",
        r"self.\1(",
        text,
        flags=re.DOTALL,
    )
    return text


def transform(wt: Path) -> None:
    mixin = wt / "python/sglang/srt/managers/scheduler_output_processor_mixin.py"
    sched = wt / "python/sglang/srt/managers/scheduler.py"
    pp = wt / "python/sglang/srt/managers/scheduler_pp_mixin.py"
    pre = wt / "python/sglang/srt/disaggregation/prefill.py"
    dec = wt / "python/sglang/srt/disaggregation/decode.py"
    dllm = wt / "python/sglang/srt/dllm/mixin/scheduler.py"
    target = wt / "python/sglang/srt/managers/scheduler_components/batch_result_processor.py"

    # Cut bottom-up so line numbers stay valid for the remaining locates.
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

    method_blocks = []
    for _, _, name in located:
        s, e = find_method_lines(
            mixin.read_text(),
            class_name="SchedulerOutputProcessorMixin",
            method_name=name,
        )
        block = cut_lines(mixin, s, e)
        block = _strip_staticmethod_typeflip(
            block, target_class="SchedulerBatchResultProcessor"
        )
        method_blocks.append((name, block))

    method_blocks.reverse()  # restore source order
    methods_text = "".join(b for _, b in method_blocks)

    rtext = target.read_text()
    rtext = rtext.rstrip() + "\n\n" + methods_text.rstrip() + "\n"
    target.write_text(rtext)

    # Delete the now-empty mixin file (all 28 methods have moved out across
    # C15+C16+C17).
    mixin.unlink()

    # Drop SchedulerOutputProcessorMixin from Scheduler — import + base.
    text = sched.read_text()
    text = text.replace(
        "from sglang.srt.managers.scheduler_output_processor_mixin import (\n"
        "    SchedulerOutputProcessorMixin,\n"
        ")\n",
        "",
    )
    text = text.replace("    SchedulerOutputProcessorMixin,\n", "")
    sched.write_text(text)

    # Caller rewrites — use the robust helper (handles single-line and
    # multi-line black-formatted calls alike).
    callers = [
        sched,
        pp,
        pre,
        dec,
        dllm,
    ]
    callsite_methods = [
        "process_batch_result_prebuilt",
        "process_batch_result_prefill",
        "process_batch_result_decode",
        "process_batch_result_idle",
    ]
    for f in callers:
        ftext = f.read_text()
        for m in callsite_methods:
            try:
                ftext = rewrite_method_call_site(
                    ftext, method_name=m, target_attr="batch_result_processor"
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
