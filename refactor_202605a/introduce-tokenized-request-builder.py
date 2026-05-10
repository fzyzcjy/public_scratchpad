#!/usr/bin/env python3
"""Introduce TokenizedRequestBuilder owner class.

Move _create_tokenized_object + _resolve_embed_overrides from
TokenizerManager to a new managers/inputs/tokenized_request_builder.py
module. The builder is dataclass-shaped (frozen=False, slots=True per
md ch4 R5 (iii)) because fake_bootstrap_room_counter mutates per-call.

Per design, builder.build() drops the trailing
self.rid_to_state[obj.rid].time_stats side effect; the two caller sites
(_tokenize_one_request / _batch_tokenize_and_process) take over the
time_stats attachment + set_tokenize_finish_time() call.

_create_tokenized_object renames to ``build`` (privacy flip allowed when
private helper -> new class public API).
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

ID = "introduce-tokenized-request-builder"
SUBJECT = "Introduce TokenizedRequestBuilder and move tokenized object construction"
BODY = """\
Move _create_tokenized_object (~100 LOC) and _resolve_embed_overrides
(staticmethod helper) from TokenizerManager into a new
@dataclass(frozen=False, slots=True, kw_only=True) TokenizedRequestBuilder
class in managers/inputs/tokenized_request_builder.py.

Fields:
  tokenizer (Optional[Any])
  config (TokenizedRequestBuilderConfig: vocab_size,
    preferred_sampling_params, sampling_params_class,
    disaggregation_transfer_backend)
  fake_bootstrap_room_counter (int = 0; mutates per build)

frozen=False because fake_bootstrap_room_counter mutates (R5 (iii)).

Per design (tokenized_request_builder.md): builder.build() is a pure
function -- the trailing two lines that wrote
self.rid_to_state[obj.rid].time_stats / .set_tokenize_finish_time()
move to the two callers (_tokenize_one_request / _batch_tokenize_and_process).
This is design-authorized non-strict-mechanical (V2.5 of plan).

_create_tokenized_object -> build (privacy flip exception); _resolve_embed_overrides
keeps underscore (private helper).
"""
AREA = "mech_tokenizer_manager"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


HEADER = '''from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Optional, Type, Union

import torch

from sglang.srt.managers.embed_types import PositionalEmbeds
from sglang.srt.managers.io_struct import (
    EmbeddingReqInput,
    GenerateReqInput,
    SessionParams,
    TokenizedEmbeddingReqInput,
    TokenizedGenerateReqInput,
)
from sglang.srt.sampling.sampling_params import SamplingParams


@dataclass(frozen=True, slots=True, kw_only=True)
class TokenizedRequestBuilderConfig:
    vocab_size: int
    preferred_sampling_params: Optional[dict]
    sampling_params_class: Type[SamplingParams]
    disaggregation_transfer_backend: str


@dataclass(slots=True, kw_only=True)
class TokenizedRequestBuilder:
    """Build TokenizedGenerateReqInput / TokenizedEmbeddingReqInput from
    (obj, input_ids, mm_inputs, ...). Pure function w.r.t. external state;
    fake_bootstrap_room_counter is the only internal mutable field.
    """

    tokenizer: Optional[Any]
    config: TokenizedRequestBuilderConfig
    fake_bootstrap_room_counter: int = 0

'''


def transform(wt: Path) -> None:
    tm = wt / "python/sglang/srt/managers/tokenizer_manager.py"
    new = wt / "python/sglang/srt/managers/inputs/tokenized_request_builder.py"

    # Cut bottom-up so earlier ranges stay valid.
    s, e = find_method_lines(
        tm.read_text(),
        class_name="TokenizerManager",
        method_name="_resolve_embed_overrides",
    )
    resolve_text = cut_lines(tm, s, e)

    s, e = find_method_lines(
        tm.read_text(),
        class_name="TokenizerManager",
        method_name="_create_tokenized_object",
    )
    create_text = cut_lines(tm, s, e)

    # Rewrite create body:
    body = create_text
    # Signature rename + kw-only.
    body = body.replace(
        "def _create_tokenized_object(\n"
        "        self,\n"
        "        obj: Union[GenerateReqInput, EmbeddingReqInput],\n"
        "        input_text: str,\n"
        "        input_ids: List[int],\n"
        "        input_embeds: Optional[List[float]] = None,\n"
        "        mm_inputs: Optional[Any] = None,\n"
        "        token_type_ids: Optional[List[int]] = None,\n"
        "    ) -> Union[TokenizedGenerateReqInput, TokenizedEmbeddingReqInput]:",
        "def build(\n"
        "        self,\n"
        "        obj: Union[GenerateReqInput, EmbeddingReqInput],\n"
        "        *,\n"
        "        input_text: str,\n"
        "        input_ids: List[int],\n"
        "        input_embeds: Optional[List[float]] = None,\n"
        "        mm_inputs: Optional[Any] = None,\n"
        "        token_type_ids: Optional[List[int]] = None,\n"
        "    ) -> Union[TokenizedGenerateReqInput, TokenizedEmbeddingReqInput]:",
    )
    body = body.replace(
        "self.preferred_sampling_params", "self.config.preferred_sampling_params"
    )
    body = body.replace(
        "self.sampling_params_class", "self.config.sampling_params_class"
    )
    body = body.replace(
        "self.raw_tokenizer_wrapper.tokenizer", "self.tokenizer"
    )
    body = body.replace(
        "self.model_config.vocab_size", "self.config.vocab_size"
    )
    body = body.replace(
        "self.server_args.disaggregation_transfer_backend",
        "self.config.disaggregation_transfer_backend",
    )
    # Drop the trailing time_stats side-effect lines (design-authorized).
    body = body.replace(
        "        tokenized_obj.time_stats = self.rid_to_state[obj.rid].time_stats\n"
        "        self.rid_to_state[obj.rid].time_stats.set_tokenize_finish_time()\n"
        "\n"
        "        return tokenized_obj\n",
        "        return tokenized_obj\n",
    )

    # _resolve_embed_overrides body unchanged (staticmethod, no self.X refs).
    new.write_text(HEADER + body.rstrip() + "\n\n" + resolve_text.rstrip() + "\n")

    # ===== tokenizer_manager.py: caller updates + ctor wiring + import =====
    text = tm.read_text()

    text = insert_after(
        text,
        anchor="from sglang.srt.managers.tokenizer_control_mixin import TokenizerControlMixin\n",
        addition=(
            "from sglang.srt.managers.inputs.tokenized_request_builder import (\n"
            "    TokenizedRequestBuilder,\n"
            "    TokenizedRequestBuilderConfig,\n"
            ")\n"
        ),
    )

    # Wire builder construction in __init__: insert before request_validator block.
    text = replace_call_site(
        text,
        old=(
            "        # Request validator\n"
            "        self.request_validator = RequestValidator(\n"
        ),
        new=(
            "        # Tokenized request builder\n"
            "        self.tokenized_request_builder = TokenizedRequestBuilder(\n"
            "            tokenizer=self.raw_tokenizer_wrapper.tokenizer,\n"
            "            config=TokenizedRequestBuilderConfig(\n"
            "                vocab_size=self.model_config.vocab_size,\n"
            "                preferred_sampling_params=self.preferred_sampling_params,\n"
            "                sampling_params_class=self.sampling_params_class,\n"
            "                disaggregation_transfer_backend=self.server_args.disaggregation_transfer_backend,\n"
            "            ),\n"
            "        )\n"
            "\n"
            "        # Request validator\n"
            "        self.request_validator = RequestValidator(\n"
        ),
    )

    # Caller 1: in _tokenize_one_request, the trailing return now needs side-effect.
    text = replace_call_site(
        text,
        old=(
            "        self.request_validator.validate_one(obj=obj, input_ids=input_ids)\n"
            "        return self._create_tokenized_object(\n"
            "            obj, input_text, input_ids, input_embeds, mm_inputs, token_type_ids\n"
            "        )\n"
        ),
        new=(
            "        self.request_validator.validate_one(obj=obj, input_ids=input_ids)\n"
            "        tokenized_obj = self.tokenized_request_builder.build(\n"
            "            obj,\n"
            "            input_text=input_text,\n"
            "            input_ids=input_ids,\n"
            "            input_embeds=input_embeds,\n"
            "            mm_inputs=mm_inputs,\n"
            "            token_type_ids=token_type_ids,\n"
            "        )\n"
            "        tokenized_obj.time_stats = self.rid_to_state[obj.rid].time_stats\n"
            "        self.rid_to_state[obj.rid].time_stats.set_tokenize_finish_time()\n"
            "        return tokenized_obj\n"
        ),
    )

    # Caller 2: in _batch_tokenize_and_process.
    text = replace_call_site(
        text,
        old=(
            "            tokenized_objs.append(\n"
            "                self._create_tokenized_object(\n"
            "                    req, req.text, input_ids_list[i], None, None, token_type_ids\n"
            "                )\n"
            "            )\n"
        ),
        new=(
            "            tokenized_obj = self.tokenized_request_builder.build(\n"
            "                req,\n"
            "                input_text=req.text,\n"
            "                input_ids=input_ids_list[i],\n"
            "                token_type_ids=token_type_ids,\n"
            "            )\n"
            "            tokenized_obj.time_stats = self.rid_to_state[req.rid].time_stats\n"
            "            self.rid_to_state[req.rid].time_stats.set_tokenize_finish_time()\n"
            "            tokenized_objs.append(tokenized_obj)\n"
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
