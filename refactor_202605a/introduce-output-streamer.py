#!/usr/bin/env python3
"""1:N split #2 of ``SchedulerOutputProcessorMixin``: 6 stream methods move
to ``SchedulerOutputStreamer`` at
``scheduler_components/output_streamer.py``.

Ctor narrow kwargs: 2 collaborators (send_to_detokenizer, tree_cache) + 6
configs (ps, server_args, is_generation, stream_interval, spec_algorithm,
disaggregation_mode) + 2 Callables (enable_hicache_storage,
load_inquirer_get_loads — the runtime-mutable Scheduler bool +
LoadInquirer's get_loads bound method).

3 privacy flips:
- ``_get_cached_tokens_details`` → ``get_cached_tokens_details`` (drop ``_``,
  sister API for upcoming BatchResultProcessor)
- ``stream_output_generation`` → ``_stream_output_generation`` (add ``_``)
- ``stream_output_embedding`` → ``_stream_output_embedding`` (add ``_``)

Cross-commit fix: ``SchedulerRequestReceiver`` (introduced in C4) took
``stream_output: Callable`` as a transitional shim. The Scheduler-side
instantiation is rewired to pass ``self.output_streamer.stream_output``;
the receiver class itself doesn't change here.

Callsites updated: 4 ``self.stream_output(...)`` callsites (3 in remaining
output_processor mixin body — BatchResultProcessor methods until C17 — and
1 in ``Scheduler.__init__`` for the receiver shim).
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

ID = "introduce-output-streamer"
SUBJECT = "Introduce SchedulerOutputStreamer (split #2 of output_processor mixin)"
BODY = """\
Pull 6 stream methods out of ``SchedulerOutputProcessorMixin`` into
``SchedulerOutputStreamer`` at
``scheduler_components/output_streamer.py``. Scheduler holds it as
``self.output_streamer``.

Ctor narrow kwargs (per CLAUDE.md ch4): 2 collaborators + 6 configs + 2
Callables (``enable_hicache_storage`` for the runtime-mutable Scheduler
bool, ``load_inquirer_get_loads`` for the bound LoadInquirer method).

3 privacy flips: ``_get_cached_tokens_details`` → ``get_cached_tokens_details``,
``stream_output_generation`` → ``_stream_output_generation``,
``stream_output_embedding`` → ``_stream_output_embedding``.

Cross-commit fix: ``SchedulerRequestReceiver`` (C4) took ``stream_output``
as a Callable transitional kwarg. Scheduler instantiation is rewired to
``stream_output=self.output_streamer.stream_output`` (the receiver class
itself unchanged).

Callsites updated:
- ``output_processor_mixin`` body (still in place until C17): 4 callsites
  (``self.stream_output`` × 3 + ``self._get_cached_tokens_details``).
- ``Scheduler.__init__``: receiver shim ``stream_output=self.stream_output`` →
  ``stream_output=self.output_streamer.stream_output``; insert the streamer
  ctor *before* the receiver ctor so the dep resolves.

The output_processor mixin remains until ``introduce-batch-result-processor``
finishes the 1:N split next.
"""
AREA = "mech_scheduler"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


TARGET_FILE_HEADER = '''\
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional

import torch
import zmq

from sglang.srt.disaggregation.utils import DisaggregationMode
from sglang.srt.environ import envs
from sglang.srt.managers.io_struct import (
    BatchEmbeddingOutput,
    BatchTokenIDOutput,
    GetLoadsReqInput,
    GetLoadsReqOutput,
)
from sglang.srt.managers.schedule_batch import BaseFinishReason, Req


logger = logging.getLogger(__name__)


# Module-level constant copied from the original output_processor mixin.
DEFAULT_FORCE_STREAM_INTERVAL = envs.SGLANG_FORCE_STREAM_INTERVAL.get()


'''


NEW_CLASS_HEADER = '''\
class SchedulerOutputStreamer:
    """Output adapter — serialize finished/sampling-complete reqs into
    ``BatchTokenIDOutput`` / ``BatchEmbeddingOutput`` and write to the
    detokenizer IPC. Composition target on Scheduler
    (``self.output_streamer``)."""

    def __init__(
        self,
        *,
        send_to_detokenizer,
        tree_cache,
        ps,
        server_args,
        is_generation: bool,
        stream_interval: int,
        spec_algorithm,
        disaggregation_mode,
        enable_hicache_storage: Callable[[], bool],
        load_inquirer_get_loads: Callable[..., Any],
    ) -> None:
        self.send_to_detokenizer = send_to_detokenizer
        self.tree_cache = tree_cache
        self.ps = ps
        self.server_args = server_args
        self.is_generation = is_generation
        self.stream_interval = stream_interval
        self.spec_algorithm = spec_algorithm
        self.disaggregation_mode = disaggregation_mode
        self.enable_hicache_storage = enable_hicache_storage
        self.load_inquirer_get_loads = load_inquirer_get_loads
        self._test_stream_output_count: int = 0

'''


SCHEDULER_INIT_INSERT = """\
        self.output_streamer = SchedulerOutputStreamer(
            send_to_detokenizer=self.send_to_detokenizer,
            tree_cache=self.tree_cache,
            ps=self.ps,
            server_args=self.server_args,
            is_generation=self.is_generation,
            stream_interval=self.stream_interval,
            spec_algorithm=self.spec_algorithm,
            disaggregation_mode=self.disaggregation_mode,
            enable_hicache_storage=lambda: self.enable_hicache_storage,
            load_inquirer_get_loads=lambda req: self.load_inquirer.get_loads(
                req,
                running_batch=self.running_batch,
                waiting_queue=self.waiting_queue,
                stats=self.metrics_reporter.stats,
                spec_total_num_accept_tokens=self.metrics_reporter.spec_total_num_accept_tokens,
                spec_total_num_forward_ct=self.metrics_reporter.spec_total_num_forward_ct,
                disagg_prefill_bootstrap_queue=getattr(self, "disagg_prefill_bootstrap_queue", None),
                disagg_prefill_inflight_queue=getattr(self, "disagg_prefill_inflight_queue", None),
                disagg_decode_prealloc_queue=getattr(self, "disagg_decode_prealloc_queue", None),
                disagg_decode_transfer_queue=getattr(self, "disagg_decode_transfer_queue", None),
            ),
        )

"""


def transform(wt: Path) -> None:
    src = wt / "python/sglang/srt/managers/scheduler_output_processor_mixin.py"
    sched = wt / "python/sglang/srt/managers/scheduler.py"
    target = wt / "python/sglang/srt/managers/scheduler_components/output_streamer.py"

    src_text = src.read_text()

    # Cut 6 stream methods bottom-up.
    method_blocks = []
    for name in [
        "stream_output_embedding",
        "stream_output_generation",
        "_trigger_crash_for_tests",
        "stream_output",
        "_get_cached_tokens_details",
        "_get_storage_backend_type",
    ]:
        s, e = find_method_lines(
            src_text, class_name="SchedulerOutputProcessorMixin", method_name=name
        )
        block = "".join(src_text.splitlines(keepends=True)[s:e])
        method_blocks.append((name, block))
        lines = src_text.splitlines(keepends=True)
        del lines[s:e]
        src_text = "".join(lines)

    src.write_text(src_text)

    # Reverse to restore source order.
    method_blocks.reverse()
    methods_text = "".join(b for _, b in method_blocks)

    # Drop ``: Scheduler`` annotations.
    methods_text = methods_text.replace("self: Scheduler", "self")

    # Body substitutions:
    # - ``self.enable_hicache_storage`` (read-as-bool) → ``self.enable_hicache_storage()``
    #   since it's now a Callable getter on the manager.
    methods_text = methods_text.replace(
        "self.enable_hicache_storage", "self.enable_hicache_storage()"
    )
    # C13 rewrote the body's ``self.get_loads(...)`` to a multi-kwarg form
    # ``self.load_inquirer.get_loads(GetLoadsReqInput(...), running_batch=...,
    # ...)``. The explicit kwargs reference Scheduler-only fields that the
    # streamer doesn't carry. Replace the whole call with a single-arg form;
    # the streamer's Callable wraps the kwargs internally (via the lambda
    # passed in ``SCHEDULER_INIT_INSERT``).
    #
    # The regex must match the outer ``)`` of the call — not any nested
    # ``)`` from the inner ``getattr(...)`` lines that black wraps onto two
    # lines. Anchor on exactly 8-space indent for the closing paren.
    import re as _re_body
    methods_text = _re_body.sub(
        r'        load = self\.load_inquirer\.get_loads\(\n.*?\n        \)',
        '        load = self.load_inquirer_get_loads(GetLoadsReqInput(include=["core"]))',
        methods_text,
        flags=_re_body.DOTALL,
    )
    # - ``self.ps`` references stay (ctor field).
    # - ``self.server_args`` / ``self.tree_cache`` etc. stay (ctor fields).
    # - ``self.send_to_detokenizer`` stays.
    # - ``self.spec_algorithm`` / ``self.disaggregation_mode`` / ``self.is_generation``
    #   / ``self.stream_interval`` stay (ctor fields).

    # Privacy flips (definitions + internal callsites).
    methods_text = methods_text.replace(
        "    def _get_cached_tokens_details(", "    def get_cached_tokens_details("
    )
    methods_text = methods_text.replace(
        "    def stream_output_generation(", "    def _stream_output_generation("
    )
    methods_text = methods_text.replace(
        "    def stream_output_embedding(", "    def _stream_output_embedding("
    )
    methods_text = methods_text.replace(
        "self._get_cached_tokens_details(", "self.get_cached_tokens_details("
    )
    methods_text = methods_text.replace(
        "self.stream_output_generation(", "self._stream_output_generation("
    )
    methods_text = methods_text.replace(
        "self.stream_output_embedding(", "self._stream_output_embedding("
    )

    # ``_trigger_crash_for_tests`` body uses ``hasattr(self, "_test_stream_output_count")``
    # — leave verbatim per Ch1 (preflight stays Ch2 except the one ctor init we
    # already added: ``self._test_stream_output_count: int = 0`` in the ctor).
    # The lazy hasattr branch becomes effectively dead but we don't remove it.

    target.write_text(TARGET_FILE_HEADER + NEW_CLASS_HEADER + methods_text)

    # Update Scheduler.
    text = sched.read_text()
    text = insert_after(
        text,
        anchor="from sglang.srt.managers.scheduler_components.logprob_result_processor import (\n    SchedulerLogprobResultProcessor,\n)\n",
        addition=(
            "from sglang.srt.managers.scheduler_components.output_streamer import (\n"
            "    SchedulerOutputStreamer,\n"
            ")\n"
        ),
    )
    # Insert streamer ctor AFTER the logprob_computer ctor (so that the next
    # commit's ``batch_result_processor`` sister kwargs resolve in correct
    # order). The receiver ctor (C4) is still earlier in the block; its
    # ``stream_output`` Callable kwarg is lazy (lambda) so order doesn't
    # matter for the receiver.
    text = insert_after(
        text,
        anchor=(
            "        self.logprob_result_processor = SchedulerLogprobResultProcessor(\n"
            "            server_args=self.server_args,\n"
            "            model_config=self.model_config,\n"
            "        )\n\n"
        ),
        addition=SCHEDULER_INIT_INSERT,
    )
    # Cross-commit fix: receiver shim ``stream_output=self.stream_output`` →
    # lazy-bound to ``self.output_streamer.stream_output``. Lambda so the
    # receiver ctor (which runs earlier in __init__) doesn't read the
    # not-yet-constructed ``self.output_streamer``.
    text = text.replace(
        "            stream_output=self.stream_output,\n",
        "            stream_output=lambda *a, **kw: self.output_streamer.stream_output(*a, **kw),\n",
    )
    # Direct callsite in Scheduler hot-path (event_loop_overlap_disagg_*) —
    # ``self.stream_output(...)`` left over from the mixin era.
    text = text.replace(
        "self.stream_output(", "self.output_streamer.stream_output("
    )
    sched.write_text(text)

    # External callers that bypassed the mixin: disaggregation/prefill.py and
    # dllm/mixin/scheduler.py both invoke ``self.stream_output(...)`` on
    # Scheduler. Route them to the streamer.
    for f in [
        wt / "python/sglang/srt/disaggregation/prefill.py",
        wt / "python/sglang/srt/dllm/mixin/scheduler.py",
    ]:
        ftext = f.read_text()
        ftext = ftext.replace(
            "self.stream_output(", "self.output_streamer.stream_output("
        )
        f.write_text(ftext)

    # Update output_processor_mixin: 4 callsites (still mixin until C17).
    text = src.read_text()
    text = text.replace(
        "self.stream_output(", "self.output_streamer.stream_output("
    )
    text = text.replace(
        "self._get_cached_tokens_details(",
        "self.output_streamer.get_cached_tokens_details(",
    )
    # ``self.stream_output_generation`` is renamed to ``_stream_output_generation``
    # on the streamer. The remaining mixin body (still in place until C17 cuts
    # it into batch_result_processor) calls it directly — re-route via streamer.
    text = text.replace(
        "self.stream_output_generation(",
        "self.output_streamer._stream_output_generation(",
    )
    text = text.replace(
        "self.stream_output_embedding(",
        "self.output_streamer._stream_output_embedding(",
    )
    src.write_text(text)


if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        area_branch=AREA_BRANCH,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
