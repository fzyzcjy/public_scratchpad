#!/usr/bin/env python3
"""Introduce RawTokenizerWrapper owner class.

Moves ownership of tokenizer / processor / mm_processor /
async_dynamic_batch_tokenizer fields from TokenizerManager to a new
@dataclass(frozen=True, slots=True, kw_only=True) RawTokenizerWrapper.

The init_tokenizer_and_processor method body becomes a
RawTokenizerWrapper.from_server_args classmethod factory (per R5 (iii)
escape hatch for frozen dataclasses needing branchy field derivation).

Subsequent commit (rtw-move-tokenize-helpers) moves the 4 tokenize-pipeline
helper methods (_detect_input_format / _prepare_tokenizer_input /
_extract_tokenizer_results / _tokenize_texts) into the class.
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

ID = "introduce-raw-tokenizer-wrapper"
SUBJECT = "Introduce RawTokenizerWrapper and move tokenizer/processor fields"
BODY = """\
Move ownership of four fields (tokenizer, processor, mm_processor,
async_dynamic_batch_tokenizer) from TokenizerManager to a new frozen
@dataclass RawTokenizerWrapper in managers/inputs/raw_tokenizer_wrapper.py.

The init_tokenizer_and_processor method becomes the
RawTokenizerWrapper.from_server_args classmethod factory (R5 (iii)).
TokenizerManager.__init__ replaces self.init_tokenizer_and_processor()
with self.raw_tokenizer_wrapper = RawTokenizerWrapper.from_server_args(...).

All self.{tokenizer, processor, mm_processor, async_dynamic_batch_tokenizer}
references in tokenizer_manager.py and tokenizer_control_mixin.py rewrite
to self.raw_tokenizer_wrapper.<field>. The score handler ctor binding
re-wires from tokenizer=self.tokenizer to
tokenizer=self.raw_tokenizer_wrapper.tokenizer.

Tokenize-pipeline helpers (_detect_input_format / _prepare_tokenizer_input /
_extract_tokenizer_results / _tokenize_texts) stay on the facade for now;
they migrate in the follow-up rtw-move-tokenize-helpers commit.
"""
AREA = "mech_tokenizer_manager"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


HEADER = '''from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Optional

from sglang.srt.configs.model_config import ModelConfig
from sglang.srt.environ import envs
from sglang.srt.managers.async_dynamic_batch_tokenizer import AsyncDynamicbatchTokenizer
from sglang.srt.managers.multimodal_processor import get_mm_processor, import_processors
from sglang.srt.server_args import ServerArgs
from sglang.srt.utils.hf_transformers_utils import (
    get_processor,
    get_tokenizer,
    get_tokenizer_from_processor,
)


def _get_processor_wrapper(server_args: ServerArgs):
    """Mirror of TokenizerManager-side _get_processor_wrapper helper."""
    return get_processor(
        server_args.tokenizer_path,
        tokenizer_mode=server_args.tokenizer_mode,
        trust_remote_code=server_args.trust_remote_code,
        revision=server_args.revision,
        use_fast=not server_args.disable_fast_image_processor,
    )


def _determine_tensor_transport_mode(server_args: ServerArgs):
    """Mirror of TokenizerManager-side _determine_tensor_transport_mode."""
    from sglang.srt.managers.mm_utils import TensorTransportMode

    if server_args.disaggregation_mode == "decode":
        return TensorTransportMode.DEFAULT
    return TensorTransportMode.DEFAULT


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
        # Initialize tokenizer and processor
        if model_config.is_multimodal:
            import_processors("sglang.srt.multimodal.processors")
            if mm_process_pkg := envs.SGLANG_EXTERNAL_MM_PROCESSOR_PACKAGE.get():
                import_processors(mm_process_pkg, overwrite=True)
            _processor = _get_processor_wrapper(server_args)
            transport_mode = _determine_tensor_transport_mode(server_args)

            # We want to parallelize the image pre-processing so we create an executor for it
            # We create mm_processor for any skip_tokenizer_init to make sure we still encode
            # images even with skip_tokenizer_init=False.
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

        # Initialize async dynamic batch tokenizer if enabled (common for both multimodal and non-multimodal)
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


# Names whose self.<X> reference must rewrite to self.raw_tokenizer_wrapper.<X>.
# Order matters for substring overlap (longest first).
RTW_FIELDS = (
    "async_dynamic_batch_tokenizer",
    "mm_processor",
    "processor",
    "tokenizer",
)


def rewrite_self_field_refs(text: str) -> str:
    """Replace self.<field> with self.raw_tokenizer_wrapper.<field>, using
    word boundary so e.g. self.tokenizer_manager / self.tokenizer_ipc_name
    don't match.
    """
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
    inputs_dir = wt / "python/sglang/srt/managers/inputs"
    # __init__.py created by define-scheduler-sender; just ensure dir.
    inputs_dir.mkdir(exist_ok=True)
    new = inputs_dir / "raw_tokenizer_wrapper.py"
    new.write_text(HEADER)

    # ===== Cut init_tokenizer_and_processor (its body lives inline in the new file) =====
    s, e = find_method_lines(
        tm.read_text(), class_name="TokenizerManager", method_name="init_tokenizer_and_processor"
    )
    cut_lines(tm, s, e)  # discard

    # ===== Rewrite all self.<rtw-field> references in tokenizer_manager.py =====
    text = tm.read_text()
    text = rewrite_self_field_refs(text)

    # ===== Replace the init_tokenizer_and_processor() call with construction =====
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

    # ===== Score handler ctor binding =====
    text = replace_call_site(
        text,
        old="            tokenizer=self.raw_tokenizer_wrapper.tokenizer,\n            rid_to_state=self.rid_to_state,",
        new="            tokenizer=self.raw_tokenizer_wrapper.tokenizer,\n            rid_to_state=self.rid_to_state,",
    )
    # (the rewrite_self_field_refs above already handled tokenizer=self.tokenizer
    # -> tokenizer=self.raw_tokenizer_wrapper.tokenizer; the line above is a sanity
    # no-op that fails loudly if the substitution is missing.)

    # ===== Add import =====
    text = insert_after(
        text,
        anchor="from sglang.srt.managers.async_dynamic_batch_tokenizer import AsyncDynamicbatchTokenizer\n",
        addition="from sglang.srt.managers.inputs.raw_tokenizer_wrapper import RawTokenizerWrapper\n",
    )

    tm.write_text(text)

    # ===== tokenizer_control_mixin.py: same self.X rewrites =====
    text = control.read_text()
    text = rewrite_self_field_refs(text)
    control.write_text(text)

    # ===== External callers (entrypoints/, template_manager.py) =====
    # tokenizer_manager.tokenizer / .processor -> .raw_tokenizer_wrapper.tokenizer / .processor
    import glob
    external_files = [Path(p) for p in glob.glob(
        str(wt / "python/sglang/srt/entrypoints/**/*.py"), recursive=True
    )]
    external_files.append(wt / "python/sglang/srt/managers/template_manager.py")
    for f in external_files:
        if not f.exists():
            continue
        t = f.read_text()
        t = re.sub(
            r"\btokenizer_manager\.tokenizer\b",
            "tokenizer_manager.raw_tokenizer_wrapper.tokenizer",
            t,
        )
        t = re.sub(
            r"\btokenizer_manager\.processor\b",
            "tokenizer_manager.raw_tokenizer_wrapper.processor",
            t,
        )
        f.write_text(t)


if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        area_branch=AREA_BRANCH,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
