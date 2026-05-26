#!/usr/bin/env python3
"""Mechanically extract inline component constructions in ``Scheduler.__init__``
into per-component ``init_<name>()`` methods, matching the style in
``tokenizer_manager.py#L236-L276``.

Motivation: downstream forks should be able to ``override`` an individual
``init_<component>`` without copying the entire ``__init__``.

Each ``Op`` declares the exact inline block to replace in ``__init__``. The
script auto-generates:
  * the replacement at the call site = leading ``# ...`` comment lines (if
    any) + ``        self.init_<name>()``
  * the new method definition = ``    def init_<name>(self) -> None:`` +
    the inline block's body (comments stripped, indentation already at 8
    spaces from the original ``__init__`` body).

New methods are spliced into ``scheduler.py`` just before
``def init_req_max_new_tokens``, which sits at the tail of the existing
``init_*`` component-method cluster.

Usage:
    uv run --python 3.12 scheduler-init-style-extract.py run
    uv run --python 3.12 scheduler-init-style-extract.py dry-run

Out of scope for this script:
  * ops that need ``__init__`` formal parameters (``tp_rank`` / ``pp_rank`` /
    ``dp_rank`` / ``gpu_id`` / ``moe_*_rank``): ``init_parallel_state``,
    ``init_metrics_collector``, ``init_metrics_reporter``. Those need
    parameter plumbing decisions, do them by hand.
  * the ``init_kv_cache`` block already lives behind ``kv_cache_builder``;
    only the surrounding inline ``decode_offload_manager`` /
    ``maybe_register_hicache_draft`` calls remain inline — those touch
    enough conditional logic that hand-extraction is safer.
  * the early flag-assignment band at lines ~308-345.
"""

# /// script
# requires-python = ">=3.10"
# dependencies = ["typer"]
# ///

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

import typer

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from _helpers import replace_call_site  # noqa: E402

REPO = Path("/Users/tom/main/workspaces/ws-main/worktrees/sglang-dev-d")
SCHED_REL = "python/sglang/srt/managers/scheduler.py"

# All new methods are inserted immediately before this anchor (the first
# non-component init method, which sits at the end of the existing
# ``init_*`` cluster). Anchor is the full ``def`` line including signature
# so it stays unique even if other ``init_*`` methods get added later.
METHOD_INSERT_ANCHOR = "    def init_req_max_new_tokens(self, req):\n"


@dataclass(frozen=True)
class Op:
    """One inline-block → ``init_<name>`` extraction.

    ``anchor`` MUST be the exact substring in ``scheduler.py``,
    including any leading ``# ...`` comment lines and the trailing blank
    line (so replacement preserves vertical spacing).
    """

    name: str       # full method name, e.g. ``init_profiler``
    anchor: str     # exact text in __init__ to remove (incl. leading comment + trailing blank)


OPS: list[Op] = [
    Op(
        name="init_profiler",
        anchor="""\
        # Init profiler
        self.profiler_manager = SchedulerProfilerManager(
            ps=self.ps,
            dp_tp_cpu_group=self.dp_tp_cpu_group,
            get_forward_ct=lambda: self.forward_ct,
        )
""",
    ),
    Op(
        name="init_weight_updater",
        anchor="""\
        self.weight_updater = SchedulerWeightUpdaterManager(
            tp_worker=self.tp_worker,
            draft_worker=self.draft_worker,
            tp_cpu_group=self.tp_cpu_group,
            memory_saver_adapter=self.memory_saver_adapter,
            flush_cache=self.flush_cache,
            is_fully_idle=self.is_fully_idle,
        )
""",
    ),
    Op(
        name="init_lora_drainer",
        anchor="""\
        # Init LoRA drainer for fair scheduling
        if self.server_args.lora_drain_wait_threshold > 0.0:
            self.lora_drainer = LoRADrainer(
                server_args.max_loras_per_batch,
                server_args.lora_drain_wait_threshold,
            )
        else:
            self.lora_drainer = None
""",
    ),
    Op(
        name="init_lora_overlap_loader",
        anchor="""\
        # Init LoRA overlap loader
        if self.enable_lora_overlap_loading:
            self.lora_overlap_loader = LoRAOverlapLoader(
                self.tp_worker.model_runner.lora_manager
            )
""",
    ),
    Op(
        name="init_grammar_manager",
        anchor="""\
        # Init the grammar backend for constrained generation
        self.grammar_manager = GrammarManager(self)
""",
    ),
    Op(
        name="init_request_receiver",
        anchor="""\
        self.request_receiver = SchedulerRequestReceiver(
            recv_from_tokenizer=self.ipc_channels.recv_from_tokenizer,
            recv_from_rpc=self.ipc_channels.recv_from_rpc,
            recv_skipper=self.recv_skipper,
            input_blocker=self.input_blocker,
            mm_receiver=self.mm_receiver,
            ps=self.ps,
            tp_group=self.tp_group,
            tp_cpu_group=self.tp_cpu_group,
            attn_tp_group=self.attn_tp_group,
            attn_tp_cpu_group=self.attn_tp_cpu_group,
            attn_cp_group=self.attn_cp_group,
            attn_cp_cpu_group=self.attn_cp_cpu_group,
            world_group=self.world_group,
            server_args=self.server_args,
            model_config=self.model_config,
            max_recv_per_poll=self.max_recv_per_poll,
            stream_output=lambda *a, **kw: self.output_streamer.stream_output(*a, **kw),
            get_last_forward_mode=lambda: (
                self.last_batch.forward_mode if self.last_batch is not None else None
            ),
        )
""",
    ),
    Op(
        name="init_dp_attn_adapter",
        anchor="""\
        self.dp_attn_adapter = SchedulerDPAttnAdapter(
            tp_group=self.tp_group,
            req_to_token_pool=self.req_to_token_pool,
            token_to_kv_pool_allocator=self.token_to_kv_pool_allocator,
            tree_cache=self.tree_cache,
            offload_tags=self.weight_updater.offload_tags,
            ps=self.ps,
            server_args=self.server_args,
            model_config=self.model_config,
            enable_overlap=self.enable_overlap,
            spec_algorithm=self.spec_algorithm,
            get_require_mlp_sync=lambda: self.require_mlp_sync,
        )
""",
    ),
    Op(
        name="init_pool_stats_observer",
        anchor="""\
        self.pool_stats_observer = SchedulerPoolStatsObserver(
            tree_cache=self.tree_cache,
            token_to_kv_pool_allocator=self.token_to_kv_pool_allocator,
            req_to_token_pool=self.req_to_token_pool,
            session_controller=self.session_controller,
            hisparse_coordinator=self.hisparse_coordinator,
            is_hybrid_swa=self.is_hybrid_swa,
            is_hybrid_ssm=self.is_hybrid_ssm,
            enable_hisparse=self.enable_hisparse,
            full_tokens_per_layer=self.full_tokens_per_layer,
            swa_tokens_per_layer=self.swa_tokens_per_layer,
            max_total_num_tokens=self.max_total_num_tokens,
            get_last_batch=lambda: self.last_batch,
            get_running_batch=lambda: self.running_batch,
        )
""",
    ),
    Op(
        name="init_invariant_checker",
        anchor="""\
        self.invariant_checker = SchedulerInvariantChecker(
            is_hybrid_swa=self.is_hybrid_swa,
            is_hybrid_ssm=self.is_hybrid_ssm,
            disaggregation_mode=self.disaggregation_mode,
            page_size=self.page_size,
            full_tokens_per_layer=self.full_tokens_per_layer,
            swa_tokens_per_layer=self.swa_tokens_per_layer,
            max_total_num_tokens=self.max_total_num_tokens,
            server_args=self.server_args,
            tree_cache=self.tree_cache,
            token_to_kv_pool_allocator=self.token_to_kv_pool_allocator,
            req_to_token_pool=self.req_to_token_pool,
            pool_stats_observer=self.pool_stats_observer,
            get_last_batch=lambda: self.last_batch,
            get_running_batch=lambda: self.running_batch,
        )
""",
    ),
    Op(
        name="init_kv_events_publisher",
        anchor="""\
        self.kv_events_publisher = SchedulerKvEventsPublisher(
            kv_events_config=self.server_args.kv_events_config,
            ps=self.ps,
            attn_tp_rank=self.ps.attn_tp_rank,
            attn_cp_rank=self.ps.attn_cp_rank,
            attn_dp_rank=self.ps.attn_dp_rank,
            dp_rank=self.ps.dp_rank,
            tree_cache=self.tree_cache,
            send_metrics_from_scheduler=self.ipc_channels.send_metrics_from_scheduler,
            max_running_requests=self.max_running_requests,
            max_total_num_tokens=self.max_total_num_tokens,
            get_stats=lambda: self.metrics_reporter.stats,
        )
""",
    ),
    Op(
        name="init_load_inquirer",
        anchor="""\
        self.load_inquirer = SchedulerLoadInquirer(
            disaggregation_mode=self.disaggregation_mode,
            ps=self.ps,
            server_args=self.server_args,
            max_total_num_tokens=self.max_total_num_tokens,
            max_running_requests=self.max_running_requests,
            pool_stats_observer=self.pool_stats_observer,
            tp_worker=self.tp_worker,
            token_to_kv_pool_allocator=self.token_to_kv_pool_allocator,
            spec_algorithm=self.spec_algorithm,
            get_running_batch=lambda: self.running_batch,
            get_waiting_queue=lambda: self.waiting_queue,
            get_stats=lambda: self.metrics_reporter.stats,
            get_chunked_req=lambda: self.chunked_req,
            get_disagg_prefill_bootstrap_queue=lambda: self.disagg_prefill_bootstrap_queue,
            get_disagg_prefill_inflight_queue=lambda: self.disagg_prefill_inflight_queue,
            get_disagg_decode_prealloc_queue=lambda: self.disagg_decode_prealloc_queue,
            get_disagg_decode_transfer_queue=lambda: self.disagg_decode_transfer_queue,
            get_spec_total_num_accept_tokens=lambda: self.metrics_reporter.spec_total_num_accept_tokens,
            get_spec_total_num_forward_ct=lambda: self.metrics_reporter.spec_total_num_forward_ct,
        )
""",
    ),
    Op(
        name="init_output_streamer",
        anchor="""\
        self.output_streamer = SchedulerOutputStreamer(
            send_to_detokenizer=self.ipc_channels.send_to_detokenizer,
            tree_cache=self.tree_cache,
            ps=self.ps,
            server_args=self.server_args,
            is_generation=self.is_generation,
            spec_algorithm=self.spec_algorithm,
            disaggregation_mode=self.disaggregation_mode,
            enable_hicache_storage=lambda: self.enable_hicache_storage,
            load_inquirer_get_loads=lambda req: self.load_inquirer.get_loads(req),
        )
""",
    ),
    Op(
        name="init_batch_result_processor",
        anchor="""\
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
            metrics_reporter=self.metrics_reporter,
            draft_worker=self.draft_worker,
            model_worker=self.model_worker,
            logprob_result_processor=SchedulerLogprobResultProcessor(
                server_args=self.server_args, model_config=self.model_config
            ),
            output_streamer=self.output_streamer,
            abort_request=self.abort_request,
        )
""",
    ),
]


def _split_leading_comments(block: str) -> tuple[list[str], list[str]]:
    """Return (comment_lines, body_lines) — comment_lines are leading
    ``# ...`` lines (at the inline-block indent); body_lines are the rest.
    Blank lines mixed into the leading comment band go with the comments.
    """
    lines = block.splitlines(keepends=True)
    comment_lines: list[str] = []
    i = 0
    while i < len(lines):
        stripped = lines[i].lstrip()
        if stripped.startswith("#"):
            comment_lines.append(lines[i])
            i += 1
        else:
            break
    return comment_lines, lines[i:]


def make_caller(op: Op) -> str:
    """Replacement text for the inline block at the call site."""
    comments, _ = _split_leading_comments(op.anchor)
    return "".join(comments) + f"        self.{op.name}()\n"


def make_method(op: Op) -> str:
    """Full ``def init_<name>(self) -> None:`` text (4-space class indent).

    Includes one trailing blank line for vertical separation against the
    next method.
    """
    _, body_lines = _split_leading_comments(op.anchor)
    body = "".join(body_lines)
    if not body.endswith("\n"):
        body += "\n"
    return f"    def {op.name}(self) -> None:\n{body}\n"


def _check_anchor_unique(text: str, op: Op) -> None:
    count = text.count(op.anchor)
    if count != 1:
        raise SystemExit(
            f"[{op.name}] anchor must appear exactly once in scheduler.py "
            f"(got {count}). Re-read the file and update Op.anchor."
        )


def _check_method_does_not_exist(text: str, op: Op) -> None:
    sig = f"    def {op.name}(self)"
    if sig in text:
        raise SystemExit(
            f"[{op.name}] method already defined in scheduler.py; refusing "
            f"to splice a duplicate. Drop this Op from OPS or rename it."
        )


def transform(sched_path: Path) -> str:
    text = sched_path.read_text()

    for op in OPS:
        _check_anchor_unique(text, op)
        _check_method_does_not_exist(text, op)

    if METHOD_INSERT_ANCHOR not in text:
        raise SystemExit(
            f"METHOD_INSERT_ANCHOR not found verbatim in scheduler.py: "
            f"{METHOD_INSERT_ANCHOR!r}"
        )

    new_methods = "".join(make_method(op) for op in OPS)

    for op in OPS:
        text = replace_call_site(text, old=op.anchor, new=make_caller(op))

    text = replace_call_site(
        text,
        old=METHOD_INSERT_ANCHOR,
        new=new_methods + METHOD_INSERT_ANCHOR,
    )

    return text


app = typer.Typer(add_completion=False, no_args_is_help=True)


@app.command()
def run(
    repo: Annotated[
        Path,
        typer.Option(help="sglang worktree to transform"),
    ] = REPO,
) -> None:
    """Apply the transform in-place to ``<repo>/<scheduler.py>``."""
    sched = repo / SCHED_REL
    if not sched.exists():
        raise SystemExit(f"scheduler.py not found: {sched}")
    new_text = transform(sched)
    sched.write_text(new_text)
    print(f"OK rewrote {sched} ({len(OPS)} extractions)")


@app.command(name="dry-run")
def dry_run(
    repo: Annotated[
        Path,
        typer.Option(help="sglang worktree to validate against"),
    ] = REPO,
) -> None:
    """Compute the transform but write nothing; only diagnostics."""
    sched = repo / SCHED_REL
    if not sched.exists():
        raise SystemExit(f"scheduler.py not found: {sched}")
    new_text = transform(sched)
    delta = len(new_text) - len(sched.read_text())
    print(f"OK dry-run; {len(OPS)} extractions; size delta = {delta:+d} bytes")


@app.command(name="show-methods")
def show_methods() -> None:
    """Print the new ``init_<name>`` methods that would be appended."""
    for op in OPS:
        print(make_method(op), end="")


@app.command(name="show-callers")
def show_callers() -> None:
    """Print the call-site replacements for each Op."""
    for op in OPS:
        print(f"# --- {op.name} ---")
        print(make_caller(op), end="")
        print()


if __name__ == "__main__":
    app()
