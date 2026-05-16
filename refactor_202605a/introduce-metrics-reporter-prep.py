#!/usr/bin/env python3
"""Inplace prep for ``introduce-metrics-reporter``: build the
``SchedulerMetricsReporter`` class skeleton **at the target path**
(``managers/scheduler_components/metrics_reporter.py``) with a slim
back-reference ctor (5 fields), instantiate on ``Scheduler``, type-flip
the 15 mixin methods to ``@staticmethod`` with
``self: "SchedulerMetricsReporter"``, rewrite body reads of Scheduler
fields to ``self.scheduler.X`` (preserving reporter-owned fields),
qualify internal sibling calls as
``SchedulerMetricsMixin.<sibling>(self, ...)``, and rewrite Scheduler /
mixin / disagg / dllm callers into the static-bound sister form
``self.<method>(self.metrics_reporter, ...)``.

After this commit:

  * ``managers/scheduler_components/metrics_reporter.py`` exists with
    the class skeleton (header imports + slim ctor).
  * ``observability/scheduler_metrics_mixin.py`` still hosts
    ``PrefillStats``, module constants, and the 15 methods (now all
    ``@staticmethod`` typed for the new class, with body reads of
    Scheduler fields routed through ``self.scheduler.X``).
  * Scheduler owns ``self.metrics_reporter`` and routes hot-path callers
    through it via ``self.<method>(self.metrics_reporter, ...)`` —
    exactly the form pool-stats-observer-prep / load-inquirer-prep use.

The upcoming ``-move`` commit is then a true byte-equal cut + paste:
cut the 15 method bodies + PrefillStats + module constants from the
mixin, paste them into the target class / module, strip
``@staticmethod`` + typeflip + sibling-call qualifier, drop the mixin
file, rewrite 3 external import paths, and collapse caller form
``self.foo(self.metrics_reporter, ...)`` → ``self.metrics_reporter.foo(...)``.
"""

# /// script
# requires-python = ">=3.10"
# dependencies = ["typer"]
# ///

import ast
import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from _helpers import find_method_lines, insert_after, replace_call_site
from _runner import run_pr

ID = "introduce-metrics-reporter-prep"
SUBJECT = "Stage metrics reporting + PrefillStats for handoff to SchedulerMetricsReporter"
BODY = """\
Inplace prep for the ``introduce-metrics-reporter`` mech move.

- Create ``managers/scheduler_components/metrics_reporter.py`` with an
  empty ``SchedulerMetricsReporter`` class skeleton (slim ctor only;
  methods land in the upcoming ``-move`` commit). The ctor takes a
  ``scheduler: "Scheduler"`` back-reference plus ``tp_rank`` /
  ``pp_rank`` / ``dp_rank`` / ``metrics_collector``.
- ``__post_init__`` runs the original ``init_metrics`` body via
  ``SchedulerMetricsMixin.init_metrics(self, tp_rank, pp_rank, dp_rank)``
  qualified call (and ``install_device_timer_on_runners`` likewise) —
  the methods still live on the mixin file during prep, and the
  qualified prefix collapses to ``self.init_metrics(...)`` in the move
  commit once the bodies are pasted onto the reporter class itself.
- Instantiate ``self.metrics_reporter = SchedulerMetricsReporter(...)``
  in ``Scheduler.__init__`` after ``self.kv_events_publisher``.
- Replace ``self.init_metrics(tp_rank, pp_rank, dp_rank)`` in
  ``Scheduler.__init__`` with the early-inline block that computes
  ``enable_metrics`` / ``is_stats_logging_rank`` /
  ``current_scheduler_metrics_enabled`` / ``enable_kv_cache_events``
  and builds the ``metrics_collector`` (option b ownership — kept on
  Scheduler at construction time because ``init_model_worker`` reads
  it before the reporter exists; the reporter then receives the same
  instance as a ctor kwarg). Drop the now-redundant
  ``self.install_device_timer_on_runners()`` call (subsumed by the
  reporter ctor).
- Ownership migration: drop ``self.num_retracted_reqs: int = 0`` and
  ``self.num_paused_reqs: int = 0`` from ``Scheduler`` (now reporter-
  owned); the single external writer in ``Scheduler.run_batch``
  rewires to ``self.metrics_reporter.num_retracted_reqs = ...``.
- In ``SchedulerMetricsMixin`` (still at the old path), convert all
  15 methods to ``@staticmethod`` with ``self: "SchedulerMetricsReporter"``
  typed first param. Body reads of Scheduler fields rewrite to
  ``self.scheduler.X`` form (driven by an AST-based reporter-owned
  whitelist; sibling method calls stay as ``self.<m>(...)`` and are
  separately qualified to ``SchedulerMetricsMixin.<m>(self, ...)``).
- Hot-path Scheduler / mixin / disagg / dllm callers rewrite from
  ``self.foo(args)`` → ``self.foo(self.metrics_reporter, args)`` —
  the static-bound sister form. In ``-move`` this collapses to
  ``self.metrics_reporter.foo(args)`` once the methods are on the
  reporter class itself.
- Spec lifetime counters / ``last_gen_throughput`` / ``step_time_dict``
  Scheduler accessors route through ``self.metrics_reporter.X`` (option
  b ownership), and the load-inquirer ctor's lambdas for
  ``get_spec_total_num_accept_tokens`` / ``get_spec_total_num_forward_ct``
  switch to ``self.metrics_reporter.spec_total_num_*``.
- ``metrics_collector`` post-init call sites route through
  ``self.metrics_reporter.metrics_collector.X(...)``. The early
  ``emit_constants`` callsite inside ``init_model_worker`` and kwarg
  passes that hand off the field object are intentionally left alone.

The 15 methods + ``PrefillStats`` + module constants stay inside the
mixin file in this commit; physical cut + paste to the target class /
module and ``SchedulerMetricsMixin`` retirement happen in
``introduce-metrics-reporter-move``.
"""
AREA = "mech_scheduler"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


TARGET_FILE_HEADER = '''\
from __future__ import annotations  # noqa: F401

import logging  # noqa: F401
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Optional  # noqa: F401

from sglang.srt.disaggregation.utils import DisaggregationMode  # noqa: F401
from sglang.srt.observability.scheduler_metrics_mixin import (  # noqa: F401
    SchedulerMetricsMixin,
)

if TYPE_CHECKING:
    from sglang.srt.managers.scheduler import Scheduler  # noqa: F401


logger = logging.getLogger(__name__)


'''


NEW_CLASS_SKELETON = '''\
@dataclass(kw_only=True)
class SchedulerMetricsReporter:
    """Prometheus / Stats hot-path. Composition target on Scheduler
    (``self.metrics_reporter``)."""

    scheduler: "Scheduler"
    tp_rank: int
    pp_rank: int
    dp_rank: Optional[int]
    metrics_collector: Any

    def __post_init__(self) -> None:
        self.num_retracted_reqs: int = 0
        self.num_paused_reqs: int = 0
        SchedulerMetricsMixin.init_metrics(self, self.tp_rank, self.pp_rank, self.dp_rank)
        SchedulerMetricsMixin.install_device_timer_on_runners(self)
'''


SCHEDULER_INIT_INSERT = """\
        self.metrics_reporter = SchedulerMetricsReporter(
            scheduler=self,
            tp_rank=tp_rank,
            pp_rank=pp_rank,
            dp_rank=dp_rank,
            metrics_collector=self.metrics_collector,
        )
        self.stats = self.metrics_reporter.stats

"""


INLINE_CURRENT_METRICS_ENABLED = (
    "        self.enable_metrics = self.server_args.enable_metrics\n"
    "        self.is_stats_logging_rank = self.ps.attn_tp_rank == 0\n"
    "        self.current_scheduler_metrics_enabled = self.enable_metrics and (\n"
    "            self.is_stats_logging_rank\n"
    "            or self.server_args.enable_metrics_for_all_schedulers\n"
    "        )\n"
    "        self.enable_kv_cache_events = bool(\n"
    "            self.server_args.kv_events_config\n"
    "            and self.ps.attn_tp_rank == 0\n"
    "            and self.ps.attn_cp_rank == 0\n"
    "        )\n"
    "        self.metrics_collector = None\n"
    "        if self.enable_metrics:\n"
    "            _engine_type = DisaggregationMode.to_engine_type(\n"
    "                self.server_args.disaggregation_mode\n"
    "            )\n"
    "            _labels = {\n"
    "                'model_name': self.server_args.served_model_name,\n"
    "                'engine_type': _engine_type,\n"
    "                'tp_rank': tp_rank,\n"
    "                'pp_rank': pp_rank,\n"
    "                'moe_ep_rank': self.ps.moe_ep_rank,\n"
    "            }\n"
    "            if self.enable_priority_scheduling:\n"
    "                _labels['priority'] = ''\n"
    "            if dp_rank is not None:\n"
    "                _labels['dp_rank'] = dp_rank\n"
    "            if self.server_args.extra_metric_labels:\n"
    "                _labels.update(self.server_args.extra_metric_labels)\n"
    "            self.metrics_collector = SchedulerMetricsCollector(\n"
    "                labels=_labels,\n"
    "                enable_lora=self.enable_lora,\n"
    "                enable_hierarchical_cache=self.enable_hierarchical_cache,\n"
    "                enable_streaming_session=self.server_args.enable_streaming_session,\n"
    "                server_args=self.server_args,\n"
    "            )\n"
)


# Methods to type-flip (15 total: 14 normal + init_metrics which is invoked
# by ctor via SchedulerMetricsMixin.init_metrics(self, ...)).
METHODS_TO_FLIP = [
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
    # FPM (forward-pass-metrics) family added on the preflight branch — move
    # along with the rest of metrics state to the reporter.
    "_init_fpm",
    "_shutdown_fpm",
    "_emit_forward_pass_metrics",
    "_build_scheduled_request_metrics",
    "_build_queued_request_metrics",
]


# Sibling calls inside method bodies: ``self.<sibling>(...)`` →
# ``SchedulerMetricsMixin.<sibling>(self, ...)``. The set is derived from a
# grep of internal cross-method calls (see plan note).
SIBLING_CALLS = [
    "_init_estimated_perf_constants",
    "_estimate_prefill_perf",
    "_estimate_decode_perf",
    "_log_hicache_stats",
    "_update_lora_metrics",
    "_calculate_utilization",
    # FPM sibling calls (called from init_metrics / _emit_forward_pass_metrics
    # / _shutdown_fpm body).
    "_init_fpm",
    "_build_scheduled_request_metrics",
    "_build_queued_request_metrics",
]


# Reporter-owned attributes (NOT rewritten to ``self.scheduler.X`` in the
# body-rewrite pass). Comprises:
#   * The 5 ctor kwargs (``scheduler`` / ``tp_rank`` / ``pp_rank`` /
#     ``dp_rank`` / ``metrics_collector``).
#   * The 2 ownership-migrated counters (``num_retracted_reqs`` /
#     ``num_paused_reqs``) set in ``__post_init__``.
#   * Every ``self.X = ...`` assignment inside ``init_metrics`` / the other
#     14 typeflipped methods (gathered by inspecting the post-chain reporter
#     class — these are the fields the reporter genuinely owns).
#   * The 15 method names themselves (so ``self.<method>(...)`` calls stay
#     as instance method calls and are separately qualified by
#     ``_qualify_sibling_calls`` rather than getting rewritten to
#     ``self.scheduler.<method>(...)``).
REPORTER_OWNED_ATTRS = frozenset({
    # Ctor kwargs
    "scheduler",
    "tp_rank",
    "pp_rank",
    "dp_rank",
    "metrics_collector",
    # __post_init__ counters
    "num_retracted_reqs",
    "num_paused_reqs",
    # init_metrics-assigned state
    "forward_ct_decode",
    "num_generated_tokens",
    "last_decode_stats_tic",
    "last_prefill_stats_tic",
    "last_gen_throughput",
    "last_input_throughput",
    "step_time_dict",
    "stats",
    "_graph_backend_label",
    "spec_num_accept_tokens",
    "spec_num_forward_ct",
    "spec_total_num_accept_tokens",
    "spec_total_num_forward_ct",
    "kv_transfer_speed_gb_s",
    "kv_transfer_latency_ms",
    "enable_metrics",
    "is_stats_logging_rank",
    "current_scheduler_metrics_enabled",
    "enable_mfu_metrics",
    "fwd_occupancy",
    "forward_pass_device_timer",
    "scheduler_status_logger",
    # _init_estimated_perf_constants-assigned state
    "_linear_flops_per_token",
    "_attn_dot_flops_coeff",
    "_kv_cache_bytes_per_token",
    "_weight_read_bytes_per_token",
    "_qkv_act_bytes_per_token",
    "_ffn_act_bytes_per_token",
    "_prefill_attn_act_read_per_token",
    "_decode_q_read_bytes_per_token",
    # update_device_timer / reset_device_timer_window state
    "_device_timer_window_batch_count",
    "_device_timer_window_gpu_time",
    "_device_timer_window_start",
    "_mfu_log_flops",
    "_mfu_log_read_bytes",
    "_mfu_log_write_bytes",
    # FPM state lives on Scheduler (NOT reporter) — pre-existing tests call
    # ``Scheduler.<method>(mock_scheduler)`` with a stub that has no
    # ``metrics_reporter`` but checks ``self.enable_fpm`` directly. So the
    # AST rewriter SHOULD turn ``self.enable_fpm`` inside reporter methods
    # into ``self.scheduler.enable_fpm`` (i.e., NOT in the owned set).
} | set(METHODS_TO_FLIP))


def _rewrite_self_to_scheduler_back_ref(method_text: str) -> str:
    """AST-based body rewrite: every ``self.X`` read where ``X`` is NOT in
    ``REPORTER_OWNED_ATTRS`` becomes ``self.scheduler.X``. Also rewrites
    ``getattr(self, "X", default)`` → ``getattr(self.scheduler, "X", default)``
    when ``X`` is a Scheduler field.

    The method is parsed as a wrapper module (``def __wrapper__(): <method>``)
    so we always have a valid parse. Replacements are applied bottom-up by
    source position to avoid invalidating later offsets.
    """
    # Wrap so the method body parses as a module.
    wrapped = "class _W:\n" + method_text
    tree = ast.parse(wrapped)
    # Collect (start_offset, end_offset, new_text) replacements.
    replacements: list[tuple[int, int, str]] = []

    # Convert (lineno, col_offset) → byte offset within ``wrapped``.
    lines = wrapped.splitlines(keepends=True)
    line_starts = [0]
    for ln in lines:
        line_starts.append(line_starts[-1] + len(ln))

    def pos(lineno: int, col_offset: int) -> int:
        return line_starts[lineno - 1] + col_offset

    for node in ast.walk(tree):
        # Case 1: ``self.X`` (an ast.Attribute whose value is ast.Name('self'))
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "self"
            and node.attr not in REPORTER_OWNED_ATTRS
        ):
            # node spans from value.col_offset through node.end_col_offset, but
            # we only want to replace the ``self`` part with ``self.scheduler``.
            s = pos(node.value.lineno, node.value.col_offset)
            e = s + len("self")
            # Skip if the text doesn't literally say "self" (defensive).
            if wrapped[s:e] == "self":
                replacements.append((s, e, "self.scheduler"))

        # Case 2: ``getattr(self, "X", ...)`` where the X string is in the
        # call's second positional arg. The first positional arg is
        # ast.Name('self'); we want to replace that with ``self.scheduler``.
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "getattr"
            and len(node.args) >= 2
            and isinstance(node.args[0], ast.Name)
            and node.args[0].id == "self"
            and isinstance(node.args[1], ast.Constant)
            and isinstance(node.args[1].value, str)
            and node.args[1].value not in REPORTER_OWNED_ATTRS
        ):
            name_node = node.args[0]
            s = pos(name_node.lineno, name_node.col_offset)
            e = s + len("self")
            if wrapped[s:e] == "self":
                replacements.append((s, e, "self.scheduler"))

    # Apply bottom-up so earlier offsets stay valid.
    replacements.sort(key=lambda r: r[0], reverse=True)
    out = wrapped
    for s, e, new in replacements:
        out = out[:s] + new + out[e:]

    # Safety net: AST positions for nodes inside f-strings (FormattedValue
    # subtrees) are unreliable on Python <3.12, causing some self.X reads
    # to be skipped. Apply a regex pass over the rewritten text to catch
    # any remaining self.X references (excluding method calls and owned
    # attrs). Already-rewritten self.scheduler.X is skipped because the
    # leading "self" in that pattern is followed by ".scheduler", and
    # REPORTER_OWNED_ATTRS contains "scheduler".
    def _regex_repl(m: "re.Match") -> str:
        attr = m.group(1)
        if attr in REPORTER_OWNED_ATTRS:
            return m.group(0)
        return f"self.scheduler.{attr}"

    out = re.sub(r"\bself\.(\w+)\b(?!\s*\()", _regex_repl, out)

    # Strip the ``class _W:\n`` wrapper prefix.
    assert out.startswith("class _W:\n")
    return out[len("class _W:\n"):]


def _qualify_sibling_calls(method_text: str) -> str:
    """Rewrite ``self.<sibling>(...)`` → ``SchedulerMetricsMixin.<sibling>(self, ...)``
    for each known intra-class sibling call. Tolerates the zero-arg form
    (``self.foo()`` → ``SchedulerMetricsMixin.foo(self)``)."""
    text = method_text
    for name in SIBLING_CALLS:
        # n-arg form: self.foo(a, b) → SchedulerMetricsMixin.foo(self, a, b)
        text = re.sub(
            rf"self\.{re.escape(name)}\(\s*(?!\))",
            f"SchedulerMetricsMixin.{name}(self, ",
            text,
        )
        # Zero-arg form: self.foo() → SchedulerMetricsMixin.foo(self)
        text = re.sub(
            rf"self\.{re.escape(name)}\(\s*\)",
            f"SchedulerMetricsMixin.{name}(self)",
            text,
        )
    return text


def _typeflip_method(text: str, *, method_name: str) -> str:
    """Type-flip a SchedulerMetricsMixin method to @staticmethod with
    ``self: "SchedulerMetricsReporter"``. Then run the back-reference
    body-rewrite and qualify sibling calls."""
    s, e = find_method_lines(
        text, class_name="SchedulerMetricsMixin", method_name=method_name
    )
    lines = text.splitlines(keepends=True)
    method_text = "".join(lines[s:e])
    # Replace the existing ``self: Scheduler`` annotation with
    # ``self: "SchedulerMetricsReporter"`` and prepend the decorator.
    new_method = method_text.replace("self: Scheduler", 'self: "SchedulerMetricsReporter"')
    # Prepend @staticmethod decorator.
    if not new_method.lstrip().startswith("@staticmethod"):
        new_method = "    @staticmethod\n" + new_method
    # Body rewrite: self.X (X = Scheduler field) → self.scheduler.X.
    new_method = _rewrite_self_to_scheduler_back_ref(new_method)
    # Qualify sibling calls (after back-ref rewrite; the sibling names are
    # in REPORTER_OWNED_ATTRS so the back-ref pass leaves them as
    # ``self.<sibling>(...)``, then this pass turns them into
    # ``SchedulerMetricsMixin.<sibling>(self, ...)``).
    new_method = _qualify_sibling_calls(new_method)
    return "".join(lines[:s]) + new_method + "".join(lines[e:])


def transform(wt: Path) -> None:
    src = wt / "python/sglang/srt/observability/scheduler_metrics_mixin.py"
    sched = wt / "python/sglang/srt/managers/scheduler.py"
    output_mixin = wt / "python/sglang/srt/managers/scheduler_output_processor_mixin.py"
    prefill = wt / "python/sglang/srt/disaggregation/prefill.py"
    dllm = wt / "python/sglang/srt/dllm/mixin/scheduler.py"
    target = wt / "python/sglang/srt/managers/scheduler_components/metrics_reporter.py"

    # 1. Create new target file at the final destination path with skeleton.
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(TARGET_FILE_HEADER + NEW_CLASS_SKELETON)

    # 2. PRE-typeflip: strip the duplicate ``SchedulerMetricsCollector``
    # construction from ``init_metrics`` BEFORE the body-rewrite pass, so the
    # anchor matches the unrewritten ``self.X`` form. Scheduler.__init__ now
    # builds + owns the collector (option b) and forwards it via the reporter
    # ctor kwarg; if init_metrics also constructs, the second
    # SchedulerMetricsCollector(...) re-registers Prometheus metrics and
    # crashes with ``Duplicated timeseries``.
    text = src.read_text()
    text = replace_call_site(
        text,
        old=(
            "        if self.enable_metrics:\n"
            "            engine_type = DisaggregationMode.to_engine_type(\n"
            "                self.server_args.disaggregation_mode\n"
            "            )\n"
            "\n"
            "            labels = {\n"
            "                \"model_name\": self.server_args.served_model_name,\n"
            "                \"engine_type\": engine_type,\n"
            "                \"tp_rank\": tp_rank,\n"
            "                \"pp_rank\": pp_rank,\n"
            "                \"moe_ep_rank\": self.ps.moe_ep_rank,\n"
            "            }\n"
            "            if self.enable_priority_scheduling:\n"
            "                labels[\"priority\"] = \"\"\n"
            "            if dp_rank is not None:\n"
            "                labels[\"dp_rank\"] = dp_rank\n"
            "            if self.server_args.extra_metric_labels:\n"
            "                labels.update(self.server_args.extra_metric_labels)\n"
            "            self.metrics_collector = SchedulerMetricsCollector(\n"
            "                labels=labels,\n"
            "                enable_lora=self.enable_lora,\n"
            "                enable_hierarchical_cache=self.enable_hierarchical_cache,\n"
            "                enable_streaming_session=self.server_args.enable_streaming_session,\n"
            "                server_args=self.server_args,\n"
            "            )\n"
            "            self.enable_mfu_metrics = self.server_args.enable_mfu_metrics\n"
        ),
        new=(
            "        if self.enable_metrics:\n"
            "            self.enable_mfu_metrics = self.server_args.enable_mfu_metrics\n"
        ),
    )
    # SchedulerMetricsCollector is no longer used in the mixin (the construction
    # block above was the only usage). Drop just that name from the grouped
    # import (other names in the same block are still used).
    text = replace_call_site(
        text,
        old="    SchedulerMetricsCollector,\n",
        new="",
    )

    # 3. Type-flip each of the 15 methods to @staticmethod with
    #    self: "SchedulerMetricsReporter" AND apply the back-reference body
    #    rewrite. Iterate bottom-up so earlier line ranges are not invalidated
    #    by later edits.
    tree = ast.parse(text)
    method_lineno = {}
    for cls in ast.walk(tree):
        if isinstance(cls, ast.ClassDef) and cls.name == "SchedulerMetricsMixin":
            for node in cls.body:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    method_lineno[node.name] = node.lineno
            break
    ordered = sorted(METHODS_TO_FLIP, key=lambda m: method_lineno.get(m, 0), reverse=True)
    for name in ordered:
        text = _typeflip_method(text, method_name=name)
    src.write_text(text)

    # 4. Scheduler: import + ctor instantiation + early-fields block +
    #    drop num_retracted/num_paused init + caller rewrites.
    text = sched.read_text()
    # Add the SchedulerMetricsReporter + SchedulerMetricsCollector imports
    # alongside the existing scheduler_components imports.
    text = insert_after(
        text,
        anchor="from sglang.srt.managers.scheduler_components.load_inquirer import (\n    SchedulerLoadInquirer,\n)\n",
        addition=(
            "from sglang.srt.managers.scheduler_components.metrics_reporter import (\n"
            "    SchedulerMetricsReporter,\n"
            ")\n"
            "from sglang.srt.observability.metrics_collector import SchedulerMetricsCollector\n"
        ),
    )
    # Replace init_metrics call with the inline early-fields block.
    text = replace_call_site(
        text,
        old="        self.init_metrics(tp_rank, pp_rank, dp_rank)\n",
        new=INLINE_CURRENT_METRICS_ENABLED,
    )
    # Insert reporter ctor BEFORE ``self.is_initializing = False`` (stable anchor).
    text = replace_call_site(
        text,
        old="        self.is_initializing = False\n",
        new=SCHEDULER_INIT_INSERT + "        self.is_initializing = False\n",
    )
    # Drop owned counter init lines (now reporter-owned).
    text = replace_call_site(text, old="        self.num_retracted_reqs: int = 0\n", new="")
    text = replace_call_site(text, old="        self.num_paused_reqs: int = 0\n", new="")
    # Drop the separate install_device_timer_on_runners call (now run from
    # reporter ctor).
    text = replace_call_site(
        text,
        old="        self.install_device_timer_on_runners()\n",
        new="",
    )
    # Load-inquirer ctor lambdas: route spec accumulator getters through
    # the reporter (ownership migration).
    text = replace_call_site(
        text,
        old="            get_spec_total_num_accept_tokens=lambda: self.spec_total_num_accept_tokens,\n"
        "            get_spec_total_num_forward_ct=lambda: self.spec_total_num_forward_ct,\n",
        new="            get_spec_total_num_accept_tokens=lambda: self.metrics_reporter.spec_total_num_accept_tokens,\n"
        "            get_spec_total_num_forward_ct=lambda: self.metrics_reporter.spec_total_num_forward_ct,\n",
    )
    # Hot-path callsites — static-bound sister form (pool-stats-observer pattern).
    text = replace_call_site(
        text,
        old="        self.log_batch_result_stats(batch, result)\n",
        new="        self.log_batch_result_stats(self.metrics_reporter, batch, result)\n",
    )
    text = replace_call_site(
        text,
        old="        self.update_device_timer()\n",
        new="        self.update_device_timer(self.metrics_reporter)\n",
    )
    text = replace_call_site(
        text,
        old="            self.reset_metrics()\n",
        new="            self.reset_metrics(self.metrics_reporter)\n",
    )
    text = replace_call_site(
        text,
        old="        self.reset_device_timer_window()\n",
        new="        self.reset_device_timer_window(self.metrics_reporter)\n",
    )
    # FPM hot-path: method calls go via static-bound sister form (collapsed
    # in move); field reads stay direct on Scheduler (fields live on
    # Scheduler, not reporter — see REPORTER_OWNED_ATTRS rationale above).
    text = replace_call_site(
        text,
        old="        if self.enable_fpm:\n            self._emit_forward_pass_metrics(batch, result)\n",
        new="        if self.enable_fpm:\n            self._emit_forward_pass_metrics(self.metrics_reporter, batch, result)\n",
    )
    text = replace_call_site(
        text,
        old="            scheduler._shutdown_fpm()\n",
        new="            scheduler.metrics_reporter._shutdown_fpm()\n",
    )
    # Spec lifetime counters now reporter-owned (post-init reads from Scheduler).
    text = replace_call_site(
        text, old="self.spec_total_num_accept_tokens",
        new="self.metrics_reporter.spec_total_num_accept_tokens",
    )
    text = replace_call_site(
        text, old="self.spec_total_num_forward_ct",
        new="self.metrics_reporter.spec_total_num_forward_ct",
    )
    text = replace_call_site(
        text, old='ret["last_gen_throughput"] = self.last_gen_throughput',
        new='ret["last_gen_throughput"] = self.metrics_reporter.last_gen_throughput',
    )
    text = replace_call_site(
        text, old='ret["step_time_dict"] = self.step_time_dict',
        new='ret["step_time_dict"] = self.metrics_reporter.step_time_dict',
    )
    text = replace_call_site(
        text,
        old="            self.num_retracted_reqs = len(retracted_reqs)\n",
        new="            self.metrics_reporter.num_retracted_reqs = len(retracted_reqs)\n",
    )
    # Route post-init metrics_collector method calls through the reporter
    # (option b ownership). The early emit_constants callsite inside
    # init_model_worker and kwarg passes are intentionally left alone.
    text = replace_call_site(
        text,
        old="                self.metrics_collector.increment_retracted_reqs(\n",
        new="                self.metrics_reporter.metrics_collector.increment_retracted_reqs(\n",
    )
    # NOTE: ``_maybe_log_idle_metrics`` body reads (``self.metrics_collector.
    # last_log_time`` / ``self.metrics_collector.log_stats(...)``) stay as
    # ``self.X`` — that method lives in ``SchedulerRuntimeCheckerMixin`` now
    # and moves to ``SchedulerMetricsReporter`` in the next commit, after
    # which ``self.metrics_collector`` resolves correctly on the reporter.
    sched.write_text(text)

    # 4.5 Test mock fix-up: ``test_scheduler_chunked_req_gate`` constructs
    #     a stub via ``Scheduler.__new__(Scheduler)`` and reads
    #     ``self.enable_fpm`` inside ``get_next_batch_to_run``. In preflight
    #     this defaulted to ``False`` via class-level annotation on
    #     ``SchedulerMetricsMixin``; once that mixin retires in C14-move
    #     the default vanishes — the test mock must set it explicitly.
    test_gate = wt / "test/registered/unit/managers/test_scheduler_chunked_req_gate.py"
    if test_gate.exists():
        ttext = test_gate.read_text()
        ttext = replace_call_site(
            ttext,
            old="    s.enable_hisparse = False\n",
            new="    s.enable_hisparse = False\n    s.enable_fpm = False\n",
        )
        test_gate.write_text(ttext)

    # 5. Output processor mixin callsites — static-bound sister form.
    text = output_mixin.read_text()
    text = re.sub(
        r"(        )self\.report_prefill_stats\(",
        r"\1self.report_prefill_stats(self.metrics_reporter, ",
        text,
    )
    text = re.sub(
        r"(            )self\.update_spec_metrics\(",
        r"\1self.update_spec_metrics(self.metrics_reporter, ",
        text,
    )
    text = re.sub(
        r"(        )self\.report_decode_stats\(",
        r"\1self.report_decode_stats(self.metrics_reporter, ",
        text,
    )
    output_mixin.write_text(text)

    # 6. Disaggregation prefill.
    text = prefill.read_text()
    text = re.sub(
        r"(        )self\.report_prefill_stats\(",
        r"\1self.report_prefill_stats(self.metrics_reporter, ",
        text,
    )
    prefill.write_text(text)

    # 7. dllm mixin.
    text = dllm.read_text()
    text = re.sub(
        r"(        )self\.report_prefill_stats\(",
        r"\1self.report_prefill_stats(self.metrics_reporter, ",
        text,
    )
    # num_generated_tokens moved from Scheduler (set by init_metrics) to
    # the reporter; redirect the dllm-mixin accumulator write.
    text = replace_call_site(
        text,
        old="self.num_generated_tokens += new_tokens\n",
        new="self.metrics_reporter.num_generated_tokens += new_tokens\n",
    )
    dllm.write_text(text)


if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        area_branch=AREA_BRANCH,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
