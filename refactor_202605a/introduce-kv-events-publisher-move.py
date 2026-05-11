#!/usr/bin/env python3
"""Mechanical move for ``introduce-kv-events-publisher``: cut 3
@staticmethods from ``SchedulerMetricsMixin``, paste them into the
``SchedulerKvEventsPublisher`` class body. Drop ``@staticmethod``,
simplify ``self: "SchedulerKvEventsPublisher"`` → bare ``self``, rewrite
callers from ``self.foo(self.kv_events_publisher, ...)`` →
``self.kv_events_publisher.foo(...)``.
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

ID = "introduce-kv-events-publisher-move"
SUBJECT = "Move 3 methods into SchedulerKvEventsPublisher class body"
BODY = """\
Mechanical cut + paste for the ``introduce-kv-events-publisher`` mech
move.

Cut ``init_kv_events`` / ``emit_kv_metrics`` / ``publish_kv_events``
(@staticmethods after prep) from ``SchedulerMetricsMixin`` and paste
them into the ``SchedulerKvEventsPublisher`` class body in
``scheduler_components/kv_events_publisher.py``.

Drop ``@staticmethod`` decorators; simplify
``self: "SchedulerKvEventsPublisher"`` type annotation to bare ``self``.
Method bodies otherwise byte-identical.

Callers updated (pure prefix transformation):
- 2 in metrics mixin (``report_prefill_stats`` / ``report_decode_stats``)
- 1 in mixin ``init_metrics`` (``init_kv_events`` call)
- 1 in scheduler.py ``on_idle`` (``publish_kv_events`` call)
"""
AREA = "mech_scheduler"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


def _strip_staticmethod_typeflip(method_text: str, *, target_class: str) -> str:
    text = method_text.replace("    @staticmethod\n", "", 1)
    text = text.replace(f"self: \"{target_class}\"", "self")
    return text


def transform(wt: Path) -> None:
    src = wt / "python/sglang/srt/observability/scheduler_metrics_mixin.py"
    sched = wt / "python/sglang/srt/managers/scheduler.py"
    target = wt / "python/sglang/srt/managers/scheduler_components/kv_events_publisher.py"

    # Cut 3 methods (bottom-up so earlier line offsets stay valid).
    method_blocks = []
    for name in ["publish_kv_events", "emit_kv_metrics", "init_kv_events"]:
        s, e = find_method_lines(
            src.read_text(),
            class_name="SchedulerMetricsMixin",
            method_name=name,
        )
        block = cut_lines(src, s, e)
        block = _strip_staticmethod_typeflip(
            block, target_class="SchedulerKvEventsPublisher"
        )
        method_blocks.append(block)

    # Reverse to restore source order: init_kv_events, emit_kv_metrics, publish_kv_events.
    method_blocks.reverse()

    rtext = target.read_text()
    rtext = rtext.rstrip() + "\n\n" + "".join(method_blocks).rstrip() + "\n"
    target.write_text(rtext)

    # Caller rewrites — use the robust helper (handles single-line and
    # multi-line black-formatted calls alike).
    for f in (src, sched):
        ftext = f.read_text()
        for method in ("emit_kv_metrics", "publish_kv_events", "init_kv_events"):
            try:
                ftext = rewrite_method_call_site(
                    ftext, method_name=method, target_attr="kv_events_publisher"
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
