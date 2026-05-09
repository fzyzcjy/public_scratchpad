#!/usr/bin/env python3
"""Reproducible transform: migrate Scheduler to NgramEmbeddingManager
(PR 2/3 of ngram embedding migration).

- Add `prepare_for_forward(batch)` method to `NgramEmbeddingManager` (body
  of `Scheduler._maybe_prepare_ngram_embedding`).
- Scheduler.maybe_init_ngram_embedding: assign
  `self.ngram_embedding_manager = self.tp_worker.model_runner.ngram_embedding_manager`
  instead of constructing its own copies.
- Scheduler._maybe_prepare_ngram_embedding becomes a delegate.
- Delete the 4 Scheduler fields: `use_ngram_embedding`, `token_table`,
  `ngram_embedding_n`, `ngram_embedding_k`.
"""

import sys
from pathlib import Path

sys.path.append(".claude/skills/mechanical-refactor-verify")
from mechanical_refactor_verify_utils import (
    verify_mechanical_refactor,
    git_add_and_commit,
)

BASE_COMMIT = "tom_refactor/44"
TARGET_COMMIT = "tom_refactor/45"


def transform(dir_root: Path) -> None:
    # ---- Append prepare_for_forward to NgramEmbeddingManager ----
    manager = dir_root / "python/sglang/srt/layers/n_gram_embedding_manager.py"
    text = manager.read_text()

    new_method = (
        "\n"
        "    def prepare_for_forward(self, batch) -> None:\n"
        "        from sglang.srt.managers.schedule_batch import ForwardMode\n"
        "\n"
        "        batch.ne_token_table = self.table\n"
        "        if batch.forward_mode != ForwardMode.EXTEND:\n"
        "            return\n"
        "        all_tokens = []\n"
        "        column_starts = []\n"
        "        request_lengths = []\n"
        "        for req in batch.reqs:\n"
        "            start = len(req.prefix_indices)\n"
        "            end = start + req.extend_input_len\n"
        "            fill_ids = req.origin_input_ids + req.output_ids\n"
        "            if start == 0:\n"
        "                tokens = fill_ids[start:end]\n"
        "                column_starts.append(0)\n"
        "            elif start < self.n:\n"
        "                tokens = fill_ids[0:end]\n"
        "                column_starts.append(0)\n"
        "            else:\n"
        "                # Prepend n-1 tokens before prefix_len for n-gram context\n"
        "                tokens = fill_ids[start - self.n + 1 : end]\n"
        "                column_starts.append(start - self.n + 1)\n"
        "            all_tokens.extend(tokens)\n"
        "            request_lengths.append(len(tokens))\n"
        "        dtype = self.table.dtype\n"
        "        device = self.table.device\n"
        "        update_token_table(\n"
        "            ne_token_table=self.table,\n"
        "            tokens=torch.tensor(all_tokens, dtype=dtype, device=device),\n"
        "            row_indices=batch.req_pool_indices,\n"
        "            column_starts=torch.tensor(column_starts, dtype=torch.int32, device=device),\n"
        "            req_lens=torch.tensor(request_lengths, dtype=torch.int32, device=device),\n"
        "            ignore_tokens=None,\n"
        "        )\n"
    )
    text = text.rstrip() + "\n" + new_method
    manager.write_text(text)

    # ---- Update Scheduler ----
    sched = dir_root / "python/sglang/srt/managers/scheduler.py"
    text = sched.read_text()

    old_init = (
        "    def maybe_init_ngram_embedding(self):\n"
        "        self.use_ngram_embedding = self.tp_worker.model_config.use_ngram_embedding\n"
        "        if self.use_ngram_embedding:\n"
        "            self.token_table = self.tp_worker.model_runner.token_table\n"
        "            hf_config = self.tp_worker.model_config.hf_config\n"
        "            self.ngram_embedding_n = hf_config.ngram_embedding_n\n"
        "            self.ngram_embedding_k = hf_config.ngram_embedding_k\n"
    )
    new_init = (
        "    def maybe_init_ngram_embedding(self):\n"
        "        self.ngram_embedding_manager = self.tp_worker.model_runner.ngram_embedding_manager\n"
    )
    assert old_init in text
    text = text.replace(old_init, new_init)

    old_prepare = (
        "    def _maybe_prepare_ngram_embedding(\n"
        "        self, batch: Optional[ScheduleBatch]\n"
        "    ) -> Optional[ScheduleBatch]:\n"
        '        """Fill the token table for ngram embedding before a forward pass."""\n'
        "        if batch is None or not self.use_ngram_embedding:\n"
        "            return batch\n"
        "        batch.ne_token_table = self.token_table\n"
        "        if batch.forward_mode == ForwardMode.EXTEND:\n"
        "            all_tokens = []\n"
        "            column_starts = []\n"
        "            request_lengths = []\n"
        "            for req in batch.reqs:\n"
        "                start = len(req.prefix_indices)\n"
        "                end = start + req.extend_input_len\n"
        "                fill_ids = req.origin_input_ids + req.output_ids\n"
        "                if start == 0:\n"
        "                    tokens = fill_ids[start:end]\n"
        "                    column_starts.append(0)\n"
        "                elif start < self.ngram_embedding_n:\n"
        "                    tokens = fill_ids[0:end]\n"
        "                    column_starts.append(0)\n"
        "                else:\n"
        "                    # Prepend n-1 tokens before prefix_len for n-gram context\n"
        "                    tokens = fill_ids[start - self.ngram_embedding_n + 1 : end]\n"
        "                    column_starts.append(start - self.ngram_embedding_n + 1)\n"
        "                all_tokens.extend(tokens)\n"
        "                request_lengths.append(len(tokens))\n"
        "            dtype = self.token_table.dtype\n"
        "            device = self.token_table.device\n"
        "            update_token_table(\n"
        "                ne_token_table=self.token_table,\n"
        "                tokens=torch.tensor(all_tokens, dtype=dtype, device=device),\n"
        "                row_indices=batch.req_pool_indices,\n"
        "                column_starts=torch.tensor(\n"
        "                    column_starts, dtype=torch.int32, device=device\n"
        "                ),\n"
        "                req_lens=torch.tensor(\n"
        "                    request_lengths, dtype=torch.int32, device=device\n"
        "                ),\n"
        "                ignore_tokens=None,\n"
        "            )\n"
        "        return batch\n"
    )
    new_prepare = (
        "    def _maybe_prepare_ngram_embedding(\n"
        "        self, batch: Optional[ScheduleBatch]\n"
        "    ) -> Optional[ScheduleBatch]:\n"
        '        """Fill the token table for ngram embedding before a forward pass."""\n'
        "        if batch is None or not self.ngram_embedding_manager.enabled:\n"
        "            return batch\n"
        "        self.ngram_embedding_manager.prepare_for_forward(batch)\n"
        "        return batch\n"
    )
    assert old_prepare in text
    text = text.replace(old_prepare, new_prepare)

    sched.write_text(text)

    git_add_and_commit(
        "Migrate Scheduler to NgramEmbeddingManager (PR 2/3)",
        cwd=str(dir_root),
    )


if __name__ == "__main__":
    verify_mechanical_refactor(
        base_commit=BASE_COMMIT,
        target_commit=TARGET_COMMIT,
        transform=transform,
    )
