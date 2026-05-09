#!/usr/bin/env python3
"""Reproducible transform: migrate `CudaGraphRunner` to read ngram embedding
state through `model_runner.ngram_embedding_manager` and drop the legacy
double-track fields on `ModelRunner` (PR 3/3 of ngram embedding migration).

- CudaGraphRunner.__init__ reads `model_runner.ngram_embedding_manager.X`
  instead of `model_runner.use_ngram_embedding` /
  `model_runner.model_config.hf_config.ngram_embedding_*` /
  `model_runner.token_table`.
- ModelRunner.maybe_init_ngram_embedding drops the trailing legacy
  double-track block (`use_ngram_embedding` and `token_table` fields).
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
    # ---- Update CudaGraphRunner ----
    cgr = dir_root / "python/sglang/srt/model_executor/cuda_graph_runner.py"
    text = cgr.read_text()

    old_use_block = (
        "        self.use_ngram_embedding = model_runner.use_ngram_embedding\n"
        "        if self.use_ngram_embedding:\n"
        "            hf_config = model_runner.model_config.hf_config\n"
        "            self.ngram_embedding_n = hf_config.ngram_embedding_n\n"
        "            self.ngram_embedding_k = hf_config.ngram_embedding_k\n"
    )
    new_use_block = (
        "        self.use_ngram_embedding = model_runner.ngram_embedding_manager.enabled\n"
        "        if self.use_ngram_embedding:\n"
        "            self.ngram_embedding_n = model_runner.ngram_embedding_manager.n\n"
        "            self.ngram_embedding_k = model_runner.ngram_embedding_manager.k\n"
    )
    assert old_use_block in text
    text = text.replace(old_use_block, new_use_block)

    old_table = (
        "            ne_token_table=(\n"
        "                model_runner.token_table if self.use_ngram_embedding else None\n"
        "            ),\n"
    )
    new_table = (
        "            ne_token_table=(\n"
        "                model_runner.ngram_embedding_manager.table if self.use_ngram_embedding else None\n"
        "            ),\n"
    )
    assert old_table in text
    text = text.replace(old_table, new_table)

    cgr.write_text(text)

    # ---- Drop the legacy double-track block in ModelRunner ----
    mr = dir_root / "python/sglang/srt/model_executor/model_runner.py"
    text = mr.read_text()

    old_legacy = (
        "        # Legacy double-track fields kept for now; Scheduler / CudaGraphRunner\n"
        "        # still read them. PRs 2 and 3 of this chain will migrate those callers\n"
        "        # to ``self.ngram_embedding_manager`` and remove the fields below.\n"
        "        self.use_ngram_embedding = self.ngram_embedding_manager.enabled\n"
        "        if self.ngram_embedding_manager.enabled:\n"
        "            self.token_table = self.ngram_embedding_manager.table\n"
    )
    assert old_legacy in text
    text = text.replace(old_legacy, "")

    mr.write_text(text)

    git_add_and_commit(
        "Migrate CudaGraphRunner to NgramEmbeddingManager and drop legacy fields (PR 3/3)",
        cwd=str(dir_root),
    )


if __name__ == "__main__":
    verify_mechanical_refactor(
        base_commit=BASE_COMMIT,
        target_commit=TARGET_COMMIT,
        transform=transform,
    )
