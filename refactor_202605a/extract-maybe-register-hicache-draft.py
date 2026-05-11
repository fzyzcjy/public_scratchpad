#!/usr/bin/env python3
"""Cut `_maybe_register_hicache_draft` from Scheduler; paste as a free
function ``maybe_register_hicache_draft`` in the same
``scheduler_components/kv_cache.py`` (created by
``extract-get-draft-kv-pool``). Update the sole caller in ``Scheduler.__init__``.

- Method body (post-C1) calls ``kv_cache.get_draft_kv_pool(...)`` with module
  qualifier — that line stays as-is when the method moves into the same
  module (the ``kv_cache.`` qualifier becomes a self-reference but pyflakes
  doesn't object; we'll switch to bare ``get_draft_kv_pool(...)`` since it's
  in the same module).
- Body reads 7 self.X fields → 7 keyword-only kwargs:
  ``tree_cache, draft_worker, spec_algorithm, server_args,
  enable_hierarchical_cache, enable_overlap, page_size``.
- Privacy flip drops the leading ``_``.
- Sole caller is ``Scheduler.__init__`` line 454.

Usage:
    uv run --python 3.12 extract-maybe-register-hicache-draft.py run
    uv run --python 3.12 extract-maybe-register-hicache-draft.py verify
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

ID = "extract-maybe-register-hicache-draft"
SUBJECT = (
    "Extract _maybe_register_hicache_draft to scheduler_components/kv_cache.py"
)
BODY = """\
Move ``_maybe_register_hicache_draft`` off Scheduler into a free function
``maybe_register_hicache_draft`` in the same
``scheduler_components/kv_cache.py`` introduced for
``get_draft_kv_pool``. Body reads 7 self.X fields (tree_cache, draft_worker,
spec_algorithm, server_args, enable_hierarchical_cache, enable_overlap,
page_size) which become keyword-only parameters. Drop the underscore prefix
per the privacy convention for new module APIs. The sole caller in
``Scheduler.__init__`` is rewritten to a module-qualified call.

The body's existing ``kv_cache.get_draft_kv_pool(...)`` self-reference is
collapsed to a bare ``get_draft_kv_pool(...)`` since both functions now live
in the same module.

No behavior change.
"""
AREA = "mech_scheduler"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


def transform(wt: Path) -> None:
    sched = wt / "python/sglang/srt/managers/scheduler.py"
    kvc = wt / "python/sglang/srt/managers/scheduler_components/kv_cache.py"

    # Cut the method.
    s, e = find_method_lines(
        sched.read_text(),
        class_name="Scheduler",
        method_name="_maybe_register_hicache_draft",
    )
    method_text = cut_lines(sched, s, e)

    # Convert to free function:
    #   - dedent 4 spaces
    #   - drop ``_`` prefix on signature; replace ``self`` with 7 keyword-only kwargs
    #   - rewrite ``self.X`` reads to bare kwarg names
    #   - collapse the ``kv_cache.get_draft_kv_pool(...)`` self-qualifier to bare
    #     ``get_draft_kv_pool(...)`` since both live in the same module now
    function_text = dedent_method_to_function(method_text)
    function_text = function_text.replace(
        "def _maybe_register_hicache_draft(self) -> None:",
        "def maybe_register_hicache_draft(\n"
        "    *,\n"
        "    tree_cache,\n"
        "    draft_worker,\n"
        "    spec_algorithm,\n"
        "    server_args,\n"
        "    enable_hierarchical_cache: bool,\n"
        "    enable_overlap: bool,\n"
        "    page_size: int,\n"
        ") -> None:",
    )
    function_text = function_text.replace(
        "if not self.enable_hierarchical_cache:",
        "if not enable_hierarchical_cache:",
    )
    function_text = function_text.replace(
        "draft_kv_pool, _ = kv_cache.get_draft_kv_pool(",
        "draft_kv_pool, _ = get_draft_kv_pool(",
    )
    function_text = function_text.replace("self.draft_worker", "draft_worker")
    function_text = function_text.replace("self.spec_algorithm", "spec_algorithm")
    function_text = function_text.replace("self.server_args", "server_args")
    function_text = function_text.replace("self.enable_overlap", "enable_overlap")
    function_text = function_text.replace("self.page_size", "page_size")
    function_text = function_text.replace("self.tree_cache", "tree_cache")

    append_to_file(kvc, function_text)

    # The new function calls ``logger.warning(...)``; introduce a module logger.
    kvc_text = kvc.read_text()
    kvc_text = insert_after(
        kvc_text,
        anchor="from typing import Any, Optional, Tuple\n",
        addition="\nimport logging\n\nlogger = logging.getLogger(__name__)\n",
    )
    kvc.write_text(kvc_text)

    # Rewrite the sole caller in Scheduler.__init__.
    text = sched.read_text()
    text = replace_call_site(
        text,
        old="        # Register draft KV pool (when spec + HiCache co-enabled).\n"
        "        self._maybe_register_hicache_draft()\n",
        new=(
            "        # Register draft KV pool (when spec + HiCache co-enabled).\n"
            "        kv_cache.maybe_register_hicache_draft(\n"
            "            tree_cache=self.tree_cache,\n"
            "            draft_worker=self.draft_worker,\n"
            "            spec_algorithm=self.spec_algorithm,\n"
            "            server_args=self.server_args,\n"
            "            enable_hierarchical_cache=self.enable_hierarchical_cache,\n"
            "            enable_overlap=self.enable_overlap,\n"
            "            page_size=self.page_size,\n"
            "        )\n"
        ),
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
