#!/usr/bin/env python3
"""Prep: RequestPreparer skeleton + composition wiring."""

# /// script
# requires-python = ">=3.10"
# dependencies = ["typer"]
# ///

import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from _helpers import insert_after, replace_call_site
from _runner import run_pr

ID = "introduce-request-preparer-prep"
SUBJECT = "Prep RequestPreparer: skeleton + composition wiring"
BODY = "Per MECH_COMMIT_SPLIT: skeleton + composition only."
AREA = "mech_tokenizer_manager"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


SKELETON = '''from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from sglang.srt.managers.multimodal_processor_owner import MultimodalProcessor
from sglang.srt.managers.raw_tokenizer_wrapper import RawTokenizerWrapper
from sglang.srt.managers.request_state import ReqState
from sglang.srt.managers.request_validator import RequestValidator
from sglang.srt.managers.tokenized_request_builder import TokenizedRequestBuilder


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
    new.write_text(SKELETON)

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
