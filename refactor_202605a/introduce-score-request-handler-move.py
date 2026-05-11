#!/usr/bin/env python3
"""Move TokenizerManagerScoreMixin body to ScoreRequestHandler; drop mixin from TM bases."""

# /// script
# requires-python = ">=3.10"
# dependencies = ["typer"]
# ///

import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from _helpers import replace_call_site
from _runner import run_pr

ID = "introduce-score-request-handler-move"
SUBJECT = "Move score mixin body to ScoreRequestHandler"
BODY = """\
Cut TokenizerManagerScoreMixin class body and paste into ScoreRequestHandler
(11 methods). Body rewrites: self.is_generation -> self.config.is_generation,
self.server_args.enable_mis -> self.config.enable_mis, self.model_config ->
self.config.model_config.

Drop the mixin from TM bases + delete the mixin file. Entrypoint callers
rewired through self.tokenizer_manager.score_request_handler.
"""
AREA = "mech_tokenizer_manager"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


EXTRA_IMPORTS = '''import logging
import math
from typing import Tuple, Union

from sglang.srt.configs.model_config import is_cross_encoding_pooler_model
from sglang.srt.managers.embed_types import PositionalEmbeds
from sglang.srt.managers.io_struct import EmbeddingReqInput, GenerateReqInput
from sglang.srt.server_args import MIS_DELIMITER_TOKEN_ID

logger = logging.getLogger(__name__)
'''


def transform(wt: Path) -> None:
    tm = wt / "python/sglang/srt/managers/tokenizer_manager.py"
    old_mixin = wt / "python/sglang/srt/managers/tokenizer_manager_score_mixin.py"
    srh = wt / "python/sglang/srt/managers/score_request_handler.py"

    # Extract mixin class body.
    old_text = old_mixin.read_text()
    class_marker = "class TokenizerManagerScoreMixin:\n"
    assert class_marker in old_text, "TokenizerManagerScoreMixin not found"
    body_start = old_text.index(class_marker) + len(class_marker)
    class_body = old_text[body_start:].rstrip() + "\n"

    class_body = class_body.replace("self.is_generation", "self.config.is_generation")
    class_body = class_body.replace("self.server_args.enable_mis", "self.config.enable_mis")
    class_body = class_body.replace("self.model_config", "self.config.model_config")

    srh_text = srh.read_text()
    srh_text = srh_text.replace(
        "from dataclasses import dataclass\n",
        "from dataclasses import dataclass\n\n" + EXTRA_IMPORTS,
    )
    srh.write_text(srh_text.rstrip() + "\n" + class_body)

    old_mixin.unlink()

    # Drop mixin import + base class from TM.
    text = tm.read_text()
    text = replace_call_site(
        text,
        old=(
            "from sglang.srt.managers.tokenizer_manager_score_mixin import (\n"
            "    TokenizerManagerScoreMixin,\n"
            ")\n"
        ),
        new="",
    )
    text = replace_call_site(
        text,
        old="class TokenizerManager(TokenizerControlMixin, TokenizerManagerScoreMixin):",
        new="class TokenizerManager(TokenizerControlMixin):",
    )
    tm.write_text(text)

    # Entrypoint callers.
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
