#!/usr/bin/env python3
"""Move _create_tokenized_object + _resolve_embed_overrides to TokenizedRequestBuilder."""

# /// script
# requires-python = ">=3.10"
# dependencies = ["typer"]
# ///

import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from _helpers import cut_lines, find_method_lines, replace_call_site
from _runner import run_pr

ID = "introduce-tokenized-request-builder-move"
SUBJECT = "Move tokenized-object construction to TokenizedRequestBuilder"
BODY = """\
Cut _create_tokenized_object + _resolve_embed_overrides from TokenizerManager
into TokenizedRequestBuilder. _create_tokenized_object renamed to ``build``.
Body rewrites self.server_args.X / self.model_config.X / etc -> self.config.X.

Per design (tokenized_request_builder.md): the trailing time_stats side-effect
moves to the 2 callers (V2.5 of plan).
"""
AREA = "mech_tokenizer_manager"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


EXTRA_IMPORTS = '''from typing import List, Union

import torch

from sglang.srt.managers.embed_types import PositionalEmbeds
from sglang.srt.managers.io_struct import (
    EmbeddingReqInput,
    GenerateReqInput,
    SessionParams,
    TokenizedEmbeddingReqInput,
    TokenizedGenerateReqInput,
)
'''


def transform(wt: Path) -> None:
    tm = wt / "python/sglang/srt/managers/tokenizer_manager.py"
    trb = wt / "python/sglang/srt/managers/tokenized_request_builder.py"

    s, e = find_method_lines(tm.read_text(), class_name="TokenizerManager", method_name="_resolve_embed_overrides")
    resolve_text = cut_lines(tm, s, e)
    s, e = find_method_lines(tm.read_text(), class_name="TokenizerManager", method_name="_create_tokenized_object")
    create_text = cut_lines(tm, s, e)

    body = create_text
    body = body.replace("def _create_tokenized_object(", "def build(")
    body = body.replace("self.preferred_sampling_params", "self.config.preferred_sampling_params")
    body = body.replace("self.sampling_params_class", "self.config.sampling_params_class")
    body = body.replace("self.raw_tokenizer_wrapper.tokenizer", "self.tokenizer")
    body = body.replace("self.model_config.vocab_size", "self.config.vocab_size")
    body = body.replace(
        "self.server_args.disaggregation_transfer_backend",
        "self.config.disaggregation_transfer_backend",
    )
    body = body.replace(
        "        tokenized_obj.time_stats = self.rid_to_state[obj.rid].time_stats\n"
        "        self.rid_to_state[obj.rid].time_stats.set_tokenize_finish_time()\n"
        "\n"
        "        return tokenized_obj\n",
        "        return tokenized_obj\n",
    )

    trb_text = trb.read_text()
    trb_text = trb_text.replace(
        "from dataclasses import dataclass\n",
        "from dataclasses import dataclass\n\n" + EXTRA_IMPORTS,
    )
    trb.write_text(trb_text.rstrip() + "\n" + body.rstrip() + "\n\n" + resolve_text.rstrip() + "\n")

    # Caller updates.
    text = tm.read_text()
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
