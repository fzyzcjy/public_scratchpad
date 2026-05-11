#!/usr/bin/env python3
"""Migrate ``SchedulerDPAttnMixin`` to a sister-class composition form
``SchedulerDPAttnAdapter`` at ``scheduler_components/dp_attn_adapter.py``.
The class ctor takes narrow typed kwargs (no ``scheduler_ref`` per CLAUDE.md
ch4); the original file is deleted.

Module-level dataclass + 2 free functions (``MLPSyncBatchInfo``,
``_update_gather_batch``, ``prepare_mlp_sync_batch_raw``) are preserved
verbatim in the new file.

5 callsites updated: ``scheduler.py`` (2) + ``scheduler_pp_mixin.py`` (1) +
``disaggregation/prefill.py`` (1) + ``disaggregation/decode.py`` (1). Method
names / signatures preserved (no renames, no privacy flips).

Usage:
    uv run --python 3.12 migrate-dp-attn-mixin.py run
    uv run --python 3.12 migrate-dp-attn-mixin.py verify
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

ID = "migrate-dp-attn-mixin"
SUBJECT = "Migrate SchedulerDPAttnMixin to SchedulerDPAttnAdapter (composition)"
BODY = """\
Move ``SchedulerDPAttnMixin`` (3 methods + dataclass + 2 module-level free
functions) from ``scheduler_dp_attn_mixin.py`` to a new
``SchedulerDPAttnAdapter`` class at
``scheduler_components/dp_attn_adapter.py``. The class is no
longer a mixin: Scheduler holds it as ``self.dp_attn_adapter`` (composition).
The ctor takes narrow typed kwargs (no ``scheduler_ref`` back-reference per
CLAUDE.md ch4).

Module-level ``MLPSyncBatchInfo`` dataclass + ``_update_gather_batch`` +
``prepare_mlp_sync_batch_raw`` are copied verbatim. The original file is
deleted.

5 callsites updated: ``scheduler.py`` (2) + ``scheduler_pp_mixin.py`` (1) +
``disaggregation/prefill.py`` (1) + ``disaggregation/decode.py`` (1). Method
names + signatures preserved (no renames, no privacy flips).

No behavior change.
"""
AREA = "mech_scheduler"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


# Class skeleton inserted in place of the original ``class SchedulerDPAttnMixin:``
NEW_CLASS_HEADER = """\
class SchedulerDPAttnAdapter:
    \"\"\"DP-attention batch synchronization adapter. Composition target on
    Scheduler (``self.dp_attn_adapter``). Owns no mutable state.\"\"\"

    def __init__(
        self,
        *,
        tp_group,
        req_to_token_pool,
        token_to_kv_pool_allocator,
        tree_cache,
        offload_tags,
        ps,
        server_args,
        model_config,
        enable_overlap: bool,
        spec_algorithm,
        require_mlp_sync: bool,
    ) -> None:
        self.tp_group = tp_group
        self.req_to_token_pool = req_to_token_pool
        self.token_to_kv_pool_allocator = token_to_kv_pool_allocator
        self.tree_cache = tree_cache
        self.offload_tags = offload_tags
        self.ps = ps
        self.server_args = server_args
        self.model_config = model_config
        self.enable_overlap = enable_overlap
        self.spec_algorithm = spec_algorithm
        self.require_mlp_sync = require_mlp_sync

"""


# Construction snippet for Scheduler.__init__ (insert before is_initializing).
SCHEDULER_INIT_INSERT = """\
        self.dp_attn_adapter = SchedulerDPAttnAdapter(
            tp_group=self.tp_group,
            req_to_token_pool=self.req_to_token_pool,
            token_to_kv_pool_allocator=self.token_to_kv_pool_allocator,
            tree_cache=self.tree_cache,
            offload_tags=self.offload_tags,
            ps=self.ps,
            server_args=self.server_args,
            model_config=self.model_config,
            enable_overlap=self.enable_overlap,
            spec_algorithm=self.spec_algorithm,
            require_mlp_sync=self.require_mlp_sync,
        )

"""


def transform(wt: Path) -> None:
    src = wt / "python/sglang/srt/managers/scheduler_dp_attn_mixin.py"
    sched = wt / "python/sglang/srt/managers/scheduler.py"
    pp = wt / "python/sglang/srt/managers/scheduler_pp_mixin.py"
    prefill = wt / "python/sglang/srt/disaggregation/prefill.py"
    decode = wt / "python/sglang/srt/disaggregation/decode.py"
    test_chunked = wt / "test/registered/unit/managers/test_scheduler_chunked_req_gate.py"
    pkg_init = wt / "python/sglang/srt/managers/scheduler_components/__init__.py"
    target = wt / "python/sglang/srt/managers/scheduler_components/dp_attn_adapter.py"

    pkg_init.parent.mkdir(parents=True, exist_ok=True)
    pkg_init.write_text("")

    # Read original file content.
    text = src.read_text()

    # Replace class header (and __init__-less mixin form) with new class skeleton.
    if "class SchedulerDPAttnMixin:\n" not in text:
        raise RuntimeError("DPAttn class header anchor mismatch")
    text = text.replace("class SchedulerDPAttnMixin:\n", NEW_CLASS_HEADER)

    # Method bodies: drop ``self: Scheduler`` annotations + rewrite self.X reads.
    # Reads:
    #   self.server_args.X    → self.server_args.X (kwarg field — no change)
    #   self.ps.X             → self.ps.X (kwarg field — no change)
    #   self.tp_group         → self.tp_group (kwarg field — no change)
    #   self.get_idle_batch   → self.get_idle_batch (method on same class — no change)
    #   self.offload_tags     → self.offload_tags (kwarg field — no change)
    #   self.require_mlp_sync → self.require_mlp_sync (kwarg field — no change)
    #   self.req_to_token_pool / token_to_kv_pool_allocator / tree_cache /
    #     model_config / enable_overlap / spec_algorithm — all kwarg fields
    #
    # Only edit needed: drop ``self: Scheduler`` annotation since the methods are
    # no longer mixed into Scheduler. Replace each per method.
    text = text.replace(
        "    def prepare_mlp_sync_batch(self: Scheduler, local_batch: ScheduleBatch):",
        "    def prepare_mlp_sync_batch(self, local_batch: ScheduleBatch):",
    )
    text = text.replace(
        "    def maybe_prepare_mlp_sync_batch(\n        self: Scheduler,",
        "    def maybe_prepare_mlp_sync_batch(\n        self,",
    )
    text = text.replace(
        "    def get_idle_batch(self: Scheduler) -> ScheduleBatch:",
        "    def get_idle_batch(self) -> ScheduleBatch:",
    )

    # Drop the ``Scheduler`` import inside TYPE_CHECKING — no longer used.
    text = text.replace(
        "    from sglang.srt.managers.scheduler import Scheduler\n",
        "",
    )

    # Write the new file at the new location, delete the source.
    target.write_text(text)
    src.unlink()

    # Update Scheduler: import + remove from inheritance + add ctor + skip is_init line.
    text = sched.read_text()
    text = text.replace(
        "from sglang.srt.managers.scheduler_dp_attn_mixin import SchedulerDPAttnMixin\n",
        "",
    )
    text = insert_after(
        text,
        anchor="from sglang.srt.managers.scheduler_components.request_receiver import (\n    SchedulerRequestReceiver,\n)\n",
        addition=(
            "from sglang.srt.managers.scheduler_components.dp_attn_adapter import (\n"
            "    SchedulerDPAttnAdapter,\n"
            ")\n"
        ),
    )
    # Remove from inheritance list (the ``    SchedulerDPAttnMixin,\n`` entry).
    text = replace_call_site(
        text,
        old="    SchedulerDPAttnMixin,\n",
        new="",
    )
    # Insert ctor instantiation just before ``self.is_initializing = False``.
    text = replace_call_site(
        text,
        old="        self.is_initializing = False\n",
        new=SCHEDULER_INIT_INSERT + "        self.is_initializing = False\n",
    )
    # 2 callsite rewrites in scheduler.py.
    text = text.replace(
        "            new_batch = self.maybe_prepare_mlp_sync_batch(new_batch)\n",
        "            new_batch = self.dp_attn_adapter.maybe_prepare_mlp_sync_batch(new_batch)\n",
    )
    text = text.replace(
        "        ret = self.maybe_prepare_mlp_sync_batch(ret, need_sync=need_mlp_sync)\n",
        "        ret = self.dp_attn_adapter.maybe_prepare_mlp_sync_batch(ret, need_sync=need_mlp_sync)\n",
    )
    sched.write_text(text)

    # Callsites in pp_mixin / disagg.
    pp_text = pp.read_text()
    pp_text = pp_text.replace(
        "                batch = self.maybe_prepare_mlp_sync_batch(batch)\n",
        "                batch = self.dp_attn_adapter.maybe_prepare_mlp_sync_batch(batch)\n",
    )
    pp.write_text(pp_text)

    pre_text = prefill.read_text()
    pre_text = pre_text.replace(
        "        batch = self.maybe_prepare_mlp_sync_batch(batch)\n",
        "        batch = self.dp_attn_adapter.maybe_prepare_mlp_sync_batch(batch)\n",
    )
    prefill.write_text(pre_text)

    dec_text = decode.read_text()
    dec_text = dec_text.replace(
        "        ret = self.maybe_prepare_mlp_sync_batch(ret)\n",
        "        ret = self.dp_attn_adapter.maybe_prepare_mlp_sync_batch(ret)\n",
    )
    decode.write_text(dec_text)

    # Test fixture: previously mocked ``s.maybe_prepare_mlp_sync_batch`` directly;
    # now the callsite is ``s.dp_attn_adapter.maybe_prepare_mlp_sync_batch``.
    test_text = test_chunked.read_text()
    test_text = test_text.replace(
        "    s.maybe_prepare_mlp_sync_batch = MagicMock(side_effect=lambda batch, **_: batch)\n",
        "    s.dp_attn_adapter = MagicMock()\n"
        "    s.dp_attn_adapter.maybe_prepare_mlp_sync_batch = MagicMock(side_effect=lambda batch, **_: batch)\n",
    )
    test_chunked.write_text(test_text)


if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        area_branch=AREA_BRANCH,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
