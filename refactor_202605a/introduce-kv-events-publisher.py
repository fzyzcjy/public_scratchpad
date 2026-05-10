#!/usr/bin/env python3
"""1:N split #1 of ``SchedulerMetricsMixin``: introduce
``SchedulerKvEventsPublisher`` at
``scheduler_components/observability/kv_events_publisher.py``.

3 KV-events methods (``init_kv_events`` / ``_emit_kv_metrics`` /
``_publish_kv_events``) and the ``KvMetrics`` dataclass move to the new
class. The init logic (rank gate + EventPublisherFactory) is consolidated
into the new class's ``__init__``; the original ``init_kv_events`` method
is removed (Scheduler.__init__ instantiates the publisher directly). 2
privacy flips (drop ``_``): ``_emit_kv_metrics`` → ``emit_kv_metrics`` /
``_publish_kv_events`` → ``publish_kv_events``.

``_emit_kv_metrics`` body's reads of ``self.stats`` / ``self.max_running_requests``
/ ``self.max_total_num_tokens`` become per-call kwargs.

Callers updated:
- ``Scheduler.__init__``: instantiate ``self.kv_events_publisher = ...``;
  inside the metrics mixin's ``init_metrics`` body the
  ``self.init_kv_events(...)`` call is removed.
- ``scheduler_metrics_mixin.py``: 4 callsites (2x emit + 2x publish in
  ``report_prefill_stats`` and ``report_decode_stats``) updated to the
  sister form.
- ``scheduler.py`` (``on_idle`` moved here in C8): 1 ``self._publish_kv_events()``
  callsite updated.

The metrics mixin remains in place; ``introduce-load-inquirer`` and
``introduce-metrics-reporter`` finish the 1:N split next.
"""

# /// script
# requires-python = ">=3.10"
# dependencies = ["typer"]
# ///

import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from _helpers import find_class_lines, find_method_lines, insert_after, replace_call_site
from _runner import run_pr

ID = "introduce-kv-events-publisher"
SUBJECT = "Introduce SchedulerKvEventsPublisher (split #1 of metrics mixin)"
BODY = """\
Pull the 3 KV-events methods + ``KvMetrics`` dataclass out of
``SchedulerMetricsMixin`` into a new ``SchedulerKvEventsPublisher`` at
``scheduler_components/observability/kv_events_publisher.py``. Scheduler
holds it as ``self.kv_events_publisher``.

The original ``init_kv_events`` method is fully removed: its rank-gate +
``EventPublisherFactory`` creation logic is consolidated into the new
class's ``__init__``. Inside ``SchedulerMetricsMixin.init_metrics`` the
``self.init_kv_events(...)`` call is removed.

2 privacy flips: ``_emit_kv_metrics`` / ``_publish_kv_events`` drop the
leading ``_`` (now public — sister API for the upcoming MetricsReporter).
``emit_kv_metrics`` body's reads of ``self.stats`` /
``self.max_running_requests`` / ``self.max_total_num_tokens`` become per-call
kwargs.

5 callsites updated:
- ``Scheduler.__init__``: instantiation.
- ``scheduler_metrics_mixin.py`` ``init_metrics``: drop ``self.init_kv_events`` call.
- ``scheduler_metrics_mixin.py`` ``report_*_stats``: 4 emit/publish callsites.
- ``scheduler.py`` ``on_idle`` (moved here in C8): 1 ``_publish_kv_events``.

The metrics mixin remains; LoadInquirer / MetricsReporter finish the split next.
"""
AREA = "mech_scheduler"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


TARGET_FILE_HEADER = '''\
from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import Optional

from sglang.srt.observability.event_publisher_factory import EventPublisherFactory
from sglang.srt.observability.kv_event_publisher import KVEventBatch


# ``SchedulerStats`` referenced only as a type hint in ``emit_kv_metrics`` —
# leave a forward-ref placeholder.
class SchedulerStats: ...  # type: ignore[no-redef]


'''


NEW_CLASS_BODY = '''\
class SchedulerKvEventsPublisher:
    """KV cache event / metrics publication channel. Composition target on
    Scheduler (``self.kv_events_publisher``)."""

    def __init__(
        self,
        *,
        kv_events_config: Optional[str],
        attn_tp_rank: int,
        attn_cp_rank: int,
        attn_dp_rank: int,
        dp_rank: Optional[int],
        tree_cache,
        send_metrics_from_scheduler,
    ) -> None:
        self.tree_cache = tree_cache
        self.send_metrics_from_scheduler = send_metrics_from_scheduler
        self.dp_rank = dp_rank
        self.enable_kv_cache_events = bool(
            kv_events_config and attn_tp_rank == 0 and attn_cp_rank == 0
        )
        if self.enable_kv_cache_events:
            self.kv_event_publisher = EventPublisherFactory.create(
                kv_events_config, attn_dp_rank
            )

    def emit_kv_metrics(
        self,
        *,
        stats,
        max_running_requests: int,
        max_total_num_tokens: int,
    ) -> None:
        if not self.enable_kv_cache_events:
            return

        kv_metrics = KvMetrics()
        kv_metrics.request_active_slots = stats.num_running_reqs.total
        kv_metrics.request_total_slots = max_running_requests
        kv_metrics.kv_active_blocks = int(
            stats.token_usage * max_total_num_tokens
        )
        kv_metrics.kv_total_blocks = max_total_num_tokens
        kv_metrics.num_requests_waiting = stats.num_queue_reqs.total
        kv_metrics.gpu_cache_usage_perc = stats.token_usage
        kv_metrics.gpu_prefix_cache_hit_rate = stats.cache_hit_rate
        kv_metrics.data_parallel_rank = (
            self.dp_rank if self.dp_rank is not None else 0
        )

        if not self.send_metrics_from_scheduler.closed:
            self.send_metrics_from_scheduler.send_pyobj(kv_metrics)

    def publish_kv_events(self) -> None:
        if not self.enable_kv_cache_events:
            return

        events = self.tree_cache.take_events()
        if events:
            self.kv_event_publisher.publish(KVEventBatch(events=events))
'''


SCHEDULER_INIT_INSERT = """\
        self.kv_events_publisher = SchedulerKvEventsPublisher(
            kv_events_config=self.server_args.kv_events_config,
            attn_tp_rank=self.ps.attn_tp_rank,
            attn_cp_rank=self.ps.attn_cp_rank,
            attn_dp_rank=self.ps.attn_dp_rank,
            dp_rank=self.ps.dp_rank,
            tree_cache=self.tree_cache,
            send_metrics_from_scheduler=self.send_metrics_from_scheduler,
        )

"""


def transform(wt: Path) -> None:
    src = wt / "python/sglang/srt/observability/scheduler_metrics_mixin.py"
    sched = wt / "python/sglang/srt/managers/scheduler.py"
    target = wt / "python/sglang/srt/managers/scheduler_components/observability/kv_events_publisher.py"

    src_text = src.read_text()

    # Cut KvMetrics dataclass + 3 methods.
    s, e = find_class_lines(src_text, class_name="KvMetrics")
    kv_metrics_block = "\n".join(src_text.splitlines()[s:e]) + "\n"
    lines = src_text.splitlines(keepends=True)
    del lines[s:e]
    src_text = "".join(lines)

    for name in ["_publish_kv_events", "_emit_kv_metrics", "init_kv_events"]:
        s, e = find_method_lines(
            src_text, class_name="SchedulerMetricsMixin", method_name=name
        )
        lines = src_text.splitlines(keepends=True)
        del lines[s:e]
        src_text = "".join(lines)

    # Inside init_metrics body, drop the line ``self.init_kv_events(self.server_args.kv_events_config)``.
    src_text = src_text.replace(
        "        self.init_kv_events(self.server_args.kv_events_config)\n",
        "",
    )
    # Update callsites in the remaining mixin body.
    src_text = src_text.replace(
        "            self._emit_kv_metrics()\n",
        "            self.kv_events_publisher.emit_kv_metrics(\n"
        "                stats=self.stats,\n"
        "                max_running_requests=self.max_running_requests,\n"
        "                max_total_num_tokens=self.max_total_num_tokens,\n"
        "            )\n",
    )
    src_text = src_text.replace(
        "        self._publish_kv_events()\n",
        "        self.kv_events_publisher.publish_kv_events()\n",
    )

    src.write_text(src_text)

    # Build new file.
    target.write_text(TARGET_FILE_HEADER + kv_metrics_block + "\n\n" + NEW_CLASS_BODY)

    # Update Scheduler: import + ctor + on_idle callsite.
    text = sched.read_text()
    text = insert_after(
        text,
        anchor="from sglang.srt.managers.scheduler_components.observability.invariant_checker import (\n    SchedulerInvariantChecker,\n)\n",
        addition=(
            "from sglang.srt.managers.scheduler_components.observability.kv_events_publisher import (\n"
            "    SchedulerKvEventsPublisher,\n"
            ")\n"
        ),
    )
    text = replace_call_site(
        text,
        old="        self.is_initializing = False\n",
        new=SCHEDULER_INIT_INSERT + "        self.is_initializing = False\n",
    )
    # on_idle (moved to scheduler.py in C8) calls self._publish_kv_events().
    text = text.replace(
        "        self._publish_kv_events()\n",
        "        self.kv_events_publisher.publish_kv_events()\n",
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
