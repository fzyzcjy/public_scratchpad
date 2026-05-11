#!/usr/bin/env python3
"""Prep: empty RequestValidator skeleton + composition wiring."""

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

ID = "introduce-request-validator-prep"
SUBJECT = "Prep RequestValidator: empty skeleton + composition wiring"
BODY = """\
Per MECH_COMMIT_SPLIT: skeleton + composition wiring only. Methods + caller
rewrites land in the next commit.
"""
AREA = "mech_tokenizer_manager"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


SKELETON = '''from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass(frozen=True, slots=True, kw_only=True)
class RequestValidatorConfig:
    context_len: int
    num_reserved_tokens: int
    is_generation: bool
    validate_total_tokens: bool
    allow_auto_truncate: bool
    enable_return_hidden_states: bool
    enable_custom_logit_processor: bool
    limit_mm_data_per_request: Optional[Dict[str, int]]
    is_matryoshka: bool
    matryoshka_dimensions: Optional[List[int]]
    hidden_size: int
    model_path: str


@dataclass(frozen=True, slots=True, kw_only=True)
class RequestValidator:
    """Request consistency / length / vocab / quota validation."""

    config: RequestValidatorConfig
'''


def transform(wt: Path) -> None:
    tm = wt / "python/sglang/srt/managers/tokenizer_manager.py"
    new = wt / "python/sglang/srt/managers/request_validator.py"
    new.write_text(SKELETON)

    text = tm.read_text()
    text = insert_after(
        text,
        anchor="from sglang.srt.managers.tokenizer_control_mixin import TokenizerControlMixin\n",
        addition=(
            "from sglang.srt.managers.request_validator import (\n"
            "    RequestValidator,\n"
            "    RequestValidatorConfig,\n"
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
            "        # Request validator\n"
            "        self.request_validator = RequestValidator(\n"
            "            config=RequestValidatorConfig(\n"
            "                context_len=self.context_len,\n"
            "                num_reserved_tokens=self.num_reserved_tokens,\n"
            "                is_generation=self.is_generation,\n"
            "                validate_total_tokens=self.validate_total_tokens,\n"
            "                allow_auto_truncate=self.server_args.allow_auto_truncate,\n"
            "                enable_return_hidden_states=self.server_args.enable_return_hidden_states,\n"
            "                enable_custom_logit_processor=self.server_args.enable_custom_logit_processor,\n"
            "                limit_mm_data_per_request=self.server_args.limit_mm_data_per_request,\n"
            "                is_matryoshka=self.model_config.is_matryoshka,\n"
            "                matryoshka_dimensions=self.model_config.matryoshka_dimensions,\n"
            "                hidden_size=self.model_config.hidden_size,\n"
            "                model_path=self.model_config.model_path,\n"
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
