#!/usr/bin/env python3
"""Prep: RequestPreparer skeleton + composition + staticmethod conversion + caller rewrites."""

# /// script
# requires-python = ">=3.10"
# dependencies = ["typer"]
# ///

import ast
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from _helpers import insert_after, replace_call_site
from _runner import run_pr

ID = "introduce-request-preparer-prep"
SUBJECT = "Stage tokenize-pipeline orchestration for handoff to RequestPreparer"
BODY = """\
Per MECH_COMMIT_SPLIT §"拆 class 场景": prep does ALL semantic work.

Builds RequestPreparer skeleton; wires composition in TM.__init__;
converts the 4 tokenize-orchestration methods (_tokenize_one_request,
_batch_tokenize_and_process, _should_use_batch_tokenization,
_batch_has_text) to @staticmethod with self: "RequestPreparer"
annotation; rewrites bodies (self.server_args.X / self.is_generation /
self.max_req_input_len / self.model_config.hf_config.architectures
-> self.config.X) and cluster cross-calls (self.foo(...) ->
TokenizerManager.foo(self, ...)); rewrites the 5 external caller sites
to TokenizerManager.<method>(self.request_preparer, ...). Methods stay
on TM in this commit; the next commit's pure cut/paste + caller prefix
replacement completes the move.
"""
AREA = "mech_tokenizer_manager"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


SKELETON = '''from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from sglang.srt.managers.tokenizer_manager_components.multimodal_processor_owner import MultimodalProcessor
from sglang.srt.managers.tokenizer_manager_components.raw_tokenizer_wrapper import RawTokenizerWrapper
from sglang.srt.managers.tokenizer_manager_components.request_state import ReqState
from sglang.srt.managers.tokenizer_manager_components.request_validator import RequestValidator
from sglang.srt.managers.tokenizer_manager_components.tokenized_request_builder import TokenizedRequestBuilder


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


def _method_ranges(text: str, class_name: str, method_name: str):
    """Return 0-indexed (decorator_start, body_start, end) of the method."""
    tree = ast.parse(text)
    func_types = (ast.FunctionDef, ast.AsyncFunctionDef)
    for cls in ast.walk(tree):
        if isinstance(cls, ast.ClassDef) and cls.name == class_name:
            for i, node in enumerate(cls.body):
                if isinstance(node, func_types) and node.name == method_name:
                    start = node.lineno - 1
                    if node.decorator_list:
                        start = node.decorator_list[0].lineno - 1
                    body_start = node.body[0].lineno - 1
                    if i + 1 < len(cls.body):
                        end = cls.body[i + 1].lineno - 1
                        nxt = cls.body[i + 1]
                        if isinstance(nxt, func_types + (ast.ClassDef,)) and nxt.decorator_list:
                            end = nxt.decorator_list[0].lineno - 1
                    else:
                        end = node.end_lineno
                    return start, body_start, end
    raise ValueError(f"{class_name}.{method_name} not found")


# New header (decorator + signature) for each method. Header replaces lines
# [decorator_start, body_start). Body (lines [body_start, end)) stays put,
# only text-substituted by the rewrite_body() helper.
NEW_HEADERS = {
    "_tokenize_one_request": (
        '    @staticmethod\n'
        '    async def _tokenize_one_request(\n'
        '        self: "RequestPreparer",\n'
        '        obj: Union[GenerateReqInput, EmbeddingReqInput],\n'
        '    ):\n'
    ),
    "_batch_tokenize_and_process": (
        '    @staticmethod\n'
        '    async def _batch_tokenize_and_process(\n'
        '        self: "RequestPreparer", batch_size: int, obj: Union[GenerateReqInput, EmbeddingReqInput]\n'
        '    ) -> List[Union[TokenizedGenerateReqInput, TokenizedEmbeddingReqInput]]:\n'
    ),
    "_batch_has_text": (
        '    @staticmethod\n'
        '    def _batch_has_text(\n'
        '        self: "RequestPreparer", batch_size: int, obj: Union[GenerateReqInput, EmbeddingReqInput]\n'
        '    ) -> bool:\n'
    ),
    "_should_use_batch_tokenization": (
        '    @staticmethod\n'
        '    def _should_use_batch_tokenization(self: "RequestPreparer", batch_size, requests) -> bool:\n'
    ),
}


def _rewrite_body(body: str) -> str:
    """Apply the prep body rewrites: self.<state> -> self.config.<state>, plus
    cluster cross-calls self.<m>(...) -> TokenizerManager.<m>(self, ...).
    All other self.X references (raw_tokenizer_wrapper, multimodal_processor,
    request_validator, tokenized_request_builder, rid_to_state) already match
    fields on RequestPreparer and stay unchanged.
    """
    # server_args.* -> config.*
    body = body.replace("self.server_args.disable_radix_cache", "self.config.disable_radix_cache")
    body = body.replace("self.server_args.language_only", "self.config.language_only")
    body = body.replace("self.server_args.encoder_transfer_backend", "self.config.encoder_transfer_backend")
    body = body.replace("self.server_args.enable_tokenizer_batch_encode", "self.config.enable_tokenizer_batch_encode")
    body = body.replace("self.server_args.enable_dp_attention", "self.config.enable_dp_attention")

    # Direct TM-only attrs -> config.*
    body = body.replace("self.is_generation", "self.config.is_generation")
    body = body.replace("self.max_req_input_len", "self.config.max_req_input_len")
    body = body.replace(
        "self.model_config.hf_config.architectures",
        "self.config.architectures",
    )

    # tokenizer / mm_processor live on raw_tokenizer_wrapper. While the methods
    # are still on TM these resolve via TM's facade @property, but after the
    # move ``self`` is the RequestPreparer (no such facade), so reach through
    # the wrapper field. Replace mm_processor first; neither is a substring of
    # the other or of self.multimodal_processor / self.tokenized_request_builder.
    body = body.replace("self.mm_processor", "self.raw_tokenizer_wrapper.mm_processor")
    body = body.replace("self.tokenizer", "self.raw_tokenizer_wrapper.tokenizer")

    # Cluster cross-calls: methods that remain on TM as @staticmethod with
    # self: RequestPreparer. Must qualify with class name to reflect "脱 self"
    # semantics per MECH_COMMIT_SPLIT.
    body = body.replace(
        "self._batch_has_text(",
        "TokenizerManager._batch_has_text(self, ",
    )
    body = body.replace(
        "self._tokenize_one_request(",
        "TokenizerManager._tokenize_one_request(self, ",
    )
    return body


def transform(wt: Path) -> None:
    tm = wt / "python/sglang/srt/managers/tokenizer_manager.py"
    new = wt / "python/sglang/srt/managers/tokenizer_manager_components/request_preparer.py"
    new.write_text(SKELETON)

    text = tm.read_text()
    text = insert_after(
        text,
        anchor="from sglang.srt.managers.tokenizer_control_mixin import TokenizerControlMixin\n",
        addition=(
            "from sglang.srt.managers.tokenizer_manager_components.request_preparer import (\n"
            "    RequestPreparer,\n"
            "    RequestPreparerConfig,\n"
            ")\n"
        ),
    )

    # Composition wiring in __init__.
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

    # Convert each method to @staticmethod with self: "RequestPreparer" typing
    # and apply in-place body rewrites. Walk bottom-up so earlier ranges stay
    # valid as we splice in new headers of possibly different line counts.
    method_order = (
        "_tokenize_one_request",
        "_batch_tokenize_and_process",
        "_batch_has_text",
        "_should_use_batch_tokenization",
    )
    ranges = {}
    for name in method_order:
        ranges[name] = _method_ranges(text, "TokenizerManager", name)
    for name in sorted(method_order, key=lambda n: -ranges[n][0]):
        s, body_s, e = _method_ranges(text, "TokenizerManager", name)
        lines = text.splitlines(keepends=True)
        body_text = "".join(lines[body_s:e])
        body_text = _rewrite_body(body_text)
        new_header = NEW_HEADERS[name]
        text = "".join(lines[:s]) + new_header + body_text + "".join(lines[e:])

    # External caller rewrites: 5 sites. Form: self.<m>(args) ->
    # TokenizerManager.<m>(self.request_preparer, args).
    text = replace_call_site(
        text,
        old="                tokenized_obj = await self._tokenize_one_request(obj)\n",
        new="                tokenized_obj = await TokenizerManager._tokenize_one_request(self.request_preparer, obj)\n",
    )
    text = replace_call_site(
        text,
        old="                        tokenized_obj = await self._tokenize_one_request(tmp_obj)\n",
        new="                        tokenized_obj = await TokenizerManager._tokenize_one_request(self.request_preparer, tmp_obj)\n",
    )
    text = replace_call_site(
        text,
        old="                *(self._tokenize_one_request(obj) for obj in objs)\n",
        new="                *(TokenizerManager._tokenize_one_request(self.request_preparer, obj) for obj in objs)\n",
    )
    text = replace_call_site(
        text,
        old="                tokenized_objs = await self._batch_tokenize_and_process(batch_size, obj)\n",
        new="                tokenized_objs = await TokenizerManager._batch_tokenize_and_process(self.request_preparer, batch_size, obj)\n",
    )
    text = replace_call_site(
        text,
        old="            if self._should_use_batch_tokenization(batch_size, obj):\n",
        new="            if TokenizerManager._should_use_batch_tokenization(self.request_preparer, batch_size, obj):\n",
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
