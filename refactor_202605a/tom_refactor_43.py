#!/usr/bin/env python3
"""Reproducible transform: introduce `NgramEmbeddingManager` (PR 1/3 of the
ngram embedding migration).

- Create `python/sglang/srt/layers/n_gram_embedding_manager.py` with the new
  class: `__init__` taking explicit fields; `from_model` classmethod factory
  (body of `ModelRunner.maybe_init_ngram_embedding`); `update_after_decode`
  method (body of `ModelRunner.maybe_update_ngram_token_table`).
- ModelRunner: `maybe_init_ngram_embedding` constructs
  `self.ngram_embedding_manager` via `NgramEmbeddingManager.from_model(...)`
  and keeps the legacy `self.use_ngram_embedding` / `self.token_table` fields
  in sync (double-track) so Scheduler / CudaGraphRunner keep working until
  PRs 2 and 3 of the chain land.
- ModelRunner: `maybe_update_ngram_token_table` becomes a 1-line delegate.
"""

import sys
from pathlib import Path

sys.path.append(".claude/skills/mechanical-refactor-verify")
from mechanical_refactor_verify_utils import (
    verify_mechanical_refactor,
    git_add_and_commit,
)

BASE_COMMIT = "tom_refactor/42"
TARGET_COMMIT = "tom_refactor/43"


MANAGER_PY = '''
from __future__ import annotations

from typing import Optional

import torch
from torch import nn

from sglang.jit_kernel.ngram_embedding import update_token_table
from sglang.srt.configs.model_config import ModelConfig


class NgramEmbeddingManager:

    def __init__(
        self,
        *,
        enabled: bool,
        table: Optional[torch.Tensor],
        n: int,
        k: int,
    ) -> None:
        self.enabled = enabled
        self.table = table
        self.n = n
        self.k = k

    @classmethod
    def from_model(
        cls,
        *,
        model: nn.Module,
        model_config: ModelConfig,
        req_to_token_pool,
        chunked_prefill_size: Optional[int],
        max_running_requests: int,
        device: str,
    ) -> "NgramEmbeddingManager":
        from sglang.srt.layers.n_gram_embedding import NgramEmbedding

        if not model_config.use_ngram_embedding:
            return cls(enabled=False, table=None, n=0, k=0)

        assert (
            chunked_prefill_size is not None and chunked_prefill_size > 0
        ), "Ngram embedding requires chunked prefill to be enabled (chunked_prefill_size > 0)"

        # Sized to mirror req_to_token (indexed by req_pool_idx).
        table = torch.empty(
            req_to_token_pool.req_to_token.shape[0],
            model_config.context_len,
            dtype=torch.int32,
            device=device,
        )
        for module in model.modules():
            if isinstance(module, NgramEmbedding):
                module.init_buffers(max_running_requests, chunked_prefill_size, device)

        hf_config = model_config.hf_config
        return cls(
            enabled=True,
            table=table,
            n=hf_config.ngram_embedding_n,
            k=hf_config.ngram_embedding_k,
        )

    def update_after_decode(
        self,
        *,
        next_token_ids: torch.Tensor,
        forward_batch,
    ) -> None:
        """Update the ngram embedding token table after sampling."""
        ngram_embedding_info = forward_batch.ngram_embedding_info
        if ngram_embedding_info is None:
            return
        ngram_embedding_info.out_column_starts[: forward_batch.batch_size] = (
            forward_batch.seq_lens
        )
        ngram_embedding_info.out_req_lens[: forward_batch.batch_size] = 1
        update_token_table(
            ne_token_table=ngram_embedding_info.token_table,
            tokens=next_token_ids.to(torch.int32),
            row_indices=forward_batch.req_pool_indices,
            column_starts=ngram_embedding_info.out_column_starts,
            req_lens=torch.ones_like(ngram_embedding_info.out_column_starts),
            ignore_tokens=None,
        )
'''


def transform(dir_root: Path) -> None:
    # ---- Create new manager file ----
    manager = dir_root / "python/sglang/srt/layers/n_gram_embedding_manager.py"
    manager.write_text(MANAGER_PY)

    # ---- Update model_runner.py ----
    mr = dir_root / "python/sglang/srt/model_executor/model_runner.py"
    text = mr.read_text()

    # Add the import.
    old_import = (
        "from sglang.srt.layers.model_parallel import apply_torch_tp\n"
        "from sglang.srt.layers.pooler import EmbeddingPoolerOutput\n"
    )
    new_import = (
        "from sglang.srt.layers.model_parallel import apply_torch_tp\n"
        "from sglang.srt.layers.n_gram_embedding_manager import NgramEmbeddingManager\n"
        "from sglang.srt.layers.pooler import EmbeddingPoolerOutput\n"
    )
    assert old_import in text
    text = text.replace(old_import, new_import)

    # Replace maybe_init_ngram_embedding body.
    old_init = (
        "    def maybe_init_ngram_embedding(self):\n"
        "        self.use_ngram_embedding = self.model_config.use_ngram_embedding\n"
        "        if self.use_ngram_embedding:\n"
        "            from sglang.srt.layers.n_gram_embedding import NgramEmbedding\n"
        "\n"
        "            # Sized to mirror req_to_token (indexed by req_pool_idx).\n"
        "            self.token_table = torch.empty(\n"
        "                self.req_to_token_pool.req_to_token.shape[0],\n"
        "                self.model_config.context_len,\n"
        "                dtype=torch.int32,\n"
        "                device=self.device,\n"
        "            )\n"
        "            chunked_prefill_size = self.server_args.chunked_prefill_size\n"
        "            assert (\n"
        "                chunked_prefill_size is not None and chunked_prefill_size > 0\n"
        '            ), "Ngram embedding requires chunked prefill to be enabled (chunked_prefill_size > 0)"\n'
        "            for module in self.model.modules():\n"
        "                if isinstance(module, NgramEmbedding):\n"
        "                    module.init_buffers(\n"
        "                        self.max_running_requests, chunked_prefill_size, self.device\n"
        "                    )\n"
    )
    new_init = (
        "    def maybe_init_ngram_embedding(self):\n"
        "        self.ngram_embedding_manager = NgramEmbeddingManager.from_model(\n"
        "            model=self.model,\n"
        "            model_config=self.model_config,\n"
        "            req_to_token_pool=self.req_to_token_pool,\n"
        "            chunked_prefill_size=self.server_args.chunked_prefill_size,\n"
        "            max_running_requests=self.max_running_requests,\n"
        "            device=self.device,\n"
        "        )\n"
        "        # Legacy double-track fields kept for now; Scheduler / CudaGraphRunner\n"
        "        # still read them. PRs 2 and 3 of this chain will migrate those callers\n"
        "        # to ``self.ngram_embedding_manager`` and remove the fields below.\n"
        "        self.use_ngram_embedding = self.ngram_embedding_manager.enabled\n"
        "        if self.ngram_embedding_manager.enabled:\n"
        "            self.token_table = self.ngram_embedding_manager.table\n"
    )
    assert old_init in text
    text = text.replace(old_init, new_init)

    # Replace maybe_update_ngram_token_table body with a 1-line delegate.
    old_update = (
        "    def maybe_update_ngram_token_table(\n"
        "        self,\n"
        "        next_token_ids: torch.Tensor,\n"
        '        forward_batch: "ForwardBatch",\n'
        "    ):\n"
        '        """Update the ngram embedding token table after sampling."""\n'
        "        ngram_embedding_info = forward_batch.ngram_embedding_info\n"
        "        if ngram_embedding_info is None:\n"
        "            return\n"
        "        ngram_embedding_info.out_column_starts[: forward_batch.batch_size] = (\n"
        "            forward_batch.seq_lens\n"
        "        )\n"
        "        ngram_embedding_info.out_req_lens[: forward_batch.batch_size] = 1\n"
        "        update_token_table(\n"
        "            ne_token_table=ngram_embedding_info.token_table,\n"
        "            tokens=next_token_ids.to(torch.int32),\n"
        "            row_indices=forward_batch.req_pool_indices,\n"
        "            column_starts=ngram_embedding_info.out_column_starts,\n"
        "            req_lens=torch.ones_like(ngram_embedding_info.out_column_starts),\n"
        "            ignore_tokens=None,\n"
        "        )\n"
    )
    new_update = (
        "    def maybe_update_ngram_token_table(\n"
        "        self,\n"
        "        next_token_ids: torch.Tensor,\n"
        '        forward_batch: "ForwardBatch",\n'
        "    ):\n"
        "        self.ngram_embedding_manager.update_after_decode(\n"
        "            next_token_ids=next_token_ids, forward_batch=forward_batch,\n"
        "        )\n"
    )
    assert old_update in text
    text = text.replace(old_update, new_update)

    mr.write_text(text)

    git_add_and_commit(
        "Introduce NgramEmbeddingManager (PR 1/3 of ngram embedding migration)",
        cwd=str(dir_root),
    )


if __name__ == "__main__":
    verify_mechanical_refactor(
        base_commit=BASE_COMMIT,
        target_commit=TARGET_COMMIT,
        transform=transform,
    )
