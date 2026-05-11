#!/usr/bin/env python3
"""1:N split #3 of ``SchedulerOutputProcessorMixin``: the remaining 11
process / collect methods move to ``SchedulerBatchResultProcessor`` at
``scheduler_components/batch_result_processor.py``. The
output_processor mixin file is then deleted.

Ctor narrow kwargs: 8 configs + 7 collaborators + 2 sisters
(``logprob_computer``, ``output_streamer``) + 6 Callable callbacks.

3 privacy flips: ``maybe_collect_routed_experts`` /
``maybe_collect_indexer_topk`` / ``maybe_collect_customized_info`` add ``_``.

Callsite updates: 4 ``self.process_batch_result_*`` callers (in scheduler.py
+ scheduler_pp_mixin.py + disaggregation/{prefill,decode}.py +
dllm/mixin/scheduler.py).
"""

# /// script
# requires-python = ">=3.10"
# dependencies = ["typer"]
# ///

import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from _helpers import insert_after, replace_call_site
from _runner import run_pr

ID = "introduce-batch-result-processor"
SUBJECT = "Introduce SchedulerBatchResultProcessor (split #3 of output_processor mixin); delete output_processor mixin file"
BODY = """\
Pull the remaining 11 process/collect methods out of
``SchedulerOutputProcessorMixin`` into ``SchedulerBatchResultProcessor`` at
``scheduler_components/batch_result_processor.py``. Scheduler holds
it as ``self.batch_result_processor``. The output_processor mixin file is
deleted.

Ctor narrow kwargs (per CLAUDE.md ch4): 8 configs (is_generation,
disaggregation_mode, enable_hisparse, enable_metrics, enable_overlap,
enable_overlap_mlx, server_args, model_config) + 7 collaborators
(token_to_kv_pool_allocator, tree_cache, hisparse_coordinator,
req_to_token_pool, decode_offload_manager, metrics_collector, draft_worker)
+ 2 sisters (logprob_computer, output_streamer) + 6 Callable callbacks
(abort_request, report_prefill_stats, report_decode_stats,
update_spec_metrics, increment_generated_tokens, advance_forward_ct_decode).

3 privacy flips: ``maybe_collect_routed_experts`` /
``maybe_collect_indexer_topk`` / ``maybe_collect_customized_info`` add ``_``
(internal-only, called from process_batch_result_prefill).

Callsite updates: 4 ``self.process_batch_result_*`` external callers in
``scheduler.py`` (process_batch_result), ``scheduler_pp_mixin.py``,
``disaggregation/prefill.py``, ``disaggregation/decode.py``,
``dllm/mixin/scheduler.py``. The mixin file is unlinked at end of
transform.

No method renames; no other privacy flips. body byte-identical apart from
``: Scheduler`` annotation drops + sister cross-call substitutions
introduced by C15/C16.
"""
AREA = "mech_scheduler"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


SCHEDULER_INIT_INSERT = """\
        self.batch_result_processor = SchedulerBatchResultProcessor(
            is_generation=self.is_generation,
            disaggregation_mode=self.disaggregation_mode,
            enable_hisparse=self.enable_hisparse,
            enable_metrics=self.enable_metrics,
            enable_overlap=self.enable_overlap,
            enable_overlap_mlx=getattr(self, "enable_overlap_mlx", False),
            server_args=self.server_args,
            model_config=self.model_config,
            token_to_kv_pool_allocator=self.token_to_kv_pool_allocator,
            tree_cache=self.tree_cache,
            hisparse_coordinator=self.hisparse_coordinator,
            req_to_token_pool=self.req_to_token_pool,
            decode_offload_manager=self.decode_offload_manager,
            metrics_collector=getattr(self, "metrics_collector", None),
            draft_worker=self.draft_worker,
            model_worker=self.model_worker,
            logprob_computer=self.logprob_computer,
            output_streamer=self.output_streamer,
            abort_request=self.abort_request,
            # Wrapped in lambdas so they resolve ``self.metrics_reporter``
            # lazily — depending on ctor insertion order this attribute may
            # not be set at the moment ``SchedulerBatchResultProcessor`` is
            # constructed (see also ``logprob_computer`` / ``output_streamer``
            # — those are sister kwargs that lambda-resolve their ``self.X``
            # the same way).
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


# We rewrite the whole remaining mixin file as the new class file rather than
# splice individual methods. After C15 + C16 the residual content is exactly
# the 11 process/collect methods + the import header. We:
#   - Replace the class header line with the new class header + ctor.
#   - Drop ``: Scheduler`` annotations.
#   - Apply 3 privacy flips (definitions + cross-method internal calls).
#   - Substitute ``self.X(...)`` Scheduler-method calls (abort_request /
#     report_prefill_stats / report_decode_stats / update_spec_metrics) with
#     ``self.X(...)`` (Callable on manager — same syntax).
#   - Substitute ``self.num_generated_tokens += n`` /
#     ``self.forward_ct_decode = (... + 1) % (1<<30)`` with the Callable
#     mutator forms ``self.increment_generated_tokens(n)`` /
#     ``self.advance_forward_ct_decode()``.
#   - Drop the now-empty mixin file.
NEW_CLASS_HEADER = '''\
class SchedulerBatchResultProcessor:
    """``Scheduler.process_batch_result`` hot-path main body. Composition
    target on Scheduler (``self.batch_result_processor``)."""

    def __init__(
        self,
        *,
        is_generation: bool,
        disaggregation_mode,
        enable_hisparse: bool,
        enable_metrics: bool,
        enable_overlap: bool,
        enable_overlap_mlx: bool,
        server_args,
        model_config,
        token_to_kv_pool_allocator,
        tree_cache,
        hisparse_coordinator,
        req_to_token_pool,
        decode_offload_manager,
        metrics_collector,
        draft_worker,
        model_worker,
        logprob_computer,
        output_streamer,
        abort_request,
        report_prefill_stats,
        report_decode_stats,
        update_spec_metrics,
        increment_generated_tokens,
        advance_forward_ct_decode,
    ) -> None:
        self.is_generation = is_generation
        self.disaggregation_mode = disaggregation_mode
        self.enable_hisparse = enable_hisparse
        self.enable_metrics = enable_metrics
        self.enable_overlap = enable_overlap
        self.enable_overlap_mlx = enable_overlap_mlx
        self.server_args = server_args
        self.model_config = model_config
        self.token_to_kv_pool_allocator = token_to_kv_pool_allocator
        self.tree_cache = tree_cache
        self.hisparse_coordinator = hisparse_coordinator
        self.req_to_token_pool = req_to_token_pool
        self.decode_offload_manager = decode_offload_manager
        self.metrics_collector = metrics_collector
        self.draft_worker = draft_worker
        self.model_worker = model_worker
        self.logprob_computer = logprob_computer
        self.output_streamer = output_streamer
        self.abort_request = abort_request
        self.report_prefill_stats = report_prefill_stats
        self.report_decode_stats = report_decode_stats
        self.update_spec_metrics = update_spec_metrics
        self.increment_generated_tokens = increment_generated_tokens
        self.advance_forward_ct_decode = advance_forward_ct_decode

'''


def transform(wt: Path) -> None:
    src = wt / "python/sglang/srt/managers/scheduler_output_processor_mixin.py"
    sched = wt / "python/sglang/srt/managers/scheduler.py"
    pp = wt / "python/sglang/srt/managers/scheduler_pp_mixin.py"
    pre = wt / "python/sglang/srt/disaggregation/prefill.py"
    dec = wt / "python/sglang/srt/disaggregation/decode.py"
    dllm = wt / "python/sglang/srt/dllm/mixin/scheduler.py"
    target = wt / "python/sglang/srt/managers/scheduler_components/batch_result_processor.py"

    src_text = src.read_text()

    # Drop ``: Scheduler`` annotations.
    src_text = src_text.replace("self: Scheduler", "self")

    # Drop ``if TYPE_CHECKING: from ... Scheduler`` block.
    src_text = src_text.replace(
        "if TYPE_CHECKING:\n    from sglang.srt.managers.scheduler import Scheduler\n\n",
        "",
    )
    # Keep ``TYPE_CHECKING`` in the typing import — the ``if TYPE_CHECKING:``
    # block still has Req / GenerationBatchResult etc. used as type hints.

    # Replace class header.
    src_text = src_text.replace(
        "class SchedulerOutputProcessorMixin:\n", NEW_CLASS_HEADER
    )

    # Privacy flips.
    src_text = src_text.replace(
        "    def maybe_collect_routed_experts(",
        "    def _maybe_collect_routed_experts(",
    )
    src_text = src_text.replace(
        "    def maybe_collect_indexer_topk(",
        "    def _maybe_collect_indexer_topk(",
    )
    src_text = src_text.replace(
        "    def maybe_collect_customized_info(",
        "    def _maybe_collect_customized_info(",
    )
    src_text = src_text.replace(
        "self.maybe_collect_routed_experts(",
        "self._maybe_collect_routed_experts(",
    )
    src_text = src_text.replace(
        "self.maybe_collect_indexer_topk(",
        "self._maybe_collect_indexer_topk(",
    )
    src_text = src_text.replace(
        "self.maybe_collect_customized_info(",
        "self._maybe_collect_customized_info(",
    )

    # Replace mutator-style writes that originally targeted Scheduler counters.
    src_text = src_text.replace(
        "self.num_generated_tokens += ",
        "self.increment_generated_tokens(",
    )
    # The above doesn't include the closing ``)`` since the original code is
    # ``self.num_generated_tokens += <expr>`` (no parens). We need to convert
    # ``self.increment_generated_tokens(<expr>`` lines to balance with ``)``.
    # Use a regex via a Python step. Simpler: manually patch typical lines.
    # The original mixin has 1-2 such writes:
    #   ``self.num_generated_tokens += len(...)``  ->  ``self.increment_generated_tokens(len(...))``
    # The ``+= ...`` part has no trailing newline before potential expressions
    # so we need to wrap up to end-of-line. Use a regex:
    import re

    src_text = re.sub(
        r"self\.increment_generated_tokens\(([^\n]+)\n",
        r"self.increment_generated_tokens(\1)\n",
        src_text,
    )

    # forward_ct_decode advance:
    #   ``self.forward_ct_decode = (self.forward_ct_decode + 1) % (1 << 30)``  ->
    #   ``self.advance_forward_ct_decode()``
    src_text = src_text.replace(
        "self.forward_ct_decode = (self.forward_ct_decode + 1) % (1 << 30)",
        "self.advance_forward_ct_decode()",
    )

    # C14 rewrote ``self.report_*_stats(...)`` / ``self.update_spec_metrics(...)``
    # in the output_processor mixin body to ``self.metrics_reporter.<X>(...)``.
    # In the new processor class those names are stashed Callables, so undo the
    # ``self.metrics_reporter.`` prefix.
    src_text = src_text.replace(
        "self.metrics_reporter.report_prefill_stats(", "self.report_prefill_stats("
    )
    src_text = src_text.replace(
        "self.metrics_reporter.report_decode_stats(", "self.report_decode_stats("
    )
    src_text = src_text.replace(
        "self.metrics_reporter.update_spec_metrics(", "self.update_spec_metrics("
    )

    target.write_text(src_text)
    src.unlink()

    # Update Scheduler: import + ctor + 1 callsite (process_batch_result dispatch).
    text = sched.read_text()
    text = text.replace(
        "from sglang.srt.managers.scheduler_output_processor_mixin import (\n"
        "    SchedulerOutputProcessorMixin,\n"
        ")\n",
        "",
    )
    text = insert_after(
        text,
        anchor="from sglang.srt.managers.scheduler_components.output_streamer import (\n    SchedulerOutputStreamer,\n)\n",
        addition=(
            "from sglang.srt.managers.scheduler_components.batch_result_processor import (\n"
            "    SchedulerBatchResultProcessor,\n"
            ")\n"
        ),
    )
    text = replace_call_site(text, old="    SchedulerOutputProcessorMixin,\n", new="")
    # Insert ctor AFTER ``output_streamer`` (sister) — so logprob_computer +
    # output_streamer are both fully constructed by the time we hit
    # ``self.batch_result_processor = ...``. Anchor on a unique token from
    # the output_streamer ctor: the `load_inquirer_get_loads=lambda` kwarg.
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
    # Hot-path callsites: ``self.process_batch_result_*(`` → ``self.batch_result_processor.process_batch_result_*(``
    for suffix in ["prefill", "decode", "idle", "prebuilt"]:
        text = text.replace(
            f"self.process_batch_result_{suffix}(",
            f"self.batch_result_processor.process_batch_result_{suffix}(",
        )
    sched.write_text(text)

    # Update remaining external callers (pp_mixin / disagg / dllm).
    for f in [pp, pre, dec, dllm]:
        text = f.read_text()
        for suffix in ["prefill", "decode", "idle", "prebuilt"]:
            text = text.replace(
                f"self.process_batch_result_{suffix}(",
                f"self.batch_result_processor.process_batch_result_{suffix}(",
            )
        f.write_text(text)


if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        area_branch=AREA_BRANCH,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
