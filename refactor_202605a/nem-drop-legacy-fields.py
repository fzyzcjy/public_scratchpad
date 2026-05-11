#!/usr/bin/env python3
"""Drop the temporary double-track ngram fields on ``ModelRunner`` (added in
``introduce-ngram-embedding-mgr`` to keep Scheduler / CudaGraphRunner /
forward_batch_info compiling during the 3-step migration).

After ``nem-migrate-maybe-prepare`` (Scheduler migrated), and
``nem-migrate-cuda-graph`` (CudaGraphRunner + forward_batch_info migrated),
nothing in the repo reads ``model_runner.use_ngram_embedding`` /
``model_runner.token_table`` directly anymore — both go through
``model_runner.ngram_embedding_manager.X`` now.

This commit removes the 3-line double-track block from ``ModelRunner.__init__``
that was scaffolding for the migration. The block was introduced in this
chain (not original ModelRunner state), so deleting it is "drop scaffolding",
not "delete original ModelRunner field" (which Ch1 still forbids).

The 4 legacy fields on ``Scheduler.maybe_init_ngram_embedding`` (``self.use_ngram_embedding``
etc) are ORIGINAL Scheduler fields, NOT scaffolding — those stay (deletion
is deferred to Ch2 per EXECUTION_GUIDE).

Usage:
    uv run --python 3.12 nem-drop-legacy-fields.py run
    uv run --python 3.12 nem-drop-legacy-fields.py verify
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

ID = "nem-drop-legacy-fields"
SUBJECT = "Drop temporary double-track ngram fields on ModelRunner"
BODY = ""
AREA = "mech_model_runner"
BASE = "tom_refactor_202605a/primary/mech_model_runner/nem-migrate-cuda-graph"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


def transform(wt: Path) -> None:
    mr = wt / "python/sglang/srt/model_executor/model_runner.py"

    text = mr.read_text()
    text = replace_call_site(
        text,
        old=(
            "        # Legacy double-track fields kept for now; Scheduler / CudaGraphRunner\n"
            "        # still read them. PRs 2 and 3 of this chain migrate those callers\n"
            "        # to ``self.ngram_embedding_manager`` and then drop the fields below.\n"
            "        self.use_ngram_embedding = self.ngram_embedding_manager.enabled\n"
            "        if self.ngram_embedding_manager.enabled:\n"
            "            self.token_table = self.ngram_embedding_manager.table\n"
        ),
        new="",
    )
    mr.write_text(text)


if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        area_branch=AREA_BRANCH,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
