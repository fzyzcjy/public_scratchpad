#!/usr/bin/env python3
"""Prep: ScoreRequestHandler skeleton + composition wiring."""

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

ID = "introduce-score-request-handler-prep"
SUBJECT = "Prep ScoreRequestHandler: skeleton + composition wiring"
BODY = "Per MECH_COMMIT_SPLIT: skeleton + composition only. Mixin methods moved in next commit."
AREA = "mech_tokenizer_manager"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


SKELETON = '''from __future__ import annotations

from dataclasses import dataclass
from typing import Any, AsyncIterator, Callable, Dict, List, Optional

import torch

from sglang.srt.configs.model_config import ModelConfig
from sglang.srt.managers.request_state import ReqState


@dataclass(frozen=True, slots=True)
class ScoreResult:
    scores: List[List[float]]
    prompt_tokens: int = 0
    pooled_hidden_states: Optional[List[Optional[torch.Tensor]]] = None


@dataclass(frozen=True, slots=True, kw_only=True)
class ScoreRequestHandlerConfig:
    is_generation: bool
    enable_mis: bool
    model_config: ModelConfig


@dataclass(frozen=True, slots=True, kw_only=True)
class ScoreRequestHandler:
    tokenizer: Optional[Any]
    rid_to_state: Dict[str, ReqState]
    generate_request: Callable[..., AsyncIterator[dict]]
    config: ScoreRequestHandlerConfig
'''


def transform(wt: Path) -> None:
    tm = wt / "python/sglang/srt/managers/tokenizer_manager.py"
    new = wt / "python/sglang/srt/managers/score_request_handler.py"
    new.write_text(SKELETON)

    text = tm.read_text()
    text = insert_after(
        text,
        anchor="from sglang.srt.managers.async_dynamic_batch_tokenizer import AsyncDynamicbatchTokenizer\n",
        addition=(
            "from sglang.srt.managers.score_request_handler import (\n"
            "    ScoreRequestHandler,\n"
            "    ScoreRequestHandlerConfig,\n"
            ")\n"
        ),
    )
    text = replace_call_site(
        text,
        old="        # Init request dispatcher\n        self.init_request_dispatcher()",
        new=(
            "        # Score request handler\n"
            "        self.score_request_handler = ScoreRequestHandler(\n"
            "            tokenizer=self.tokenizer,\n"
            "            rid_to_state=self.rid_to_state,\n"
            "            generate_request=self.generate_request,\n"
            "            config=ScoreRequestHandlerConfig(\n"
            "                is_generation=self.is_generation,\n"
            "                enable_mis=self.server_args.enable_mis,\n"
            "                model_config=self.model_config,\n"
            "            ),\n"
            "        )\n"
            "\n"
            "        # Init request dispatcher\n"
            "        self.init_request_dispatcher()"
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
