#!/usr/bin/env python3
"""Introduce MultimodalProcessor owner class.

Move two methods (_should_dispatch_to_encoder and
_handle_epd_disaggregation_encode_request) plus the conditional
mm_receiver field construction from init_disaggregation into a new
@dataclass(frozen=True, slots=True, kw_only=True) MultimodalProcessor.

The MM if/else branch in _tokenize_one_request is NOT extracted in this
commit -- that's deferred to mmp-extract-tokenize-branch (#23) per plan
risk #5 / V2.6.

mm_processor stays owned by RawTokenizerWrapper (introduced in #7);
MultimodalProcessor borrows the reference (passed in via ctor).
mm_receiver moves OFF facade INTO MultimodalProcessor.

Privacy flips per md ch3:
  _should_dispatch_to_encoder            -> should_dispatch_to_encoder
  _handle_epd_disaggregation_encode_request -> maybe_dispatch_to_encoder
"""

# /// script
# requires-python = ">=3.10"
# dependencies = ["typer"]
# ///

import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from _helpers import (
    cut_lines,
    find_method_lines,
    insert_after,
    replace_call_site,
)
from _runner import run_pr

ID = "introduce-multimodal-processor"
SUBJECT = "Introduce MultimodalProcessor and move EPD dispatch methods"
BODY = """\
Move _should_dispatch_to_encoder + _handle_epd_disaggregation_encode_request
methods from TokenizerManager into a new @dataclass MultimodalProcessor in
managers/multimodal_processor.py. Also move the conditional
mm_receiver = create_mm_receiver(...) block out of init_disaggregation
into the MultimodalProcessor.from_server_args classmethod factory.

Fields:
  mm_processor (Optional[Any], borrowed reference from RawTokenizerWrapper)
  mm_receiver (Optional, lives here exclusively now)
  config (MultimodalProcessorConfig: language_only, encoder_transfer_backend,
    enable_adaptive_dispatch_to_encoder, encoder_dispatch_min_items)

Renames per design (privacy flip, private -> new class public API):
  _should_dispatch_to_encoder            -> should_dispatch_to_encoder
  _handle_epd_disaggregation_encode_request -> maybe_dispatch_to_encoder

The MM if/else branch in _tokenize_one_request stays on facade -- its
extraction is the separate mmp-extract-tokenize-branch commit (#23).

Caller updates: facade.generate_request calls
self.multimodal_processor.maybe_dispatch_to_encoder; the MM branch of
_tokenize_one_request reads self.multimodal_processor.mm_receiver.
"""
AREA = "mech_tokenizer_manager"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


HEADER = '''from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional, Union

from sglang.srt.configs.model_config import ModelConfig
from sglang.srt.disaggregation.encode_receiver import create_mm_receiver
from sglang.srt.environ import envs
from sglang.srt.managers.io_struct import EmbeddingReqInput, GenerateReqInput
from sglang.srt.server_args import ServerArgs

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True, kw_only=True)
class MultimodalProcessorConfig:
    language_only: bool
    encoder_transfer_backend: str
    enable_adaptive_dispatch_to_encoder: bool
    encoder_dispatch_min_items: int


@dataclass(frozen=True, slots=True, kw_only=True)
class MultimodalProcessor:
    """Owns mm_processor / mm_receiver and EPD dispatch routing."""

    mm_processor: Optional[Any]
    mm_receiver: Optional[Any]
    config: MultimodalProcessorConfig

    @classmethod
    def from_server_args(
        cls,
        *,
        server_args: ServerArgs,
        model_config: ModelConfig,
        mm_processor: Optional[Any],
    ) -> "MultimodalProcessor":
        if server_args.language_only:
            mm_receiver = create_mm_receiver(
                server_args,
                dtype=model_config.dtype,
            )
        else:
            mm_receiver = None
        return cls(
            mm_processor=mm_processor,
            mm_receiver=mm_receiver,
            config=MultimodalProcessorConfig(
                language_only=server_args.language_only,
                encoder_transfer_backend=server_args.encoder_transfer_backend,
                enable_adaptive_dispatch_to_encoder=server_args.enable_adaptive_dispatch_to_encoder,
                encoder_dispatch_min_items=envs.SGLANG_ENCODER_DISPATCH_MIN_ITEMS.get(),
            ),
        )

'''


def transform(wt: Path) -> None:
    tm = wt / "python/sglang/srt/managers/tokenizer_manager.py"
    new = wt / "python/sglang/srt/managers/multimodal_processor.py"

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

    # Apply self.X rewrites + signature renames in bodies.
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
        # Cross-method rename within bodies.
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

    new.write_text(HEADER + should_text.rstrip() + "\n\n" + handle_text.rstrip() + "\n")

    # ===== tokenizer_manager.py: drop mm_receiver assignment block + caller updates =====
    text = tm.read_text()

    # Drop the conditional mm_receiver assignment in init_disaggregation.
    text = replace_call_site(
        text,
        old=(
            "        # Encoder Disaggregation\n"
            "        if self.server_args.language_only:\n"
            "            self.mm_receiver = create_mm_receiver(\n"
            "                self.server_args,\n"
            "                dtype=self.model_config.dtype,\n"
            "            )\n"
        ),
        new="",
    )

    # Caller for maybe_dispatch_to_encoder.
    text = replace_call_site(
        text,
        old="            self._handle_epd_disaggregation_encode_request(obj)",
        new="            self.multimodal_processor.maybe_dispatch_to_encoder(obj)",
    )

    # Caller in MM branch (stays on facade until #23): self.mm_receiver -> self.multimodal_processor.mm_receiver
    # Use word boundary to avoid mm_receiver_X collisions.
    text = re.sub(
        r"\bself\.mm_receiver\b",
        "self.multimodal_processor.mm_receiver",
        text,
    )

    # Add import.
    text = insert_after(
        text,
        anchor="from sglang.srt.managers.tokenizer_control_mixin import TokenizerControlMixin\n",
        addition="from sglang.srt.managers.multimodal_processor import MultimodalProcessor\n",
    )

    # Wire construction: AFTER raw_tokenizer_wrapper is built (it's a dependency)
    # and BEFORE the existing tokenized_request_builder block.
    text = replace_call_site(
        text,
        old=(
            "        # Tokenized request builder\n"
            "        self.tokenized_request_builder = TokenizedRequestBuilder(\n"
        ),
        new=(
            "        # Multimodal processor\n"
            "        self.multimodal_processor = MultimodalProcessor.from_server_args(\n"
            "            server_args=self.server_args,\n"
            "            model_config=self.model_config,\n"
            "            mm_processor=self.raw_tokenizer_wrapper.mm_processor,\n"
            "        )\n"
            "\n"
            "        # Tokenized request builder\n"
            "        self.tokenized_request_builder = TokenizedRequestBuilder(\n"
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
