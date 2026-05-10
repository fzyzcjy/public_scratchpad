#!/usr/bin/env python3
"""Move 4 logprob methods + 1 module-level free fn + 1 module-level constant
out of tokenizer_manager.py into a new ``managers/logprob_ops.py`` module.
The four methods become free functions; ``self.tokenizer`` reads become an
explicit ``tokenizer`` kwarg. Constants/free-fn drop the leading underscore
(privacy-flip allowed when private helper becomes new module's public API).
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
    find_function_lines,
    find_method_lines,
    insert_after,
    replace_call_site,
)
from _runner import run_pr

ID = "move-logprob-ops"
SUBJECT = "Move logprob processing to managers/logprob_ops.py"
BODY = """\
Move 4 logprob methods (add_logprob_to_meta_info / convert_logprob_style /
detokenize_logprob_tokens / detokenize_top_logprobs_tokens), the module-level
constant _INCREMENTAL_STREAMING_META_INFO_KEYS, and the module-level free
function _slice_streaming_output_meta_info from tokenizer_manager.py to a
new managers/logprob_ops.py module.

Renames per design (privacy flip exception: private helper -> new module
public API):
  add_logprob_to_meta_info       -> fill_meta_info
  convert_logprob_style          -> absorb_recv
  detokenize_logprob_tokens      -> _detokenize_logprob_tokens (module-private)
  detokenize_top_logprobs_tokens -> _detokenize_top_logprobs_tokens
  _INCREMENTAL_STREAMING_META_INFO_KEYS -> INCREMENTAL_STREAMING_META_INFO_KEYS
  _slice_streaming_output_meta_info     -> slice_streaming_output_meta_info

self.tokenizer reads become a tokenizer kwarg. No behavior change.
"""
AREA = "mech_tokenizer_manager"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


HEADER = '''from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from sglang.srt.managers.io_struct import BatchStrOutput
from sglang.srt.managers.request_state import ReqState

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


def transform(wt: Path) -> None:
    tm = wt / "python/sglang/srt/managers/tokenizer_manager.py"
    new = wt / "python/sglang/srt/managers/logprob_ops.py"

    # Cut bottom-up so earlier line ranges stay valid.
    s, e = find_method_lines(
        tm.read_text(), class_name="TokenizerManager", method_name="detokenize_top_logprobs_tokens"
    )
    detokenize_top_text = cut_lines(tm, s, e)

    s, e = find_method_lines(
        tm.read_text(), class_name="TokenizerManager", method_name="detokenize_logprob_tokens"
    )
    detokenize_text = cut_lines(tm, s, e)

    s, e = find_method_lines(
        tm.read_text(), class_name="TokenizerManager", method_name="convert_logprob_style"
    )
    convert_text = cut_lines(tm, s, e)

    s, e = find_method_lines(
        tm.read_text(), class_name="TokenizerManager", method_name="add_logprob_to_meta_info"
    )
    add_text = cut_lines(tm, s, e)

    # Module-level free fn + constant cut last (line numbers smaller).
    s, e = find_function_lines(tm.read_text(), function_name="_slice_streaming_output_meta_info")
    cut_lines(tm, s, e)  # discard — we provide a renamed version in HEADER

    # Cut the constant block (no AST helper for module-level const; do it via line-range scan).
    text = tm.read_text()
    const_start_marker = '_INCREMENTAL_STREAMING_META_INFO_KEYS = (\n'
    idx = text.index(const_start_marker)
    end_marker = ')\n'
    end_idx = text.index(end_marker, idx) + len(end_marker)
    # Also drop the trailing blank line so we don't leave a stray gap.
    while text[end_idx:end_idx + 1] == "\n":
        end_idx += 1
    text = text[:idx] + text[end_idx:]
    tm.write_text(text)

    # ===== Build the new module =====

    # add_logprob_to_meta_info -> fill_meta_info
    fill_meta_info = dedent_method_to_function(add_text)
    fill_meta_info = fill_meta_info.replace(
        "def add_logprob_to_meta_info(\n    self,\n    meta_info: dict,\n    state: ReqState,\n    top_logprobs_num: int,\n    token_ids_logprob: List[int],\n    return_text_in_logprobs: bool,\n):",
        "def fill_meta_info(\n    meta_info: dict,\n    state: ReqState,\n    *,\n    top_logprobs_num: int,\n    token_ids_logprob: Optional[List[int]],\n    return_text_in_logprobs: bool,\n    tokenizer: Optional[Any],\n) -> None:",
    )
    fill_meta_info = fill_meta_info.replace(
        "self.detokenize_logprob_tokens(",
        "_detokenize_logprob_tokens(",
    )
    fill_meta_info = fill_meta_info.replace(
        "self.detokenize_top_logprobs_tokens(",
        "_detokenize_top_logprobs_tokens(",
    )
    # The two _detokenize_*_tokens calls take `decode_to_text` positionally as
    # the third arg in the old form. Convert each call's last positional arg
    # `return_text_in_logprobs,` to keyword args so the new (kw-only) signature
    # is satisfied. Use regex to be agnostic of indentation/whitespace.
    import re as _re
    fill_meta_info = _re.sub(
        r"^(\s+)return_text_in_logprobs,\s*\n",
        lambda m: f"{m.group(1)}decode_to_text=return_text_in_logprobs,\n{m.group(1)}tokenizer=tokenizer,\n",
        fill_meta_info,
        flags=_re.MULTILINE,
    )

    # convert_logprob_style -> absorb_recv
    absorb_recv = dedent_method_to_function(convert_text)
    absorb_recv = absorb_recv.replace(
        "def convert_logprob_style(\n    self,\n    meta_info: dict,\n    state: ReqState,\n    top_logprobs_num: int,\n    token_ids_logprob: List[int],\n    return_text_in_logprobs: bool,\n    recv_obj: BatchStrOutput,\n    recv_obj_index: int,\n):",
        "def absorb_recv(\n    meta_info: dict,\n    state: ReqState,\n    *,\n    top_logprobs_num: int,\n    token_ids_logprob: Optional[List[int]],\n    return_text_in_logprobs: bool,\n    recv_obj: BatchStrOutput,\n    recv_obj_index: int,\n    tokenizer: Optional[Any],\n) -> None:",
    )
    # Replace the trailing self.add_logprob_to_meta_info(...) call (positional args)
    # with fill_meta_info(...) using kwargs for the new keyword-only params.
    absorb_recv = absorb_recv.replace(
        "    self.add_logprob_to_meta_info(\n"
        "        meta_info,\n"
        "        state,\n"
        "        state.obj.top_logprobs_num,\n"
        "        state.obj.token_ids_logprob,\n"
        "        return_text_in_logprobs,\n"
        "    )\n",
        "    fill_meta_info(\n"
        "        meta_info,\n"
        "        state,\n"
        "        top_logprobs_num=state.obj.top_logprobs_num,\n"
        "        token_ids_logprob=state.obj.token_ids_logprob,\n"
        "        return_text_in_logprobs=return_text_in_logprobs,\n"
        "        tokenizer=tokenizer,\n"
        "    )\n",
    )

    # detokenize_logprob_tokens -> _detokenize_logprob_tokens
    detokenize = dedent_method_to_function(detokenize_text)
    detokenize = detokenize.replace(
        "def detokenize_logprob_tokens(\n    self,\n    token_logprobs_val: List[float],\n    token_logprobs_idx: List[int],\n    decode_to_text: bool,\n):",
        "def _detokenize_logprob_tokens(\n    token_logprobs_val: List[float],\n    token_logprobs_idx: List[int],\n    *,\n    decode_to_text: bool,\n    tokenizer: Optional[Any],\n) -> List[Tuple[float, int, Optional[str]]]:",
    )
    detokenize = detokenize.replace(
        "        assert self.tokenizer is not None\n",
        "        assert tokenizer is not None\n",
    )
    detokenize = detokenize.replace(
        "        token_texts = self.tokenizer.batch_decode(",
        "        token_texts = tokenizer.batch_decode(",
    )

    # detokenize_top_logprobs_tokens -> _detokenize_top_logprobs_tokens
    detokenize_top = dedent_method_to_function(detokenize_top_text)
    detokenize_top = detokenize_top.replace(
        "def detokenize_top_logprobs_tokens(\n    self,\n    token_logprobs_val: List[float],\n    token_logprobs_idx: List[int],\n    decode_to_text: bool,\n):",
        "def _detokenize_top_logprobs_tokens(\n    token_logprobs_val: List[List[float]],\n    token_logprobs_idx: List[List[int]],\n    *,\n    decode_to_text: bool,\n    tokenizer: Optional[Any],\n) -> List[Optional[List[Tuple[float, int, Optional[str]]]]]:",
    )
    detokenize_top = detokenize_top.replace(
        "                self.detokenize_logprob_tokens(\n"
        "                    token_logprobs_val[i], token_logprobs_idx[i], decode_to_text\n"
        "                )\n",
        "                _detokenize_logprob_tokens(\n"
        "                    token_logprobs_val[i],\n"
        "                    token_logprobs_idx[i],\n"
        "                    decode_to_text=decode_to_text,\n"
        "                    tokenizer=tokenizer,\n"
        "                )\n",
    )

    new.write_text(
        HEADER
        + fill_meta_info.rstrip()
        + "\n\n\n"
        + absorb_recv.rstrip()
        + "\n\n\n"
        + detokenize.rstrip()
        + "\n\n\n"
        + detokenize_top.rstrip()
        + "\n"
    )

    # ===== Update tokenizer_manager.py callers =====

    text = tm.read_text()

    # Add the import (module-qualified per EXECUTION_GUIDE rule 6).
    text = insert_after(
        text,
        anchor="from sglang.srt.managers.async_dynamic_batch_tokenizer import AsyncDynamicbatchTokenizer\n",
        addition="from sglang.srt.managers import logprob_ops\n",
    )

    # _coalesce_streaming_chunks: for key in _INCREMENTAL_STREAMING_META_INFO_KEYS
    text = replace_call_site(
        text,
        old="for key in _INCREMENTAL_STREAMING_META_INFO_KEYS:",
        new="for key in logprob_ops.INCREMENTAL_STREAMING_META_INFO_KEYS:",
    )

    # _slice_streaming_output_meta_info: 2 callers
    text = text.replace(
        "_slice_streaming_output_meta_info(meta_info, output_offset)",
        "logprob_ops.slice_streaming_output_meta_info(meta_info, output_offset)",
    )

    # convert_logprob_style: 1 caller (in _handle_batch_output)
    text = text.replace(
        "                self.convert_logprob_style(\n"
        "                    meta_info,\n"
        "                    state,\n"
        "                    state.obj.top_logprobs_num,\n"
        "                    state.obj.token_ids_logprob,\n"
        "                    state.obj.return_text_in_logprobs\n"
        "                    and not self.server_args.skip_tokenizer_init,\n"
        "                    recv_obj,\n"
        "                    i,\n"
        "                )\n",
        "                logprob_ops.absorb_recv(\n"
        "                    meta_info,\n"
        "                    state,\n"
        "                    top_logprobs_num=state.obj.top_logprobs_num,\n"
        "                    token_ids_logprob=state.obj.token_ids_logprob,\n"
        "                    return_text_in_logprobs=state.obj.return_text_in_logprobs\n"
        "                    and not self.server_args.skip_tokenizer_init,\n"
        "                    recv_obj=recv_obj,\n"
        "                    recv_obj_index=i,\n"
        "                    tokenizer=self.tokenizer,\n"
        "                )\n",
    )

    # add_logprob_to_meta_info: 1 caller (in _handle_abort_req)
    text = text.replace(
        "            self.add_logprob_to_meta_info(\n"
        "                meta_info,\n"
        "                state,\n"
        "                state.obj.top_logprobs_num,\n"
        "                state.obj.token_ids_logprob,\n"
        "                state.obj.return_text_in_logprobs\n"
        "                and not self.server_args.skip_tokenizer_init,\n"
        "            )\n",
        "            logprob_ops.fill_meta_info(\n"
        "                meta_info,\n"
        "                state,\n"
        "                top_logprobs_num=state.obj.top_logprobs_num,\n"
        "                token_ids_logprob=state.obj.token_ids_logprob,\n"
        "                return_text_in_logprobs=state.obj.return_text_in_logprobs\n"
        "                and not self.server_args.skip_tokenizer_init,\n"
        "                tokenizer=self.tokenizer,\n"
        "            )\n",
    )

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
