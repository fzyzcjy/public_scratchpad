#!/usr/bin/env python3
"""Move TokenizerManagerScoreMixin into a standalone
``managers/score_request_handler.py`` module. The mixin becomes a
``@dataclass(frozen=True, slots=True, kw_only=True)`` ``ScoreRequestHandler``
class with explicit fields (tokenizer, rid_to_state, generate_request
Callable, config). ``ScoreResult`` moves with it.

Note: score_request_handler.md ch3.1 specifies three Callable fields
(create_tokenized_object / send_one_request / wait_one_response) instead
of one generate_request Callable. The three-Callable form requires
restructuring the body of ``score_request`` (which currently calls
``self.generate_request(...)``) into separate tokenize / send / wait
phases, which is a sub-handler split forbidden in Ch1. PR1 stays
mechanical and keeps a single ``generate_request`` Callable; the
three-Callable refactor is deferred to Ch2 alongside the rest of
score_request_handler.md ch3.2 PR2–PR4.
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
    insert_after,
    replace_call_site,
)
from _runner import run_pr

ID = "introduce-score-request-handler"
SUBJECT = "Introduce ScoreRequestHandler and move score mixin to managers/score_request_handler.py"
BODY = """\
Move the entire TokenizerManagerScoreMixin (11 methods + ScoreResult dataclass)
out of tokenizer_manager_score_mixin.py into a new
managers/score_request_handler.py module as a standalone
@dataclass(frozen=True, slots=True, kw_only=True) ScoreRequestHandler class.

Fields injected via ctor:
  tokenizer (Optional[Any])
  rid_to_state (Dict[str, ReqState])
  generate_request (Callable[..., AsyncIterator[dict]])  -- bound to facade.generate_request
  config (ScoreRequestHandlerConfig: is_generation / enable_mis / model_config)

Caller updates:
  TokenizerManager: drops TokenizerManagerScoreMixin from base classes;
    constructs self.score_request_handler in __init__.
  entrypoints/engine_score_mixin.py / openai/serving_score.py /
    openai/serving_rerank.py: tokenizer_manager.score_{request,prompts}(...)
    -> tokenizer_manager.score_request_handler.score_{request,prompts}(...).
  ScoreResult import in engine_score_mixin.py rewires to the new module.

Deletes tokenizer_manager_score_mixin.py.

Per score_request_handler.md ch3.1 (with deviation noted in script docstring):
single generate_request Callable instead of three (create_tokenized_object /
send_one_request / wait_one_response) -- the latter would require a
sub-handler split that is Ch2 territory.
"""
AREA = "mech_tokenizer_manager"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


# Build the new score_request_handler.py contents.

NEW_FILE_HEADER = '''from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Any, AsyncIterator, Callable, Dict, List, Optional, Tuple, Union

import torch

from sglang.srt.configs.model_config import ModelConfig, is_cross_encoding_pooler_model
from sglang.srt.managers.embed_types import PositionalEmbeds
from sglang.srt.managers.io_struct import EmbeddingReqInput, GenerateReqInput
from sglang.srt.managers.request_state import ReqState
from sglang.srt.server_args import MIS_DELIMITER_TOKEN_ID

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ScoreResult:
    scores: List[List[float]]
    prompt_tokens: int = 0
    # Per-item pooled hidden states (pre-head transformer output).
    # CPU tensors when return_pooled_hidden_states=True; kept as tensors so
    # in-process consumers (gRPC, engine API) avoid a .tolist() round-trip.
    # The HTTP path converts to lists in serving_score.py before JSON serialization.
    # Same layout as scores: one tensor per item (not a single packed 2D tensor).
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
    old_mixin = wt / "python/sglang/srt/managers/tokenizer_manager_score_mixin.py"
    new = wt / "python/sglang/srt/managers/score_request_handler.py"

    # ===== 1. Read old mixin and extract the class body =====
    old_text = old_mixin.read_text()

    # The class body starts at "class TokenizerManagerScoreMixin:\n" and runs to
    # EOF (it's the last definition in the file).
    class_marker = "class TokenizerManagerScoreMixin:\n"
    assert class_marker in old_text, "TokenizerManagerScoreMixin not found"
    body_start = old_text.index(class_marker) + len(class_marker)
    class_body = old_text[body_start:].rstrip() + "\n"

    # ===== 2. Apply self.X -> self.config.X / kept-as-is rewrites =====
    # tokenizer / rid_to_state / generate_request keep the same name (now fields
    # of ScoreRequestHandler with the same name). is_generation / enable_mis /
    # model_config become self.config.X.
    class_body = class_body.replace("self.is_generation", "self.config.is_generation")
    class_body = class_body.replace("self.server_args.enable_mis", "self.config.enable_mis")
    class_body = class_body.replace("self.model_config", "self.config.model_config")

    new.write_text(NEW_FILE_HEADER + class_body)

    # ===== 3. Delete old mixin file =====
    old_mixin.unlink()

    # ===== 4. Update tokenizer_manager.py =====
    text = tm.read_text()

    # Drop the multi-line import block "from sglang.srt.managers.tokenizer_manager_score_mixin import (\n    TokenizerManagerScoreMixin,\n)\n"
    text = replace_call_site(
        text,
        old=(
            "from sglang.srt.managers.tokenizer_manager_score_mixin import (\n"
            "    TokenizerManagerScoreMixin,\n"
            ")\n"
        ),
        new="",
    )

    # Drop TokenizerManagerScoreMixin from base classes.
    text = replace_call_site(
        text,
        old="class TokenizerManager(TokenizerControlMixin, TokenizerManagerScoreMixin):",
        new="class TokenizerManager(TokenizerControlMixin):",
    )

    # Add the new import.
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

    # Wire the handler in __init__: insert before init_request_dispatcher() call.
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

    # ===== 5. Update entrypoint callers =====
    engine = wt / "python/sglang/srt/entrypoints/engine_score_mixin.py"
    serving_score = wt / "python/sglang/srt/entrypoints/openai/serving_score.py"
    serving_rerank = wt / "python/sglang/srt/entrypoints/openai/serving_rerank.py"

    text = engine.read_text()
    text = replace_call_site(
        text,
        old="from sglang.srt.managers.tokenizer_manager_score_mixin import ScoreResult",
        new="from sglang.srt.managers.score_request_handler import ScoreResult",
    )
    text = text.replace(
        "self.tokenizer_manager.score_request(",
        "self.tokenizer_manager.score_request_handler.score_request(",
    )
    engine.write_text(text)

    text = serving_score.read_text()
    text = replace_call_site(
        text,
        old="self.tokenizer_manager.score_request(",
        new="self.tokenizer_manager.score_request_handler.score_request(",
    )
    serving_score.write_text(text)

    text = serving_rerank.read_text()
    text = replace_call_site(
        text,
        old="self.tokenizer_manager.score_prompts(",
        new="self.tokenizer_manager.score_request_handler.score_prompts(",
    )
    serving_rerank.write_text(text)


if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        area_branch=AREA_BRANCH,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
