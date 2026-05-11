#!/usr/bin/env python3
"""Move (pure cut/paste): TokenizerManagerScoreMixin body relocates to ScoreRequestHandler."""

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
SUBJECT = "Move score mixin body to ScoreRequestHandler: pure cut/paste + caller prefix replacement"
BODY = """\
Pure physical move per MECH_COMMIT_SPLIT. Cut TokenizerManagerScoreMixin
class body (11 @staticmethod methods, already retyped to
self: "ScoreRequestHandler" in prep); paste into ScoreRequestHandler,
dropping @staticmethod decorators and restoring plain self. Drop the
mixin base from TokenizerManager bases and delete the mixin file.

Caller prefix replacement:
``TokenizerManagerScoreMixin.<method>(self.tokenizer_manager.score_request_handler, ...)``
→ ``self.tokenizer_manager.score_request_handler.<method>(...)``.
Drop the now-unused TokenizerManagerScoreMixin import from the three
entrypoint caller files.
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

    # ---- 1. Extract the (already-prepped) mixin class body. Bytes inside
    # the class body are identical to what we want in the new class, except
    # for the @staticmethod decorator on each method and the
    # ``self: "ScoreRequestHandler"`` annotation — both stripped below.
    old_text = old_mixin.read_text()
    class_marker = "class TokenizerManagerScoreMixin:\n"
    assert class_marker in old_text, "TokenizerManagerScoreMixin not found"
    body_start = old_text.index(class_marker) + len(class_marker)
    class_body = old_text[body_start:].rstrip() + "\n"

    # Drop @staticmethod decorators (one per method, 11 total).
    class_body = class_body.replace("    @staticmethod\n", "")
    # Restore plain ``self`` (drop the type annotation) — both multi-line and
    # single-line forms.
    class_body = class_body.replace('self: "ScoreRequestHandler",', "self,")
    class_body = class_body.replace('self: "ScoreRequestHandler"', "self")
    # Internal cross-method calls were rewritten by prep to the class-qualified
    # form ``TokenizerManagerScoreMixin.<method>(self, ...)``. After move,
    # methods are regular instance methods on ScoreRequestHandler — flip the
    # qualifier so lint resolves and runtime dispatch lands on the new class.
    class_body = class_body.replace(
        "TokenizerManagerScoreMixin.", "ScoreRequestHandler."
    )

    # ---- 2. Append into the handler module + add the extra imports the
    # moved body needs.
    srh_text = srh.read_text()
    srh_text = srh_text.replace(
        "from dataclasses import dataclass\n",
        "from dataclasses import dataclass\n\n" + EXTRA_IMPORTS,
    )
    srh.write_text(srh_text.rstrip() + "\n" + class_body)

    # ---- 3. Delete the now-empty mixin file.
    old_mixin.unlink()

    # ---- 4. TM: drop mixin import + drop mixin from bases.
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

    # ---- 5. Caller prefix replacement across the three entrypoint files.
    # Every prep-stage ``TokenizerManagerScoreMixin.<method>(self.tokenizer_manager.score_request_handler, ...)``
    # collapses to ``self.tokenizer_manager.score_request_handler.<method>(...)``.
    # Drop the prep-injected mixin import too.
    engine = wt / "python/sglang/srt/entrypoints/engine_score_mixin.py"
    serving_score = wt / "python/sglang/srt/entrypoints/openai/serving_score.py"
    serving_rerank = wt / "python/sglang/srt/entrypoints/openai/serving_rerank.py"

    mixin_import = (
        "from sglang.srt.managers.tokenizer_manager_score_mixin import (\n"
        "    TokenizerManagerScoreMixin,\n"
        ")\n"
    )

    import re as _re
    for path, methods in (
        (engine, ("score_request",)),
        (serving_score, ("score_request",)),
        (serving_rerank, ("score_prompts",)),
    ):
        ftext = path.read_text()
        for method in methods:
            # Handle both single-line and multi-line (black-wrapped) forms.
            ftext = ftext.replace(
                f"TokenizerManagerScoreMixin.{method}(self.tokenizer_manager.score_request_handler, ",
                f"self.tokenizer_manager.score_request_handler.{method}(",
            )
            # Multi-line: `TokenizerManagerScoreMixin.<m>(\n    self.tokenizer_manager.score_request_handler,\n    X`
            ftext = _re.sub(
                rf"TokenizerManagerScoreMixin\.{_re.escape(method)}\(\s*\n(\s*)self\.tokenizer_manager\.score_request_handler,\s*\n\1",
                lambda m, _meth=method: f"self.tokenizer_manager.score_request_handler.{_meth}(\n{m.group(1)}",
                ftext,
            )
        # Drop mixin import (might not exist if no callers needed it).
        if mixin_import in ftext:
            ftext = ftext.replace(mixin_import, "")
        path.write_text(ftext)

    # ScoreResult import in engine_score_mixin.py already points at the new
    # handler module (rewired in prep); nothing more to do for it.


if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        area_branch=AREA_BRANCH,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
