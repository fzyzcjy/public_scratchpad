#!/usr/bin/env python3
"""Mechanical move for ``introduce-metrics-reporter``: cut the 15
prep-form ``@staticmethod`` methods + ``PrefillStats`` + module
constants from ``SchedulerMetricsMixin`` (at
``observability/scheduler_metrics_mixin.py``) and paste them into the
``SchedulerMetricsReporter`` class body / module scope (at
``managers/scheduler_components/metrics_reporter.py``). Drop
``@staticmethod`` decorators; simplify
``self: "SchedulerMetricsReporter"`` annotation to bare ``self``; strip
the ``SchedulerMetricsMixin.<sibling>(self, ...)`` qualified prefix on
internal sibling calls. Drop ``SchedulerMetricsMixin`` from
``Scheduler`` inheritance and delete the mixin file. Rewrite three
external import paths to the new module
(``scheduler.py``, ``schedule_batch.py``, ``dllm/mixin/scheduler.py``).
Collapse caller form
``self.<method>(self.metrics_reporter, ...)`` →
``self.metrics_reporter.<method>(...)`` — pure prefix transformation.
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
from _helpers import (
    cut_lines,
    find_class_lines,
    find_method_lines,
    rewrite_method_call_site,
)
from _runner import run_pr

ID = "introduce-metrics-reporter-move"
SUBJECT = "Hand metrics reporting over to SchedulerMetricsReporter (retire metrics mixin)"
BODY = """\
Mechanical cut + paste for the ``introduce-metrics-reporter`` mech move.

Cut the 15 methods (all @staticmethod after prep) +
``PrefillStats`` dataclass + module constants
(``RECORD_STEP_TIME`` / ``LOG_FORWARD_ITERS`` /
``ENABLE_METRICS_DEVICE_TIMER``) from
``SchedulerMetricsMixin`` and paste them into the
``SchedulerMetricsReporter`` class body / module scope at
``scheduler_components/metrics_reporter.py``. Drop ``@staticmethod``
decorators; simplify ``self: "SchedulerMetricsReporter"`` annotation
to bare ``self`` (in class context the type is implicit). Strip the
``SchedulerMetricsMixin.<sibling>(self, ...)`` qualified form on
internal sibling calls (and the matching ctor-body
``SchedulerMetricsMixin.init_metrics(self, ...)`` /
``SchedulerMetricsMixin.install_device_timer_on_runners(self)``) — the
methods are now in the same class, plain ``self.<method>(...)`` resolves.
Method bodies otherwise byte-identical to the post-prep state.

Source mixin module retired: the file
``observability/scheduler_metrics_mixin.py`` is removed.
``SchedulerMetricsMixin`` is dropped from ``Scheduler`` parents.

All callers updated:
  ``self.<method>(self.metrics_reporter, ...)`` →
  ``self.metrics_reporter.<method>(...)``
(pure prefix transformation, via the canonical
``rewrite_method_call_site`` helper):
- ``scheduler.py``: hot-path sister calls + the
  ``self.metrics_reporter.log_batch_result_stats(...)`` etc. variants.
- ``scheduler_output_processor_mixin.py``:
  ``report_prefill_stats`` / ``update_spec_metrics`` /
  ``report_decode_stats``.
- ``disaggregation/prefill.py``: ``report_prefill_stats``.
- ``dllm/mixin/scheduler.py``: ``report_prefill_stats`` + PrefillStats
  import path rewrite.

3 import-path rewrites (pure prefix replace):
- ``scheduler.py``: ``RECORD_STEP_TIME`` / ``PrefillStats`` import block
  moves from observability/scheduler_metrics_mixin → scheduler_components/metrics_reporter.
- ``schedule_batch.py``: TYPE_CHECKING ``PrefillStats`` import.
- ``dllm/mixin/scheduler.py``: ``PrefillStats`` local import.
"""
AREA = "mech_scheduler"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


METHOD_ORDER = [
    "init_metrics",
    "install_device_timer_on_runners",
    "update_spec_metrics",
    "_init_estimated_perf_constants",
    "_estimate_prefill_perf",
    "_estimate_decode_perf",
    "reset_metrics",
    "report_prefill_stats",
    "report_decode_stats",
    "log_batch_result_stats",
    "_log_hicache_stats",
    "_update_lora_metrics",
    "_calculate_utilization",
    "update_device_timer",
    "reset_device_timer_window",
]


# Constants that must be copied across (module-level, before PrefillStats).
MODULE_CONSTANTS = [
    "RECORD_STEP_TIME",
    "LOG_FORWARD_ITERS",
    "ENABLE_METRICS_DEVICE_TIMER",
]


def _strip_staticmethod_typeflip(method_text: str) -> str:
    """Drop ``@staticmethod``, the ``self: "SchedulerMetricsReporter"``
    annotation, and the qualified-call prefix on sibling /
    init_metrics / install_device_timer_on_runners callers.

    Sibling-call stripping is regex-based (tolerates single-line and
    multi-line black formatting alike)."""
    text = method_text.replace("    @staticmethod\n", "", 1)
    text = text.replace('self: "SchedulerMetricsReporter"', "self")
    # Regex: SchedulerMetricsMixin.<method>(<ws>self<ws>(optional comma+ws))
    # → self.<method>(
    text = re.sub(
        r"SchedulerMetricsMixin\.(\w+)\(\s*self\s*\)",
        r"self.\1()",
        text,
        flags=re.DOTALL,
    )
    text = re.sub(
        r"SchedulerMetricsMixin\.(\w+)\(\s*self\s*,\s*",
        r"self.\1(",
        text,
        flags=re.DOTALL,
    )
    return text


def _cut_method_to_target(src: Path, target: Path, *, method_name: str) -> None:
    s, e = find_method_lines(
        src.read_text(),
        class_name="SchedulerMetricsMixin",
        method_name=method_name,
    )
    block = cut_lines(src, s, e)
    block = _strip_staticmethod_typeflip(block)

    rtext = target.read_text()
    rtext = rtext.rstrip() + "\n\n" + block.rstrip() + "\n"
    target.write_text(rtext)


def transform(wt: Path) -> None:
    src = wt / "python/sglang/srt/observability/scheduler_metrics_mixin.py"
    sched = wt / "python/sglang/srt/managers/scheduler.py"
    output_mixin = wt / "python/sglang/srt/managers/scheduler_output_processor_mixin.py"
    prefill = wt / "python/sglang/srt/disaggregation/prefill.py"
    dllm = wt / "python/sglang/srt/dllm/mixin/scheduler.py"
    schedule_batch = wt / "python/sglang/srt/managers/schedule_batch.py"
    target = wt / "python/sglang/srt/managers/scheduler_components/metrics_reporter.py"

    # NOTE: Cut module-level items (PrefillStats class + constants) FIRST while
    # the mixin class body still has methods (ast.parse would reject empty class).
    # Then cut methods last.

    # 1a. Cut PrefillStats dataclass from mixin → paste into target at module scope.
    mixin_text = src.read_text()
    s, e = find_class_lines(mixin_text, class_name="PrefillStats")
    prefill_stats_block = cut_lines(src, s, e)

    target_text = target.read_text()
    cs, ce = find_class_lines(target_text, class_name="SchedulerMetricsReporter")
    target_lines = target_text.splitlines(keepends=True)
    target.write_text(
        "".join(target_lines[:cs])
        + prefill_stats_block.rstrip()
        + "\n\n\n"
        + "".join(target_lines[cs:])
    )

    # 1b. Cut module-level constants from mixin (line scan; no ast).
    mixin_text = src.read_text()
    mixin_lines = mixin_text.splitlines(keepends=True)
    const_lines = []
    keep_lines = []
    for line in mixin_lines:
        m = re.match(r"^([A-Z_][A-Z0-9_]*)\s*=", line)
        if m and m.group(1) in MODULE_CONSTANTS:
            const_lines.append(line)
        else:
            keep_lines.append(line)
    src.write_text("".join(keep_lines))

    target_text = target.read_text()
    ps_start, _ = find_class_lines(target_text, class_name="PrefillStats")
    tlines = target_text.splitlines(keepends=True)
    target.write_text(
        "".join(tlines[:ps_start])
        + "".join(const_lines)
        + "\n"
        + "".join(tlines[ps_start:])
    )

    # 2. Cut 15 methods bottom-up from mixin (class will end up empty but file
    #    is unlinked at end).
    method_blocks = []
    for name in reversed(METHOD_ORDER):
        s, e = find_method_lines(
            src.read_text(),
            class_name="SchedulerMetricsMixin",
            method_name=name,
        )
        block = cut_lines(src, s, e)
        block = _strip_staticmethod_typeflip(block)
        method_blocks.append(block)
    method_blocks.reverse()

    # 3. Strip the SchedulerMetricsMixin.foo(self, ...) qualifier from the
    #    target's ctor body too. Append methods.
    rtext = target.read_text()
    rtext = _strip_staticmethod_typeflip(rtext)
    rtext = rtext.rstrip() + "\n\n" + "".join(method_blocks).rstrip() + "\n"
    target.write_text(rtext)

    target_text = target.read_text()
    # Insert constants before PrefillStats. PrefillStats is the first class def
    # in the file; insert constants right before its decorator/header.
    ps_start, _ = find_class_lines(target_text, class_name="PrefillStats")
    tlines = target_text.splitlines(keepends=True)
    new_target_text = (
        "".join(tlines[:ps_start])
        + "".join(const_lines)
        + "\n"
        + "".join(tlines[ps_start:])
    )
    target.write_text(new_target_text)

    # 5. The target file now has all needed content. Replace its skeleton-only
    #    import header with the full set of imports needed by the relocated
    #    methods (taken verbatim from the original mixin header). The
    #    ``from sglang.srt.observability.scheduler_metrics_mixin import (
    #    SchedulerMetricsMixin,)`` import in target is now stale (no qualified
    #    references remain) — drop it. Append the additional imports the moved
    #    method bodies need.
    target_text = target.read_text()
    target_text = target_text.replace(
        "from sglang.srt.observability.scheduler_metrics_mixin import (  # noqa: F401\n"
        "    SchedulerMetricsMixin,\n"
        ")\n",
        "",
    )
    # Add the imports the moved bodies need (deduped against the skeleton's
    # existing import set). Inserted after the existing
    # ``from sglang.srt.disaggregation.utils import DisaggregationMode`` line.
    target_text = target_text.replace(
        "from sglang.srt.disaggregation.utils import DisaggregationMode  # noqa: F401\n",
        "import dataclasses\n"
        "import time\n"
        "from collections import defaultdict\n"
        "from typing import List, Tuple, Union  # noqa: F401\n"
        "\n"
        "from sglang.srt.disaggregation.utils import DisaggregationMode\n"
        "from sglang.srt.environ import envs\n"
        "from sglang.srt.managers.schedule_batch import ScheduleBatch\n"
        "from sglang.srt.managers.utils import GenerationBatchResult\n"
        "from sglang.srt.observability.metrics_collector import (\n"
        "    DPCooperationInfo,\n"
        "    QueueCount,\n"
        "    SchedulerMetricsCollector,\n"
        "    SchedulerStats,\n"
        "    compute_routing_key_stats,\n"
        ")\n"
        "from sglang.srt.utils.device_timer import DeviceTimer\n"
        "from sglang.srt.utils.scheduler_status_logger import SchedulerStatusLogger\n",
    )
    # Add TYPE_CHECKING entries the moved bodies reference (Req, PrefillAdder,
    # EmbeddingBatchResult) alongside the existing Scheduler import.
    target_text = target_text.replace(
        "if TYPE_CHECKING:\n"
        "    from sglang.srt.managers.scheduler import Scheduler  # noqa: F401\n",
        "if TYPE_CHECKING:\n"
        "    from sglang.srt.managers.schedule_batch import Req\n"
        "    from sglang.srt.managers.schedule_policy import PrefillAdder\n"
        "    from sglang.srt.managers.scheduler import EmbeddingBatchResult, Scheduler  # noqa: F401\n",
    )
    target.write_text(target_text)

    # 6. Delete the (now empty modulo header) mixin file.
    src.unlink()

    # 7. Scheduler: import-path rewrite + drop SchedulerMetricsMixin parent +
    #    collapse caller form.
    text = sched.read_text()
    text = text.replace(
        "from sglang.srt.observability.scheduler_metrics_mixin import (\n"
        "    RECORD_STEP_TIME,\n"
        "    PrefillStats,\n"
        "    SchedulerMetricsMixin,\n"
        ")\n",
        "from sglang.srt.managers.scheduler_components.metrics_reporter import (\n"
        "    RECORD_STEP_TIME,\n"
        "    PrefillStats,\n"
        ")\n",
    )
    # Drop SchedulerMetricsMixin from Scheduler bases.
    text = text.replace(
        "    SchedulerMetricsMixin,\n",
        "",
    )
    # Collapse caller form: self.<method>(self.metrics_reporter, ...) →
    # self.metrics_reporter.<method>(...).
    for method in METHOD_ORDER:
        try:
            text = rewrite_method_call_site(
                text, method_name=method, target_attr="metrics_reporter"
            )
        except ValueError:
            pass
    sched.write_text(text)

    # 8. Output processor mixin: caller form collapse.
    text = output_mixin.read_text()
    for method in METHOD_ORDER:
        try:
            text = rewrite_method_call_site(
                text, method_name=method, target_attr="metrics_reporter"
            )
        except ValueError:
            pass
    output_mixin.write_text(text)

    # 9. Disaggregation prefill: caller form collapse.
    text = prefill.read_text()
    for method in METHOD_ORDER:
        try:
            text = rewrite_method_call_site(
                text, method_name=method, target_attr="metrics_reporter"
            )
        except ValueError:
            pass
    prefill.write_text(text)

    # 10. dllm mixin: caller form collapse + PrefillStats import path rewrite.
    text = dllm.read_text()
    for method in METHOD_ORDER:
        try:
            text = rewrite_method_call_site(
                text, method_name=method, target_attr="metrics_reporter"
            )
        except ValueError:
            pass
    text = text.replace(
        "from sglang.srt.observability.scheduler_metrics_mixin import PrefillStats",
        "from sglang.srt.managers.scheduler_components.metrics_reporter import PrefillStats",
    )
    dllm.write_text(text)

    # 11. schedule_batch.py: PrefillStats TYPE_CHECKING import path rewrite.
    text = schedule_batch.read_text()
    text = text.replace(
        "from sglang.srt.observability.scheduler_metrics_mixin import PrefillStats",
        "from sglang.srt.managers.scheduler_components.metrics_reporter import PrefillStats",
    )
    schedule_batch.write_text(text)


if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        area_branch=AREA_BRANCH,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
