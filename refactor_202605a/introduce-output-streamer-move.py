#!/usr/bin/env python3
"""Mechanical move for ``introduce-output-streamer``: cut 6 @staticmethods
from ``SchedulerOutputProcessorMixin``, paste them into the
``SchedulerOutputStreamer`` class body. Drop ``@staticmethod`` decorators,
simplify ``self: "SchedulerOutputStreamer"`` → bare ``self``, rewrite
callers ``self.<m>(self.output_streamer, ...)`` →
``self.output_streamer.<m>(...)``.
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
    cut_lines,
    ensure_bare_imports,
    ensure_imports,
    find_method_lines,
    rewrite_method_call_site,
)
from _runner import run_pr

ID = "introduce-output-streamer-move"
SUBJECT = "Move output streaming to SchedulerOutputStreamer"
BODY = """\
Mechanical cut + paste for the ``introduce-output-streamer`` mech move.

Cut the stream @staticmethods (after prep) from
``SchedulerOutputProcessorMixin`` and paste them into
``SchedulerOutputStreamer`` body in
``scheduler_components/output_streamer.py``.

Drop ``@staticmethod`` decorators; simplify
``self: "SchedulerOutputStreamer"`` → bare ``self``. Method bodies
byte-identical (all Callable substitutions + privacy flips happened in
prep so this step is pure mechanical cut+paste).

All callers updated:
  ``self.<m>(self.output_streamer, ...)`` →
  ``self.output_streamer.<m>(...)``
(pure prefix transformation).
"""
AREA = "mech_scheduler"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


# Methods listed in source order so the moved block stays in the same
# layout as the original mixin.
METHODS = [
    "_get_storage_backend_type",
    "get_cached_tokens_details",  # was _get_cached_tokens_details
    "stream_output",
    "_trigger_crash_for_tests",
    "_stream_output_generation",  # was stream_output_generation
    "_stream_output_embedding",   # was stream_output_embedding
]


def _strip_staticmethod_typeflip(method_text: str, *, target_class: str) -> str:
    text = method_text.replace("    @staticmethod\n", "", 1)
    text = text.replace(f"self: \"{target_class}\"", "self")
    # Sibling-dispatch strip: inside the moved body, `self.<m>(self.output_streamer, ...)`
    # was the prep-form for cross-class @staticmethod calls. After the body lands
    # on SchedulerOutputStreamer, ``self`` already IS the streamer — drop the
    # extra `self.output_streamer,` positional arg.
    import re
    text = re.sub(
        r"self\.(\w+)\(\s*self\.output_streamer\s*(?:,\s*)?",
        r"self.\1(",
        text,
        flags=re.DOTALL,
    )
    return text


def transform(wt: Path) -> None:
    mixin = wt / "python/sglang/srt/managers/scheduler_output_processor_mixin.py"
    sched = wt / "python/sglang/srt/managers/scheduler.py"
    target = wt / "python/sglang/srt/managers/scheduler_components/output_streamer.py"

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
            block, target_class="SchedulerOutputStreamer"
        )
        method_blocks.append((name, block))

    method_blocks.reverse()  # restore source order
    methods_text = "".join(b for _, b in method_blocks)

    rtext = target.read_text()
    rtext = rtext.rstrip() + "\n\n" + methods_text.rstrip() + "\n"
    # Re-inject imports the method bodies need (prep wrote these; ruff F401
    # stripped them while the bodies were absent).
    rtext = ensure_bare_imports(rtext, ["import torch\n"])
    rtext = ensure_imports(
        rtext,
        runtime={
            "typing": ("List", "Optional"),
            "sglang.srt.disaggregation.utils": "DisaggregationMode",
            "sglang.srt.managers.io_struct": (
                "BatchEmbeddingOutput",
                "BatchTokenIDOutput",
                "GetLoadsReqInput",
            ),
            "sglang.srt.managers.schedule_batch": ("BaseFinishReason", "Req"),
        },
    )
    target.write_text(rtext)

    # Caller rewrites — use the robust helper (handles single-line and
    # multi-line black-formatted calls alike).
    callsite_methods = [
        "stream_output",
        "get_cached_tokens_details",
        "_stream_output_generation",
        "_stream_output_embedding",
    ]
    for f in [
        mixin,
        sched,
        wt / "python/sglang/srt/disaggregation/prefill.py",
        wt / "python/sglang/srt/dllm/mixin/scheduler.py",
    ]:
        ftext = f.read_text()
        for m in callsite_methods:
            try:
                ftext = rewrite_method_call_site(
                    ftext, method_name=m, target_attr="output_streamer"
                )
            except ValueError:
                pass  # not all methods called in every file
        f.write_text(ftext)

    # Disagg queue classes hold ``self.scheduler`` back-reference, not
    # ``self`` of Scheduler/mixin. Prep emitted transitional sister form
    # ``self.scheduler.stream_output(self.scheduler.output_streamer, ...)``;
    # collapse to ``self.scheduler.output_streamer.stream_output(...)``.
    import re
    for f in [
        wt / "python/sglang/srt/disaggregation/prefill.py",
        wt / "python/sglang/srt/disaggregation/decode.py",
    ]:
        ftext = f.read_text()
        ftext = re.sub(
            r"self\.scheduler\.stream_output\(\s*self\.scheduler\.output_streamer\s*,\s*",
            "self.scheduler.output_streamer.stream_output(",
            ftext,
        )
        ftext = re.sub(
            r"self\.scheduler\.stream_output\(\s*self\.scheduler\.output_streamer\s*\)",
            "self.scheduler.output_streamer.stream_output()",
            ftext,
        )
        f.write_text(ftext)

    # Scheduler receiver shim: prep wired
    # ``stream_output=lambda *a, **kw: self.stream_output(self.output_streamer, *a, **kw)``;
    # collapse to a direct method reference now that ``stream_output`` lives
    # on the streamer.
    text = sched.read_text()
    text = text.replace(
        "            stream_output=lambda *a, **kw: self.stream_output(self.output_streamer, *a, **kw),\n",
        "            stream_output=self.output_streamer.stream_output,\n",
    )
    sched.write_text(text)


if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        area_branch=AREA_BRANCH,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
