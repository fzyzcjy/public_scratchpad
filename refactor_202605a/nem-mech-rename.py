#!/usr/bin/env python3
"""Rename ``NgramEmbeddingManager`` fields + factory + 2 methods.

| kind         | 旧                                        | 新                       |
|--------------|-------------------------------------------|--------------------------|
| field        | ``use_ngram_embedding``                   | ``enabled``              |
| field        | ``token_table``                           | ``table``                |
| field        | ``ngram_embedding_n``                     | ``n``                    |
| field        | ``ngram_embedding_k``                     | ``k``                    |
| classmethod  | ``maybe_init_ngram_embedding``            | ``from_model``           |
| method       | ``maybe_prepare_ngram_embedding``         | ``prepare_for_forward``  |
| method       | ``maybe_update_ngram_token_table``        | ``update_after_decode``  |

Internal callers within ``NgramEmbeddingManager`` go through ``self.X``;
external callers go through ``model_runner.ngram_embedding_manager.X`` or
``NgramEmbeddingManager.maybe_init_ngram_embedding``. Both rewire here.

The ``Scheduler.maybe_init_ngram_embedding`` method is a *different*
method on a different class — left untouched.

Usage:
    uv run --python 3.12 nem-mech-rename.py run
    uv run --python 3.12 nem-mech-rename.py verify
"""

# /// script
# requires-python = ">=3.10"
# dependencies = ["typer"]
# ///

import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from _runner import run_pr

ID = "nem-mech-rename"
SUBJECT = "Rename NgramEmbeddingManager fields + factory + 2 methods"
BODY = ""
AREA = "mech_model_runner"
BASE = "tom_refactor_202605a/primary/mech_model_runner/ha-mech-drop-is-draft-worker"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


# Inside the source file, ``self.X`` carries the old name. After this commit
# the field name is X-new on both class side and ctor kwarg.
_INSIDE_SUBS = [
    # field accesses on ``self``
    ("self.use_ngram_embedding", "self.enabled"),
    ("self.token_table", "self.table"),
    ("self.ngram_embedding_n", "self.n"),
    ("self.ngram_embedding_k", "self.k"),
    # ctor kwarg names + types
    ("use_ngram_embedding: bool,", "enabled: bool,"),
    ("token_table: Optional[torch.Tensor],", "table: Optional[torch.Tensor],"),
    ("ngram_embedding_n: int,", "n: int,"),
    ("ngram_embedding_k: int,", "k: int,"),
    # ctor call kwargs (from_model returns NgramEmbeddingManager(...))
    ("use_ngram_embedding=use_ngram_embedding", "enabled=use_ngram_embedding"),
    ("token_table=token_table", "table=token_table"),
    ("ngram_embedding_n=ngram_embedding_n", "n=ngram_embedding_n"),
    ("ngram_embedding_k=ngram_embedding_k", "k=ngram_embedding_k"),
    # __init__ body assignments — RHS still carries the original kwarg name
    # because the ``self.X`` rename only touched the LHS. Rewire RHS to the
    # new kwarg names so ``self.enabled = enabled`` etc. resolves.
    ("self.enabled = use_ngram_embedding", "self.enabled = enabled"),
    ("self.table = token_table", "self.table = table"),
    ("self.n = ngram_embedding_n", "self.n = n"),
    ("self.k = ngram_embedding_k", "self.k = k"),
    # method def lines
    ("def maybe_init_ngram_embedding", "def from_model"),
    ("def maybe_prepare_ngram_embedding", "def prepare_for_forward"),
    ("def maybe_update_ngram_token_table", "def update_after_decode"),
]


# Outside callers go through a clear qualifier — scoped substitutions
# avoid colliding with ``Scheduler.maybe_init_ngram_embedding`` etc.
_OUTSIDE_SUBS = [
    ("ngram_embedding_manager.use_ngram_embedding", "ngram_embedding_manager.enabled"),
    ("ngram_embedding_manager.token_table", "ngram_embedding_manager.table"),
    ("ngram_embedding_manager.ngram_embedding_n", "ngram_embedding_manager.n"),
    ("ngram_embedding_manager.ngram_embedding_k", "ngram_embedding_manager.k"),
    ("NgramEmbeddingManager.maybe_init_ngram_embedding", "NgramEmbeddingManager.from_model"),
    (".maybe_prepare_ngram_embedding(", ".prepare_for_forward("),
    # update_after_decode is invoked via ``self.ngram_embedding_manager.maybe_update_ngram_token_table(``
    # — qualifying on ``manager.`` keeps Scheduler's own renames untouched.
    ("ngram_embedding_manager.maybe_update_ngram_token_table", "ngram_embedding_manager.update_after_decode"),
]


_OUTSIDE_FILES = [
    "python/sglang/srt/model_executor/cuda_graph_runner.py",
    "python/sglang/srt/model_executor/model_runner.py",
    "python/sglang/srt/managers/scheduler.py",
    "python/sglang/srt/model_executor/forward_batch_info.py",
]


def transform(wt: Path) -> None:
    src = wt / "python/sglang/srt/layers/n_gram_embedding_manager.py"
    text = src.read_text()
    for old, new in _INSIDE_SUBS:
        text = text.replace(old, new)
    src.write_text(text)

    for relpath in _OUTSIDE_FILES:
        path = wt / relpath
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
