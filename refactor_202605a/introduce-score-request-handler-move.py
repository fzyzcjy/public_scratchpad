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
from _helpers import replace_call_site, rewrite_intra_class_calls
from _runner import run_pr

ID = "introduce-score-request-handler-move"
SUBJECT = "Hand scoring over to ScoreRequestHandler"
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


_SCORE_METHODS = (
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
)


def transform(wt: Path) -> None:
    tm = wt / "python/sglang/srt/managers/tokenizer_manager.py"
    old_mixin = wt / "python/sglang/srt/managers/tokenizer_manager_score_mixin.py"
    srh = wt / "python/sglang/srt/managers/tokenizer_manager_components/score_request_handler.py"

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
    # Collapse prep-stage ``TokenizerManagerScoreMixin.<m>(self, ...)`` calls to
    # plain ``self.<m>(...)`` — methods are regular instance methods on
    # ScoreRequestHandler after the move.
    class_body = rewrite_intra_class_calls(
        class_body,
        source_classes=["TokenizerManagerScoreMixin"],
        target_class="ScoreRequestHandler",
        methods=list(_SCORE_METHODS),
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
    # The mixin import is pre-existing upstream code; black formats it as a
    # single line when it fits in 88 cols (current main) or as a wrapped
    # ``(\n    Name,\n)`` block otherwise (older main). Tolerate both.
    import re as _re4

    text = tm.read_text()
    text, n_removed = _re4.subn(
        r"from sglang\.srt\.managers\.tokenizer_manager_score_mixin import "
        r"(?:\(\s*TokenizerManagerScoreMixin,?\s*\)|TokenizerManagerScoreMixin)\n",
        "",
        text,
    )
    if n_removed != 1:
        raise ValueError(
            f"expected exactly one TokenizerManagerScoreMixin import in TM, removed {n_removed}"
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

    # ---- 6. Stale module docstring in engine_score_mixin.py mentioning the
    # deleted mixin class.
    engine_text = engine.read_text()
    engine_text = engine_text.replace(
        "These methods delegate to TokenizerManager.score_request() which is provided\n"
        "by TokenizerManagerScoreMixin.",
        "These methods delegate to ``self.tokenizer_manager.score_request_handler.score_request()``\n"
        "(provided by ScoreRequestHandler).",
    )
    engine.write_text(engine_text)

    # ---- 7. Test files referencing the deleted ``tokenizer_manager_score_mixin``
    # module / its ``TokenizerManagerScoreMixin`` class / its ``ScoreResult``
    # re-export. ``score_request_handler`` is the new home for both.
    test_serving_rerank = wt / "test/registered/prefill_only/test_serving_rerank.py"
    if test_serving_rerank.exists():
        t = test_serving_rerank.read_text()
        t = t.replace(
            "from sglang.srt.managers.tokenizer_manager_score_mixin import ScoreResult",
            "from sglang.srt.managers.tokenizer_manager_components.score_request_handler import ScoreResult",
        )
        test_serving_rerank.write_text(t)

    test_embed_overrides = wt / "test/registered/prefill_only/test_embed_overrides.py"
    if test_embed_overrides.exists():
        t = test_embed_overrides.read_text()
        # Fix module-doc reference.
        t = t.replace(
            "- Score mixin override resolution (tokenizer_manager_score_mixin.py)",
            "- ScoreRequestHandler override resolution (score_request_handler.py)",
        )
        # Replace import + class inheritance. The mixin pattern doesn't work
        # against a frozen+slots dataclass; turn ``_FakeMixin`` into a plain
        # stub class and call ScoreRequestHandler's methods as unbound. Tests
        # that mutate ``self.mixin.is_generation`` etc. still work because
        # ``_FakeMixin`` has no slots restriction.
        t = t.replace(
            "from sglang.srt.managers.tokenizer_manager_score_mixin import (\n"
            "    TokenizerManagerScoreMixin,\n"
            ")",
            "from sglang.srt.managers.tokenizer_manager_components.score_request_handler import (\n"
            "    ScoreRequestHandler,\n"
            "    ScoreRequestHandlerConfig,\n"
            ")",
        )
        t = t.replace(
            'class _FakeMixin(TokenizerManagerScoreMixin):\n'
            '    """Minimal stub to call mixin methods without a full TokenizerManager."""\n',
            'class _FakeMixin:\n'
            '    """Minimal stub to call mixin methods without a full TokenizerManager."""\n'
            "\n"
            + "".join(f"    {m} = ScoreRequestHandler.{m}\n" for m in _SCORE_METHODS),
        )
        # score_request reads the config-backed fields, so the fake needs a real
        # ScoreRequestHandlerConfig mirroring its direct attributes.
        t = t.replace(
            "    def __init__(self, enable_mis=False):\n"
            "        self.server_args = _FakeServerArgs(enable_mis)\n"
            "        self.tokenizer = None\n"
            "        self.is_generation = True\n",
            "    def __init__(self, enable_mis=False):\n"
            "        self.server_args = _FakeServerArgs(enable_mis)\n"
            "        self.tokenizer = None\n"
            "        self.is_generation = True\n"
            "        self.config = ScoreRequestHandlerConfig(\n"
            "            is_generation=True,\n"
            "            enable_mis=enable_mis,\n"
            "            model_config=None,\n"
            "        )\n",
        )
        # Rewrite ``self.mixin.<method>(...)`` → ``ScoreRequestHandler.<method>(self.mixin, ...)``
        # for the methods that ScoreRequestHandler owns (now post-move).
        for method in (
            "_resolve_overrides_for_sequence",
            "_resolve_embed_overrides_for_request",
            "_build_token_id_inputs",
            "score_request",
        ):
            t = _re.sub(
                rf"\bself\.mixin\.{_re.escape(method)}\(",
                f"ScoreRequestHandler.{method}(self.mixin, ",
                t,
            )
        test_embed_overrides.write_text(t)


if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        area_branch=AREA_BRANCH,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
