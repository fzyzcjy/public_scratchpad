#!/usr/bin/env python3
"""Inplace prep for ``introduce-kv-events-publisher``: build the
``SchedulerKvEventsPublisher`` class skeleton (ctor + ``KvMetrics``
dataclass, NO methods yet), instantiate on Scheduler, type-flip 3 mixin
methods to ``@staticmethod`` with ``self: "SchedulerKvEventsPublisher"``,
rewrite callers to the sister form.

Body bytes byte-identical wrt the post-move state (modulo decorator +
``self: SchedulerKvEventsPublisher`` → bare ``self`` signature
simplification in the move commit).

Privacy flips (``_emit_kv_metrics`` → ``emit_kv_metrics`` /
``_publish_kv_events`` → ``publish_kv_events``) were done in the
preceding ``-pre-rename`` commit; method bodies otherwise unchanged.
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

ID = "introduce-kv-events-publisher-prep"
SUBJECT = "Build SchedulerKvEventsPublisher skeleton + @staticmethod prep (prep for move)"
BODY = """\
Inplace prep for the ``introduce-kv-events-publisher`` mech move.

- Create ``scheduler_components/kv_events_publisher.py`` with an empty
  ``SchedulerKvEventsPublisher`` class skeleton (ctor + ``KvMetrics``
  dataclass moved here; no methods yet).
- Instantiate ``self.kv_events_publisher = SchedulerKvEventsPublisher(...)``
  in ``Scheduler.__init__`` just before ``self.is_initializing = False``.
- In ``SchedulerMetricsMixin``, convert 3 methods (``init_kv_events`` /
  ``emit_kv_metrics`` / ``publish_kv_events``) to ``@staticmethod`` with
  ``self: "SchedulerKvEventsPublisher"`` type annotation. Body bytes
  unchanged.
- Callers (2 in metrics mixin, 1 in scheduler.py ``on_idle``) rewritten
  to ``self.<method>(self.kv_events_publisher, ...)``.

The 3 methods stay inside ``SchedulerMetricsMixin`` in this commit;
physical cut + paste to ``SchedulerKvEventsPublisher`` body happens in
``introduce-kv-events-publisher-move``.

Block-move audit (2026-05-11): the audit flagged inlining the
``init_kv_events`` body into ``SchedulerKvEventsPublisher.__init__`` as
a "block-move candidate" that might be extractable into a ``-pre-prep``
commit. On review, this is not separable: the destination
(``SchedulerKvEventsPublisher.__init__``) does not exist before this
commit — building the class skeleton + ctor is precisely what this prep
does. The ctor inlining is structurally intrinsic to introducing the
class and cannot be hoisted into an earlier commit. No
``introduce-kv-events-publisher-pre-prep`` is created.
"""
AREA = "mech_scheduler"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


# Target file: header + dataclass + empty class skeleton (no methods).
TARGET_FILE_HEADER = '''\
from __future__ import annotations

import dataclasses
import time
from dataclasses import dataclass
from typing import Optional

from sglang.srt.disaggregation.kv_events import EventPublisherFactory, KVEventBatch


# ``SchedulerStats`` referenced only as a type hint in ``emit_kv_metrics`` —
# leave a forward-ref placeholder.
class SchedulerStats: ...  # type: ignore[no-redef]


'''


NEW_CLASS_SKELETON = '''\
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
        max_running_requests: int,
        max_total_num_tokens: int,
    ) -> None:
        self.tree_cache = tree_cache
        self.send_metrics_from_scheduler = send_metrics_from_scheduler
        self.dp_rank = dp_rank
        self.attn_tp_rank = attn_tp_rank
        self.attn_cp_rank = attn_cp_rank
        self.attn_dp_rank = attn_dp_rank
        self.max_running_requests = max_running_requests
        self.max_total_num_tokens = max_total_num_tokens
        self.enable_kv_cache_events = bool(
            kv_events_config and attn_tp_rank == 0 and attn_cp_rank == 0
        )
        if self.enable_kv_cache_events:
            self.kv_event_publisher = EventPublisherFactory.create(
                kv_events_config, attn_dp_rank
            )
'''


SCHEDULER_INIT_INSERT = '''\
        self.kv_events_publisher = SchedulerKvEventsPublisher(
            kv_events_config=self.server_args.kv_events_config,
            attn_tp_rank=self.ps.attn_tp_rank,
            attn_cp_rank=self.ps.attn_cp_rank,
            attn_dp_rank=self.ps.attn_dp_rank,
            dp_rank=self.ps.dp_rank,
            tree_cache=self.tree_cache,
            send_metrics_from_scheduler=self.send_metrics_from_scheduler,
            max_running_requests=self.max_running_requests,
            max_total_num_tokens=self.max_total_num_tokens,
        )

'''


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


def transform(wt: Path) -> None:
    src = wt / "python/sglang/srt/observability/scheduler_metrics_mixin.py"
    sched = wt / "python/sglang/srt/managers/scheduler.py"
    target = wt / "python/sglang/srt/managers/scheduler_components/kv_events_publisher.py"

    # 1. Move the ``KvMetrics`` dataclass out of the mixin into the new file.
    src_text = src.read_text()
    s, e = find_class_lines(src_text, class_name="KvMetrics")
    kv_metrics_block = "".join(src_text.splitlines(keepends=True)[s:e]).rstrip() + "\n"
    lines = src_text.splitlines(keepends=True)
    del lines[s:e]
    src_text = "".join(lines)
    src.write_text(src_text)

    # 2. Create new target file (skeleton: header + KvMetrics + empty class).
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        TARGET_FILE_HEADER + kv_metrics_block + "\n\n" + NEW_CLASS_SKELETON
    )

    # 3. Type-flip 3 mixin methods to @staticmethod + self: SchedulerKvEventsPublisher.
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

    # 4. Mixin internal callsites: route through sister.
    text = text.replace(
        "            self.emit_kv_metrics()\n",
        "            self.emit_kv_metrics(self.kv_events_publisher)\n",
    )
    text = text.replace(
        "        self.publish_kv_events()\n",
        "        self.publish_kv_events(self.kv_events_publisher)\n",
    )
    # ``init_kv_events`` is still called from ``init_metrics`` body.
    text = text.replace(
        "        self.init_kv_events(self.server_args.kv_events_config)\n",
        "        self.init_kv_events(\n"
        "            self.kv_events_publisher, self.server_args.kv_events_config\n"
        "        )\n",
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
    text = replace_call_site(
        text,
        old="        self.is_initializing = False\n",
        new=SCHEDULER_INIT_INSERT + "        self.is_initializing = False\n",
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
