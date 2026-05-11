#!/usr/bin/env python3
"""Inplace prep for ``introduce-tokenized-request-builder``: create the
``TokenizedRequestBuilder`` skeleton (with ``TokenizedRequestBuilderConfig``)
in a new file, instantiate ``self.tokenized_request_builder`` in
TokenizerManager.__init__, convert ``_create_tokenized_object`` to
``@staticmethod def build(self: TokenizedRequestBuilder, ...)`` inplace and
rewrite its body's ``self.X`` reads to resolve against the builder, and
rewrite the 2 caller sites to ``TokenizerManager.build(self.tokenized_request_builder, ...)``.

``_resolve_embed_overrides`` is already a ``@staticmethod`` (no self) and
stays inplace in this commit; physical relocation happens in
``introduce-tokenized-request-builder-move``.

Body bytes are byte-identical wrt the post-move state (modulo decorator +
the ``def build(self: TokenizedRequestBuilder, ...)`` -> ``def build(self, ...)``
signature simplification in the move commit).
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

ID = "introduce-tokenized-request-builder-prep"
SUBJECT = "Build TokenizedRequestBuilder skeleton + @staticmethod prep (prep for move)"
BODY = """\
Inplace prep for the ``introduce-tokenized-request-builder`` mech move.

- Create ``managers/tokenized_request_builder.py`` with
  ``TokenizedRequestBuilderConfig`` (frozen=True, slots=True, kw_only=True;
  vocab_size / preferred_sampling_params / sampling_params_class /
  disaggregation_transfer_backend) and an empty ``TokenizedRequestBuilder``
  (slots=True, kw_only=True; tokenizer / config /
  fake_bootstrap_room_counter=0). No methods yet.
- Instantiate ``self.tokenized_request_builder = TokenizedRequestBuilder(...)``
  in ``TokenizerManager.__init__`` just before the request_validator block.
- In TokenizerManager, convert ``_create_tokenized_object`` to
  ``@staticmethod`` with ``self: "TokenizedRequestBuilder"`` type annotation
  and rename to ``build`` (privacy flip allowed when private helper -> new
  class public API). Body's ``self.preferred_sampling_params`` /
  ``self.sampling_params_class`` / ``self.raw_tokenizer_wrapper.tokenizer`` /
  ``self.model_config.vocab_size`` /
  ``self.server_args.disaggregation_transfer_backend`` rewritten to resolve
  against the builder's ``tokenizer`` / ``config`` fields. The trailing two
  lines that wrote ``self.rid_to_state[obj.rid].time_stats`` /
  ``set_tokenize_finish_time()`` are removed from the body and absorbed by
  the 2 callers (design-authorized; ``rid_to_state`` is not a builder
  field). The single intra-body call ``self._resolve_embed_overrides(...)``
  rewritten to ``TokenizerManager._resolve_embed_overrides(...)`` (it stays
  on TM until the move commit).
- ``_resolve_embed_overrides`` already ``@staticmethod`` -- no changes; it
  stays in TM in this commit.
- 2 callers rewritten:
  ``self._create_tokenized_object(...)`` ->
  ``TokenizerManager.build(self.tokenized_request_builder, ...)`` with
  keyword-only args; trailing ``tokenized_obj.time_stats = ...`` /
  ``set_tokenize_finish_time()`` lines added at each call site.

The ``build`` staticmethod stays inside TokenizerManager in this commit;
physical cut + paste to ``TokenizedRequestBuilder`` body happens in
``introduce-tokenized-request-builder-move``.
"""
AREA = "mech_tokenizer_manager"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


# Header for the new builder file (skeleton only, no methods yet).
BUILDER_HEADER = '''from __future__ import annotations

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


# Construction snippet for TokenizerManager.__init__. Inserted just before
# the request_validator block.
INIT_INSERT = '''        # Tokenized request builder
        self.tokenized_request_builder = TokenizedRequestBuilder(
            tokenizer=self.raw_tokenizer_wrapper.tokenizer,
            config=TokenizedRequestBuilderConfig(
                vocab_size=self.model_config.vocab_size,
                preferred_sampling_params=self.preferred_sampling_params,
                sampling_params_class=SamplingParams,
                disaggregation_transfer_backend=self.server_args.disaggregation_transfer_backend,
            ),
        )

'''


# Trailing two lines to remove from the build body. Indented at 8 spaces
# (inside class -> inside method).
TIME_STATS_BLOCK = (
    "        tokenized_obj.time_stats = self.rid_to_state[obj.rid].time_stats\n"
    "        self.rid_to_state[obj.rid].time_stats.set_tokenize_finish_time()\n"
    "\n"
    "        return tokenized_obj\n"
)
TIME_STATS_REPLACEMENT = "        return tokenized_obj\n"


def transform(wt: Path) -> None:
    tm = wt / "python/sglang/srt/managers/tokenizer_manager.py"
    builder = wt / "python/sglang/srt/managers/tokenized_request_builder.py"

    # 1. Create new file with skeleton (no methods yet).
    builder.write_text(BUILDER_HEADER)

    # 2. In TokenizerManager, transform _create_tokenized_object inplace:
    #    @staticmethod, rename to build, type-flip self, body field-path
    #    rewrites, drop trailing time_stats side-effect block, retarget
    #    intra-body call to _resolve_embed_overrides.
    text = tm.read_text()
    s, e = find_method_lines(
        text, class_name="TokenizerManager", method_name="_create_tokenized_object"
    )
    lines = text.splitlines(keepends=True)
    method_text = "".join(lines[s:e])

    new_method = method_text.replace(
        "    def _create_tokenized_object(\n        self,\n",
        "    @staticmethod\n"
        "    def build(\n"
        "        self: \"TokenizedRequestBuilder\",\n",
        1,
    )
    if new_method == method_text:
        raise RuntimeError("_create_tokenized_object signature shape unexpected")

    # Body field-path rewrites: self.X reads now resolve against the builder.
    new_method = new_method.replace(
        "self.preferred_sampling_params", "self.config.preferred_sampling_params"
    )
    new_method = new_method.replace(
        "self.sampling_params_class", "self.config.sampling_params_class"
    )
    new_method = new_method.replace(
        "self.raw_tokenizer_wrapper.tokenizer", "self.tokenizer"
    )
    new_method = new_method.replace(
        "self.model_config.vocab_size", "self.config.vocab_size"
    )
    new_method = new_method.replace(
        "self.server_args.disaggregation_transfer_backend",
        "self.config.disaggregation_transfer_backend",
    )
    # Intra-body call: _resolve_embed_overrides still lives on TM in this
    # commit, so qualify it explicitly.
    new_method = new_method.replace(
        "self._resolve_embed_overrides(",
        "TokenizerManager._resolve_embed_overrides(",
    )
    # Drop trailing time_stats side-effect block (design-authorized; moves
    # to the 2 callers).
    if TIME_STATS_BLOCK not in new_method:
        raise RuntimeError("time_stats trailing-block anchor mismatch")
    new_method = new_method.replace(TIME_STATS_BLOCK, TIME_STATS_REPLACEMENT)

    text = "".join(lines[:s]) + new_method + "".join(lines[e:])

    # 3. Add import for TokenizedRequestBuilder / Config.
    text = insert_after(
        text,
        anchor="from sglang.srt.managers.tokenizer_control_mixin import TokenizerControlMixin\n",
        addition=(
            "from sglang.srt.managers.tokenized_request_builder import (\n"
            "    TokenizedRequestBuilder,\n"
            "    TokenizedRequestBuilderConfig,\n"
            ")\n"
        ),
    )

    # 4. Wire builder instantiation in TokenizerManager.__init__, just
    # before the request_validator block.
    text = replace_call_site(
        text,
        old=(
            "        # Request validator\n"
            "        self.request_validator = RequestValidator(\n"
        ),
        new=(
            INIT_INSERT
            + "        # Request validator\n"
            "        self.request_validator = RequestValidator(\n"
        ),
    )

    # 5. Caller 1: _tokenize_one_request. Trailing return absorbs the
    # time_stats side-effect that was dropped from the body.
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
            "        tokenized_obj = TokenizerManager.build(\n"
            "            self.tokenized_request_builder,\n"
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

    # 6. Caller 2: _batch_tokenize_and_process.
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
            "            tokenized_obj = TokenizerManager.build(\n"
            "                self.tokenized_request_builder,\n"
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
