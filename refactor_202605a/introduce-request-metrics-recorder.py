#!/usr/bin/env python3
"""Introduce RequestMetricsRecorder owner class.

Move the if self.enable_metrics: branch of init_metric_collector_watchdog,
plus collect_metrics + _request_has_grammar methods, into a new
@dataclass(slots=True, kw_only=True) RequestMetricsRecorder.

Watchdog (gc_warning_threshold_secs + soft_watchdog) stays on facade per
md ch4 'gc_warning / soft_watchdog 不归本 class'.

PR1: method/field names retained (no observe rename).
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
    find_method_lines,
    insert_after,
    replace_call_site,
)
from _runner import run_pr

ID = "introduce-request-metrics-recorder"
SUBJECT = "Introduce RequestMetricsRecorder and move metrics methods"
BODY = """\
Move collect_metrics + _request_has_grammar methods from TokenizerManager
into a new managers/observability/request_metrics_recorder.py module as a
@dataclass(slots=True, kw_only=True) RequestMetricsRecorder (frozen=False
because metrics_collector is constructed in __post_init__).

Owns metrics_collector: Optional[TokenizerMetricsCollector] (None when
enable_metrics=False). __post_init__ encapsulates the if self.enable_metrics:
construction block formerly in init_metric_collector_watchdog, plus the
start_cpu_monitor_thread('tokenizer') side effect.

Watchdog config (gc_warning_threshold_secs + soft_watchdog) stays on facade
per md ch4 -- this commit removes only the metrics-part block from
init_metric_collector_watchdog; the watchdog block remains.

Caller updates: self.collect_metrics / self.metrics_collector references
in tokenizer_manager.py route through self.request_metrics_recorder.<X>.

Per md ch3 PR1 form: method names + field names retained (no rename to
observe / etc.); ch3.2 actions deferred to Ch2.
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
    new = wt / "python/sglang/srt/managers/observability/request_metrics_recorder.py"

    # Cut bottom-up.
    s, e = find_method_lines(
        tm.read_text(), class_name="TokenizerManager", method_name="_request_has_grammar"
    )
    has_grammar_text = cut_lines(tm, s, e)

    s, e = find_method_lines(
        tm.read_text(), class_name="TokenizerManager", method_name="collect_metrics"
    )
    collect_text = cut_lines(tm, s, e)

    new.write_text(HEADER + collect_text.rstrip() + "\n\n" + has_grammar_text.rstrip() + "\n")

    # ===== Drop the metrics block from init_metric_collector_watchdog =====
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

    # ===== Add import =====
    text = insert_after(
        text,
        anchor="from sglang.srt.managers.tokenizer_control_mixin import TokenizerControlMixin\n",
        addition="from sglang.srt.managers.observability.request_metrics_recorder import RequestMetricsRecorder\n",
    )

    # ===== Wire construction =====
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

    # ===== Caller updates =====
    text = text.replace(
        "self.collect_metrics(state, recv_obj, i)",
        "self.request_metrics_recorder.collect_metrics(state, recv_obj, i)",
    )
    text = text.replace(
        "self.metrics_collector.observe_one_aborted_request(",
        "self.request_metrics_recorder.metrics_collector.observe_one_aborted_request(",
    )
    text = text.replace(
        "self.metrics_collector.labels",
        "self.request_metrics_recorder.metrics_collector.labels",
    )
    text = text.replace(
        "self.metrics_collector.observe_time_to_first_token(",
        "self.request_metrics_recorder.metrics_collector.observe_time_to_first_token(",
    )
    text = text.replace(
        "self.metrics_collector.observe_inter_token_latency(",
        "self.request_metrics_recorder.metrics_collector.observe_inter_token_latency(",
    )
    text = text.replace(
        "self.metrics_collector.observe_one_finished_request(",
        "self.request_metrics_recorder.metrics_collector.observe_one_finished_request(",
    )
    text = text.replace(
        "self._request_has_grammar(state.obj)",
        "self.request_metrics_recorder._request_has_grammar(state.obj)",
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
