#!/usr/bin/env python3
"""Reproducible transform for PR #26548.

Extract ``ScheduleBatch.release_req`` and ``ScheduleBatch.retract_all`` as
module-level free functions in ``schedule_batch.py``. The methods stay
behind as one-line wrappers that forward to the free functions.

Pure cut-paste: the *bodies* of the new free functions are derived from
the existing method bodies via AST-located range cut + a handful of text
substitutions (``self.X`` → ``X`` for the four dependency attributes,
and an inner-call rewrite for ``retract_all``). The only fresh text in
this script is the new free-function signatures and the wrapper method
bodies, both of which are necessarily new wiring code.

Run from the sglang repo root:

    python3 transform-release-req-free-func.py
"""

# /// script
# requires-python = ">=3.10"
# ///

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from _helpers import (  # noqa: E402
    dedent_method_to_function,
    find_method_lines,
    replace_call_site,
)

SKILL_PATH = (
    Path("/Users/tom/main/workspaces/ws-main/worktrees/sglang-dev-c")
    / ".claude/skills/mechanical-refactor-verify"
)
sys.path.insert(0, str(SKILL_PATH))
from mechanical_refactor_verify_utils import (  # noqa: E402
    git_add_and_commit,
    verify_mechanical_refactor,
)

BASE_COMMIT = "a34e245c12"
TARGET_COMMIT = "cb5d1b88a9"

SRC_REL = "python/sglang/srt/managers/schedule_batch.py"

CLASS_ANCHOR = (
    "@dataclasses.dataclass\nclass ScheduleBatch(ScheduleBatchDisaggregationDecodeMixin):"
)

FREE_RELEASE_REQ_SIG = """\
def release_req(
    *,
    req: Req,
    remaing_req_count: int,
    server_args: ServerArgs,
    req_to_token_pool: ReqToTokenPool,
    token_to_kv_pool_allocator: BaseTokenToKVPoolAllocator,
    tree_cache: BasePrefixCache,
    hisparse_coordinator: Optional[HiSparseCoordinator],
) -> None:
"""

FREE_RETRACT_ALL_SIG = """\
def retract_all(
    *,
    reqs: List[Req],
    server_args: ServerArgs,
    req_to_token_pool: ReqToTokenPool,
    token_to_kv_pool_allocator: BaseTokenToKVPoolAllocator,
    tree_cache: BasePrefixCache,
    hisparse_coordinator: Optional[HiSparseCoordinator],
) -> List[Req]:
"""

# Trailing blank line preserved to match the original method block's
# in-class spacing (``find_method_lines`` includes the blank separator
# before the next method).
NEW_RELEASE_REQ_WRAPPER = """\
    def release_req(self, idx: int, remaing_req_count: int, server_args: ServerArgs):
        release_req(
            req=self.reqs[idx],
            remaing_req_count=remaing_req_count,
            server_args=server_args,
            req_to_token_pool=self.req_to_token_pool,
            token_to_kv_pool_allocator=self.token_to_kv_pool_allocator,
            tree_cache=self.tree_cache,
            hisparse_coordinator=self.hisparse_coordinator,
        )

"""

NEW_RETRACT_ALL_WRAPPER = """\
    def retract_all(self, server_args: ServerArgs):
        retracted_reqs = retract_all(
            reqs=self.reqs,
            server_args=server_args,
            req_to_token_pool=self.req_to_token_pool,
            token_to_kv_pool_allocator=self.token_to_kv_pool_allocator,
            tree_cache=self.tree_cache,
            hisparse_coordinator=self.hisparse_coordinator,
        )
        self.reqs = []
        return retracted_reqs

"""

# Inner call rewrite for ``retract_all``'s loop body: the single-line
# ``self.release_req(idx, ...)`` becomes a multi-line keyword-arg call.
OLD_INNER_CALL = (
    "            self.release_req(idx, len(reqs) - idx, server_args)\n"
)
NEW_INNER_CALL = (
    "            release_req(\n"
    "                req=reqs[idx],\n"
    "                remaing_req_count=len(reqs) - idx,\n"
    "                server_args=server_args,\n"
    "                req_to_token_pool=req_to_token_pool,\n"
    "                token_to_kv_pool_allocator=token_to_kv_pool_allocator,\n"
    "                tree_cache=tree_cache,\n"
    "                hisparse_coordinator=hisparse_coordinator,\n"
    "            )\n"
)

# Order: ``reqs`` last so the substring ``self.reqs`` is rewritten *after*
# the inner-call rewrite (which still relies on ``self.release_req``).
SELF_ATTRS_FOR_RELEASE_REQ = (
    "hisparse_coordinator",
    "req_to_token_pool",
    "token_to_kv_pool_allocator",
    "tree_cache",
)


def _extract_method_block(text: str, *, method_name: str) -> str:
    s, e = find_method_lines(text, class_name="ScheduleBatch", method_name=method_name)
    lines = text.splitlines(keepends=True)
    return "".join(lines[s:e])


def _free_release_req(method_text: str) -> str:
    body = method_text.split("\n", 1)[1]
    body = body.replace("        req = self.reqs[idx]\n\n", "", 1)
    for attr in SELF_ATTRS_FOR_RELEASE_REQ:
        body = body.replace(f"self.{attr}", attr)
    body = dedent_method_to_function(body)
    return FREE_RELEASE_REQ_SIG + body


def _free_retract_all(method_text: str) -> str:
    body = method_text.split("\n", 1)[1]
    # Substitute ``self.reqs`` first so the inner call appears as
    # ``self.release_req(idx, len(reqs) - idx, server_args)`` ready for
    # the OLD_INNER_CALL → NEW_INNER_CALL rewrite below.
    body = body.replace("self.reqs", "reqs")
    body = body.replace(OLD_INNER_CALL, NEW_INNER_CALL, 1)
    # Drop the ``reqs = []`` line plus the blank line before it (the
    # list-clearing stays on the wrapper method, not the free function).
    body = body.replace("\n        reqs = []\n", "", 1)
    body = dedent_method_to_function(body)
    return FREE_RETRACT_ALL_SIG + body


def transform(dir_root: Path) -> None:
    src = dir_root / SRC_REL
    text = src.read_text()

    release_req_method = _extract_method_block(text, method_name="release_req")
    retract_all_method = _extract_method_block(text, method_name="retract_all")

    free_release_req = _free_release_req(release_req_method)
    free_retract_all = _free_retract_all(retract_all_method)

    text = replace_call_site(text, old=release_req_method, new=NEW_RELEASE_REQ_WRAPPER)
    text = replace_call_site(text, old=retract_all_method, new=NEW_RETRACT_ALL_WRAPPER)

    # Insert free functions right before the ``ScheduleBatch`` class.
    # Bodies returned by ``_free_X`` already end with ``\\n\\n`` (the method
    # block's trailing blank, dedented). Adding one more ``\\n`` between
    # them and before the class yields the standard 2-blank-line PEP 8
    # spacing.
    insertion = free_release_req + "\n" + free_retract_all + "\n"
    text = replace_call_site(text, old=CLASS_ANCHOR, new=insertion + CLASS_ANCHOR)

    src.write_text(text)

    git_add_and_commit(
        "Extract release_req and retract_all as module-level free functions",
        cwd=str(dir_root),
    )


if __name__ == "__main__":
    verify_mechanical_refactor(
        base_commit=BASE_COMMIT,
        target_commit=TARGET_COMMIT,
        transform=transform,
    )
