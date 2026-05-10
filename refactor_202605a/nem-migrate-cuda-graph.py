#!/usr/bin/env python3
"""Migrate `CudaGraphRunner` ngram-embedding consumer onto `NgramEmbeddingManager`
(PR 3/3 of the ngram embedding migration).

- `cuda_graph_runner.py` currently reads `model_runner.use_ngram_embedding`
  / `model_runner.model_config.hf_config.ngram_embedding_n` /
  `.ngram_embedding_k`, plus `model_runner.token_table` (one cap-time read at
  the buffer-construction call site). This PR rewires every read to
  `model_runner.ngram_embedding_manager.{enabled,n,k,table}` so the legacy
  double-track fields on ModelRunner are no longer consulted by
  CudaGraphRunner.
- The double-track fields on ModelRunner (`self.use_ngram_embedding` /
  `self.token_table`) are NOT deleted -- per Ch1 ("删除原 ModelRunner 字段" is
  forbidden), removal is deferred to Ch2.
- Per ch3.1 of `ngram_embedding.md`: only the consumer rewires belong here;
  no rename of CudaGraphRunner's own field (`self.use_ngram_embedding`),
  since renaming is Ch2.

Usage:
    uv run --python 3.12 nem-migrate-cuda-graph.py run
    uv run --python 3.12 nem-migrate-cuda-graph.py verify
"""

# /// script
# requires-python = ">=3.10"
# dependencies = ["typer"]
# ///

import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from _helpers import replace_call_site
from _runner import run_pr

ID = "nem-migrate-cuda-graph"
SUBJECT = "Migrate CudaGraphRunner ngram-embedding reads to NgramEmbeddingManager (PR 3/3)"
BODY = ""
AREA = "mech_model_runner"
BASE = "tom_refactor_202605a/raw/mech_model_runner/nem-migrate-maybe-prepare"
TARGET = f"tom_refactor_202605a/raw/{AREA}/{ID}"


def transform(wt: Path) -> None:
    cgr = wt / "python/sglang/srt/model_executor/cuda_graph_runner.py"

    text = cgr.read_text()

    # Block of 4 reads in CudaGraphRunner.__init__: redirect ModelRunner
    # bare-field reads to the ngram_embedding_manager. Field name on the
    # manager is `use_ngram_embedding` (not yet renamed to `enabled` -- that
    # rename is Ch2), and `n` / `k` are already short names per /43.
    text = replace_call_site(
        text,
        old=(
            "        self.use_ngram_embedding = model_runner.use_ngram_embedding\n"
            "        if self.use_ngram_embedding:\n"
            "            hf_config = model_runner.model_config.hf_config\n"
            "            self.ngram_embedding_n = hf_config.ngram_embedding_n\n"
            "            self.ngram_embedding_k = hf_config.ngram_embedding_k\n"
        ),
        new=(
            "        self.use_ngram_embedding = (\n"
            "            model_runner.ngram_embedding_manager.use_ngram_embedding\n"
            "        )\n"
            "        if self.use_ngram_embedding:\n"
            "            self.ngram_embedding_n = (\n"
            "                model_runner.ngram_embedding_manager.ngram_embedding_n\n"
            "            )\n"
            "            self.ngram_embedding_k = (\n"
            "                model_runner.ngram_embedding_manager.ngram_embedding_k\n"
            "            )\n"
        ),
    )

    # The `ne_token_table=` kwarg in capture-time buffer construction reads
    # the table from ModelRunner directly -- redirect to the manager.
    text = replace_call_site(
        text,
        old=(
            "            ne_token_table=(\n"
            "                model_runner.token_table if self.use_ngram_embedding else None\n"
            "            ),\n"
        ),
        new=(
            "            ne_token_table=(\n"
            "                model_runner.ngram_embedding_manager.token_table\n"
            "                if self.use_ngram_embedding\n"
            "                else None\n"
            "            ),\n"
        ),
    )

    cgr.write_text(text)

if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        target=TARGET,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
