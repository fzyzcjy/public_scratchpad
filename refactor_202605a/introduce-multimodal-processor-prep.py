#!/usr/bin/env python3
"""Prep: MultimodalProcessor skeleton + composition wiring."""

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

ID = "introduce-multimodal-processor-prep"
SUBJECT = "Prep MultimodalProcessor: skeleton + composition wiring"
BODY = "Per MECH_COMMIT_SPLIT: skeleton + composition only. Methods + callers in next commit."
AREA = "mech_tokenizer_manager"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


SKELETON = '''from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from sglang.srt.configs.model_config import ModelConfig
from sglang.srt.disaggregation.encode_receiver import create_mm_receiver
from sglang.srt.environ import envs
from sglang.srt.server_args import ServerArgs


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
    new = wt / "python/sglang/srt/managers/multimodal_processor_owner.py"
    new.write_text(SKELETON)

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
    text = insert_after(
        text,
        anchor="from sglang.srt.managers.tokenizer_control_mixin import TokenizerControlMixin\n",
        addition="from sglang.srt.managers.multimodal_processor_owner import MultimodalProcessor\n",
    )
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
