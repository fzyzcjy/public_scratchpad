#!/usr/bin/env python3
"""No-op stub: PR 3/3 of the original ngram embedding migration plan was to
*delete* the legacy double-track block on ModelRunner -- specifically the
trailing 3 lines added in /43 that keep ``self.use_ngram_embedding`` and
``self.token_table`` writing to themselves -- plus the consumer migration on
CudaGraphRunner that reads through ``model_runner.ngram_embedding_manager``.

Per ``EXECUTION_GUIDE.md`` Ch1 rule: **删除原 ModelRunner 字段** ❌（即便方法
搬走了字段不再被自身用到，**保留**——deferred 到 Ch2）. The double-track
deletion is therefore Ch2 work, not Ch1.

The CudaGraphRunner / forward_batch_info consumer migration would technically
be Ch1-valid (caller-site rewrite), but is kept paired with the legacy-field
deletion as a single Ch2 PR for chain coherence -- otherwise we leave a half
state where some consumers go through the manager and others don't.

This stub keeps the chain numbering aligned with the rest of the sprint
(``tom_refactor/45`` is a real ref pointing at the same commit as
``tom_refactor/44``); it is intentionally a no-op so ``run`` produces an
empty commit-free push.

Usage:
    uv run --python 3.12 tom_refactor_45.py run
    uv run --python 3.12 tom_refactor_45.py verify
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

BASE = "tom_refactor/44"
TARGET = "tom_refactor/45"


def transform(wt: Path) -> None:  # noqa: ARG001 -- intentional no-op
    """Intentional no-op. See module docstring."""
    return


if __name__ == "__main__":
    run_pr(transform=transform, base=BASE, target=TARGET)
