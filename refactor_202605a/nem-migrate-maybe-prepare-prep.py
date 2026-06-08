#!/usr/bin/env python3
"""Prep stage for nem-migrate-maybe-prepare (MECH_COMMIT_SPLIT §"split-class scenario"):

Reshape ``Scheduler._maybe_prepare_ngram_embedding`` toward becoming a
``NgramEmbeddingManager`` method named ``prepare_for_forward`` (combining
privacy flip + nem-mech-rename in one step at extraction time).

- ``@staticmethod`` + ``self: NgramEmbeddingManager``.
- Body subs reflect manager's renamed fields:
  ``self.use_ngram_embedding`` → ``self.enabled``, ``self.token_table`` →
  ``self.table``, ``self.ngram_embedding_n`` → ``self.n``.
- Scheduler caller: ``self._maybe_prepare_ngram_embedding(ret)`` →
  ``Scheduler.prepare_for_forward(self.ngram_embedding_manager, ret)``.
- ``Scheduler.maybe_init_ngram_embedding`` gains a manager-ref line.
- Test mock: relocate.
"""

# /// script
# requires-python = ">=3.10"
# dependencies = ["typer"]
# ///

import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from _helpers import find_method_lines, replace_call_site
from _runner import run_pr

ID = "nem-migrate-maybe-prepare-prep"
SUBJECT = "Prep _maybe_prepare_ngram_embedding for move onto NgramEmbeddingManager"
BODY = ""
AREA = "mech_model_runner"
BASE = "tom_refactor_202605a/primary/mech_model_runner/introduce-ngram-embedding-mgr"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


def transform(wt: Path) -> None:
    sched = wt / "python/sglang/srt/managers/scheduler.py"
    test_chunked = wt / "test/registered/unit/managers/test_scheduler_chunked_req_gate.py"

    # Reshape Scheduler's method in place.
    text = sched.read_text()
    start, end = find_method_lines(
        text, class_name="Scheduler", method_name="_maybe_prepare_ngram_embedding"
    )
    lines = text.splitlines(keepends=True)
    method = "".join(lines[start:end])
    # Signature swap + rename (privacy flip + nem-mech-rename combined).
    # The body's first arg is ``self, batch: ...`` on one line.
    method = method.replace(
        "    def _maybe_prepare_ngram_embedding(\n        self, batch: Optional[ScheduleBatch]\n    )",
        "    @staticmethod\n    def prepare_for_forward(\n        self: \"NgramEmbeddingManager\", batch: Optional[ScheduleBatch]\n    )",
        1,
    )
    # Body field renames (manager already uses renamed fields).
    method = method.replace("self.use_ngram_embedding", "self.enabled")
    method = method.replace("self.token_table", "self.table")
    method = method.replace("self.ngram_embedding_n", "self.n")
    text = "".join(lines[:start]) + method + "".join(lines[end:])

    # maybe_init_ngram_embedding gains the manager-ref line.
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

    # Scheduler caller: class-qualified.
    text = replace_call_site(
        text,
        old="self._maybe_prepare_ngram_embedding(",
        new="Scheduler.prepare_for_forward(self.ngram_embedding_manager, ",
    )

    sched.write_text(text)

    # Test mock relocate.
    text = test_chunked.read_text()
    text = replace_call_site(
        text,
        old=(
            "    s._maybe_prepare_ngram_embedding = MagicMock(side_effect=lambda batch: batch)\n"
        ),
        new=(
            "    s.ngram_embedding_manager = MagicMock()\n"
            "    s.ngram_embedding_manager.prepare_for_forward = MagicMock(\n"
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
