#!/usr/bin/env python3
"""Mechanical move for ``extract-maybe-register-hicache-draft``: cut the
@staticmethod from Scheduler, append to ``scheduler_components/kv_cache.py``
(file already exists from the prior ``-move`` commit). Drop ``@staticmethod``,
dedent 4 spaces, collapse self-module qualifier
(``kv_cache.get_draft_kv_pool`` → ``get_draft_kv_pool``), add module logger,
rewrite caller.

Deviation from strict byte-equivalence: 1 line in the body changes due to
the self-qualifier collapse (the method now lives in the same module as
``get_draft_kv_pool``). All other body lines are byte-equivalent to the
prep state modulo dedent + decorator removal.
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
    dedent_method_to_function,
    find_method_lines,
    insert_after,
    replace_call_site,
)
from _runner import run_pr

ID = "extract-maybe-register-hicache-draft-move"
SUBJECT = "Move maybe_register_hicache_draft to scheduler_components/kv_cache.py"
BODY = """\
Mechanical cut + paste for the ``extract-maybe-register-hicache-draft``
mech move.

Cut ``Scheduler.maybe_register_hicache_draft`` (@staticmethod after the
prep commit) and append to ``scheduler_components/kv_cache.py``. Drop
``@staticmethod`` decorator; dedent body to module level. Collapse
self-module qualifier ``kv_cache.get_draft_kv_pool(...)`` → bare
``get_draft_kv_pool(...)`` since both functions now live in the same
module.

Add a module logger to ``kv_cache.py`` (the moved function calls
``logger.warning(...)``).

Sole caller in ``Scheduler.__init__`` updated from
``Scheduler.maybe_register_hicache_draft(...)`` →
``kv_cache.maybe_register_hicache_draft(...)`` (pure prefix replacement).
"""
AREA = "mech_scheduler"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


def transform(wt: Path) -> None:
    sched = wt / "python/sglang/srt/managers/scheduler.py"
    kvc = wt / "python/sglang/srt/managers/scheduler_components/kv_cache.py"

    # Cut the @staticmethod from Scheduler.
    s, e = find_method_lines(
        sched.read_text(),
        class_name="Scheduler",
        method_name="maybe_register_hicache_draft",
    )
    method_text = cut_lines(sched, s, e)

    # Drop @staticmethod decorator; dedent.
    function_text = method_text.replace("    @staticmethod\n", "", 1)
    function_text = dedent_method_to_function(function_text)

    # Self-module qualifier collapse.
    function_text = function_text.replace(
        "kv_cache.get_draft_kv_pool(", "get_draft_kv_pool("
    )

    append_to_file(kvc, function_text)

    # The moved function calls logger.warning(...); introduce module logger.
    kvc_text = kvc.read_text()
    kvc_text = insert_after(
        kvc_text,
        anchor="from __future__ import annotations\n",
        addition="\nimport logging\n\nlogger = logging.getLogger(__name__)\n",
    )
    kvc.write_text(kvc_text)

    # Rewrite caller (pure prefix replace).
    text = sched.read_text()
    text = replace_call_site(
        text,
        old="Scheduler.maybe_register_hicache_draft(",
        new="kv_cache.maybe_register_hicache_draft(",
    )
    sched.write_text(text)


if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        area_branch=AREA_BRANCH,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
