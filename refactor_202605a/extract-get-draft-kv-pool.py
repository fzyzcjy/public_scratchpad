#!/usr/bin/env python3
"""Cut `_get_draft_kv_pool` method from Scheduler; paste as a free function
``get_draft_kv_pool`` in ``mem_cache/kv_cache_builder.py`` (new
package). Update 2 callers and add an import.

- Method body reads 4 self.X fields (`draft_worker`, `spec_algorithm`,
  `enable_overlap`, `server_args`); these become explicit kwargs on the free
  function. Privacy flip drops the leading ``_``.
- Two callsites in ``Scheduler``: ``_maybe_register_hicache_draft`` (1 call)
  and ``init_disaggregation`` (1 call). Both rewritten to module-qualified
  ``kv_cache_builder.get_draft_kv_pool(...)`` per EXECUTION_GUIDE item 6.

Usage:
    uv run --python 3.12 extract-get-draft-kv-pool.py run
    uv run --python 3.12 extract-get-draft-kv-pool.py verify
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
    cut_lines,
    dedent_method_to_function,
    find_method_lines,
    insert_after,
    replace_call_site,
)
from _runner import run_pr

ID = "extract-get-draft-kv-pool"
SUBJECT = "Extract _get_draft_kv_pool to mem_cache/kv_cache_builder.py"
BODY = """\
Move ``_get_draft_kv_pool`` off Scheduler into a new free function
``get_draft_kv_pool`` in
``python/sglang/srt/mem_cache/kv_cache_builder.py``. Body is
unchanged except ``self.X`` reads (4 fields: draft_worker, spec_algorithm,
enable_overlap, server_args) become keyword-only parameters. Drop the
underscore prefix per the privacy convention for methods that move out to a
new module's public API. Two callers (``_maybe_register_hicache_draft`` and
``init_disaggregation``) updated to module-qualified calls.

No behavior change.
"""
AREA = "mech_scheduler"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


HEADER = '''from __future__ import annotations

from typing import Any, Optional, Tuple


'''


def transform(wt: Path) -> None:
    sched = wt / "python/sglang/srt/managers/scheduler.py"
    pkg_init = wt / "python/sglang/srt/managers/scheduler_components/__init__.py"
    setup_init = wt / "python/sglang/srt/managers/scheduler_components/__init__.py"
    kvc = wt / "python/sglang/srt/mem_cache/kv_cache_builder.py"

    # Create the new package skeleton.
    pkg_init.parent.mkdir(parents=True, exist_ok=True)
    setup_init.parent.mkdir(parents=True, exist_ok=True)
    pkg_init.write_text("")
    setup_init.write_text("")

    # Cut the method from Scheduler.
    s, e = find_method_lines(
        sched.read_text(),
        class_name="Scheduler",
        method_name="_get_draft_kv_pool",
    )
    method_text = cut_lines(sched, s, e)

    # Convert method to free function:
    #   - dedent 4 spaces (method body becomes module-level body)
    #   - replace signature: drop leading underscore + self -> 4 keyword-only kwargs
    #   - rewrite self.X reads to bare kwarg names
    function_text = dedent_method_to_function(method_text)
    function_text = function_text.replace(
        "def _get_draft_kv_pool(self):",
        "def get_draft_kv_pool(\n"
        "    *,\n"
        "    draft_worker,\n"
        "    spec_algorithm,\n"
        "    server_args,\n"
        "    enable_overlap: bool,\n"
        ") -> Tuple[Optional[Any], Optional[Any]]:",
    )
    function_text = function_text.replace("self.draft_worker", "draft_worker")
    function_text = function_text.replace("self.spec_algorithm", "spec_algorithm")
    function_text = function_text.replace("self.enable_overlap", "enable_overlap")
    function_text = function_text.replace("self.server_args", "server_args")

    kvc.write_text(HEADER + function_text)

    # Rewrite the 2 callers.
    text = sched.read_text()
    text = replace_call_site(
        text,
        old="        draft_kv_pool, _ = self._get_draft_kv_pool()\n",
        new=(
            "        draft_kv_pool, _ = kv_cache_builder.get_draft_kv_pool(\n"
            "            draft_worker=self.draft_worker,\n"
            "            spec_algorithm=self.spec_algorithm,\n"
            "            server_args=self.server_args,\n"
            "            enable_overlap=self.enable_overlap,\n"
            "        )\n"
        ),
    )
    text = replace_call_site(
        text,
        old="        draft_token_to_kv_pool, model_config = self._get_draft_kv_pool()\n",
        new=(
            "        draft_token_to_kv_pool, model_config = kv_cache_builder.get_draft_kv_pool(\n"
            "            draft_worker=self.draft_worker,\n"
            "            spec_algorithm=self.spec_algorithm,\n"
            "            server_args=self.server_args,\n"
            "            enable_overlap=self.enable_overlap,\n"
            "        )\n"
        ),
    )

    # Add import. Anchor: any nearby existing scheduler-internal import. We pick a
    # very stable anchor — the line for `scheduler_input_blocker`, which sits in
    # the alphabetically-sorted scheduler_* import block.
    text = insert_after(
        text,
        anchor="from sglang.srt.managers.scheduler_input_blocker import SchedulerInputBlocker\n",
        addition="from sglang.srt.mem_cache import kv_cache_builder\n",
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
