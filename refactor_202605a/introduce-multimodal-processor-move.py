#!/usr/bin/env python3
"""Move EPD dispatch methods to MultimodalProcessor."""

# /// script
# requires-python = ">=3.10"
# dependencies = ["typer"]
# ///

import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from _helpers import cut_lines, find_method_lines, replace_call_site
from _runner import run_pr

ID = "introduce-multimodal-processor-move"
SUBJECT = "Move EPD dispatch methods to MultimodalProcessor"
BODY = """\
Cut _should_dispatch_to_encoder + _handle_epd_disaggregation_encode_request
from TM into MultimodalProcessor. Privacy flip per design:
  _should_dispatch_to_encoder            -> should_dispatch_to_encoder
  _handle_epd_disaggregation_encode_request -> maybe_dispatch_to_encoder

Body rewrites self.server_args.X -> self.config.X. Callers updated.
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
    mp = wt / "python/sglang/srt/managers/multimodal_processor.py"

    s, e = find_method_lines(tm.read_text(), class_name="TokenizerManager", method_name="_handle_epd_disaggregation_encode_request")
    handle_text = cut_lines(tm, s, e)
    s, e = find_method_lines(tm.read_text(), class_name="TokenizerManager", method_name="_should_dispatch_to_encoder")
    should_text = cut_lines(tm, s, e)

    def rewrite(body: str) -> str:
        body = body.replace(
            "self.server_args.enable_adaptive_dispatch_to_encoder",
            "self.config.enable_adaptive_dispatch_to_encoder",
        )
        body = body.replace(
            "self.server_args.encoder_transfer_backend",
            "self.config.encoder_transfer_backend",
        )
        body = body.replace(
            "envs.SGLANG_ENCODER_DISPATCH_MIN_ITEMS.get()",
            "self.config.encoder_dispatch_min_items",
        )
        body = body.replace(
            "self._should_dispatch_to_encoder",
            "self.should_dispatch_to_encoder",
        )
        return body

    should_text = rewrite(should_text).replace(
        "def _should_dispatch_to_encoder(",
        "def should_dispatch_to_encoder(",
    )
    handle_text = rewrite(handle_text).replace(
        "def _handle_epd_disaggregation_encode_request(",
        "def maybe_dispatch_to_encoder(",
    )

    mp_text = mp.read_text()
    mp_text = mp_text.replace(
        "from dataclasses import dataclass\n",
        "from dataclasses import dataclass\n\n" + EXTRA_IMPORTS,
    )
    mp.write_text(mp_text.rstrip() + "\n" + should_text.rstrip() + "\n\n" + handle_text.rstrip() + "\n")

    text = tm.read_text()
    text = replace_call_site(
        text,
        old="            self._handle_epd_disaggregation_encode_request(obj)",
        new="            self.multimodal_processor.maybe_dispatch_to_encoder(obj)",
    )
    text = re.sub(
        r"\bself\.mm_receiver\b",
        "self.multimodal_processor.mm_receiver",
        text,
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
