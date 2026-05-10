#!/usr/bin/env python3
"""Migrate `Scheduler._maybe_prepare_ngram_embedding` onto `NgramEmbeddingManager`
(PR 2/3 of the ngram embedding migration).

- Cut `_maybe_prepare_ngram_embedding` from Scheduler via ``cut_lines`` and
  append it onto `NgramEmbeddingManager`. Body is byte-identical: the method
  reads ``self.use_ngram_embedding`` / ``self.token_table`` /
  ``self.ngram_embedding_n``, and the manager (per /43) carries those exact
  field names -- no renames required.
- Scheduler.maybe_init_ngram_embedding gains a ``self.ngram_embedding_manager
  = self.tp_worker.model_runner.ngram_embedding_manager`` line; the existing
  4 fields (``use_ngram_embedding`` / ``token_table`` / ``ngram_embedding_n``
  / ``ngram_embedding_k``) stay (Ch1 forbids deleting them; deferred to Ch2).
- Scheduler caller `ret = self._maybe_prepare_ngram_embedding(ret)` becomes
  `ret = self.ngram_embedding_manager._maybe_prepare_ngram_embedding(ret)`
  (method privacy is preserved -- privacy flip is Ch2).

Usage:
    uv run --python 3.12 nem-migrate-maybe-prepare.py run
    uv run --python 3.12 nem-migrate-maybe-prepare.py verify
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
    append_to_file,
    cut_lines,
    find_method_lines,
    insert_after,
    replace_call_site,
)
from _runner import run_pr

ID = "nem-migrate-maybe-prepare"
SUBJECT = "Migrate _maybe_prepare_ngram_embedding to NgramEmbeddingManager (PR 2/3)"
BODY = ""
AREA = "mech_model_runner"
BASE = "tom_refactor_202605a/primary/mech_model_runner/introduce-ngram-embedding-mgr"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


def transform(wt: Path) -> None:
    sched = wt / "python/sglang/srt/managers/scheduler.py"
    manager = wt / "python/sglang/srt/layers/n_gram_embedding_manager.py"

    # The migrated body needs:
    #   - `ForwardMode` at runtime (from sglang.srt.managers.schedule_batch)
    #   - `Optional` at annotation time (typing) — added now since usage
    #     lands in this PR; if added in /43 ruff F401 would strip it.
    #   - `ScheduleBatch` at annotation time — TYPE_CHECKING block (same
    #     ruff-F401 reason).
    text = manager.read_text()
    text = text.replace(
        "from typing import TYPE_CHECKING\n",
        "from typing import TYPE_CHECKING, Optional\n",
    )
    text = insert_after(
        text,
        anchor="from sglang.jit_kernel.ngram_embedding import update_token_table\n",
        addition=(
            "from sglang.srt.managers.schedule_batch import ForwardMode\n"
        ),
    )
    text = insert_after(
        text,
        anchor="if TYPE_CHECKING:\n",
        addition=(
            "    from sglang.srt.managers.schedule_batch import ScheduleBatch\n"
        ),
    )
    manager.write_text(text)

    # ---- Cut _maybe_prepare_ngram_embedding from Scheduler. ----
    s, e = find_method_lines(
        sched.read_text(),
        class_name="Scheduler",
        method_name="_maybe_prepare_ngram_embedding",
    )
    method_text = cut_lines(sched, s, e)

    # Privacy flip exception (per EXECUTION_GUIDE): the leading underscore made
    # sense as a Scheduler-internal helper; on the new owner class it is the
    # public preparation API. Drop the underscore.
    method_text = method_text.replace(
        "def _maybe_prepare_ngram_embedding(",
        "def maybe_prepare_ngram_embedding(",
    )
    append_to_file(manager, method_text.rstrip() + "\n")

    # ---- Update Scheduler ----
    text = sched.read_text()

    # Add the manager-ref assignment to maybe_init_ngram_embedding -- prepend
    # the new line, keep the existing 4 field assignments untouched (Ch1
    # forbids deleting Scheduler fields here -- that is Ch2 work).
    text = replace_call_site(
        text,
        old=(
            "    def maybe_init_ngram_embedding(self):\n"
            "        self.use_ngram_embedding = self.tp_worker.model_config.use_ngram_embedding\n"
        ),
        new=(
            "    def maybe_init_ngram_embedding(self):\n"
            "        self.ngram_embedding_manager = self.tp_worker.model_runner.ngram_embedding_manager\n"
            "        self.use_ngram_embedding = self.tp_worker.model_config.use_ngram_embedding\n"
        ),
    )

    # Update the sole caller in Scheduler.run_batch (or wherever). The method
    # also drops its underscore prefix on extraction (privacy-flip exception).
    text = replace_call_site(
        text,
        old="self._maybe_prepare_ngram_embedding(",
        new="self.ngram_embedding_manager.maybe_prepare_ngram_embedding(",
    )

    sched.write_text(text)

    # Test fake fix: test_scheduler_chunked_req_gate.py constructs a partial
    # Scheduler via `__new__`, stubbing `_maybe_prepare_ngram_embedding` as a
    # MagicMock attribute. After /44, the call path is
    # `self.ngram_embedding_manager.maybe_prepare_ngram_embedding(...)` (note
    # the privacy flip), so the stub needs to be relocated.
    test_chunked = wt / "test/registered/unit/managers/test_scheduler_chunked_req_gate.py"
    text = test_chunked.read_text()
    text = replace_call_site(
        text,
        old=(
            "    s._maybe_prepare_ngram_embedding = MagicMock(side_effect=lambda batch: batch)\n"
        ),
        new=(
            "    s.ngram_embedding_manager = MagicMock()\n"
            "    s.ngram_embedding_manager.maybe_prepare_ngram_embedding = MagicMock(\n"
            "        side_effect=lambda batch: batch\n"
            "    )\n"
        ),
    )
    test_chunked.write_text(text)

if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        area_branch=AREA_BRANCH,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
