#!/usr/bin/env python3
"""Inplace prep for ``migrate-dp-attn-mixin``: create the
``SchedulerDPAttnAdapter`` class skeleton at
``scheduler_components/dp_attn.py`` (ctor + fields only, no methods),
instantiate in Scheduler.__init__, convert the 3
``SchedulerDPAttnMixin`` methods to ``@staticmethod`` with
``self: "SchedulerDPAttnAdapter"`` type annotation, and rewrite the 5
callers to ``self.<method>(self.dp_attn_adapter, ...)``.

Method bodies byte-identical wrt the post-move state (modulo decorator +
the ``def foo(self: SchedulerDPAttnAdapter, ...)`` → ``def foo(self, ...)``
signature simplification in the move commit).
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

ID = "migrate-dp-attn-mixin-prep"
SUBJECT = "Introduce SchedulerDPAttnAdapter to own DP-attention state"
BODY = """\
Inplace prep for the ``migrate-dp-attn-mixin`` mech move.

- Create ``scheduler_components/dp_attn.py`` with an empty
  ``SchedulerDPAttnAdapter`` class (collaborator/config fields enumerated
  in the dataclass body below). No methods yet.
- Instantiate ``self.dp_attn_adapter = SchedulerDPAttnAdapter(...)`` in
  ``Scheduler.__init__`` just before ``self.is_initializing = False``.
- In ``scheduler_dp_attn_mixin.py``, convert the adapter methods
  (``prepare_mlp_sync_batch`` / ``maybe_prepare_mlp_sync_batch`` /
  ``get_idle_batch``) to ``@staticmethod`` with
  ``self: "SchedulerDPAttnAdapter"`` type annotation. Body bytes unchanged.
- Callers in scheduler.py, scheduler_pp_mixin.py, disaggregation/prefill.py,
  and disaggregation/decode.py are rewritten to
  ``self.<method>(self.dp_attn_adapter, ...)``.

The adapter methods stay inside ``SchedulerDPAttnMixin`` in this commit;
physical cut + paste to ``SchedulerDPAttnAdapter`` body happens in
``migrate-dp-attn-mixin-move``.
"""
AREA = "mech_scheduler"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


ADAPTER_HEADER = '''from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from sglang.srt.configs.model_config import ModelConfig
from sglang.srt.distributed.parallel_state_wrapper import ParallelState
from sglang.srt.mem_cache.allocator import BaseTokenToKVPoolAllocator
from sglang.srt.mem_cache.base_prefix_cache import BasePrefixCache
from sglang.srt.mem_cache.memory_pool import ReqToTokenPool
from sglang.srt.server_args import ServerArgs
from sglang.srt.speculative.spec_info import SpeculativeAlgorithm

if TYPE_CHECKING:
    from sglang.srt.distributed.parallel_state import GroupCoordinator


@dataclass(kw_only=True, slots=True, frozen=True)
class SchedulerDPAttnAdapter:
    tp_group: "GroupCoordinator"
    req_to_token_pool: ReqToTokenPool
    token_to_kv_pool_allocator: BaseTokenToKVPoolAllocator
    tree_cache: BasePrefixCache
    offload_tags: set[str]
    ps: ParallelState
    server_args: ServerArgs
    model_config: ModelConfig
    enable_overlap: bool
    spec_algorithm: SpeculativeAlgorithm
    require_mlp_sync: bool
'''


INIT_INSERT = '''        self.dp_attn_adapter = SchedulerDPAttnAdapter(
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

'''


def transform(wt: Path) -> None:
    mixin = wt / "python/sglang/srt/managers/scheduler_dp_attn_mixin.py"
    sched = wt / "python/sglang/srt/managers/scheduler.py"
    pp = wt / "python/sglang/srt/managers/scheduler_pp_mixin.py"
    prefill = wt / "python/sglang/srt/disaggregation/prefill.py"
    decode = wt / "python/sglang/srt/disaggregation/decode.py"
    pkg_init = wt / "python/sglang/srt/managers/scheduler_components/__init__.py"
    target = wt / "python/sglang/srt/managers/scheduler_components/dp_attn.py"

    # 1. Create new file with empty class skeleton.
    pkg_init.parent.mkdir(parents=True, exist_ok=True)
    if not pkg_init.exists():
        pkg_init.write_text("")
    target.write_text(ADAPTER_HEADER)

    # 2. In mixin file, convert 3 methods to @staticmethod inplace.
    text = mixin.read_text()

    # prepare_mlp_sync_batch — original signature:
    #   ``def prepare_mlp_sync_batch(self: Scheduler, local_batch: ScheduleBatch):``
    s, e = find_method_lines(
        text, class_name="SchedulerDPAttnMixin", method_name="prepare_mlp_sync_batch"
    )
    lines = text.splitlines(keepends=True)
    method_text = "".join(lines[s:e])
    if "    def prepare_mlp_sync_batch(self: Scheduler, " not in method_text:
        raise RuntimeError("prepare_mlp_sync_batch signature shape unexpected")
    new_method = method_text.replace(
        "    def prepare_mlp_sync_batch(self: Scheduler, ",
        '    @staticmethod\n    def prepare_mlp_sync_batch(self: "SchedulerDPAttnAdapter", ',
    )
    text = "".join(lines[:s]) + new_method + "".join(lines[e:])

    # maybe_prepare_mlp_sync_batch — original signature spans 2 lines:
    #   ``def maybe_prepare_mlp_sync_batch(\n        self: Scheduler,\n``
    s, e = find_method_lines(
        text, class_name="SchedulerDPAttnMixin", method_name="maybe_prepare_mlp_sync_batch"
    )
    lines = text.splitlines(keepends=True)
    method_text = "".join(lines[s:e])
    if "    def maybe_prepare_mlp_sync_batch(\n        self: Scheduler,\n" not in method_text:
        raise RuntimeError("maybe_prepare_mlp_sync_batch signature shape unexpected")
    new_method = method_text.replace(
        "    def maybe_prepare_mlp_sync_batch(\n        self: Scheduler,\n",
        '    @staticmethod\n    def maybe_prepare_mlp_sync_batch(\n        self: "SchedulerDPAttnAdapter",\n',
    )
    text = "".join(lines[:s]) + new_method + "".join(lines[e:])

    # get_idle_batch — original signature:
    #   ``def get_idle_batch(self: Scheduler) -> ScheduleBatch:``
    s, e = find_method_lines(
        text, class_name="SchedulerDPAttnMixin", method_name="get_idle_batch"
    )
    lines = text.splitlines(keepends=True)
    method_text = "".join(lines[s:e])
    if "    def get_idle_batch(self: Scheduler)" not in method_text:
        raise RuntimeError("get_idle_batch signature shape unexpected")
    new_method = method_text.replace(
        "    def get_idle_batch(self: Scheduler)",
        '    @staticmethod\n    def get_idle_batch(self: "SchedulerDPAttnAdapter")',
    )
    text = "".join(lines[:s]) + new_method + "".join(lines[e:])

    # Add TYPE_CHECKING import for the new TargetClass so the
    # ``self: "SchedulerDPAttnAdapter"`` annotation resolves under pyflakes.
    if "from sglang.srt.managers.scheduler_components.dp_attn import SchedulerDPAttnAdapter" not in text:
        text = text.replace(
            "if TYPE_CHECKING:\n",
            "if TYPE_CHECKING:\n"
            "    from sglang.srt.managers.scheduler_components.dp_attn import SchedulerDPAttnAdapter\n",
            1,
        )

    # Rewrite intra-mixin sibling staticmethod calls (otherwise ``self`` here
    # is a ``SchedulerDPAttnAdapter`` and the bound-method lookup fails).
    text = text.replace(
        "            get_idle_batch=self.get_idle_batch,\n",
        "            get_idle_batch=lambda: SchedulerDPAttnMixin.get_idle_batch(self),\n",
    )
    text = text.replace(
        "            batch = self.prepare_mlp_sync_batch(batch)\n",
        "            batch = SchedulerDPAttnMixin.prepare_mlp_sync_batch(self, batch)\n",
    )

    mixin.write_text(text)

    # 3. In scheduler.py, add import + ctor instantiation.
    text = sched.read_text()
    text = insert_after(
        text,
        anchor="from sglang.srt.managers.scheduler_components.request_receiver import (\n    SchedulerRequestReceiver,\n)\n",
        addition=(
            "from sglang.srt.managers.scheduler_components.dp_attn import (\n"
            "    SchedulerDPAttnAdapter,\n"
            ")\n"
        ),
    )
    text = replace_call_site(
        text,
        old="        self.is_initializing = False\n",
        new=INIT_INSERT + "        self.is_initializing = False\n",
    )

    # 4. Callsite rewrites in scheduler.py (2 sites).
    text = replace_call_site(
        text,
        old="            new_batch = self.maybe_prepare_mlp_sync_batch(new_batch)\n",
        new="            new_batch = self.maybe_prepare_mlp_sync_batch(\n"
        "                self.dp_attn_adapter, new_batch\n"
        "            )\n",
    )
    text = replace_call_site(
        text,
        old="        ret = self.maybe_prepare_mlp_sync_batch(ret, need_sync=need_mlp_sync)\n",
        new="        ret = self.maybe_prepare_mlp_sync_batch(\n"
        "            self.dp_attn_adapter, ret, need_sync=need_mlp_sync\n"
        "        )\n",
    )
    sched.write_text(text)

    # 5. Callsite rewrites in scheduler_pp_mixin.py (1 site).
    pp_text = pp.read_text()
    pp_text = replace_call_site(
        pp_text,
        old="                batch = self.maybe_prepare_mlp_sync_batch(batch)\n",
        new="                batch = self.maybe_prepare_mlp_sync_batch(\n"
        "                    self.dp_attn_adapter, batch\n"
        "                )\n",
    )
    pp.write_text(pp_text)

    # 6. Callsite rewrites in disaggregation/prefill.py (1 site).
    pre_text = prefill.read_text()
    pre_text = replace_call_site(
        pre_text,
        old="        batch = self.maybe_prepare_mlp_sync_batch(batch)\n",
        new="        batch = self.maybe_prepare_mlp_sync_batch(\n"
        "            self.dp_attn_adapter, batch\n"
        "        )\n",
    )
    prefill.write_text(pre_text)

    # 7. Callsite rewrites in disaggregation/decode.py (1 site).
    dec_text = decode.read_text()
    dec_text = replace_call_site(
        dec_text,
        old="        ret = self.maybe_prepare_mlp_sync_batch(ret)\n",
        new="        ret = self.maybe_prepare_mlp_sync_batch(\n"
        "            self.dp_attn_adapter, ret\n"
        "        )\n",
    )
    decode.write_text(dec_text)


if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        area_branch=AREA_BRANCH,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
