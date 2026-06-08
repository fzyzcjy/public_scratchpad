#!/usr/bin/env python3
"""Prep: TokenizedRequestBuilder skeleton + composition wiring + in-place staticmethod conversion + caller rewrites."""

# /// script
# requires-python = ">=3.10"
# dependencies = ["typer"]
# ///

import ast
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from _helpers import insert_after, replace_call_site, wire_component_init
from _runner import run_pr

ID = "introduce-tokenized-request-builder-prep"
SUBJECT = "Stage TokenizedRequest assembly for handoff to TokenizedRequestBuilder"
BODY = """\
Per MECH_COMMIT_SPLIT §"split-class scenario": prep does ALL semantic work.

Builds TokenizedRequestBuilder skeleton; wires composition in TM.__init__;
converts _create_tokenized_object to @staticmethod with a
self: "TokenizedRequestBuilder" annotation (_resolve_embed_overrides is
already a staticmethod and is left as-is); applies body rewrites;
rewrites callers to ``TokenizerManager._create_tokenized_object(self.tokenized_request_builder, ...)``
form. The method stays on TM in this commit; the next commit's pure
cut/paste + caller prefix replacement completes the move.
"""
AREA = "mech_tokenizer_manager"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


SKELETON = '''from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Type

from sglang.srt.managers.tokenizer_manager_components.request_state import ReqState
from sglang.srt.sampling.sampling_params import SamplingParams


@dataclass(frozen=True, slots=True, kw_only=True)
class TokenizedRequestBuilderConfig:
    vocab_size: int
    preferred_sampling_params: Optional[dict]
    sampling_params_class: Type[SamplingParams]
    disaggregation_transfer_backend: str


@dataclass(slots=True, kw_only=True)
class TokenizedRequestBuilder:
    tokenizer: Optional[Any]
    config: TokenizedRequestBuilderConfig
    rid_to_state: Dict[str, ReqState]
    fake_bootstrap_room_counter: int = 0
'''


def _method_ranges(text: str, class_name: str, method_name: str):
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


# Replacement header for _create_tokenized_object: @staticmethod + self: TargetClass typing.
NEW_CREATE_HEADER = '''    @staticmethod
    def _create_tokenized_object(
        self: "TokenizedRequestBuilder",
        obj: Union[GenerateReqInput, EmbeddingReqInput],
        input_text: str,
        input_ids: Optional[List[int]],
        input_embeds: Optional[Union[List[float], None]] = None,
        mm_inputs=None,
        token_type_ids: Optional[List[int]] = None,
    ) -> Union[TokenizedGenerateReqInput, TokenizedEmbeddingReqInput]:
'''


def transform(wt: Path) -> None:
    tm = wt / "python/sglang/srt/managers/tokenizer_manager.py"
    new = wt / "python/sglang/srt/managers/tokenizer_manager_components/tokenized_request_builder.py"
    new.write_text(SKELETON)

    text = tm.read_text()

    # The fake bootstrap_room counter now lives on TokenizedRequestBuilder (its
    # only reader, _create_tokenized_object, runs with builder-typed self from
    # this commit on), so drop the now-dead facade copy.
    text = replace_call_site(
        text,
        old=(
            "        # Single-source counter for auto-assigning fake bootstrap_room.\n"
            "        self.fake_bootstrap_room_counter = 0\n"
        ),
        new="",
    )

    text = insert_after(
        text,
        anchor="from sglang.srt.managers.tokenizer_control_mixin import TokenizerControlMixin\n",
        addition=(
            "from sglang.srt.managers.tokenizer_manager_components.tokenized_request_builder import (\n"
            "    TokenizedRequestBuilder,\n"
            "    TokenizedRequestBuilderConfig,\n"
            ")\n"
        ),
    )

    # Composition wiring.
    text = wire_component_init(
        text,
        attr="tokenized_request_builder",
        before_attr="request_validator",
        construction=(
            "        self.tokenized_request_builder = TokenizedRequestBuilder(\n"
            "            tokenizer=self.tokenizer,\n"
            "            config=TokenizedRequestBuilderConfig(\n"
            "                vocab_size=self.model_config.vocab_size,\n"
            "                preferred_sampling_params=self.preferred_sampling_params,\n"
            "                sampling_params_class=SamplingParams,\n"
            "                disaggregation_transfer_backend=self.server_args.disaggregation_transfer_backend,\n"
            "            ),\n"
            "        )\n"
        ),
    )

    # Convert _create_tokenized_object to @staticmethod with self: "TokenizedRequestBuilder" typing;
    # apply body rewrites in-place. Body stays in TM class.
    s, body_s, e = _method_ranges(text, "TokenizerManager", "_create_tokenized_object")
    lines = text.splitlines(keepends=True)
    original_header = "".join(lines[s:body_s])
    expected_header = NEW_CREATE_HEADER.replace("    @staticmethod\n", "").replace(
        'self: "TokenizedRequestBuilder",', "self,"
    )
    if original_header.rstrip("\n") != expected_header.rstrip("\n"):
        raise ValueError(
            "_create_tokenized_object header drifted from the expected upstream form:\n"
            + original_header
        )
    body_text = "".join(lines[body_s:e])

    # Body rewrites (self.X → self.config.X / self.tokenizer / etc.)
    body_text = body_text.replace("self.preferred_sampling_params", "self.config.preferred_sampling_params")
    body_text = body_text.replace("self.sampling_params_class", "self.config.sampling_params_class")
    body_text = body_text.replace("self.model_config.vocab_size", "self.config.vocab_size")
    body_text = body_text.replace(
        "self.server_args.disaggregation_transfer_backend",
        "self.config.disaggregation_transfer_backend",
    )
    new_method = NEW_CREATE_HEADER + body_text
    text = "".join(lines[:s]) + new_method + "".join(lines[e:])

    # _create_tokenized_object's body dispatches to it via self; at this commit
    # the builder has no such method yet, so class-qualify (the move collapses
    # it back to self-dispatch).
    text = replace_call_site(
        text,
        old="                positional_embed_overrides = self._resolve_embed_overrides(\n",
        new="                positional_embed_overrides = TokenizerManager._resolve_embed_overrides(\n",
    )

    # _resolve_embed_overrides is already @staticmethod; just retag self typing (it has no `self` param).
    # (Original is `def _resolve_embed_overrides(obj):` so no change needed — leave it.)

    # Caller rewrites: 2 internal sites use _create_tokenized_object.
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
            "        return TokenizerManager._create_tokenized_object(\n"
            "            self.tokenized_request_builder,\n"
            "            obj,\n"
            "            input_text,\n"
            "            input_ids,\n"
            "            input_embeds,\n"
            "            mm_inputs,\n"
            "            token_type_ids,\n"
            "        )\n"
        ),
    )
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
            "            tokenized_objs.append(\n"
            "                TokenizerManager._create_tokenized_object(\n"
            "                    self.tokenized_request_builder,\n"
            "                    req,\n"
            "                    req.text,\n"
            "                    input_ids_list[i],\n"
            "                    None,\n"
            "                    None,\n"
            "                    token_type_ids,\n"
            "                )\n"
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
