#!/usr/bin/env python3
"""Move (pure cut/paste): MultimodalProcessor methods relocate from TM to target class."""

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

ID = "introduce-multimodal-processor-move"
SUBJECT = "Move MultimodalProcessor methods: pure cut/paste + privacy flip + caller prefix replacement"
BODY = """\
Pure physical move per MECH_COMMIT_SPLIT. Cut @staticmethod
_should_dispatch_to_encoder + _handle_epd_disaggregation_encode_request
from TokenizerManager; paste into MultimodalProcessor (drop @staticmethod,
replace ``self: "MultimodalProcessor"`` → plain ``self``). Privacy flip
per design:
  _should_dispatch_to_encoder              -> should_dispatch_to_encoder
  _handle_epd_disaggregation_encode_request -> maybe_dispatch_to_encoder

Caller prefix replacement:
  TokenizerManager._handle_epd_disaggregation_encode_request(self.multimodal_processor, obj)
    -> self.multimodal_processor.maybe_dispatch_to_encoder(obj)
  TokenizerManager._should_dispatch_to_encoder(self, obj) (intra-class call)
    -> self.should_dispatch_to_encoder(obj)
"""
AREA = "mech_tokenizer_manager"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


EXTRA_IMPORTS = '''import logging
from typing import Union

from sglang.srt.managers.io_struct import EmbeddingReqInput, GenerateReqInput

logger = logging.getLogger(__name__)
'''


def transform(wt: Path) -> None:
    tm = wt / "python/sglang/srt/managers/tokenizer_manager.py"
    mp = wt / "python/sglang/srt/managers/multimodal_processor_owner.py"

    # Cut bottom-up.
    s, e = find_method_lines(
        tm.read_text(),
        class_name="TokenizerManager",
        method_name="_handle_epd_disaggregation_encode_request",
    )
    handle_text = cut_lines(tm, s, e)
    s, e = find_method_lines(
        tm.read_text(),
        class_name="TokenizerManager",
        method_name="_should_dispatch_to_encoder",
    )
    should_text = cut_lines(tm, s, e)

    # Strip @staticmethod + restore plain self. Privacy flip renames.
    def strip_staticmethod_and_self_type(body: str) -> str:
        body = body.replace("    @staticmethod\n", "", 1)
        body = body.replace('self: "MultimodalProcessor",', "self,")
        return body

    should_text = strip_staticmethod_and_self_type(should_text)
    should_text = should_text.replace(
        "def _should_dispatch_to_encoder(",
        "def should_dispatch_to_encoder(",
        1,
    )

    handle_text = strip_staticmethod_and_self_type(handle_text)
    handle_text = handle_text.replace(
        "def _handle_epd_disaggregation_encode_request(",
        "def maybe_dispatch_to_encoder(",
        1,
    )
    # Intra-class call: TokenizerManager._should_dispatch_to_encoder(self, obj)
    #                 → self.should_dispatch_to_encoder(obj).
    # Regex tolerates the black-wrapped multi-line variant where ``self, obj``
    # ends up on its own line.
    import re as _re

    handle_text = _re.sub(
        r"TokenizerManager\._should_dispatch_to_encoder\(\s*self,\s*obj\s*\)",
        "self.should_dispatch_to_encoder(obj)",
        handle_text,
    )

    mp_text = mp.read_text()
    mp_text = mp_text.replace(
        "from dataclasses import dataclass\n",
        "from dataclasses import dataclass\n\n" + EXTRA_IMPORTS,
    )
    mp.write_text(
        mp_text.rstrip()
        + "\n"
        + should_text.rstrip()
        + "\n\n"
        + handle_text.rstrip()
        + "\n"
    )

    # Caller prefix replacement on TM side.
    text = tm.read_text()
    text = replace_call_site(
        text,
        old=(
            "            TokenizerManager._handle_epd_disaggregation_encode_request(\n"
            "                self.multimodal_processor, obj\n"
            "            )\n"
        ),
        new="            self.multimodal_processor.maybe_dispatch_to_encoder(obj)\n",
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
