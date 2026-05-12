#!/usr/bin/env python3
"""Introduce `NgramEmbeddingManager` (PR 1/3 of the ngram embedding migration).

- New file `python/sglang/srt/layers/n_gram_embedding_manager.py`. Class body
  is assembled from the two ModelRunner method bodies cut via ``cut_lines``
  -- no hand-written re-implementation of the source code.
- The manager's 4 fields keep the original ModelRunner / Scheduler field
  names (``use_ngram_embedding`` / ``token_table`` / ``ngram_embedding_n`` /
  ``ngram_embedding_k``) so /44's cut Scheduler body and /45's CudaGraphRunner
  consumer migration do not need to rename anything (Ch1 forbids renames).
- `maybe_init_ngram_embedding` becomes a classmethod factory (kept the
  original method name; renaming to a more idiomatic ``from_model`` is
  deferred to Ch2). Body is the original byte-for-byte except for: signature
  line swap, ``self.X`` -> kwarg substitutions, the two ``self.Y =``
  writebacks redirected to local vars, and a final ``return cls(...)``.
- `maybe_update_ngram_token_table` moves verbatim onto the manager (the
  original body did not consult any ``self.X`` field of ModelRunner, so no
  substitutions are required).
- ModelRunner: delete both methods (no delegates, per Ch1). The two call
  sites in ``__init__`` and ``sample`` are rewritten inline -- ``__init__``
  constructs the manager and double-tracks the legacy ``use_ngram_embedding``
  / ``token_table`` fields so Scheduler / CudaGraphRunner keep working until
  PRs 2 and 3 land.

Usage:
    uv run --python 3.12 introduce-ngram-embedding-mgr.py run
    uv run --python 3.12 introduce-ngram-embedding-mgr.py verify
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

ID = "introduce-ngram-embedding-mgr"
SUBJECT = "Introduce NgramEmbeddingManager (PR 1/3 of ngram embedding migration)"
BODY = ""
AREA = "mech_model_runner"
BASE = "tom_refactor_202605a/primary/mech_model_runner/rwt-migrate-modelexpress-publish"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


MANAGER_HEADER = '''from __future__ import annotations

from typing import TYPE_CHECKING, Optional

import torch

from sglang.jit_kernel.ngram_embedding import update_token_table
from sglang.srt.configs.model_config import ModelConfig
from sglang.srt.mem_cache.memory_pool import ReqToTokenPool
from sglang.srt.server_args import ServerArgs

if TYPE_CHECKING:
    from sglang.srt.model_executor.forward_batch_info import ForwardBatch


class NgramEmbeddingManager:

    def __init__(
        self,
        *,
        use_ngram_embedding: bool,
        token_table: Optional[torch.Tensor],
        ngram_embedding_n: int,
        ngram_embedding_k: int,
    ):
        self.use_ngram_embedding = use_ngram_embedding
        self.token_table = token_table
        self.ngram_embedding_n = ngram_embedding_n
        self.ngram_embedding_k = ngram_embedding_k

'''


# Replacement for the call site in ModelRunner.__init__:
#     self.maybe_init_ngram_embedding()
# Per MECH_COMMIT_SPLIT "长 ctor → init_X" rule, the multi-line factory call
# lives in its own helper method.
INLINE_INIT_CALL = "        self.init_ngram_embedding_manager()\n"

# The helper method body — inserted before ``_build_model_config`` in
# ModelRunner. Combines the factory call and the legacy double-track fields
# (the latter are dropped by ``nem-drop-legacy-fields`` later in the chain).
_INIT_HELPER = '''    def init_ngram_embedding_manager(self):
        self.ngram_embedding_manager = NgramEmbeddingManager.maybe_init_ngram_embedding(
            model=self.model,
            model_config=self.model_config,
            req_to_token_pool=self.req_to_token_pool,
            server_args=self.server_args,
            max_running_requests=self.max_running_requests,
            device=self.device,
        )
        # Legacy double-track fields kept for now; Scheduler / CudaGraphRunner
        # still read them. PRs 2 and 3 of this chain migrate those callers
        # to ``self.ngram_embedding_manager`` and then drop the fields below.
        self.use_ngram_embedding = self.ngram_embedding_manager.use_ngram_embedding
        if self.ngram_embedding_manager.use_ngram_embedding:
            self.token_table = self.ngram_embedding_manager.token_table

'''


def _transform_init_method(method_text: str) -> str:
    """Convert the cut ``maybe_init_ngram_embedding`` body into a classmethod
    factory body. Edits are textual:
      - swap signature, add ``@classmethod`` decorator
      - prepend defaults so the final ``return cls(...)`` gets a value either
        branch (the original ``if self.use_ngram_embedding:`` block stays as
        the gate -- no control-flow restructure)
      - replace ``self.X`` reads with the matching kwarg name
      - redirect the two ``self.Y =`` writebacks to local vars whose names
        match the ctor kwargs (``use_ngram_embedding``, ``token_table``)
      - append n/k extraction (still inside the ``if`` block) and
        ``return cls(...)``
    """
    text = method_text

    text = text.replace(
        "    def maybe_init_ngram_embedding(self):\n",
        "    @classmethod\n"
        "    def maybe_init_ngram_embedding(\n"
        "        cls,\n"
        "        *,\n"
        "        model: torch.nn.Module,\n"
        "        model_config: ModelConfig,\n"
        "        req_to_token_pool: ReqToTokenPool,\n"
        "        server_args: ServerArgs,\n"
        "        max_running_requests: int,\n"
        "        device: str,\n"
        "    ):\n"
        "        token_table = None\n"
        "        ngram_embedding_n = 0\n"
        "        ngram_embedding_k = 0\n",
    )

    # Redirect the two ``self.Y =`` writebacks to local vars.
    text = text.replace(
        "        self.use_ngram_embedding = self.model_config.use_ngram_embedding\n",
        "        use_ngram_embedding = model_config.use_ngram_embedding\n",
    )
    text = text.replace(
        "            self.token_table = torch.empty(\n",
        "            token_table = torch.empty(\n",
    )

    # ``self.X`` -> kwarg / local-var renames (read-only references).
    text = text.replace("self.use_ngram_embedding", "use_ngram_embedding")
    text = text.replace("self.req_to_token_pool", "req_to_token_pool")
    text = text.replace("self.model_config", "model_config")
    text = text.replace("self.server_args", "server_args")
    text = text.replace("self.max_running_requests", "max_running_requests")
    text = text.replace("self.model.modules()", "model.modules()")
    text = text.replace("self.device", "device")

    body_tail = (
        "            hf_config = model_config.hf_config\n"
        "            ngram_embedding_n = hf_config.ngram_embedding_n\n"
        "            ngram_embedding_k = hf_config.ngram_embedding_k\n"
        "        return cls(\n"
        "            use_ngram_embedding=use_ngram_embedding,\n"
        "            token_table=token_table,\n"
        "            ngram_embedding_n=ngram_embedding_n,\n"
        "            ngram_embedding_k=ngram_embedding_k,\n"
        "        )\n"
    )
    return text.rstrip() + "\n" + body_tail


def transform(wt: Path) -> None:
    mr = wt / "python/sglang/srt/model_executor/model_runner.py"
    manager = wt / "python/sglang/srt/layers/n_gram_embedding_manager.py"

    # Cut the two method bodies from ModelRunner (source order: init at
    # ~L2310, update at ~L2332).
    s, e = find_method_lines(
        mr.read_text(),
        class_name="ModelRunner",
        method_name="maybe_init_ngram_embedding",
    )
    init_method_text = cut_lines(mr, s, e)

    s, e = find_method_lines(
        mr.read_text(),
        class_name="ModelRunner",
        method_name="maybe_update_ngram_token_table",
    )
    update_method_text = cut_lines(mr, s, e)

    init_block = _transform_init_method(init_method_text)
    manager.write_text(
        MANAGER_HEADER + init_block + "\n" + update_method_text.rstrip() + "\n"
    )

    # Update ModelRunner: import + rewrite both call sites inline.
    text = mr.read_text()
    text = replace_call_site(
        text,
        old=(
            "from sglang.srt.layers.model_parallel import apply_torch_tp\n"
            "from sglang.srt.layers.pooler import EmbeddingPoolerOutput\n"
        ),
        new=(
            "from sglang.srt.layers.model_parallel import apply_torch_tp\n"
            "from sglang.srt.layers.n_gram_embedding_manager import NgramEmbeddingManager\n"
            "from sglang.srt.layers.pooler import EmbeddingPoolerOutput\n"
        ),
    )

    text = replace_call_site(
        text,
        old="        self.maybe_init_ngram_embedding()\n",
        new=INLINE_INIT_CALL,
    )
    # Insert the init helper method before ``_build_model_config``.
    text = text.replace(
        "    def init_msprobe(",
        _INIT_HELPER + "    def init_msprobe(",
        1,
    )

    text = replace_call_site(
        text,
        old="        self.maybe_update_ngram_token_table(next_token_ids, forward_batch)\n",
        new=(
            "        self.ngram_embedding_manager.maybe_update_ngram_token_table(\n"
            "            next_token_ids=next_token_ids,\n"
            "            forward_batch=forward_batch,\n"
            "        )\n"
        ),
    )

    mr.write_text(text)

    # Absorbed from nem-mech-rename + nem-mech-frozen: shorter field / method
    # names (the class name already carries the ``Ngram`` semantic) and
    # ``@dataclass(frozen, slots, kw_only)`` form for the value-object class.
    _rename_and_freeze_manager(wt)


_INSIDE_SUBS = [
    # self.X reads
    ("self.use_ngram_embedding", "self.enabled"),
    ("self.token_table", "self.table"),
    ("self.ngram_embedding_n", "self.n"),
    ("self.ngram_embedding_k", "self.k"),
    # ctor kwargs in __init__ signature
    ("use_ngram_embedding: bool,", "enabled: bool,"),
    ("token_table: Optional[torch.Tensor],", "table: Optional[torch.Tensor],"),
    ("ngram_embedding_n: int,", "n: int,"),
    ("ngram_embedding_k: int,", "k: int,"),
    # from_model's `return cls(use_ngram_embedding=use_ngram_embedding, ...)`
    ("use_ngram_embedding=use_ngram_embedding", "enabled=use_ngram_embedding"),
    ("token_table=token_table", "table=token_table"),
    ("ngram_embedding_n=ngram_embedding_n", "n=ngram_embedding_n"),
    ("ngram_embedding_k=ngram_embedding_k", "k=ngram_embedding_k"),
    # __init__ body assignments — RHS still has original kwarg names
    ("self.enabled = use_ngram_embedding", "self.enabled = enabled"),
    ("self.table = token_table", "self.table = table"),
    ("self.n = ngram_embedding_n", "self.n = n"),
    ("self.k = ngram_embedding_k", "self.k = k"),
    # method def lines
    ("def maybe_init_ngram_embedding", "def from_model"),
    ("def maybe_prepare_ngram_embedding", "def prepare_for_forward"),
    ("def maybe_update_ngram_token_table", "def update_after_decode"),
]


_OUTSIDE_SUBS = [
    ("ngram_embedding_manager.use_ngram_embedding", "ngram_embedding_manager.enabled"),
    ("ngram_embedding_manager.token_table", "ngram_embedding_manager.table"),
    ("ngram_embedding_manager.ngram_embedding_n", "ngram_embedding_manager.n"),
    ("ngram_embedding_manager.ngram_embedding_k", "ngram_embedding_manager.k"),
    ("NgramEmbeddingManager.maybe_init_ngram_embedding", "NgramEmbeddingManager.from_model"),
    (".maybe_prepare_ngram_embedding(", ".prepare_for_forward("),
    ("ngram_embedding_manager.maybe_update_ngram_token_table", "ngram_embedding_manager.update_after_decode"),
]


_OUTSIDE_FILES = [
    "python/sglang/srt/model_executor/cuda_graph_runner.py",
    "python/sglang/srt/model_executor/model_runner.py",
    "python/sglang/srt/managers/scheduler.py",
    "python/sglang/srt/model_executor/forward_batch_info.py",
]


def _rename_and_freeze_manager(wt: Path) -> None:
    src = wt / "python/sglang/srt/layers/n_gram_embedding_manager.py"
    text = src.read_text()
    for old, new in _INSIDE_SUBS:
        text = text.replace(old, new)
    # Apply nem-mech-frozen: replace handwritten __init__ with dataclass form.
    text = insert_after(
        text,
        anchor="from typing import TYPE_CHECKING, Optional\n",
        addition="from dataclasses import dataclass\n",
    )
    text = replace_call_site(
        text,
        old=(
            "class NgramEmbeddingManager:\n"
            "\n"
            "    def __init__(\n"
            "        self,\n"
            "        *,\n"
            "        enabled: bool,\n"
            "        table: Optional[torch.Tensor],\n"
            "        n: int,\n"
            "        k: int,\n"
            "    ):\n"
            "        self.enabled = enabled\n"
            "        self.table = table\n"
            "        self.n = n\n"
            "        self.k = k\n"
        ),
        new=(
            "@dataclass(frozen=True, slots=True, kw_only=True)\n"
            "class NgramEmbeddingManager:\n"
            "    enabled: bool\n"
            "    table: Optional[torch.Tensor]\n"
            "    n: int\n"
            "    k: int\n"
        ),
    )
    src.write_text(text)

    for relpath in _OUTSIDE_FILES:
        path = wt / relpath
        if not path.exists():
            continue
        text = path.read_text()
        for old, new in _OUTSIDE_SUBS:
            text = text.replace(old, new)
        path.write_text(text)


if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        area_branch=AREA_BRANCH,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
