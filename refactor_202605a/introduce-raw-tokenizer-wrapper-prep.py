#!/usr/bin/env python3
"""Prep: RawTokenizerWrapper full skeleton (with factory) + composition wiring + facade field rewrites."""

# /// script
# requires-python = ">=3.10"
# dependencies = ["typer"]
# ///

import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from _helpers import insert_after, replace_call_site
from _runner import run_pr

ID = "introduce-raw-tokenizer-wrapper-prep"
SUBJECT = "Prep RawTokenizerWrapper: skeleton + factory + composition wiring + facade field rewrites"
BODY = "Per MECH_COMMIT_SPLIT: build the target file + composition wiring + facade self.<field> rewrites; move (cut init_tokenizer_and_processor + InputFormat + entrypoint rewrites) is next commit."
AREA = "mech_tokenizer_manager"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


HEADER = '''from __future__ import annotations  # noqa: F401

import logging  # noqa: F401
import os  # noqa: F401
from dataclasses import dataclass  # noqa: F401
from enum import Enum  # noqa: F401
from typing import Any, Optional  # noqa: F401

from sglang.srt.configs.model_config import ModelConfig  # noqa: F401
from sglang.srt.environ import envs  # noqa: F401
from sglang.srt.managers.async_dynamic_batch_tokenizer import AsyncDynamicbatchTokenizer  # noqa: F401
from sglang.srt.managers.multimodal_processor import get_mm_processor, import_processors  # noqa: F401
from sglang.srt.server_args import ServerArgs  # noqa: F401
from sglang.srt.utils.hf_transformers_utils import (  # noqa: F401
    get_processor,
    get_tokenizer,
    get_tokenizer_from_processor,
)

logger = logging.getLogger(__name__)


class InputFormat(Enum):
    """Input format types for tokenization handling."""

    SINGLE_STRING = 1
    BATCH_STRINGS = 2
    CROSS_ENCODER_PAIRS = 3


def _get_processor_wrapper(server_args: ServerArgs):
    try:
        processor = get_processor(
            server_args.tokenizer_path,
            tokenizer_mode=server_args.tokenizer_mode,
            trust_remote_code=server_args.trust_remote_code,
            revision=server_args.revision,
            use_fast=not server_args.disable_fast_image_processor,
            tokenizer_backend=server_args.tokenizer_backend,
        )
    except ValueError as e:
        error_message = str(e)
        if "does not have a slow version" in error_message:
            logger.info(
                f"Processor {server_args.tokenizer_path} does not have a slow version. Automatically use fast version"
            )
            processor = get_processor(
                server_args.tokenizer_path,
                tokenizer_mode=server_args.tokenizer_mode,
                trust_remote_code=server_args.trust_remote_code,
                revision=server_args.revision,
                use_fast=True,
                tokenizer_backend=server_args.tokenizer_backend,
            )
        else:
            raise e
    return processor


def _determine_tensor_transport_mode(server_args: ServerArgs):
    is_cross_node = server_args.dist_init_addr
    if is_cross_node:
        return "default"
    else:
        return "cuda_ipc"


@dataclass(frozen=True, slots=True, kw_only=True)
class RawTokenizerWrapper:
    """Owns tokenizer / processor / mm_processor / async_dynamic_batch_tokenizer."""

    tokenizer: Optional[Any]
    processor: Optional[Any]
    mm_processor: Optional[Any]
    async_dynamic_batch_tokenizer: Optional[AsyncDynamicbatchTokenizer]

    @classmethod
    def from_server_args(
        cls,
        *,
        server_args: ServerArgs,
        model_config: ModelConfig,
    ) -> "RawTokenizerWrapper":
        if model_config.is_multimodal:
            import_processors("sglang.srt.multimodal.processors")
            if mm_process_pkg := envs.SGLANG_EXTERNAL_MM_PROCESSOR_PACKAGE.get():
                import_processors(mm_process_pkg, overwrite=True)
            _processor = _get_processor_wrapper(server_args)
            transport_mode = _determine_tensor_transport_mode(server_args)
            mm_processor = get_mm_processor(
                model_config.hf_config,
                server_args,
                _processor,
                transport_mode,
                model_config=model_config,
            )
            if server_args.skip_tokenizer_init:
                tokenizer = processor = None
            else:
                processor = _processor
                tokenizer = get_tokenizer_from_processor(processor)
                os.environ["TOKENIZERS_PARALLELISM"] = "false"
        else:
            mm_processor = processor = None
            if server_args.skip_tokenizer_init:
                tokenizer = None
            else:
                tokenizer = get_tokenizer(
                    server_args.tokenizer_path,
                    tokenizer_mode=server_args.tokenizer_mode,
                    trust_remote_code=server_args.trust_remote_code,
                    revision=server_args.revision,
                    tokenizer_backend=server_args.tokenizer_backend,
                )
        if (
            server_args.enable_dynamic_batch_tokenizer
            and not server_args.skip_tokenizer_init
        ):
            async_dynamic_batch_tokenizer = AsyncDynamicbatchTokenizer(
                tokenizer,
                max_batch_size=server_args.dynamic_batch_tokenizer_batch_size,
                batch_wait_timeout_s=server_args.dynamic_batch_tokenizer_batch_timeout,
            )
        else:
            async_dynamic_batch_tokenizer = None
        return cls(
            tokenizer=tokenizer,
            processor=processor,
            mm_processor=mm_processor,
            async_dynamic_batch_tokenizer=async_dynamic_batch_tokenizer,
        )
'''


RTW_FIELDS = (
    "async_dynamic_batch_tokenizer",
    "mm_processor",
    "processor",
    "tokenizer",
)


def rewrite_self_field_refs(text: str) -> str:
    for field in RTW_FIELDS:
        text = re.sub(
            rf"self\.{re.escape(field)}\b",
            f"self.raw_tokenizer_wrapper.{field}",
            text,
        )
    return text


def transform(wt: Path) -> None:
    tm = wt / "python/sglang/srt/managers/tokenizer_manager.py"
    control = wt / "python/sglang/srt/managers/tokenizer_control_mixin.py"
    new = wt / "python/sglang/srt/managers/raw_tokenizer_wrapper.py"
    new.write_text(HEADER)

    # Replace the init_tokenizer_and_processor() call with composition wiring.
    text = tm.read_text()
    text = replace_call_site(
        text,
        old="        # Initialize tokenizer and multimodalprocessor\n        self.init_tokenizer_and_processor()",
        new=(
            "        # Initialize tokenizer and multimodal processor\n"
            "        self.raw_tokenizer_wrapper = RawTokenizerWrapper.from_server_args(\n"
            "            server_args=self.server_args,\n"
            "            model_config=self.model_config,\n"
            "        )"
        ),
    )
    # Rewrite self.<field> refs in TM (not within init_tokenizer_and_processor body,
    # which still exists as a now-orphaned method until move).
    text = rewrite_self_field_refs(text)
    text = insert_after(
        text,
        anchor="from sglang.srt.managers.async_dynamic_batch_tokenizer import AsyncDynamicbatchTokenizer\n",
        addition="from sglang.srt.managers.raw_tokenizer_wrapper import RawTokenizerWrapper\n",
    )
    tm.write_text(text)

    text = control.read_text()
    text = rewrite_self_field_refs(text)
    control.write_text(text)


if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        area_branch=AREA_BRANCH,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
