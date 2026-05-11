#!/usr/bin/env python3
"""Inplace prep for ``introduce-request-metrics-recorder``: build the
``RequestMetricsRecorder`` dataclass skeleton in
``managers/request_metrics_recorder.py``, instantiate
``self.request_metrics_recorder`` in TM ``__init__``, drop the metrics
block from ``init_metric_collector_watchdog`` (its logic now lives in
``RequestMetricsRecorder.__post_init__``), convert ``collect_metrics`` and
``_request_has_grammar`` to ``@staticmethod`` with ``self:
RequestMetricsRecorder`` annotation, and rewrite all
``self.metrics_collector.*`` references to
``self.request_metrics_recorder.metrics_collector.*``.

Method bodies stay inside ``TokenizerManager`` class in this commit; the
physical cut + paste to ``RequestMetricsRecorder`` body happens in
``introduce-request-metrics-recorder-move``.
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

ID = "introduce-request-metrics-recorder-prep"
SUBJECT = "Build RequestMetricsRecorder skeleton + @staticmethod prep (prep for move)"
BODY = """\
Inplace prep for the ``introduce-request-metrics-recorder`` mech move.

- Create ``managers/request_metrics_recorder.py`` with a
  ``@dataclass(slots=True, kw_only=True) RequestMetricsRecorder`` whose
  ``__post_init__`` encapsulates the ``if self.enable_metrics:``
  construction block formerly in ``init_metric_collector_watchdog``
  (plus the ``start_cpu_monitor_thread('tokenizer')`` side effect).
- Instantiate ``self.request_metrics_recorder = RequestMetricsRecorder(...)``
  in ``TokenizerManager.__init__`` just before the request log manager
  block.
- Drop the metrics block from ``init_metric_collector_watchdog`` — its
  logic now lives in ``RequestMetricsRecorder.__post_init__``. The
  watchdog block stays.
- Convert ``collect_metrics`` and ``_request_has_grammar`` to
  ``@staticmethod`` with ``self: "RequestMetricsRecorder"`` type
  annotation. Bodies byte-identical.
- Rewrite call sites:
    ``self.metrics_collector.X`` →
      ``self.request_metrics_recorder.metrics_collector.X``
    ``self.collect_metrics(state, recv_obj, i)`` →
      ``TokenizerManager.collect_metrics(self.request_metrics_recorder, state, recv_obj, i)``
    ``self._request_has_grammar(state.obj)`` →
      ``TokenizerManager._request_has_grammar(self.request_metrics_recorder, state.obj)``

The 2 methods stay inside TokenizerManager in this commit; physical cut
+ paste to ``RequestMetricsRecorder`` body happens in
``introduce-request-metrics-recorder-move``.
"""
AREA = "mech_tokenizer_manager"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


HEADER = '''from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional, Union

from sglang.srt.disaggregation.utils import DisaggregationMode
from sglang.srt.managers.io_struct import (
    BatchEmbeddingOutput,
    BatchStrOutput,
    BatchTokenIDOutput,
    GenerateReqInput,
)
from sglang.srt.managers.request_state import ReqState
from sglang.srt.observability.cpu_monitor import start_cpu_monitor_thread
from sglang.srt.observability.metrics_collector import TokenizerMetricsCollector
from sglang.srt.server_args import ServerArgs

logger = logging.getLogger(__name__)


@dataclass(slots=True, kw_only=True)
class RequestMetricsRecorder:
    """Per-request Prometheus metrics emission."""

    server_args: ServerArgs
    enable_metrics: bool
    enable_priority_scheduling: bool
    metrics_collector: Optional[TokenizerMetricsCollector] = None

    def __post_init__(self) -> None:
        if not self.enable_metrics:
            return
        engine_type = DisaggregationMode.to_engine_type(
            self.server_args.disaggregation_mode
        )
        labels = {
            "model_name": self.server_args.served_model_name,
            "engine_type": engine_type,
        }
        if self.enable_priority_scheduling:
            labels["priority"] = ""
        if self.server_args.tokenizer_metrics_allowed_custom_labels:
            for label in self.server_args.tokenizer_metrics_allowed_custom_labels:
                labels[label] = ""
        if self.server_args.extra_metric_labels:
            labels.update(self.server_args.extra_metric_labels)
        self.metrics_collector = TokenizerMetricsCollector(
            server_args=self.server_args,
            labels=labels,
            bucket_time_to_first_token=self.server_args.bucket_time_to_first_token,
            bucket_e2e_request_latency=self.server_args.bucket_e2e_request_latency,
            bucket_inter_token_latency=self.server_args.bucket_inter_token_latency,
        )
        start_cpu_monitor_thread("tokenizer")
'''


def transform(wt: Path) -> None:
    tm = wt / "python/sglang/srt/managers/tokenizer_manager.py"
    new = wt / "python/sglang/srt/managers/request_metrics_recorder.py"

    # 1. Create the new file with the dataclass skeleton.
    new.write_text(HEADER)

    # 2. Drop the metrics block from init_metric_collector_watchdog; its
    #    logic now lives in RequestMetricsRecorder.__post_init__.
    text = tm.read_text()
    text = replace_call_site(
        text,
        old=(
            "    def init_metric_collector_watchdog(self):\n"
            "        # Metrics\n"
            "        if self.enable_metrics:\n"
            "            engine_type = DisaggregationMode.to_engine_type(\n"
            "                self.server_args.disaggregation_mode\n"
            "            )\n"
            "\n"
            "            labels = {\n"
            "                \"model_name\": self.server_args.served_model_name,\n"
            "                \"engine_type\": engine_type,\n"
            "            }\n"
            "            if self.enable_priority_scheduling:\n"
            "                labels[\"priority\"] = \"\"\n"
            "            if self.server_args.tokenizer_metrics_allowed_custom_labels:\n"
            "                for label in self.server_args.tokenizer_metrics_allowed_custom_labels:\n"
            "                    labels[label] = \"\"\n"
            "            if self.server_args.extra_metric_labels:\n"
            "                labels.update(self.server_args.extra_metric_labels)\n"
            "            self.metrics_collector = TokenizerMetricsCollector(\n"
            "                server_args=self.server_args,\n"
            "                labels=labels,\n"
            "                bucket_time_to_first_token=self.server_args.bucket_time_to_first_token,\n"
            "                bucket_e2e_request_latency=self.server_args.bucket_e2e_request_latency,\n"
            "                bucket_inter_token_latency=self.server_args.bucket_inter_token_latency,\n"
            "            )\n"
            "\n"
            "            start_cpu_monitor_thread(\"tokenizer\")\n"
            "\n"
        ),
        new=(
            "    def init_metric_collector_watchdog(self):\n"
        ),
    )

    # 3. Add import for RequestMetricsRecorder.
    text = insert_after(
        text,
        anchor="from sglang.srt.managers.tokenizer_control_mixin import TokenizerControlMixin\n",
        addition="from sglang.srt.managers.request_metrics_recorder import RequestMetricsRecorder\n",
    )

    # 4. Wire construction of self.request_metrics_recorder in __init__.
    text = replace_call_site(
        text,
        old=(
            "        # Request log manager\n"
            "        self.request_log_manager = RequestLogManager.from_server_args(\n"
        ),
        new=(
            "        # Request metrics recorder\n"
            "        self.request_metrics_recorder = RequestMetricsRecorder(\n"
            "            server_args=self.server_args,\n"
            "            enable_metrics=self.enable_metrics,\n"
            "            enable_priority_scheduling=self.enable_priority_scheduling,\n"
            "        )\n"
            "\n"
            "        # Request log manager\n"
            "        self.request_log_manager = RequestLogManager.from_server_args(\n"
        ),
    )

    # 5. Convert collect_metrics to @staticmethod with self: RequestMetricsRecorder.
    s, e = find_method_lines(text, class_name="TokenizerManager", method_name="collect_metrics")
    lines = text.splitlines(keepends=True)
    method_text = "".join(lines[s:e])
    if "    def collect_metrics(self, state: ReqState, recv_obj: BatchStrOutput, i: int):\n" not in method_text:
        raise RuntimeError("collect_metrics signature shape unexpected")
    new_method = method_text.replace(
        "    def collect_metrics(self, state: ReqState, recv_obj: BatchStrOutput, i: int):\n",
        "    @staticmethod\n"
        "    def collect_metrics(self: \"RequestMetricsRecorder\", state: ReqState, recv_obj: BatchStrOutput, i: int):\n",
    )
    text = "".join(lines[:s]) + new_method + "".join(lines[e:])

    # 6. Convert _request_has_grammar to @staticmethod with self: RequestMetricsRecorder.
    s, e = find_method_lines(text, class_name="TokenizerManager", method_name="_request_has_grammar")
    lines = text.splitlines(keepends=True)
    method_text = "".join(lines[s:e])
    if "    def _request_has_grammar(self, obj: GenerateReqInput) -> bool:\n" not in method_text:
        raise RuntimeError("_request_has_grammar signature shape unexpected")
    new_method = method_text.replace(
        "    def _request_has_grammar(self, obj: GenerateReqInput) -> bool:\n",
        "    @staticmethod\n"
        "    def _request_has_grammar(self: \"RequestMetricsRecorder\", obj: GenerateReqInput) -> bool:\n",
    )
    text = "".join(lines[:s]) + new_method + "".join(lines[e:])

    # 7. Caller rewrites. `self.metrics_collector.*` references in TM body
    #    must route through the recorder (its body still reads `self.metrics_collector.*`
    #    because the type-flipped self IS a RequestMetricsRecorder there).
    #    External call sites (in TM facade methods, NOT in the bodies of the
    #    type-flipped staticmethods) need to thread through
    #    self.request_metrics_recorder.
    text = text.replace(
        "self.collect_metrics(state, recv_obj, i)",
        "TokenizerManager.collect_metrics(self.request_metrics_recorder, state, recv_obj, i)",
    )
    text = text.replace(
        "            self.metrics_collector.observe_one_aborted_request(\n"
        "                self.metrics_collector.labels\n"
        "            )\n",
        "            self.request_metrics_recorder.metrics_collector.observe_one_aborted_request(\n"
        "                self.request_metrics_recorder.metrics_collector.labels\n"
        "            )\n",
    )

    tm.write_text(text)


if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        area_branch=AREA_BRANCH,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
