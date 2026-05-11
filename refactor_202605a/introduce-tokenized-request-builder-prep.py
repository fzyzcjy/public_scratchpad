#!/usr/bin/env python3
"""Prep: empty TokenizedRequestBuilder skeleton + composition wiring."""

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

ID = "introduce-tokenized-request-builder-prep"
SUBJECT = "Prep TokenizedRequestBuilder: empty skeleton + composition wiring"
BODY = "Per MECH_COMMIT_SPLIT: skeleton + composition only. Methods + callers in next commit."
AREA = "mech_tokenizer_manager"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


SKELETON = '''from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional, Type

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
    (obj, input_ids, mm_inputs, ...). fake_bootstrap_room_counter mutates per build.
    """

    tokenizer: Optional[Any]
    config: TokenizedRequestBuilderConfig
    fake_bootstrap_room_counter: int = 0
'''


def transform(wt: Path) -> None:
    tm = wt / "python/sglang/srt/managers/tokenizer_manager.py"
    new = wt / "python/sglang/srt/managers/tokenized_request_builder.py"
    new.write_text(SKELETON)

    text = tm.read_text()
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
            "                sampling_params_class=SamplingParams,\n"
            "                disaggregation_transfer_backend=self.server_args.disaggregation_transfer_backend,\n"
            "            ),\n"
            "        )\n"
            "\n"
            "        # Request validator\n"
            "        self.request_validator = RequestValidator(\n"
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
