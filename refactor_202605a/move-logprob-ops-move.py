#!/usr/bin/env python3
"""Mechanical move of the 4 logprob staticmethods (now @staticmethod after
``move-logprob-ops-prep``) out of TokenizerManager into a new
``managers/tokenizer_manager_components/logprob_ops.py`` module.

Also cuts the module-level constant ``_INCREMENTAL_STREAMING_META_INFO_KEYS``
and module-level free fn ``_slice_streaming_output_meta_info`` from
tokenizer_manager.py and places them in the new module under their
public (no-underscore) names.

Per MECH_COMMIT_SPLIT: only physical relocation + scope-induced renames
(leading ``_`` loses meaning at module level; class-qualified names lose
their qualifier; ``add_logprob_to_meta_info`` -> ``fill_meta_info`` and
``convert_logprob_style`` -> ``absorb_recv`` follow the design rename).
The signature reshape + intra-method call rewrites already landed in
``move-logprob-ops-prep``.
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
    find_function_lines,
    find_method_lines,
    insert_after,
    replace_call_site,
)
from _runner import run_pr

ID = "move-logprob-ops-move"
SUBJECT = "Move 4 logprob staticmethods + slice helper to managers/tokenizer_manager_components/logprob_ops.py"
BODY = """\
Physical move only:
  - Cut 4 @staticmethod logprob methods from TokenizerManager
    (add_logprob_to_meta_info / convert_logprob_style /
    detokenize_logprob_tokens / detokenize_top_logprobs_tokens)
  - Cut module-level _INCREMENTAL_STREAMING_META_INFO_KEYS constant
  - Cut module-level _slice_streaming_output_meta_info free fn
  - Drop ``@staticmethod`` decorators; dedent bodies to module level
  - Renames (scope-induced + design):
      add_logprob_to_meta_info       -> fill_meta_info
      convert_logprob_style          -> absorb_recv
      detokenize_logprob_tokens      -> _detokenize_logprob_tokens
      detokenize_top_logprobs_tokens -> _detokenize_top_logprobs_tokens
      _INCREMENTAL_STREAMING_META_INFO_KEYS -> INCREMENTAL_STREAMING_META_INFO_KEYS
      _slice_streaming_output_meta_info     -> slice_streaming_output_meta_info
  - Add ``from sglang.srt.managers import logprob_ops`` import to TM
  - Update all call sites: ``TokenizerManager.<method>(`` -> ``logprob_ops.<new_name>(``
    (pure prefix replacement); ``_INCREMENTAL_STREAMING_META_INFO_KEYS`` ->
    ``logprob_ops.INCREMENTAL_STREAMING_META_INFO_KEYS``;
    ``_slice_streaming_output_meta_info(`` -> ``logprob_ops.slice_streaming_output_meta_info(``
"""
AREA = "mech_tokenizer_manager"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


HEADER = '''from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from sglang.srt.managers.io_struct import BatchStrOutput
from sglang.srt.managers.tokenizer_manager_components.request_state import ReqState

INCREMENTAL_STREAMING_META_INFO_KEYS = (
    "output_token_logprobs",
    "output_top_logprobs",
    "output_token_ids_logprobs",
)


def slice_streaming_output_meta_info(
    meta_info: Dict[Any, Any],
    last_output_offset: int,
) -> None:
    """Align output-side metadata with the current incremental streaming chunk."""
    for key in meta_info.keys() & set(INCREMENTAL_STREAMING_META_INFO_KEYS):
        meta_info[key] = meta_info[key][last_output_offset:]


'''


def _staticmethod_to_function(method_text: str, *, new_name: str, old_name: str) -> str:
    """Drop ``@staticmethod`` decorator, dedent body 4 spaces, rename ``def``.

    Also rewrites any cross-method ``TokenizerManager.<old>(`` references in the
    body to the new in-module names (pure prefix replacement, no body edits
    beyond the rename). The set of renames is fixed across all 4 methods.
    """
    function_text = method_text.replace("    @staticmethod\n", "", 1)
    function_text = dedent_method_to_function(function_text)
    function_text = function_text.replace(
        f"def {old_name}(", f"def {new_name}(", 1
    )
    # Intra-body cross-method call rewrites. After ``move-logprob-ops-prep``
    # these are all ``TokenizerManager.<old>(...)`` form.
    function_text = function_text.replace(
        "TokenizerManager.add_logprob_to_meta_info(", "fill_meta_info("
    )
    function_text = function_text.replace(
        "TokenizerManager.detokenize_logprob_tokens(", "_detokenize_logprob_tokens("
    )
    function_text = function_text.replace(
        "TokenizerManager.detokenize_top_logprobs_tokens(", "_detokenize_top_logprobs_tokens("
    )
    return function_text


def transform(wt: Path) -> None:
    tm = wt / "python/sglang/srt/managers/tokenizer_manager.py"
    new = wt / "python/sglang/srt/managers/tokenizer_manager_components/logprob_ops.py"

    # Cut bottom-up (highest line numbers first) so earlier ranges remain valid.
    s, e = find_method_lines(
        tm.read_text(),
        class_name="TokenizerManager",
        method_name="detokenize_top_logprobs_tokens",
    )
    detokenize_top_text = cut_lines(tm, s, e)

    s, e = find_method_lines(
        tm.read_text(),
        class_name="TokenizerManager",
        method_name="detokenize_logprob_tokens",
    )
    detokenize_text = cut_lines(tm, s, e)

    s, e = find_method_lines(
        tm.read_text(),
        class_name="TokenizerManager",
        method_name="convert_logprob_style",
    )
    convert_text = cut_lines(tm, s, e)

    s, e = find_method_lines(
        tm.read_text(),
        class_name="TokenizerManager",
        method_name="add_logprob_to_meta_info",
    )
    add_text = cut_lines(tm, s, e)

    # Cut module-level free fn (line-range cut).
    s, e = find_function_lines(tm.read_text(), function_name="_slice_streaming_output_meta_info")
    cut_lines(tm, s, e)

    # Cut the module-level constant block (no AST helper for module-level consts;
    # do it via line-range scan).
    text = tm.read_text()
    const_start_marker = "_INCREMENTAL_STREAMING_META_INFO_KEYS = (\n"
    idx = text.index(const_start_marker)
    end_marker = ")\n"
    end_idx = text.index(end_marker, idx) + len(end_marker)
    # Also drop the trailing blank line(s) so we don't leave a stray gap.
    while text[end_idx : end_idx + 1] == "\n":
        end_idx += 1
    text = text[:idx] + text[end_idx:]
    tm.write_text(text)

    # ===== Build the new module =====

    fill_meta_info_fn = _staticmethod_to_function(
        add_text, new_name="fill_meta_info", old_name="add_logprob_to_meta_info"
    )
    absorb_recv_fn = _staticmethod_to_function(
        convert_text, new_name="absorb_recv", old_name="convert_logprob_style"
    )
    detokenize_fn = _staticmethod_to_function(
        detokenize_text,
        new_name="_detokenize_logprob_tokens",
        old_name="detokenize_logprob_tokens",
    )
    detokenize_top_fn = _staticmethod_to_function(
        detokenize_top_text,
        new_name="_detokenize_top_logprobs_tokens",
        old_name="detokenize_top_logprobs_tokens",
    )

    new.write_text(
        HEADER
        + fill_meta_info_fn.rstrip()
        + "\n\n\n"
        + absorb_recv_fn.rstrip()
        + "\n\n\n"
        + detokenize_fn.rstrip()
        + "\n\n\n"
        + detokenize_top_fn.rstrip()
        + "\n"
    )

    # ===== Update tokenizer_manager.py: import + call sites =====
    text = tm.read_text()

    # Add the import (module-qualified per EXECUTION_GUIDE rule 6).
    text = insert_after(
        text,
        anchor="from sglang.srt.managers.async_dynamic_batch_tokenizer import AsyncDynamicbatchTokenizer\n",
        addition="from sglang.srt.managers.tokenizer_manager_components import logprob_ops\n",
    )

    # Intra-module-level callers for the cut constant + free fn.
    text = replace_call_site(
        text,
        old="for key in _INCREMENTAL_STREAMING_META_INFO_KEYS:",
        new="for key in logprob_ops.INCREMENTAL_STREAMING_META_INFO_KEYS:",
    )
    text = replace_call_site(
        text,
        old="_slice_streaming_output_meta_info(",
        new="logprob_ops.slice_streaming_output_meta_info(",
    )

    # Pure prefix replacements for the 4 methods (already in
    # ``TokenizerManager.<method>(`` form after the prep commit).
    text = replace_call_site(
        text,
        old="TokenizerManager.add_logprob_to_meta_info(",
        new="logprob_ops.fill_meta_info(",
    )
    text = replace_call_site(
        text,
        old="TokenizerManager.convert_logprob_style(",
        new="logprob_ops.absorb_recv(",
    )
    # NOTE: detokenize_logprob_tokens / detokenize_top_logprobs_tokens have NO
    # external callers in TM -- they're only called from within
    # add_logprob_to_meta_info (which itself was just cut from TM). So no
    # ``TokenizerManager.detokenize_*(`` references remain after the four method
    # bodies are removed.

    tm.write_text(text)


if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        area_branch=AREA_BRANCH,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
