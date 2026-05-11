#!/usr/bin/env python3
"""Prep: RequestMetricsRecorder skeleton + composition wiring + __post_init__ + in-place staticmethod conversion + caller rewrites."""

# /// script
# requires-python = ">=3.10"
# dependencies = ["typer"]
# ///

import ast
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from _helpers import insert_after, replace_call_site
from _runner import run_pr

ID = "introduce-request-metrics-recorder-prep"
SUBJECT = "Stage per-request metrics for handoff to RequestMetricsRecorder"
BODY = """\
Per MECH_COMMIT_SPLIT §"拆 class 场景": prep does ALL semantic work.

Builds RequestMetricsRecorder skeleton; wires composition in TM.__init__;
relocates the metrics-construction block from
init_metric_collector_watchdog into RequestMetricsRecorder.__post_init__
(factory-style logic, mirrors RTW's from_server_args pattern); converts
collect_metrics + _request_has_grammar to @staticmethod with
self: "RequestMetricsRecorder" annotation; rewrites callers to
``TokenizerManager.<method>(self.request_metrics_recorder, ...)`` form
and ``self.metrics_collector.X`` → ``self.request_metrics_recorder.metrics_collector.X``.
Methods stay on TM in this commit; the next commit's pure cut/paste +
caller prefix replacement completes the move.
"""
AREA = "mech_tokenizer_manager"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


SKELETON = '''from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from sglang.srt.disaggregation.utils import DisaggregationMode
from sglang.srt.observability.cpu_monitor import start_cpu_monitor_thread
from sglang.srt.observability.metrics_collector import TokenizerMetricsCollector
from sglang.srt.server_args import ServerArgs


@dataclass(slots=True, kw_only=True)
class RequestMetricsRecorder:
    """Per-request Prometheus metrics emission."""

    server_args: ServerArgs
    enable_metrics: bool
    enable_priority_scheduling: bool
    disaggregation_mode: DisaggregationMode
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


def _method_ranges(text: str, class_name: str, method_name: str):
    tree = ast.parse(text)
    func_types = (ast.FunctionDef, ast.AsyncFunctionDef)
    for cls in ast.walk(tree):
        if isinstance(cls, ast.ClassDef) and cls.name == class_name:
            for i, node in enumerate(cls.body):
                if isinstance(node, func_types) and node.name == method_name:
                    start = node.lineno - 1
                    if node.decorator_list:
                        start = node.decorator_list[0].lineno - 1
                    body_start = node.body[0].lineno - 1
                    if i + 1 < len(cls.body):
                        end = cls.body[i + 1].lineno - 1
                        nxt = cls.body[i + 1]
                        if isinstance(nxt, func_types + (ast.ClassDef,)) and nxt.decorator_list:
                            end = nxt.decorator_list[0].lineno - 1
                    else:
                        end = node.end_lineno
                    return start, body_start, end
    raise ValueError(f"{class_name}.{method_name} not found")


# Replacement headers: @staticmethod + self: TargetClass typing. Body byte-equivalent
# across prep→move so the move commit is a pure cut/paste.
NEW_HAS_GRAMMAR_HEADER = '''    @staticmethod
    def _request_has_grammar(self: "RequestMetricsRecorder", obj: GenerateReqInput) -> bool:
'''

NEW_COLLECT_HEADER = '''    @staticmethod
    def collect_metrics(self: "RequestMetricsRecorder", state: ReqState, recv_obj: BatchStrOutput, i: int):
'''


def _replace_method_header(text: str, class_name: str, method_name: str, new_header: str) -> str:
    s, body_s, e = _method_ranges(text, class_name, method_name)
    lines = text.splitlines(keepends=True)
    body_text = "".join(lines[body_s:e])
    new_method = new_header + body_text
    return "".join(lines[:s]) + new_method + "".join(lines[e:])


def transform(wt: Path) -> None:
    tm = wt / "python/sglang/srt/managers/tokenizer_manager.py"
    new = wt / "python/sglang/srt/managers/request_metrics_recorder.py"
    new.write_text(SKELETON)

    text = tm.read_text()
    text = insert_after(
        text,
        anchor="from sglang.srt.managers.tokenizer_control_mixin import TokenizerControlMixin\n",
        addition="from sglang.srt.managers.request_metrics_recorder import RequestMetricsRecorder\n",
    )

    # Composition wiring. disaggregation_mode field stays on TM (not removed).
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
            "            disaggregation_mode=self.disaggregation_mode,\n"
            "        )\n"
            "\n"
            "        # Request log manager\n"
            "        self.request_log_manager = RequestLogManager.from_server_args(\n"
        ),
    )

    # Drop the metrics-construction block from init_metric_collector_watchdog
    # (now lives in RequestMetricsRecorder.__post_init__).
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

    # Convert _request_has_grammar + collect_metrics to @staticmethod with
    # self: "RequestMetricsRecorder" typing; body stays byte-equivalent.
    text = _replace_method_header(text, "TokenizerManager", "_request_has_grammar", NEW_HAS_GRAMMAR_HEADER)
    text = _replace_method_header(text, "TokenizerManager", "collect_metrics", NEW_COLLECT_HEADER)

    # Caller rewrites.
    text = replace_call_site(
        text,
        old="                self.collect_metrics(state, recv_obj, i)\n",
        new="                TokenizerManager.collect_metrics(\n"
            "                    self.request_metrics_recorder, state, recv_obj, i\n"
            "                )\n",
    )
    text = replace_call_site(
        text,
        old=(
            "            self.metrics_collector.observe_one_aborted_request(\n"
            "                self.metrics_collector.labels\n"
            "            )\n"
        ),
        new=(
            "            self.request_metrics_recorder.metrics_collector.observe_one_aborted_request(\n"
            "                self.request_metrics_recorder.metrics_collector.labels\n"
            "            )\n"
        ),
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
