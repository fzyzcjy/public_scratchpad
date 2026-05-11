#!/usr/bin/env python3
"""In-place prep for moving the 4 logprob methods out of TokenizerManager.

Make each of ``add_logprob_to_meta_info``, ``convert_logprob_style``,
``detokenize_logprob_tokens``, ``detokenize_top_logprobs_tokens`` a
``@staticmethod`` with the final signature shape (explicit kwargs incl.
``tokenizer: Optional[Any]``); rewrite each body's ``self.tokenizer`` reads
and ``self.<other_method>(...)`` calls. Bodies stay inside TokenizerManager.

The module-level constant ``_INCREMENTAL_STREAMING_META_INFO_KEYS`` and
module-level free fn ``_slice_streaming_output_meta_info`` remain untouched
in this commit -- they get cut + renamed in ``move-logprob-ops-move``.

All caller sites (intra-method + 3 external) switch to
``TokenizerManager.<method>(...)`` form so the next commit is a pure prefix
replacement.

Methods keep their ORIGINAL names in this commit; the scope-induced rename
(e.g. ``add_logprob_to_meta_info`` -> ``fill_meta_info``) is deferred to
``move-logprob-ops-move``.
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

ID = "move-logprob-ops-prep"
SUBJECT = "Prep 4 logprob methods for move: staticmethod + explicit kwargs"
BODY = """\
In-place prep per MECH_COMMIT_SPLIT before the physical move:

  - Add @staticmethod to add_logprob_to_meta_info / convert_logprob_style
    / detokenize_logprob_tokens / detokenize_top_logprobs_tokens
  - Drop ``self`` on each; add explicit kwargs (incl. ``tokenizer``)
  - Body rewrites: ``self.tokenizer`` -> ``tokenizer``
  - Intra-method calls go through ``TokenizerManager.<method>(...)`` with
    explicit kwargs
  - 3 external callers (_handle_batch_output / _handle_abort_req) switch
    to ``TokenizerManager.<method>(...)`` form

No behavior change. Bodies stay in TokenizerManager. Original method names
are preserved -- the scope-induced rename (drop class qualifier, drop
leading underscore on the free fn / const) happens in the move commit.
"""
AREA = "mech_tokenizer_manager"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


# ===== Replacement signature headers (4-space class indent, @staticmethod) =====

NEW_ADD_LOGPROB_HEADER = '''    @staticmethod
    def add_logprob_to_meta_info(
        meta_info: dict,
        state: ReqState,
        *,
        top_logprobs_num: int,
        token_ids_logprob: Optional[List[int]],
        return_text_in_logprobs: bool,
        tokenizer: Optional[Any],
    ) -> None:
'''

NEW_CONVERT_HEADER = '''    @staticmethod
    def convert_logprob_style(
        meta_info: dict,
        state: ReqState,
        *,
        top_logprobs_num: int,
        token_ids_logprob: Optional[List[int]],
        return_text_in_logprobs: bool,
        recv_obj: BatchStrOutput,
        recv_obj_index: int,
        tokenizer: Optional[Any],
    ) -> None:
'''

NEW_DETOKENIZE_HEADER = '''    @staticmethod
    def detokenize_logprob_tokens(
        token_logprobs_val: List[float],
        token_logprobs_idx: List[int],
        *,
        decode_to_text: bool,
        tokenizer: Optional[Any],
    ) -> List[Tuple[float, int, Optional[str]]]:
'''

NEW_DETOKENIZE_TOP_HEADER = '''    @staticmethod
    def detokenize_top_logprobs_tokens(
        token_logprobs_val: List[List[float]],
        token_logprobs_idx: List[List[int]],
        *,
        decode_to_text: bool,
        tokenizer: Optional[Any],
    ) -> List[Optional[List[Tuple[float, int, Optional[str]]]]]:
'''


# ===== Per-method body transforms =====


def _rewrite_add_logprob(method_text: str) -> str:
    """add_logprob_to_meta_info: replace signature; rewrite intra-method calls
    to TokenizerManager.detokenize_*_tokens(...) with explicit kwargs."""
    text = method_text
    old_header = (
        "    def add_logprob_to_meta_info(\n"
        "        self,\n"
        "        meta_info: dict,\n"
        "        state: ReqState,\n"
        "        top_logprobs_num: int,\n"
        "        token_ids_logprob: List[int],\n"
        "        return_text_in_logprobs: bool,\n"
        "    ):\n"
    )
    if old_header not in text:
        raise RuntimeError("add_logprob_to_meta_info signature anchor mismatch")
    text = text.replace(old_header, NEW_ADD_LOGPROB_HEADER)

    # 2 calls to self.detokenize_logprob_tokens(..., return_text_in_logprobs,)
    # (positional 3rd arg) become TokenizerManager.detokenize_logprob_tokens(...,
    # decode_to_text=return_text_in_logprobs, tokenizer=tokenizer,).
    text = text.replace(
        "                self.detokenize_logprob_tokens(\n"
        "                    state.input_token_logprobs_val[len(state.input_token_logprobs) :],\n"
        "                    state.input_token_logprobs_idx[len(state.input_token_logprobs) :],\n"
        "                    return_text_in_logprobs,\n"
        "                )\n",
        "                TokenizerManager.detokenize_logprob_tokens(\n"
        "                    state.input_token_logprobs_val[len(state.input_token_logprobs) :],\n"
        "                    state.input_token_logprobs_idx[len(state.input_token_logprobs) :],\n"
        "                    decode_to_text=return_text_in_logprobs,\n"
        "                    tokenizer=tokenizer,\n"
        "                )\n",
    )
    text = text.replace(
        "                self.detokenize_logprob_tokens(\n"
        "                    state.output_token_logprobs_val[len(state.output_token_logprobs) :],\n"
        "                    state.output_token_logprobs_idx[len(state.output_token_logprobs) :],\n"
        "                    return_text_in_logprobs,\n"
        "                )\n",
        "                TokenizerManager.detokenize_logprob_tokens(\n"
        "                    state.output_token_logprobs_val[len(state.output_token_logprobs) :],\n"
        "                    state.output_token_logprobs_idx[len(state.output_token_logprobs) :],\n"
        "                    decode_to_text=return_text_in_logprobs,\n"
        "                    tokenizer=tokenizer,\n"
        "                )\n",
    )

    # 4 calls to self.detokenize_top_logprobs_tokens(...) with positional 3rd
    # arg become TokenizerManager.detokenize_top_logprobs_tokens(...) with kwargs.
    text = text.replace(
        "                    self.detokenize_top_logprobs_tokens(\n"
        "                        state.input_top_logprobs_val[len(state.input_top_logprobs) :],\n"
        "                        state.input_top_logprobs_idx[len(state.input_top_logprobs) :],\n"
        "                        return_text_in_logprobs,\n"
        "                    )\n",
        "                    TokenizerManager.detokenize_top_logprobs_tokens(\n"
        "                        state.input_top_logprobs_val[len(state.input_top_logprobs) :],\n"
        "                        state.input_top_logprobs_idx[len(state.input_top_logprobs) :],\n"
        "                        decode_to_text=return_text_in_logprobs,\n"
        "                        tokenizer=tokenizer,\n"
        "                    )\n",
    )
    text = text.replace(
        "                    self.detokenize_top_logprobs_tokens(\n"
        "                        state.output_top_logprobs_val[len(state.output_top_logprobs) :],\n"
        "                        state.output_top_logprobs_idx[len(state.output_top_logprobs) :],\n"
        "                        return_text_in_logprobs,\n"
        "                    )\n",
        "                    TokenizerManager.detokenize_top_logprobs_tokens(\n"
        "                        state.output_top_logprobs_val[len(state.output_top_logprobs) :],\n"
        "                        state.output_top_logprobs_idx[len(state.output_top_logprobs) :],\n"
        "                        decode_to_text=return_text_in_logprobs,\n"
        "                        tokenizer=tokenizer,\n"
        "                    )\n",
    )
    text = text.replace(
        "                    self.detokenize_top_logprobs_tokens(\n"
        "                        state.input_token_ids_logprobs_val[\n"
        "                            len(state.input_token_ids_logprobs) :\n"
        "                        ],\n"
        "                        state.input_token_ids_logprobs_idx[\n"
        "                            len(state.input_token_ids_logprobs) :\n"
        "                        ],\n"
        "                        return_text_in_logprobs,\n"
        "                    )\n",
        "                    TokenizerManager.detokenize_top_logprobs_tokens(\n"
        "                        state.input_token_ids_logprobs_val[\n"
        "                            len(state.input_token_ids_logprobs) :\n"
        "                        ],\n"
        "                        state.input_token_ids_logprobs_idx[\n"
        "                            len(state.input_token_ids_logprobs) :\n"
        "                        ],\n"
        "                        decode_to_text=return_text_in_logprobs,\n"
        "                        tokenizer=tokenizer,\n"
        "                    )\n",
    )
    text = text.replace(
        "                    self.detokenize_top_logprobs_tokens(\n"
        "                        state.output_token_ids_logprobs_val[\n"
        "                            len(state.output_token_ids_logprobs) :\n"
        "                        ],\n"
        "                        state.output_token_ids_logprobs_idx[\n"
        "                            len(state.output_token_ids_logprobs) :\n"
        "                        ],\n"
        "                        return_text_in_logprobs,\n"
        "                    )\n",
        "                    TokenizerManager.detokenize_top_logprobs_tokens(\n"
        "                        state.output_token_ids_logprobs_val[\n"
        "                            len(state.output_token_ids_logprobs) :\n"
        "                        ],\n"
        "                        state.output_token_ids_logprobs_idx[\n"
        "                            len(state.output_token_ids_logprobs) :\n"
        "                        ],\n"
        "                        decode_to_text=return_text_in_logprobs,\n"
        "                        tokenizer=tokenizer,\n"
        "                    )\n",
    )
    return text


def _rewrite_convert(method_text: str) -> str:
    """convert_logprob_style: replace signature; rewrite trailing
    self.add_logprob_to_meta_info(...) -> TokenizerManager.add_logprob_to_meta_info(...)
    with explicit kwargs (incl. tokenizer)."""
    text = method_text
    old_header = (
        "    def convert_logprob_style(\n"
        "        self,\n"
        "        meta_info: dict,\n"
        "        state: ReqState,\n"
        "        top_logprobs_num: int,\n"
        "        token_ids_logprob: List[int],\n"
        "        return_text_in_logprobs: bool,\n"
        "        recv_obj: BatchStrOutput,\n"
        "        recv_obj_index: int,\n"
        "    ):\n"
    )
    if old_header not in text:
        raise RuntimeError("convert_logprob_style signature anchor mismatch")
    text = text.replace(old_header, NEW_CONVERT_HEADER)

    text = text.replace(
        "        self.add_logprob_to_meta_info(\n"
        "            meta_info,\n"
        "            state,\n"
        "            state.obj.top_logprobs_num,\n"
        "            state.obj.token_ids_logprob,\n"
        "            return_text_in_logprobs,\n"
        "        )\n",
        "        TokenizerManager.add_logprob_to_meta_info(\n"
        "            meta_info,\n"
        "            state,\n"
        "            top_logprobs_num=state.obj.top_logprobs_num,\n"
        "            token_ids_logprob=state.obj.token_ids_logprob,\n"
        "            return_text_in_logprobs=return_text_in_logprobs,\n"
        "            tokenizer=tokenizer,\n"
        "        )\n",
    )
    return text


def _rewrite_detokenize(method_text: str) -> str:
    """detokenize_logprob_tokens: replace signature; ``self.tokenizer`` -> ``tokenizer``."""
    text = method_text
    old_header = (
        "    def detokenize_logprob_tokens(\n"
        "        self,\n"
        "        token_logprobs_val: List[float],\n"
        "        token_logprobs_idx: List[int],\n"
        "        decode_to_text: bool,\n"
        "    ):\n"
    )
    if old_header not in text:
        raise RuntimeError("detokenize_logprob_tokens signature anchor mismatch")
    text = text.replace(old_header, NEW_DETOKENIZE_HEADER)
    text = text.replace(
        "            assert self.tokenizer is not None\n",
        "            assert tokenizer is not None\n",
    )
    text = text.replace(
        "            token_texts = self.tokenizer.batch_decode(",
        "            token_texts = tokenizer.batch_decode(",
    )
    return text


def _rewrite_detokenize_top(method_text: str) -> str:
    """detokenize_top_logprobs_tokens: replace signature; rewrite intra-method
    self.detokenize_logprob_tokens(...) call to TokenizerManager.<...>(...) with kwargs."""
    text = method_text
    old_header = (
        "    def detokenize_top_logprobs_tokens(\n"
        "        self,\n"
        "        token_logprobs_val: List[float],\n"
        "        token_logprobs_idx: List[int],\n"
        "        decode_to_text: bool,\n"
        "    ):\n"
    )
    if old_header not in text:
        raise RuntimeError("detokenize_top_logprobs_tokens signature anchor mismatch")
    text = text.replace(old_header, NEW_DETOKENIZE_TOP_HEADER)
    if "                    self.detokenize_logprob_tokens(\n" not in text:
        raise RuntimeError("detokenize_top: intra-method call anchor mismatch")
    text = text.replace(
        "                    self.detokenize_logprob_tokens(\n"
        "                        token_logprobs_val[i], token_logprobs_idx[i], decode_to_text\n"
        "                    )\n",
        "                    TokenizerManager.detokenize_logprob_tokens(\n"
        "                        token_logprobs_val[i],\n"
        "                        token_logprobs_idx[i],\n"
        "                        decode_to_text=decode_to_text,\n"
        "                        tokenizer=tokenizer,\n"
        "                    )\n",
    )
    return text


def _rewrite_one_method(text: str, method_name: str, rewriter) -> str:
    """Locate method by name, hand its slice to rewriter, splice result back."""
    s, e = find_method_lines(text, class_name="TokenizerManager", method_name=method_name)
    lines = text.splitlines(keepends=True)
    method_text = "".join(lines[s:e])
    new_method = rewriter(method_text)
    return "".join(lines[:s]) + new_method + "".join(lines[e:])


def transform(wt: Path) -> None:
    tm = wt / "python/sglang/srt/managers/tokenizer_manager.py"
    text = tm.read_text()

    # Rewrite the 4 methods in place. Order doesn't matter since each lookup
    # uses fresh AST line numbers.
    text = _rewrite_one_method(text, "add_logprob_to_meta_info", _rewrite_add_logprob)
    text = _rewrite_one_method(text, "convert_logprob_style", _rewrite_convert)
    text = _rewrite_one_method(text, "detokenize_logprob_tokens", _rewrite_detokenize)
    text = _rewrite_one_method(text, "detokenize_top_logprobs_tokens", _rewrite_detokenize_top)

    # External caller 1: _handle_batch_output -> self.convert_logprob_style(...)
    text = replace_call_site(
        text,
        old=(
            "                self.convert_logprob_style(\n"
            "                    meta_info,\n"
            "                    state,\n"
            "                    state.obj.top_logprobs_num,\n"
            "                    state.obj.token_ids_logprob,\n"
            "                    state.obj.return_text_in_logprobs\n"
            "                    and not self.server_args.skip_tokenizer_init,\n"
            "                    recv_obj,\n"
            "                    i,\n"
            "                )\n"
        ),
        new=(
            "                TokenizerManager.convert_logprob_style(\n"
            "                    meta_info,\n"
            "                    state,\n"
            "                    top_logprobs_num=state.obj.top_logprobs_num,\n"
            "                    token_ids_logprob=state.obj.token_ids_logprob,\n"
            "                    return_text_in_logprobs=state.obj.return_text_in_logprobs\n"
            "                    and not self.server_args.skip_tokenizer_init,\n"
            "                    recv_obj=recv_obj,\n"
            "                    recv_obj_index=i,\n"
            "                    tokenizer=self.tokenizer,\n"
            "                )\n"
        ),
    )

    # External caller 2: _handle_abort_req -> self.add_logprob_to_meta_info(...)
    text = replace_call_site(
        text,
        old=(
            "            self.add_logprob_to_meta_info(\n"
            "                meta_info,\n"
            "                state,\n"
            "                state.obj.top_logprobs_num,\n"
            "                state.obj.token_ids_logprob,\n"
            "                state.obj.return_text_in_logprobs\n"
            "                and not self.server_args.skip_tokenizer_init,\n"
            "            )\n"
        ),
        new=(
            "            TokenizerManager.add_logprob_to_meta_info(\n"
            "                meta_info,\n"
            "                state,\n"
            "                top_logprobs_num=state.obj.top_logprobs_num,\n"
            "                token_ids_logprob=state.obj.token_ids_logprob,\n"
            "                return_text_in_logprobs=state.obj.return_text_in_logprobs\n"
            "                and not self.server_args.skip_tokenizer_init,\n"
            "                tokenizer=self.tokenizer,\n"
            "            )\n"
        ),
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
