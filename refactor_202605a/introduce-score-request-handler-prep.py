#!/usr/bin/env python3
"""Prep: ScoreRequestHandler skeleton + composition wiring + in-place staticmethod conversion + caller rewrites."""

# /// script
# requires-python = ">=3.10"
# dependencies = ["typer"]
# ///

import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from _helpers import insert_after, replace_call_site, wire_component_init
from _runner import run_pr

ID = "introduce-score-request-handler-prep"
SUBJECT = "Stage scoring methods for handoff to ScoreRequestHandler"
BODY = """\
Per MECH_COMMIT_SPLIT §"拆 class 场景": prep does ALL semantic work.

Builds ScoreRequestHandler skeleton (incl. ScoreResult dataclass); wires
composition in TM.__init__; converts all 11 mixin methods to
@staticmethod with self: "ScoreRequestHandler" annotation; applies body
rewrites (self.is_generation -> self.config.is_generation,
self.server_args.enable_mis -> self.config.enable_mis,
self.model_config -> self.config.model_config); rewrites internal
cluster cross-calls to TokenizerManagerScoreMixin.<method>(self, ...) form;
rewrites external callers (engine_score_mixin.py, openai/serving_score.py,
openai/serving_rerank.py) to TokenizerManagerScoreMixin.<method>(
self.tokenizer_manager.score_request_handler, ...) form; rewires ScoreResult
import to point at the new handler module. Methods stay on
TokenizerManagerScoreMixin in this commit; the next commit's pure
cut/paste + caller prefix replacement completes the move.
"""
AREA = "mech_tokenizer_manager"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


SKELETON = '''from __future__ import annotations

from dataclasses import dataclass
from typing import Any, AsyncIterator, Callable, Dict, List, Optional

import torch

from sglang.srt.configs.model_config import ModelConfig
from sglang.srt.managers.tokenizer_manager_components.request_state import ReqState


@dataclass(frozen=True, slots=True, kw_only=True)
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


# Internal cluster cross-calls inside the mixin. Each becomes
# TokenizerManagerScoreMixin.<method>(self, ...) once methods are @staticmethod.
# The 11 mixin methods that may be called internally:
_INTERNAL_METHODS = [
    "score_request",
    "score_prompts",
    "_build_multi_item_token_sequence",
    "_batch_tokenize_query_and_items",
    "_process_multi_item_scoring_results",
    "_process_single_item_scoring_results",
    "_resolve_overrides_for_sequence",
    "_resolve_embed_overrides_for_request",
    "_build_token_id_inputs",
    "_convert_logprobs_to_scores",
    "_extract_logprobs_for_tokens",
]


def _rewrite_internal_cross_calls(text: str) -> str:
    """Rewrite ``self.<method>(`` -> ``TokenizerManagerScoreMixin.<method>(self, `` and
    ``self.<method>()`` -> ``TokenizerManagerScoreMixin.<method>(self)``.

    Done as plain text replace because every occurrence inside the mixin file
    is a cross-call we want to rewrite. ``def self.foo`` doesn't occur.
    """
    for method in _INTERNAL_METHODS:
        # Zero-arg form first (so the nargs replace doesn't eat the closing paren).
        text = text.replace(f"self.{method}()", f"TokenizerManagerScoreMixin.{method}(self)")
        text = text.replace(f"self.{method}(", f"TokenizerManagerScoreMixin.{method}(self, ")
    return text


def _apply_body_rewrites(text: str) -> str:
    """self.X -> self.config.X for fields now living on ScoreRequestHandlerConfig.

    Also handles the two ``getattr(self, "is_generation", True)`` and one
    ``getattr(self, "model_config", None)`` patterns — they're no longer
    needed once self is a ScoreRequestHandler (the fields always exist).
    """
    text = text.replace(
        'is_generation = getattr(self, "is_generation", True)',
        "is_generation = self.config.is_generation",
    )
    text = text.replace(
        'model_config = getattr(self, "model_config", None)',
        "model_config = self.config.model_config",
    )
    text = text.replace("self.server_args.enable_mis", "self.config.enable_mis")
    # Direct attribute forms. Current upstream reads ``self.is_generation`` /
    # ``self.model_config`` directly (the older ``getattr(self, ...)`` forms
    # above are gone), so rewrite the bare reads to the config-backed fields.
    # Done after the getattr forms so we never double-touch: the produced
    # ``self.config.is_generation`` does not contain ``self.is_generation`` as a
    # substring (``self.c`` vs ``self.i``). self.tokenizer / self.rid_to_state /
    # self.generate_request remain untouched — direct fields on the skeleton.
    text = text.replace("self.is_generation", "self.config.is_generation")
    text = text.replace("self.model_config", "self.config.model_config")
    return text


def _convert_methods_to_staticmethod(text: str) -> str:
    """Insert ``@staticmethod`` + retype first param to ``self: "ScoreRequestHandler"``
    for each of the 11 mixin methods. Body stays in place; only header changes.
    """
    for method in _INTERNAL_METHODS:
        # Cover both ``def`` and ``async def`` forms.
        for kw in ("async def", "def"):
            old = f"    {kw} {method}(\n        self,"
            new = f'    @staticmethod\n    {kw} {method}(\n        self: "ScoreRequestHandler",'
            if old in text:
                text = text.replace(old, new, 1)
                break
            # Single-line ``def foo(self, ...):`` form (rare here but cheap to handle).
            old_single = f"    {kw} {method}(self,"
            new_single = f'    @staticmethod\n    {kw} {method}(self: "ScoreRequestHandler",'
            if old_single in text:
                text = text.replace(old_single, new_single, 1)
                break
    return text


def transform(wt: Path) -> None:
    tm = wt / "python/sglang/srt/managers/tokenizer_manager.py"
    mixin = wt / "python/sglang/srt/managers/tokenizer_manager_score_mixin.py"
    new = wt / "python/sglang/srt/managers/tokenizer_manager_components/score_request_handler.py"
    engine = wt / "python/sglang/srt/entrypoints/engine_score_mixin.py"
    serving_score = wt / "python/sglang/srt/entrypoints/openai/serving_score.py"
    serving_rerank = wt / "python/sglang/srt/entrypoints/openai/serving_rerank.py"

    # ---- 1. Build skeleton (incl. ScoreResult) at new path.
    new.write_text(SKELETON)

    # ---- 2. TM: import handler + wire composition.
    text = tm.read_text()
    text = insert_after(
        text,
        anchor="from sglang.srt.managers.async_dynamic_batch_tokenizer import AsyncDynamicbatchTokenizer\n",
        addition=(
            "from sglang.srt.managers.tokenizer_manager_components.score_request_handler import (\n"
            "    ScoreRequestHandler,\n"
            "    ScoreRequestHandlerConfig,\n"
            ")\n"
        ),
    )
    # First owner-class composition: anchor on init_request_dispatcher (which
    # runs at the end of __init__) and insert BEFORE it. Subsequent preps then
    # chain via their own ``# <previous owner>`` markers, all staying above
    # init_request_dispatcher — required because its entry list references
    # ``self.<owner>.handle_X`` and those must exist at call time.
    text = wire_component_init(
        text,
        attr="score_request_handler",
        construction=(
            "        self.score_request_handler = ScoreRequestHandler(\n"
            "            tokenizer=self.tokenizer,\n"
            "            rid_to_state=self.rid_to_state,\n"
            "            generate_request=lambda obj, request=None: self.generate_request(\n"
            "                obj, request\n"
            "            ),\n"
            "            config=ScoreRequestHandlerConfig(\n"
            "                is_generation=self.is_generation,\n"
            "                enable_mis=self.server_args.enable_mis,\n"
            "                model_config=self.model_config,\n"
            "            ),\n"
            "        )\n"
        ),
    )
    tm.write_text(text)

    # ---- 3. Mixin file: delete local ScoreResult def + rewire its import to
    # the new handler module; convert all 11 methods to @staticmethod with
    # self: "ScoreRequestHandler" typing; apply body rewrites; rewrite all
    # 17 internal cluster cross-calls. Body bytes (besides headers + the few
    # rewritten attribute accesses) stay identical, ready for pure cut/paste
    # in the move commit.
    mtext = mixin.read_text()

    # Remove the in-file ScoreResult dataclass (now lives in handler module).
    score_result_block = (
        "@dataclass(frozen=True, slots=True)\n"
        "class ScoreResult:\n"
        "    scores: List[List[float]]\n"
        "    prompt_tokens: int = 0\n"
        "    # Per-item pooled hidden states (pre-head transformer output).\n"
        "    # CPU tensors when return_pooled_hidden_states=True; kept as tensors so\n"
        "    # in-process consumers (gRPC, engine API) avoid a .tolist() round-trip.\n"
        "    # The HTTP path converts to lists in serving_score.py before JSON serialization.\n"
        "    # Same layout as scores: one tensor per item (not a single packed 2D tensor).\n"
        "    pooled_hidden_states: Optional[List[Optional[torch.Tensor]]] = None\n"
        "\n"
        "\n"
    )
    mtext = replace_call_site(mtext, old=score_result_block, new="")
    # Re-import ScoreResult from new module so the mixin's signatures still resolve.
    mtext = insert_after(
        mtext,
        anchor="from sglang.srt.managers.io_struct import EmbeddingReqInput, GenerateReqInput\n",
        addition="from sglang.srt.managers.tokenizer_manager_components.score_request_handler import ScoreResult\n",
    )

    mtext = _convert_methods_to_staticmethod(mtext)
    mtext = _apply_body_rewrites(mtext)
    mtext = _rewrite_internal_cross_calls(mtext)
    mixin.write_text(mtext)

    # ---- 4. External callers: 4 sites. Each ``self.tokenizer_manager.<method>(...)``
    # becomes ``TokenizerManagerScoreMixin.<method>(self.tokenizer_manager.score_request_handler, ...)``.
    # Plus rewire the ScoreResult import in engine_score_mixin.py to the new module.
    etext = engine.read_text()
    etext = replace_call_site(
        etext,
        old="from sglang.srt.managers.tokenizer_manager_score_mixin import ScoreResult",
        new="from sglang.srt.managers.tokenizer_manager_components.score_request_handler import ScoreResult",
    )
    # Two sites in engine_score_mixin.py: score_request.
    etext = replace_call_site(
        etext,
        old="self.tokenizer_manager.score_request(",
        new="TokenizerManagerScoreMixin.score_request(self.tokenizer_manager.score_request_handler, ",
    )
    # Second occurrence (await variant) — replace_call_site replaces all occurrences via str.replace.
    # If the helper only replaces the first, fall back to a direct pass: it uses str.replace which
    # already substitutes all matches. Both call sites have the same prefix so a single pass suffices.
    # Need a TokenizerManagerScoreMixin import in engine_score_mixin.py.
    etext = insert_after(
        etext,
        anchor="from sglang.srt.managers.tokenizer_manager_components.score_request_handler import ScoreResult\n",
        addition=(
            "from sglang.srt.managers.tokenizer_manager_score_mixin import (\n"
            "    TokenizerManagerScoreMixin,\n"
            ")\n"
        ),
    )
    engine.write_text(etext)

    stext = serving_score.read_text()
    stext = replace_call_site(
        stext,
        old="self.tokenizer_manager.score_request(",
        new="TokenizerManagerScoreMixin.score_request(self.tokenizer_manager.score_request_handler, ",
    )
    stext = insert_after(
        stext,
        anchor="from sglang.srt.entrypoints.openai.serving_base import OpenAIServingBase\n",
        addition=(
            "from sglang.srt.managers.tokenizer_manager_score_mixin import (\n"
            "    TokenizerManagerScoreMixin,\n"
            ")\n"
        ),
    )
    serving_score.write_text(stext)

    rtext = serving_rerank.read_text()
    rtext = replace_call_site(
        rtext,
        old="self.tokenizer_manager.score_prompts(",
        new="TokenizerManagerScoreMixin.score_prompts(self.tokenizer_manager.score_request_handler, ",
    )
    rtext = insert_after(
        rtext,
        anchor="from sglang.srt.entrypoints.openai.serving_base import OpenAIServingBase\n",
        addition=(
            "from sglang.srt.managers.tokenizer_manager_score_mixin import (\n"
            "    TokenizerManagerScoreMixin,\n"
            ")\n"
        ),
    )
    serving_rerank.write_text(rtext)


if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        area_branch=AREA_BRANCH,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
