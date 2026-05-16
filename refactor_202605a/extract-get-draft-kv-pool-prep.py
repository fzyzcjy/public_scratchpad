#!/usr/bin/env python3
"""Inplace prep step for ``extract-get-draft-kv-pool``: in Scheduler, convert
``_get_draft_kv_pool(self)`` to ``@staticmethod get_draft_kv_pool(*, kwargs)``
and rewrite 2 callers to class-qualified ``Scheduler.get_draft_kv_pool(...)``.

Body rewrite (``self.X`` → bare ``X``) is the minimal "脱钩 self" change
needed to make the method statically callable. The method **stays in
Scheduler** in this commit; the physical move to ``kv_cache.py`` happens in
``extract-get-draft-kv-pool-move``.

After this commit, scheduler.py contains a `@staticmethod` whose body bytes
will be byte-equivalent (mod dedent + decorator) to the body in the target
module after ``extract-get-draft-kv-pool-move``.
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

ID = "extract-get-draft-kv-pool-prep"
SUBJECT = "Decouple _get_draft_kv_pool from self before extraction"
BODY = """\
Inplace prep step for the ``extract-get-draft-kv-pool`` mech move.

In Scheduler, ``_get_draft_kv_pool(self)`` becomes
``@staticmethod get_draft_kv_pool(*, draft_worker, spec_algorithm,
server_args, enable_overlap)``. The ``self.X`` reads in the body become
bare kwarg names. Privacy underscore dropped for the upcoming module-level
public API.

The callsites in Scheduler are updated to the class-qualified form
``Scheduler.get_draft_kv_pool(draft_worker=self.draft_worker, ...)``.

The method stays inside Scheduler. The physical cut + paste to
``mem_cache/kv_cache_builder.py`` happens in
``extract-get-draft-kv-pool-move``.
"""
AREA = "mech_scheduler"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


NEW_SIGNATURE = (
    "    @staticmethod\n"
    "    def get_draft_kv_pool(\n"
    "        *,\n"
    "        draft_worker: \"BaseTpWorker\",\n"
    "        spec_algorithm: SpeculativeAlgorithm,\n"
    "        server_args: ServerArgs,\n"
    "        enable_overlap: bool,\n"
    "    ):"
)


CALLER_NEW = (
    "{lhs} = Scheduler.get_draft_kv_pool(\n"
    "            draft_worker=self.draft_worker,\n"
    "            spec_algorithm=self.spec_algorithm,\n"
    "            server_args=self.server_args,\n"
    "            enable_overlap=self.enable_overlap,\n"
    "        )\n"
)


def transform(wt: Path) -> None:
    sched = wt / "python/sglang/srt/managers/scheduler.py"
    text = sched.read_text()

    # Locate method in Scheduler.
    s, e = find_method_lines(
        text, class_name="Scheduler", method_name="_get_draft_kv_pool"
    )
    lines = text.splitlines(keepends=True)
    method_text = "".join(lines[s:e])

    # Rewrite signature + body (within method scope only).
    new_method = method_text.replace(
        "    def _get_draft_kv_pool(self):", NEW_SIGNATURE
    )
    for field in ("draft_worker", "spec_algorithm", "enable_overlap", "server_args"):
        new_method = new_method.replace(f"self.{field}", field)

    text = "".join(lines[:s]) + new_method + "".join(lines[e:])

    # Rewrite 2 callers.
    for old_lhs in (
        "        draft_kv_pool, _",
        "        draft_token_to_kv_pool, model_config",
    ):
        old = f"{old_lhs} = self._get_draft_kv_pool()\n"
        new = CALLER_NEW.format(lhs=old_lhs)
        if old not in text:
            raise ValueError(f"caller anchor not found: {old!r}")
        text = text.replace(old, new)

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
