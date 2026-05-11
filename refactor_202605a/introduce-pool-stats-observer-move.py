#!/usr/bin/env python3
"""Mechanical move for ``introduce-pool-stats-observer``: cut the 12 prep-form
@staticmethods from ``SchedulerRuntimeCheckerMixin``, paste them into the
``SchedulerPoolStatsObserver`` class body. Drop ``@staticmethod`` decorators;
simplify ``self: "SchedulerPoolStatsObserver"`` annotation to bare ``self``;
strip the ``SchedulerRuntimeCheckerMixin.`` prefix from internal sibling
calls (and the explicit ``self`` positional). Rewrite all callers
``self.<method>(self.pool_stats_observer, ...)`` →
``self.pool_stats_observer.<method>(...)`` — pure prefix transformation.
"""

# /// script
# requires-python = ">=3.10"
# dependencies = ["typer"]
# ///

import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from _helpers import cut_lines, find_method_lines
from _runner import run_pr

ID = "introduce-pool-stats-observer-move"
SUBJECT = "Move 12 stats methods into SchedulerPoolStatsObserver class body"
BODY = """\
Mechanical cut + paste for the ``introduce-pool-stats-observer`` mech move.

Cut the 12 stats methods (all @staticmethod after prep) from
``SchedulerRuntimeCheckerMixin`` and paste them into the
``SchedulerPoolStatsObserver`` class body in
``scheduler_components/pool_stats_observer.py``. Drop ``@staticmethod``
decorators; simplify ``self: "SchedulerPoolStatsObserver"`` annotation to
bare ``self`` (in class context the type is implicit). Strip the
``SchedulerRuntimeCheckerMixin.<method>(self, ...)`` qualified form on
internal sibling calls to plain ``self.<method>(...)`` (the methods are now
in the same class). Method bodies otherwise byte-identical.

All callers updated:
  ``self.<method>(self.pool_stats_observer, ...)`` →
  ``self.pool_stats_observer.<method>(...)``
(pure prefix transformation):
- ``scheduler.py``: 5 callsites.
- ``scheduler_runtime_checker_mixin.py``: 7 callsites (incl.
  ``create_scheduler_watchdog`` ``scheduler.`` prefix).
- ``observability/scheduler_metrics_mixin.py``: 5 callsites.

The runtime_checker mixin file still hosts the 10 check methods +
``create_scheduler_watchdog``; those move in the next commit
(``introduce-invariant-checker``).
"""
AREA = "mech_scheduler"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


METHOD_ORDER = [
    "streaming_session_count",
    "active_pool_idxs",
    "session_held_tokens",
    "session_held_full_tokens",
    "session_held_swa_tokens",
    "session_held_req_count",
    "session_held_mamba_slots",
    "get_pool_stats",
    "_get_token_info",
    "_get_hisparse_token_info",
    "_get_mamba_token_info",
    "_get_swa_token_info",
]


# Sibling-call qualified → unqualified rewrites. After the methods land on
# ``SchedulerPoolStatsObserver``, ``self.<method>(...)`` resolves correctly.
SIBLING_CALL_REWRITES = [
    # active_pool_idxs siblings.
    (
        "SchedulerRuntimeCheckerMixin.active_pool_idxs(self, last_batch=last_batch, running_batch=running_batch)",
        "self.active_pool_idxs(last_batch=last_batch, running_batch=running_batch)",
    ),
    # get_pool_stats siblings (4 _get_*_token_info; _get_hisparse_token_info
    # also takes pool_stats positional).
    (
        "SchedulerRuntimeCheckerMixin._get_swa_token_info(self)",
        "self._get_swa_token_info()",
    ),
    (
        "SchedulerRuntimeCheckerMixin._get_mamba_token_info(self)",
        "self._get_mamba_token_info()",
    ),
    (
        "SchedulerRuntimeCheckerMixin._get_token_info(self)",
        "self._get_token_info()",
    ),
    (
        "SchedulerRuntimeCheckerMixin._get_hisparse_token_info(self, pool_stats)",
        "self._get_hisparse_token_info(pool_stats)",
    ),
]


def _strip_staticmethod_typeflip(method_text: str, *, target_class: str) -> str:
    """Drop @staticmethod, the ``self: TargetClass`` annotation, and the
    ``SchedulerRuntimeCheckerMixin.<sibling>(self, ...)`` qualified form on
    internal sibling calls.

    Sibling-call stripping is regex-based (tolerates single-line and
    multi-line black formatting alike).
    """
    text = method_text.replace("    @staticmethod\n", "", 1)
    text = text.replace(f'self: "{target_class}"', "self")
    # Regex: SchedulerRuntimeCheckerMixin.<method>(<ws>self<ws>(optional comma+ws))
    # → self.<method>(
    text = re.sub(
        r"SchedulerRuntimeCheckerMixin\.(\w+)\(\s*self\s*(?:,\s*)?",
        r"self.\1(",
        text,
        flags=re.DOTALL,
    )
    return text


def transform(wt: Path) -> None:
    src = wt / "python/sglang/srt/managers/scheduler_runtime_checker_mixin.py"
    sched = wt / "python/sglang/srt/managers/scheduler.py"
    metrics_mixin = wt / "python/sglang/srt/observability/scheduler_metrics_mixin.py"
    target = wt / "python/sglang/srt/managers/scheduler_components/pool_stats_observer.py"

    # Cut 12 methods bottom-up.
    method_blocks = []
    for name in reversed(METHOD_ORDER):
        s, e = find_method_lines(
            src.read_text(),
            class_name="SchedulerRuntimeCheckerMixin",
            method_name=name,
        )
        block = cut_lines(src, s, e)
        block = _strip_staticmethod_typeflip(
            block, target_class="SchedulerPoolStatsObserver"
        )
        method_blocks.append(block)
    # Restore source order.
    method_blocks.reverse()

    # Append into the SchedulerPoolStatsObserver class body. The skeleton
    # ends with ``self.max_total_num_tokens = max_total_num_tokens\n``;
    # append after that (methods already have 4-space class-body indent).
    rtext = target.read_text()
    rtext = rtext.rstrip() + "\n\n" + "".join(method_blocks).rstrip() + "\n"
    target.write_text(rtext)

    # Drop the now-unused PoolStats re-import from the mixin (no method left
    # in this file references it after the move).
    text = src.read_text()
    text = text.replace(
        "from sglang.srt.managers.scheduler_components.pool_stats_observer import PoolStats\n",
        "",
        1,
    )
    src.write_text(text)

    # Caller rewrites: pure ``<receiver>.<method>(<receiver>.pool_stats_observer, ...)``
    # → ``<receiver>.pool_stats_observer.<method>(...)``. Use a regex that
    # tolerates either single-line or multi-line black-formatted forms.
    # ``<receiver>`` is ``self`` or ``scheduler``.
    for f in [sched, src, metrics_mixin]:
        text = f.read_text()
        for receiver in ("self", "scheduler"):
            for method in METHOD_ORDER:
                # No-arg form: ``<recv>.<m>(<recv>.pool_stats_observer)`` → ``<recv>.pool_stats_observer.<m>()``.
                text = re.sub(
                    rf"{re.escape(receiver)}\.{re.escape(method)}\(\s*"
                    rf"{re.escape(receiver)}\.pool_stats_observer\s*\)",
                    f"{receiver}.pool_stats_observer.{method}()",
                    text,
                )
                # N-arg form: ``<recv>.<m>(<recv>.pool_stats_observer, ...)`` →
                # ``<recv>.pool_stats_observer.<m>(...)``.
                text = re.sub(
                    rf"{re.escape(receiver)}\.{re.escape(method)}\(\s*"
                    rf"{re.escape(receiver)}\.pool_stats_observer,\s*",
                    f"{receiver}.pool_stats_observer.{method}(",
                    text,
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
