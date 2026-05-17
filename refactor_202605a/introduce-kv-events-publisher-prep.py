#!/usr/bin/env python3
"""Inplace prep for ``introduce-kv-events-publisher``: append the
``SchedulerKvEventsPublisher`` class skeleton to
``scheduler_components/kv_events_publisher.py`` (the ``KvMetrics``
dataclass already lives there from the preceding ``pre-move``).
Instantiate on Scheduler, type-flip 3 mixin methods to ``@staticmethod``
with ``self: "SchedulerKvEventsPublisher"``, rewrite ``emit_kv_metrics``
body reads of ``self.stats.X`` to ``self.get_stats().X`` Callable-getter
form, rewrite callers to the sister form.

Body bytes byte-identical wrt the post-move state (modulo decorator +
``self: SchedulerKvEventsPublisher`` → bare ``self`` signature
simplification in the move commit).

Privacy flips (``_emit_kv_metrics`` → ``emit_kv_metrics`` /
``_publish_kv_events`` → ``publish_kv_events``) were done in the
preceding ``-pre-rename`` commit; method bodies otherwise unchanged
apart from the ``self.stats`` → ``self.get_stats()`` getter rewrite in
``emit_kv_metrics``.
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
    ensure_bare_imports,
    ensure_imports,
    find_class_lines,
    find_method_lines,
    insert_after,
    replace_call_site,
)
from _runner import run_pr

ID = "introduce-kv-events-publisher-prep"
SUBJECT = "Stand up SchedulerKvEventsPublisher; migrate KV-event state to it"
BODY = """\
Inplace prep for the ``introduce-kv-events-publisher`` mech move.

- KvMetrics dataclass move (absorbed from former ``-pre-move`` straggler):
  cut the ``KvMetrics`` dataclass body byte-identical from
  ``observability/scheduler_metrics_mixin.py`` into the new module
  ``scheduler_components/kv_events_publisher.py``. Rewire the mixin to
  re-import ``KvMetrics`` from the new module so the existing
  ``KvMetrics()`` reference in ``emit_kv_metrics`` continues to resolve.
- Append an empty ``SchedulerKvEventsPublisher`` class skeleton (ctor;
  no methods yet) to the same ``scheduler_components/kv_events_publisher.py``
  module. Ctor adds ``get_stats: Callable[[], SchedulerStats]``
  for runtime-mutable scheduler stats (CLAUDE.md §4 form).
- Instantiate ``self.kv_events_publisher = SchedulerKvEventsPublisher(...)``
  in ``Scheduler.__init__`` just before ``self.is_initializing = False``,
  passing ``get_stats=lambda: self.stats``.
- In ``SchedulerMetricsMixin``, convert ``init_kv_events`` /
  ``emit_kv_metrics`` / ``publish_kv_events`` to ``@staticmethod`` with
  ``self: "SchedulerKvEventsPublisher"`` type annotation.
- ``emit_kv_metrics`` body rewrites ``self.stats.X`` reads as
  ``self.get_stats().X`` Callable-getter calls. Otherwise unchanged.
- Callers in the metrics mixin and in scheduler.py ``on_idle`` are
  rewritten to ``self.<method>(self.kv_events_publisher, ...)``.

The converted methods stay inside ``SchedulerMetricsMixin`` in this
commit; physical cut + paste to ``SchedulerKvEventsPublisher`` body
happens in ``introduce-kv-events-publisher-move``.
"""
AREA = "mech_scheduler"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


# Target file header (KvMetrics dataclass moves into this module FIRST,
# then the SchedulerKvEventsPublisher class skeleton is appended).
TARGET_FILE_HEADER = '''\
from __future__ import annotations

import dataclasses
import time
from dataclasses import dataclass
from typing import Any, Callable, Optional

from sglang.srt.disaggregation.kv_events import EventPublisherFactory, KVEventBatch


class SchedulerStats: ...  # type: ignore[no-redef]


'''


# Class skeleton appended to the target module (KvMetrics dataclass lands
# in the module FIRST, via the pre-move step that opens this transform).
NEW_CLASS_SKELETON = '''\
@dataclass(kw_only=True, slots=True)
class SchedulerKvEventsPublisher:
    kv_events_config: Optional[str]
    ps: "ParallelState"
    attn_tp_rank: int
    attn_cp_rank: int
    attn_dp_rank: int
    dp_rank: Optional[int]
    tree_cache: "BasePrefixCache"
    send_metrics_from_scheduler: Optional["zmq.Socket"]
    max_running_requests: int
    max_total_num_tokens: int
    get_stats: Callable
    enable_kv_cache_events: bool = False
    kv_event_publisher: Any = None

    def __post_init__(self) -> None:
        from sglang.srt.observability.scheduler_metrics_mixin import (
            SchedulerMetricsMixin,
        )

        SchedulerMetricsMixin.init_kv_events(self, self.kv_events_config)
'''


SCHEDULER_INIT_INSERT = '''\
        self.kv_events_publisher = SchedulerKvEventsPublisher(
            kv_events_config=self.server_args.kv_events_config,
            ps=self.ps,
            attn_tp_rank=self.ps.attn_tp_rank,
            attn_cp_rank=self.ps.attn_cp_rank,
            attn_dp_rank=self.ps.attn_dp_rank,
            dp_rank=self.ps.dp_rank,
            tree_cache=self.tree_cache,
            send_metrics_from_scheduler=self.send_metrics_from_scheduler,
            max_running_requests=self.max_running_requests,
            max_total_num_tokens=self.max_total_num_tokens,
            get_stats=lambda: self.stats,
        )

'''


# Body rewrites applied inside ``emit_kv_metrics`` so that, after the move,
# the method reads runtime-mutable scheduler ``stats`` through the
# Callable getter instead of referencing the (no-longer-present)
# ``self.stats`` attribute. Each anchor is unique within the method body.
EMIT_KV_METRICS_BODY_REWRITES = [
    (
        "kv_metrics.request_active_slots = self.stats.num_running_reqs.total",
        "kv_metrics.request_active_slots = self.get_stats().num_running_reqs.total",
    ),
    (
        "self.stats.token_usage * self.max_total_num_tokens",
        "self.get_stats().token_usage * self.max_total_num_tokens",
    ),
    (
        "kv_metrics.num_requests_waiting = self.stats.num_queue_reqs.total",
        "kv_metrics.num_requests_waiting = self.get_stats().num_queue_reqs.total",
    ),
    (
        "kv_metrics.gpu_cache_usage_perc = self.stats.token_usage",
        "kv_metrics.gpu_cache_usage_perc = self.get_stats().token_usage",
    ),
    (
        "kv_metrics.gpu_prefix_cache_hit_rate = self.stats.cache_hit_rate",
        "kv_metrics.gpu_prefix_cache_hit_rate = self.get_stats().cache_hit_rate",
    ),
]


def _add_static_decorator_and_typeflip(text: str, *, class_name: str,
                                       method_name: str,
                                       target_class: str,
                                       original_self_sig: str) -> str:
    """In-place: prepend ``@staticmethod`` and replace the ``self: Scheduler``
    (or just ``self``) part of the signature with
    ``self: "<TargetClass>"``.

    ``original_self_sig`` is the exact substring inside the def-line that
    represents the ``self`` parameter (e.g. ``self: Scheduler`` or
    ``self: Scheduler, foo: int``). We replace only the leading ``self``
    part, leaving any trailing params untouched.
    """
    s, e = find_method_lines(text, class_name=class_name, method_name=method_name)
    lines = text.splitlines(keepends=True)
    method_text = "".join(lines[s:e])
    if original_self_sig not in method_text:
        raise RuntimeError(
            f"{class_name}.{method_name}: anchor {original_self_sig!r} not found"
        )
    new_self_sig = original_self_sig.replace(
        "self: Scheduler", f"self: \"{target_class}\""
    )
    new_method = method_text.replace(original_self_sig, new_self_sig, 1)
    # Add @staticmethod above the ``def`` line.
    new_method = new_method.replace(
        f"    def {method_name}(",
        f"    @staticmethod\n    def {method_name}(",
        1,
    )
    return "".join(lines[:s]) + new_method + "".join(lines[e:])


def _rewrite_emit_kv_metrics_body(text: str) -> str:
    """Rewrite ``self.stats.X`` reads inside ``emit_kv_metrics`` to
    ``self.get_stats().X`` Callable-getter form. Each anchor is unique
    inside the method body.
    """
    s, e = find_method_lines(
        text,
        class_name="SchedulerMetricsMixin",
        method_name="emit_kv_metrics",
    )
    lines = text.splitlines(keepends=True)
    method_text = "".join(lines[s:e])
    for old, new in EMIT_KV_METRICS_BODY_REWRITES:
        if old not in method_text:
            raise RuntimeError(
                f"emit_kv_metrics body rewrite anchor not found: {old!r}"
            )
        method_text = method_text.replace(old, new, 1)
    return "".join(lines[:s]) + method_text + "".join(lines[e:])


def transform(wt: Path) -> None:
    src = wt / "python/sglang/srt/observability/scheduler_metrics_mixin.py"
    sched = wt / "python/sglang/srt/managers/scheduler.py"
    target = wt / "python/sglang/srt/managers/scheduler_components/kv_events_publisher.py"
    pkg_init = wt / "python/sglang/srt/managers/scheduler_components/__init__.py"

    # -1. KvMetrics dataclass move (absorbed from former ``-pre-move`` straggler):
    #     cut the dataclass out of the mixin, paste it verbatim into the new
    #     target module, then re-import KvMetrics from the new module so the
    #     existing ``KvMetrics()`` reference in ``emit_kv_metrics`` resolves.
    src_text = src.read_text()
    s, e = find_class_lines(src_text, class_name="KvMetrics")
    kv_metrics_block = "".join(src_text.splitlines(keepends=True)[s:e]).rstrip() + "\n"
    lines = src_text.splitlines(keepends=True)
    del lines[s:e]
    src_text = "".join(lines)
    src_text = insert_after(
        src_text,
        anchor="from sglang.srt.utils.scheduler_status_logger import SchedulerStatusLogger\n",
        addition="from sglang.srt.managers.scheduler_components.kv_events_publisher import KvMetrics\n",
    )
    src.write_text(src_text)

    pkg_init.parent.mkdir(parents=True, exist_ok=True)
    if not pkg_init.exists():
        pkg_init.write_text("")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(TARGET_FILE_HEADER + kv_metrics_block)

    # 0. Drop leading underscore on emit_kv_metrics / publish_kv_events
    #    so they expose a public API matching the sister manager forms.
    text = src.read_text()
    text = text.replace(
        "    def _emit_kv_metrics(self: Scheduler):",
        "    def emit_kv_metrics(self: Scheduler):",
    )
    text = text.replace(
        "    def _publish_kv_events(self: Scheduler):",
        "    def publish_kv_events(self: Scheduler):",
    )
    text = text.replace(
        "            self._emit_kv_metrics()\n",
        "            self.emit_kv_metrics()\n",
    )
    text = text.replace(
        "        self._publish_kv_events()\n",
        "        self.publish_kv_events()\n",
    )
    src.write_text(text)

    text = sched.read_text()
    text = text.replace(
        "        self._publish_kv_events()\n",
        "        self.publish_kv_events()\n",
    )
    sched.write_text(text)

    # 1. Append the SchedulerKvEventsPublisher class skeleton to the target
    #    file (KvMetrics already lives there from pre-move). The skeleton
    #    needs ``dataclass`` + ``Any`` / ``Callable`` / ``Optional`` typing
    #    imports; pre-move's file may have had them stripped by isort/ruff
    #    if KvMetrics alone didn't use them.
    target_text = target.read_text()
    target_text = ensure_imports(
        target_text,
        runtime={
            "dataclasses": ("dataclass",),
            "typing": ("Any", "Callable", "Optional"),
        },
        type_checking={
            "sglang.srt.distributed.parallel_state_wrapper": ("ParallelState",),
            "sglang.srt.mem_cache.base_prefix_cache": ("BasePrefixCache",),
        },
    )
    target_text = ensure_bare_imports(target_text, ["import zmq\n"])
    if not target_text.endswith("\n"):
        target_text += "\n"
    target.write_text(target_text + "\n" + NEW_CLASS_SKELETON)

    # 2. Type-flip 3 mixin methods to @staticmethod + self: SchedulerKvEventsPublisher.
    text = src.read_text()
    text = _add_static_decorator_and_typeflip(
        text,
        class_name="SchedulerMetricsMixin",
        method_name="init_kv_events",
        target_class="SchedulerKvEventsPublisher",
        original_self_sig="self: Scheduler, kv_events_config: Optional[str]",
    )
    text = _add_static_decorator_and_typeflip(
        text,
        class_name="SchedulerMetricsMixin",
        method_name="emit_kv_metrics",
        target_class="SchedulerKvEventsPublisher",
        original_self_sig="self: Scheduler",
    )
    text = _add_static_decorator_and_typeflip(
        text,
        class_name="SchedulerMetricsMixin",
        method_name="publish_kv_events",
        target_class="SchedulerKvEventsPublisher",
        original_self_sig="self: Scheduler",
    )

    # 3. Rewrite ``emit_kv_metrics`` body reads to Callable-getter form so
    #    the method survives the move into ``SchedulerKvEventsPublisher``
    #    (which has no ``stats`` attribute, only ``get_stats: Callable``).
    text = _rewrite_emit_kv_metrics_body(text)

    # 4. Mixin internal callsites: route through sister.
    text = text.replace(
        "            self.emit_kv_metrics()\n",
        "            self.emit_kv_metrics(self.kv_events_publisher)\n",
    )
    text = text.replace(
        "        self.publish_kv_events()\n",
        "        self.publish_kv_events(self.kv_events_publisher)\n",
    )
    # ``init_kv_events`` is no longer called from ``init_metrics``; the
    # call moves into ``Scheduler.__init__`` right after the publisher ctor
    # (see SCHEDULER_INIT_INSERT below).
    text = text.replace(
        "        self.init_kv_events(self.server_args.kv_events_config)\n\n",
        "",
    )
    # Add TYPE_CHECKING import for the new TargetClass so the
    # ``self: "SchedulerKvEventsPublisher"`` annotation resolves under pyflakes.
    if "from sglang.srt.managers.scheduler_components.kv_events_publisher import SchedulerKvEventsPublisher" not in text:
        text = text.replace(
            "if TYPE_CHECKING:\n",
            "if TYPE_CHECKING:\n"
            "    from sglang.srt.managers.scheduler_components.kv_events_publisher import SchedulerKvEventsPublisher\n",
            1,
        )
    src.write_text(text)

    # 5. Scheduler: import + ctor + on_idle callsite.
    text = sched.read_text()
    text = insert_after(
        text,
        anchor="from sglang.srt.managers.scheduler_components.invariant_checker import (\n    SchedulerInvariantChecker,\n)\n",
        addition=(
            "from sglang.srt.managers.scheduler_components.kv_events_publisher import (\n"
            "    SchedulerKvEventsPublisher,\n"
            ")\n"
        ),
    )
    # The publisher is not built yet at the ``build_kv_cache(...)`` call site,
    # so ``self.enable_kv_cache_events`` (which now lives on the publisher)
    # is unavailable. Inline the formula it used to compute.
    text = text.replace(
        "            enable_kv_cache_events=self.enable_kv_cache_events,\n",
        "            enable_kv_cache_events=bool(\n"
        "                self.server_args.kv_events_config\n"
        "                and self.ps.attn_tp_rank == 0\n"
        "                and self.ps.attn_cp_rank == 0\n"
        "            ),\n",
    )
    text = replace_call_site(
        text,
        old="        self.is_initializing = False\n",
        new=SCHEDULER_INIT_INSERT + "        self.is_initializing = False\n",
    )
    # Default ``self.send_metrics_from_scheduler = None`` at top of init_ipc_channels.
    # The original conditionally creates the socket only when
    # ``current_scheduler_metrics_enabled`` is True; the publisher now reads the
    # field unconditionally in its ctor, so the attribute must always exist.
    text = text.replace(
        "    def init_ipc_channels(self, port_args: PortArgs):\n"
        "        context = zmq.Context(2)\n"
        "        self.idle_sleeper = None\n",
        "    def init_ipc_channels(self, port_args: PortArgs):\n"
        "        context = zmq.Context(2)\n"
        "        self.idle_sleeper = None\n"
        "        self.send_metrics_from_scheduler = None\n",
    )
    # on_idle (in scheduler.py since C8) callsite.
    text = text.replace(
        "        self.publish_kv_events()\n",
        "        self.publish_kv_events(self.kv_events_publisher)\n",
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
