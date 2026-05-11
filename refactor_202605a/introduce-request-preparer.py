#!/usr/bin/env python3
"""Introduce RequestPreparer owner class.

Move 4 methods (_tokenize_one_request / _batch_tokenize_and_process /
_should_use_batch_tokenization / _batch_has_text) from TokenizerManager
into a new @dataclass(frozen=True, slots=True, kw_only=True) RequestPreparer.

Per md ch3.1, method names retain leading underscore (PR1 form);
the privacy flip + Callable->direct injection are deferred to Ch2.
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
    find_method_lines,
    insert_after,
    replace_call_site,
)
from _runner import run_pr

ID = "introduce-request-preparer"
SUBJECT = "Introduce RequestPreparer and move 4 tokenize-orchestration methods"
BODY = """\
Move 4 tokenize-orchestration methods (_tokenize_one_request /
_batch_tokenize_and_process / _should_use_batch_tokenization /
_batch_has_text) from TokenizerManager into a new
@dataclass(frozen=True, slots=True, kw_only=True) RequestPreparer in
managers/request_preparer.py.

Per md ch3.1 PR1 form: method names keep their leading underscore;
RequestPreparer takes already-extracted owner classes by direct injection
(raw_tokenizer_wrapper, multimodal_processor, request_validator,
tokenized_request_builder) plus rid_to_state and a RequestPreparerConfig.

Method bodies' self.X references rewrite:
  self.server_args.X     -> self.config.X (relevant flags only)
  self.is_generation     -> self.config.is_generation
  self.max_req_input_len -> self.config.max_req_input_len
  self.model_config.hf_config.architectures -> self.config.architectures
  self.raw_tokenizer_wrapper.X / self.multimodal_processor.X /
  self.request_validator.X / self.tokenized_request_builder.X /
  self.rid_to_state -- kept as-is (matching field names on RequestPreparer).

5 caller sites (generate_request / _handle_batch_request) update to
self.request_preparer._<method>(...).
"""
AREA = "mech_tokenizer_manager"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


HEADER = '''from __future__ import annotations

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


def transform(wt: Path) -> None:
    tm = wt / "python/sglang/srt/managers/tokenizer_manager.py"
    new = wt / "python/sglang/srt/managers/request_preparer.py"

    # Cut bottom-up.
    method_names = (
        "_tokenize_one_request",
        "_batch_tokenize_and_process",
        "_should_use_batch_tokenization",
        "_batch_has_text",
    )
    name_to_range = {}
    for n in method_names:
        s, e = find_method_lines(tm.read_text(), class_name="TokenizerManager", method_name=n)
        name_to_range[n] = (s, e)
    cut_blocks = {}
    for n in sorted(method_names, key=lambda nn: -name_to_range[nn][0]):
        s, e = find_method_lines(tm.read_text(), class_name="TokenizerManager", method_name=n)
        cut_blocks[n] = cut_lines(tm, s, e)

    def rewrite(body: str) -> str:
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

    bodies_in_file_order = [cut_blocks[n] for n in method_names]
    rewritten = [rewrite(b) for b in bodies_in_file_order]
    new.write_text(HEADER + "\n\n".join(b.rstrip() for b in rewritten) + "\n")

    # ===== tokenizer_manager.py: caller updates + ctor wiring + import =====
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

    # Wire preparer construction: AFTER tokenized_request_builder + multimodal_processor + request_validator.
    # Insert before the score_request_handler block.
    text = replace_call_site(
        text,
        old=(
            "        # Score request handler\n"
            "        self.score_request_handler = ScoreRequestHandler(\n"
        ),
        new=(
            "        # Request preparer\n"
            "        self.request_preparer = RequestPreparer(\n"
            "            raw_tokenizer_wrapper=self.raw_tokenizer_wrapper,\n"
            "            multimodal_processor=self.multimodal_processor,\n"
            "            request_validator=self.request_validator,\n"
            "            tokenized_request_builder=self.tokenized_request_builder,\n"
            "            rid_to_state=self.rid_to_state,\n"
            "            config=RequestPreparerConfig(\n"
            "                skip_tokenizer_init=self.server_args.skip_tokenizer_init,\n"
            "                enable_dp_attention=self.server_args.enable_dp_attention,\n"
            "                enable_tokenizer_batch_encode=self.server_args.enable_tokenizer_batch_encode,\n"
            "                is_generation=self.is_generation,\n"
            "                disable_radix_cache=self.server_args.disable_radix_cache,\n"
            "                is_multimodal=self.model_config.is_multimodal,\n"
            "                architectures=self.model_config.hf_config.architectures,\n"
            "                max_req_input_len=self.max_req_input_len,\n"
            "                language_only=self.server_args.language_only,\n"
            "                encoder_transfer_backend=self.server_args.encoder_transfer_backend,\n"
            "            ),\n"
            "        )\n"
            "\n"
            "        # Score request handler\n"
            "        self.score_request_handler = ScoreRequestHandler(\n"
        ),
    )

    # Caller updates (5 sites in facade):
    # _tokenize_one_request: 3 sites (in generate_request + _handle_batch_request)
    text = text.replace(
        "                tokenized_obj = await self._tokenize_one_request(obj)\n",
        "                tokenized_obj = await self.request_preparer._tokenize_one_request(obj)\n",
    )
    text = text.replace(
        "                        tokenized_obj = await self._tokenize_one_request(tmp_obj)\n",
        "                        tokenized_obj = await self.request_preparer._tokenize_one_request(tmp_obj)\n",
    )
    text = text.replace(
        "                *(self._tokenize_one_request(obj) for obj in objs)\n",
        "                *(self.request_preparer._tokenize_one_request(obj) for obj in objs)\n",
    )
    # _batch_tokenize_and_process: 1 site
    text = text.replace(
        "                tokenized_objs = await self._batch_tokenize_and_process(batch_size, obj)\n",
        "                tokenized_objs = await self.request_preparer._batch_tokenize_and_process(batch_size, obj)\n",
    )
    # _should_use_batch_tokenization: 1 site
    text = text.replace(
        "            if self._should_use_batch_tokenization(batch_size, obj):\n",
        "            if self.request_preparer._should_use_batch_tokenization(batch_size, obj):\n",
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
