#!/usr/bin/env python3
"""Inplace prep for ``extract-maybe-register-hicache-draft``: in Scheduler,
convert ``_maybe_register_hicache_draft(self)`` to a @staticmethod with 7
keyword-only kwargs. Rewrite sole caller to class-qualified form.

The method **stays in Scheduler** in this commit. The physical move happens
in ``extract-maybe-register-hicache-draft-move``.

Body bytes (post-prep) will be byte-equivalent to body bytes in
``kv_cache.py`` after the move, modulo dedent + decorator removal and one
self-qualifier collapse (``kv_cache.get_draft_kv_pool`` → ``get_draft_kv_pool``,
documented in the move commit).
"""

# /// script
# requires-python = ">=3.10"
# dependencies = ["typer"]
# ///

import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from _helpers import find_method_lines
from _runner import run_pr

ID = "extract-maybe-register-hicache-draft-prep"
SUBJECT = "Convert _maybe_register_hicache_draft to @staticmethod (prep for move)"
BODY = """\
Inplace prep for the ``extract-maybe-register-hicache-draft`` mech move.

In Scheduler, ``_maybe_register_hicache_draft(self) -> None`` becomes
``@staticmethod maybe_register_hicache_draft(*, tree_cache, draft_worker,
spec_algorithm, server_args, enable_hierarchical_cache, enable_overlap,
page_size) -> None``. The 7 ``self.X`` reads become bare kwarg names.
Privacy underscore dropped for the upcoming module-level public API.

Sole callsite ``Scheduler.__init__`` rewritten to class-qualified form.

The method stays inside Scheduler; physical cut + paste to
``scheduler_components/kv_cache.py`` happens in the move commit.
"""
AREA = "mech_scheduler"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


NEW_SIGNATURE = (
    "    @staticmethod\n"
    "    def maybe_register_hicache_draft(\n"
    "        *,\n"
    "        tree_cache,\n"
    "        draft_worker,\n"
    "        spec_algorithm,\n"
    "        server_args,\n"
    "        enable_hierarchical_cache: bool,\n"
    "        enable_overlap: bool,\n"
    "        page_size: int,\n"
    "    ) -> None:"
)


FIELDS = (
    "tree_cache",
    "draft_worker",
    "spec_algorithm",
    "server_args",
    "enable_hierarchical_cache",
    "enable_overlap",
    "page_size",
)


def transform(wt: Path) -> None:
    sched = wt / "python/sglang/srt/managers/scheduler.py"
    text = sched.read_text()

    s, e = find_method_lines(
        text, class_name="Scheduler", method_name="_maybe_register_hicache_draft"
    )
    lines = text.splitlines(keepends=True)
    method_text = "".join(lines[s:e])

    new_method = method_text.replace(
        "    def _maybe_register_hicache_draft(self) -> None:", NEW_SIGNATURE
    )
    for field in FIELDS:
        new_method = new_method.replace(f"self.{field}", field)

    text = "".join(lines[:s]) + new_method + "".join(lines[e:])

    # Rewrite sole caller.
    text = text.replace(
        "        # Register draft KV pool (when spec + HiCache co-enabled).\n"
        "        self._maybe_register_hicache_draft()\n",
        "        # Register draft KV pool (when spec + HiCache co-enabled).\n"
        "        Scheduler.maybe_register_hicache_draft(\n"
        "            tree_cache=self.tree_cache,\n"
        "            draft_worker=self.draft_worker,\n"
        "            spec_algorithm=self.spec_algorithm,\n"
        "            server_args=self.server_args,\n"
        "            enable_hierarchical_cache=self.enable_hierarchical_cache,\n"
        "            enable_overlap=self.enable_overlap,\n"
        "            page_size=self.page_size,\n"
        "        )\n",
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
