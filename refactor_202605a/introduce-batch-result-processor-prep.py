#!/usr/bin/env python3
"""Inplace prep for ``introduce-batch-result-processor``: create empty
``SchedulerBatchResultProcessor`` class skeleton, instantiate on Scheduler,
convert the remaining 11 process/collect methods on
``SchedulerOutputProcessorMixin`` to ``@staticmethod`` with
``self: "SchedulerBatchResultProcessor"`` type annotation, rewrite
callers, apply 3 privacy flips, and route metrics_reporter calls + mutator
writes through Callable callbacks.

PRAGMATIC DEVIATION: The 6 Callable callbacks (``abort_request``,
``report_prefill_stats``, ``report_decode_stats``, ``update_spec_metrics``,
``increment_generated_tokens``, ``advance_forward_ct_decode``) and the
corresponding body substitutions
(``self.num_generated_tokens +=`` → ``self.increment_generated_tokens(...)``,
``self.forward_ct_decode = (...) % (1 << 30)`` →
``self.advance_forward_ct_decode()``, and undoing C14's
``self.metrics_reporter.X(`` → ``self.X(`` substitution) are strictly
fancy reshape per ``MECH_COMMIT_SPLIT.md``. They are bundled here so the
moved bodies stay byte-identical for the upcoming -move step.
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

ID = "introduce-batch-result-processor-prep"
SUBJECT = "Carve out SchedulerBatchResultProcessor for batch-result state"
BODY = """\
Inplace prep for the ``introduce-batch-result-processor`` mech move (the
last extract from ``SchedulerOutputProcessorMixin``).

- Create ``scheduler_components/batch_result_processor.py`` with an empty
  ``SchedulerBatchResultProcessor`` class. Ctor takes the configs,
  collaborators, sisters (``logprob_computer``, ``output_streamer``) and
  Callable callbacks (``abort_request``, ``report_prefill_stats``,
  ``report_decode_stats``, ``update_spec_metrics``,
  ``increment_generated_tokens``, ``advance_forward_ct_decode``).
- Instantiate ``self.batch_result_processor = SchedulerBatchResultProcessor(...)``
  in ``Scheduler.__init__`` immediately after the ``output_streamer`` ctor.
  Callbacks wrapped in lambdas so they resolve ``self.metrics_reporter``
  lazily.
- In ``SchedulerOutputProcessorMixin``, convert the remaining
  process/collect methods to ``@staticmethod`` with
  ``self: "SchedulerBatchResultProcessor"`` type annotation. Drop
  ``: Scheduler`` annotation.
- Privacy flips: ``maybe_collect_routed_experts`` /
  ``maybe_collect_indexer_topk`` / ``maybe_collect_customized_info`` add
  ``_`` (internal-only, called from ``process_batch_result_prefill``).
- Body substitutions for Callable routing:
  - Undo the metrics-reporter ``self.metrics_reporter.report_prefill_stats(`` /
    ``report_decode_stats`` / ``update_spec_metrics`` rewrites (now plain
    Callables on the processor).
  - ``self.num_generated_tokens += <expr>`` →
    ``self.increment_generated_tokens(<expr>)`` (regex closure).
  - ``self.forward_ct_decode = (self.forward_ct_decode + 1) % (1 << 30)``
    → ``self.advance_forward_ct_decode()``.
- Callsite rewrites: ``process_batch_result_{prefill,decode,idle,prebuilt}``
  callers in scheduler.py + scheduler_pp_mixin.py +
  disaggregation/{prefill,decode}.py + dllm/mixin/scheduler.py rewritten
  to ``self.<m>(self.batch_result_processor, ...)``.

PRAGMATIC DEVIATION (per ``MECH_COMMIT_SPLIT.md``): the Callable ctor
kwargs + their body substitutions + the mutator rewrites are fancy
reshape and should live in a follow-up nonmech commit. We bundle them
here to keep the chain buildable and the moved bodies byte-identical
across the ``-move`` step.

The converted methods stay inside the mixin in this commit; physical
cut + paste to ``SchedulerBatchResultProcessor`` body (and deletion of
the mixin file) happens in ``introduce-batch-result-processor-move``.
"""
AREA = "mech_scheduler"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


# Note: the 11 method names are discovered dynamically — by the time
# this prep runs, the mixin contains exactly the methods left after
# C15+C16's prep+move. We list them explicitly to match the original
# single-shot script and avoid AST drift.
METHODS = [
    # Source order, residual mixin contents after C15+C16 processed.
    "process_batch_result_prebuilt",
    "maybe_collect_routed_experts",
    "maybe_collect_indexer_topk",
    "maybe_collect_customized_info",
    "process_batch_result_prefill",
    "_resolve_spec_overlap_tokens",
    "process_batch_result_idle",
    "process_batch_result_decode",
    "_handle_finished_req",
    "_maybe_update_reasoning_tokens",
    "_mamba_prefix_cache_update",
]


TARGET_FILE_HEADER = '''\
from __future__ import annotations  # noqa: F401

import logging  # noqa: F401
from dataclasses import dataclass
from typing import Any, TYPE_CHECKING, List, Union  # noqa: F401

import torch  # noqa: F401

from sglang.srt.disaggregation.utils import DisaggregationMode  # noqa: F401
from sglang.srt.environ import envs  # noqa: F401
from sglang.srt.layers.logits_processor import LogitsProcessorOutput  # noqa: F401
from sglang.srt.managers.io_struct import AbortReq  # noqa: F401
from sglang.srt.managers.schedule_batch import Req, ScheduleBatch  # noqa: F401
from sglang.srt.mem_cache.common import maybe_cache_unfinished_req, release_kv_cache  # noqa: F401
from sglang.srt.server_args import get_global_server_args  # noqa: F401
from sglang.srt.state_capturer.indexer_topk import get_global_indexer_capturer  # noqa: F401
from sglang.srt.state_capturer.routed_experts import get_global_experts_capturer  # noqa: F401

if TYPE_CHECKING:
    from sglang.srt.managers.scheduler import (  # noqa: F401
        EmbeddingBatchResult,
        GenerationBatchResult,
    )

logger = logging.getLogger(__name__)


@dataclass(kw_only=True, slots=True, frozen=True)
class SchedulerBatchResultProcessor:
    is_generation: bool
    disaggregation_mode: Any
    enable_overlap: bool
    enable_overlap_mlx: bool
    server_args: Any
    model_config: Any
    token_to_kv_pool_allocator: Any
    tree_cache: Any
    hisparse_coordinator: Any
    req_to_token_pool: Any
    decode_offload_manager: Any
    metrics_collector: Any
    draft_worker: Any
    model_worker: Any
    logprob_result_processor: Any
    output_streamer: Any
    abort_request: Any
    report_prefill_stats: Any
    report_decode_stats: Any
    update_spec_metrics: Any
    increment_generated_tokens: Any
    advance_forward_ct_decode: Any
'''


SCHEDULER_INIT_INSERT = """\
        self.batch_result_processor = SchedulerBatchResultProcessor(
            is_generation=self.is_generation,
            disaggregation_mode=self.disaggregation_mode,
            enable_overlap=self.enable_overlap,
            enable_overlap_mlx=self.enable_overlap_mlx,
            server_args=self.server_args,
            model_config=self.model_config,
            token_to_kv_pool_allocator=self.token_to_kv_pool_allocator,
            tree_cache=self.tree_cache,
            hisparse_coordinator=self.hisparse_coordinator,
            req_to_token_pool=self.req_to_token_pool,
            decode_offload_manager=self.decode_offload_manager,
            metrics_collector=self.metrics_collector,
            draft_worker=self.draft_worker,
            model_worker=self.model_worker,
            logprob_result_processor=SchedulerLogprobResultProcessor(
                server_args=self.server_args, model_config=self.model_config
            ),
            output_streamer=self.output_streamer,
            abort_request=self.abort_request,
            report_prefill_stats=lambda *a, **k: self.metrics_reporter.report_prefill_stats(*a, **k),
            report_decode_stats=lambda *a, **k: self.metrics_reporter.report_decode_stats(*a, **k),
            update_spec_metrics=lambda *a, **k: self.metrics_reporter.update_spec_metrics(*a, **k),
            increment_generated_tokens=lambda n: setattr(
                self.metrics_reporter,
                "num_generated_tokens",
                self.metrics_reporter.num_generated_tokens + n,
            ),
            advance_forward_ct_decode=lambda: setattr(
                self.metrics_reporter,
                "forward_ct_decode",
                (self.metrics_reporter.forward_ct_decode + 1) % (1 << 30),
            ),
        )

"""


def transform(wt: Path) -> None:
    sched = wt / "python/sglang/srt/managers/scheduler.py"
    mixin = wt / "python/sglang/srt/managers/scheduler_output_processor_mixin.py"
    target = wt / "python/sglang/srt/managers/scheduler_components/batch_result_processor.py"

    # 1. Create skeleton target file.
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(TARGET_FILE_HEADER)

    # 2. Convert 11 methods on the mixin to @staticmethod with type-flip.
    text = mixin.read_text()

    for name in METHODS:
        s, e = find_method_lines(
            text,
            class_name="SchedulerOutputProcessorMixin",
            method_name=name,
        )
        lines = text.splitlines(keepends=True)
        method_text = "".join(lines[s:e])

        single_line_sig = f"    def {name}(self: Scheduler, "
        single_line_no_args = f"    def {name}(self: Scheduler)"
        multi_line_sig = f"    def {name}(\n        self: Scheduler,"

        if single_line_sig in method_text:
            new_method = method_text.replace(
                single_line_sig,
                f"    @staticmethod\n    def {name}(self: \"SchedulerBatchResultProcessor\", ",
                1,
            )
        elif single_line_no_args in method_text:
            new_method = method_text.replace(
                single_line_no_args,
                f"    @staticmethod\n    def {name}(self: \"SchedulerBatchResultProcessor\")",
                1,
            )
        elif multi_line_sig in method_text:
            new_method = method_text.replace(
                multi_line_sig,
                f"    @staticmethod\n    def {name}(\n        self: \"SchedulerBatchResultProcessor\",",
                1,
            )
        else:
            raise RuntimeError(
                f"signature shape for {name} unrecognized; sample: {method_text[:200]!r}"
            )

        text = "".join(lines[:s]) + new_method + "".join(lines[e:])

    # 3. Privacy flips on definitions + intra-mixin internal callsites.
    text = text.replace(
        "    def maybe_collect_routed_experts(",
        "    def _maybe_collect_routed_experts(",
    )
    text = text.replace(
        "    def maybe_collect_indexer_topk(",
        "    def _maybe_collect_indexer_topk(",
    )
    text = text.replace(
        "    def maybe_collect_customized_info(",
        "    def _maybe_collect_customized_info(",
    )
    text = text.replace(
        "self.maybe_collect_routed_experts(",
        "self._maybe_collect_routed_experts(",
    )
    text = text.replace(
        "self.maybe_collect_indexer_topk(",
        "self._maybe_collect_indexer_topk(",
    )
    text = text.replace(
        "self.maybe_collect_customized_info(",
        "self._maybe_collect_customized_info(",
    )

    # 4. Mutator rewrites:
    #    - ``self.num_generated_tokens += <expr>`` →
    #      ``self.increment_generated_tokens(<expr>)``
    text = text.replace(
        "self.num_generated_tokens += ",
        "self.increment_generated_tokens(",
    )
    # Close out the parens at end-of-line — the original is
    # ``self.num_generated_tokens += <expr>\n`` (no parens) so we wrap.
    import re
    text = re.sub(
        r"self\.increment_generated_tokens\(([^\n]+)\n",
        r"self.increment_generated_tokens(\1)\n",
        text,
    )
    #    - ``self.forward_ct_decode = (self.forward_ct_decode + 1) % (1 << 30)``
    #      → ``self.advance_forward_ct_decode()``
    text = text.replace(
        "self.forward_ct_decode = (self.forward_ct_decode + 1) % (1 << 30)",
        "self.advance_forward_ct_decode()",
    )
    # Undo C14's ``self.metrics_reporter.X(`` rewrites (now plain Callables).
    text = text.replace(
        "self.metrics_reporter.report_prefill_stats(",
        "self.report_prefill_stats(",
    )
    text = text.replace(
        "self.metrics_reporter.report_decode_stats(",
        "self.report_decode_stats(",
    )
    text = text.replace(
        "self.metrics_reporter.update_spec_metrics(",
        "self.update_spec_metrics(",
    )

    # Drop ctor flag fields → read via ``self.server_args.X``. All
    # occurrences of ``self.enable_hisparse`` / ``self.enable_metrics`` in
    # this mixin live inside the 11 methods being moved (verified at base
    # of mech_preflight; no other methods on the mixin reference them), so
    # a plain text.replace is scope-safe here.
    text = text.replace(
        "self.enable_hisparse", "self.server_args.enable_hisparse"
    )
    text = text.replace(
        "self.enable_metrics", "self.server_args.enable_metrics"
    )

    # 5. Caller form: ``self.<m>(self.batch_result_processor, <rest>)`` for
    #    the 4 dispatch entry points. These callers live in scheduler.py,
    #    scheduler_pp_mixin.py, disaggregation/prefill.py,
    #    disaggregation/decode.py, dllm/mixin/scheduler.py. The mixin body
    #    itself also calls ``process_batch_result_*`` cross-method.
    # Add TYPE_CHECKING import for the new TargetClass so the
    # ``self: "SchedulerBatchResultProcessor"`` annotation resolves under pyflakes.
    if "from sglang.srt.managers.scheduler_components.batch_result_processor import SchedulerBatchResultProcessor" not in text:
        text = text.replace(
            "if TYPE_CHECKING:\n",
            "if TYPE_CHECKING:\n"
            "    from sglang.srt.managers.scheduler_components.batch_result_processor import SchedulerBatchResultProcessor\n",
            1,
        )
    mixin.write_text(text)

    # 6. Scheduler: add import + ctor.
    text = sched.read_text()
    text = insert_after(
        text,
        anchor="from sglang.srt.managers.scheduler_components.output_streamer import (\n    SchedulerOutputStreamer,\n)\n",
        addition=(
            "from sglang.srt.managers.scheduler_components.batch_result_processor import (\n"
            "    SchedulerBatchResultProcessor,\n"
            ")\n"
        ),
    )
    # Insert ctor AFTER the output_streamer ctor block. Anchor on its
    # closing paren + blank line.
    import re as _re
    match_pat = _re.compile(
        r"(        self\.output_streamer = SchedulerOutputStreamer\(\n"
        r"(?:.*\n)+?"
        r"        \)\n\n)",
    )
    m = match_pat.search(text)
    if m is None:
        raise RuntimeError("output_streamer ctor block not found in scheduler.py")
    text = text[: m.end()] + SCHEDULER_INIT_INSERT + text[m.end():]

    # 7. Nesting: drop the standalone ``self.logprob_result_processor =
    #    SchedulerLogprobResultProcessor(...)`` field on Scheduler (C15 added
    #    it as a sister). It now lives inside ``batch_result_processor`` —
    #    constructed inline by SCHEDULER_INIT_INSERT above. Callers reach it
    #    via ``self.batch_result_processor.logprob_result_processor``.
    text = _re.sub(
        r"        self\.logprob_result_processor = SchedulerLogprobResultProcessor\(\n"
        r"(?:.*\n)+?"
        r"        \)\n\n",
        "",
        text,
        count=1,
    )
    sched.write_text(text)

    # 8. Disagg-prefill mixin caller fix-up: a couple of call sites read
    #    ``self.logprob_result_processor`` directly (where ``self`` is
    #    Scheduler via mixin). After nesting, route via batch_result_processor.
    prefill = wt / "python/sglang/srt/disaggregation/prefill.py"
    if prefill.exists():
        ptext = prefill.read_text()
        ptext = ptext.replace(
            "self.logprob_result_processor",
            "self.batch_result_processor.logprob_result_processor",
        )
        prefill.write_text(ptext)

    # 7. Caller rewrites: ``self.process_batch_result_*(`` → form
    #    ``self.process_batch_result_*(self.batch_result_processor, ...)``.
    callers = [
        sched,
        mixin,
        wt / "python/sglang/srt/managers/scheduler_pp_mixin.py",
        wt / "python/sglang/srt/disaggregation/prefill.py",
        wt / "python/sglang/srt/disaggregation/decode.py",
        wt / "python/sglang/srt/dllm/mixin/scheduler.py",
    ]
    for f in callers:
        ftext = f.read_text()
        for suffix in ["prefill", "decode", "idle", "prebuilt"]:
            ftext = ftext.replace(
                f"self.process_batch_result_{suffix}(",
                f"self.process_batch_result_{suffix}(self.batch_result_processor, ",
            )
        # ``process_batch_result`` (top-level dispatch, no _suffix) STAYS in
        # Scheduler as a regular (self, batch, result) method — it routes to
        # ``self.batch_result_processor.process_batch_result_<suffix>``
        # internally. Do NOT rewrite its callers.
        f.write_text(ftext)


if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        area_branch=AREA_BRANCH,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
