#!/usr/bin/env python3
"""Inplace prep for ``introduce-request-preparer``: create the empty
``RequestPreparer`` class skeleton, instantiate in
``TokenizerManager.__init__``, convert 4 methods to ``@staticmethod`` with
``self: RequestPreparer`` typing (body rewritten to address fields on the
target class), and rewrite callers to
``TokenizerManager.<method>(self.request_preparer, ...)``.

Body bytes are now byte-identical wrt the post-move state: the
``self.server_args.X``/``self.is_generation``/``self.max_req_input_len``/
``self.model_config.hf_config.architectures`` reads are rewritten to
``self.config.X``/``self.config.is_generation``/etc. here in prep so the
move commit only does pure structural relocation.
"""

# /// script
# requires-python = ">=3.10"
# dependencies = ["typer"]
# ///

import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from _helpers import find_method_lines, insert_after, replace_call_site
from _runner import run_pr

ID = "introduce-request-preparer-prep"
SUBJECT = "Build RequestPreparer skeleton + @staticmethod prep (prep for move)"
BODY = """\
Inplace prep for the ``introduce-request-preparer`` mech move.

- Create ``managers/request_preparer.py`` with a
  ``@dataclass(frozen=True, slots=True, kw_only=True) RequestPreparer``
  (6 injected fields: raw_tokenizer_wrapper, multimodal_processor,
  request_validator, tokenized_request_builder, rid_to_state, config)
  plus a sibling ``RequestPreparerConfig`` carrying 10 server-args / model
  flags. No methods yet.
- Instantiate ``self.request_preparer = RequestPreparer(...)`` in
  ``TokenizerManager.__init__`` just before the score request handler.
- In TokenizerManager, convert 4 methods (``_tokenize_one_request`` /
  ``_batch_tokenize_and_process`` / ``_should_use_batch_tokenization`` /
  ``_batch_has_text``) to ``@staticmethod`` with
  ``self: \"RequestPreparer\"`` type annotation. Body ``self.X`` reads are
  rewritten where ``X`` is not a RequestPreparer field
  (``self.server_args.X`` -> ``self.config.X``,
  ``self.is_generation`` -> ``self.config.is_generation``,
  ``self.max_req_input_len`` -> ``self.config.max_req_input_len``,
  ``self.model_config.hf_config.architectures`` ->
  ``self.config.architectures``).
- 5 caller sites (generate_request / _handle_batch_request) rewritten to
  ``TokenizerManager.<method>(self.request_preparer, ...)``
  (class-qualified call).

The 4 methods stay inside TokenizerManager in this commit; physical cut +
paste to ``RequestPreparer`` body happens in
``introduce-request-preparer-move``.
"""
AREA = "mech_tokenizer_manager"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


PREPARER_HEADER = '''from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Union

from sglang.srt.managers.embed_types import PositionalEmbeds  # noqa: F401  (used by sub-pipeline imports)
from sglang.srt.managers.multimodal_processor import MultimodalProcessor
from sglang.srt.managers.raw_tokenizer_wrapper import RawTokenizerWrapper
from sglang.srt.managers.request_validator import RequestValidator
from sglang.srt.managers.tokenized_request_builder import TokenizedRequestBuilder
from sglang.srt.managers.io_struct import (
    EmbeddingReqInput,
    GenerateReqInput,
    TokenizedEmbeddingReqInput,
    TokenizedGenerateReqInput,
)
from sglang.srt.managers.request_state import ReqState
from sglang.srt.managers.schedule_batch import MultimodalDataItem
from sglang.srt.environ import envs

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True, kw_only=True)
class RequestPreparerConfig:
    skip_tokenizer_init: bool
    enable_dp_attention: bool
    enable_tokenizer_batch_encode: bool
    is_generation: bool
    disable_radix_cache: bool
    is_multimodal: bool
    architectures: List[str]
    max_req_input_len: Optional[int]
    language_only: bool
    encoder_transfer_backend: str


@dataclass(frozen=True, slots=True, kw_only=True)
class RequestPreparer:
    raw_tokenizer_wrapper: RawTokenizerWrapper
    multimodal_processor: MultimodalProcessor
    request_validator: RequestValidator
    tokenized_request_builder: TokenizedRequestBuilder
    rid_to_state: Dict[str, ReqState]
    config: RequestPreparerConfig
'''


INIT_INSERT = '''        # Request preparer
        self.request_preparer = RequestPreparer(
            raw_tokenizer_wrapper=self.raw_tokenizer_wrapper,
            multimodal_processor=self.multimodal_processor,
            request_validator=self.request_validator,
            tokenized_request_builder=self.tokenized_request_builder,
            rid_to_state=self.rid_to_state,
            config=RequestPreparerConfig(
                skip_tokenizer_init=self.server_args.skip_tokenizer_init,
                enable_dp_attention=self.server_args.enable_dp_attention,
                enable_tokenizer_batch_encode=self.server_args.enable_tokenizer_batch_encode,
                is_generation=self.is_generation,
                disable_radix_cache=self.server_args.disable_radix_cache,
                is_multimodal=self.model_config.is_multimodal,
                architectures=self.model_config.hf_config.architectures,
                max_req_input_len=self.max_req_input_len,
                language_only=self.server_args.language_only,
                encoder_transfer_backend=self.server_args.encoder_transfer_backend,
            ),
        )

'''


def _rewrite_body(body: str) -> str:
    """Rewrite ``self.X`` reads where ``X`` is not a RequestPreparer field.

    After this, every ``self.X`` in the body resolves to a real
    RequestPreparer field, so the method runs correctly when invoked as
    ``TokenizerManager.<m>(self.request_preparer, ...)`` (prep form) and
    later as ``self.request_preparer.<m>(...)`` (move form) with body byte
    unchanged.
    """
    body = body.replace("self.server_args.disable_radix_cache", "self.config.disable_radix_cache")
    body = body.replace("self.server_args.language_only", "self.config.language_only")
    body = body.replace("self.server_args.encoder_transfer_backend", "self.config.encoder_transfer_backend")
    body = body.replace("self.server_args.enable_tokenizer_batch_encode", "self.config.enable_tokenizer_batch_encode")
    body = body.replace("self.server_args.enable_dp_attention", "self.config.enable_dp_attention")
    body = body.replace("self.is_generation", "self.config.is_generation")
    body = body.replace("self.max_req_input_len", "self.config.max_req_input_len")
    body = body.replace(
        "self.model_config.hf_config.architectures",
        "self.config.architectures",
    )
    return body


def _staticmethod_typeflip(method_text: str) -> str:
    """Prepend ``@staticmethod`` and retype ``self`` to ``"RequestPreparer"``.

    Handles both single-line ``def foo(self, ...)`` and multi-line
    ``def foo(\\n        self,\\n        ...)`` signatures by replacing the
    first ``self`` parameter in the signature.
    """
    # Add @staticmethod decorator (4-space indent for class body).
    # The method block as returned by find_method_lines starts with the
    # `def`/`async def` line at 4-space indent; just prepend the decorator.
    lines = method_text.splitlines(keepends=True)
    # Find the def line (first line that contains ``def `` after stripping).
    def_idx = next(
        i for i, l in enumerate(lines)
        if l.lstrip().startswith("def ") or l.lstrip().startswith("async def ")
    )
    # Insert @staticmethod just before the def line.
    lines.insert(def_idx, "    @staticmethod\n")
    out = "".join(lines)

    # Retype the first ``self`` parameter. Two shapes:
    #   single-line:  ``def foo(self, ...)``  /  ``async def foo(self, ...)``
    #   multi-line:   ``def foo(\n        self,\n        ...)``
    # Use targeted replacements.
    candidates = [
        ("(self, ", "(self: \"RequestPreparer\", "),
        ("(\n        self,\n", "(\n        self: \"RequestPreparer\",\n"),
        ("(self,\n", "(self: \"RequestPreparer\",\n"),
    ]
    for old, new in candidates:
        if old in out:
            return out.replace(old, new, 1)
    raise RuntimeError(
        f"could not retype self in method; signature shape unexpected:\n{out[:200]}"
    )


def transform(wt: Path) -> None:
    tm = wt / "python/sglang/srt/managers/tokenizer_manager.py"
    preparer = wt / "python/sglang/srt/managers/request_preparer.py"

    # 1. Create new file with empty RequestPreparer / RequestPreparerConfig.
    preparer.write_text(PREPARER_HEADER)

    # 2. In TokenizerManager, transform each method in place:
    #    add @staticmethod, retype self, rewrite body.
    method_names = (
        "_tokenize_one_request",
        "_batch_tokenize_and_process",
        "_should_use_batch_tokenization",
        "_batch_has_text",
    )
    for name in method_names:
        text = tm.read_text()
        s, e = find_method_lines(text, class_name="TokenizerManager", method_name=name)
        lines = text.splitlines(keepends=True)
        method_text = "".join(lines[s:e])
        method_text = _rewrite_body(method_text)
        method_text = _staticmethod_typeflip(method_text)
        new_text = "".join(lines[:s]) + method_text + "".join(lines[e:])
        tm.write_text(new_text)

    # 3. Add import + ctor instantiation in TokenizerManager.
    text = tm.read_text()
    text = insert_after(
        text,
        anchor="from sglang.srt.managers.tokenizer_control_mixin import TokenizerControlMixin\n",
        addition=(
            "from sglang.srt.managers.request_preparer import (\n"
            "    RequestPreparer,\n"
            "    RequestPreparerConfig,\n"
            ")\n"
        ),
    )
    text = replace_call_site(
        text,
        old=(
            "        # Score request handler\n"
            "        self.score_request_handler = ScoreRequestHandler(\n"
        ),
        new=(
            INIT_INSERT
            + "        # Score request handler\n"
            "        self.score_request_handler = ScoreRequestHandler(\n"
        ),
    )

    # 4. Caller updates (5 sites): class-qualified form.
    # _tokenize_one_request: 3 sites.
    text = text.replace(
        "                tokenized_obj = await self._tokenize_one_request(obj)\n",
        "                tokenized_obj = await TokenizerManager._tokenize_one_request(self.request_preparer, obj)\n",
    )
    text = text.replace(
        "                        tokenized_obj = await self._tokenize_one_request(tmp_obj)\n",
        "                        tokenized_obj = await TokenizerManager._tokenize_one_request(self.request_preparer, tmp_obj)\n",
    )
    text = text.replace(
        "                *(self._tokenize_one_request(obj) for obj in objs)\n",
        "                *(TokenizerManager._tokenize_one_request(self.request_preparer, obj) for obj in objs)\n",
    )
    # _batch_tokenize_and_process: 1 site.
    text = text.replace(
        "                tokenized_objs = await self._batch_tokenize_and_process(batch_size, obj)\n",
        "                tokenized_objs = await TokenizerManager._batch_tokenize_and_process(self.request_preparer, batch_size, obj)\n",
    )
    # _should_use_batch_tokenization: 1 site.
    text = text.replace(
        "            if self._should_use_batch_tokenization(batch_size, obj):\n",
        "            if TokenizerManager._should_use_batch_tokenization(self.request_preparer, batch_size, obj):\n",
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
