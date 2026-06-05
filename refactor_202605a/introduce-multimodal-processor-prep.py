#!/usr/bin/env python3
"""Prep: MultimodalProcessor skeleton + composition + staticmethod conversion + caller rewrites."""

# /// script
# requires-python = ">=3.10"
# dependencies = ["typer"]
# ///

import ast
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from _helpers import insert_after, replace_call_site, wire_component_init
from _runner import run_pr

ID = "introduce-multimodal-processor-prep"
SUBJECT = "Stage EPD dispatch for handoff to MultimodalProcessor"
BODY = """\
Per MECH_COMMIT_SPLIT §"拆 class 场景": prep does ALL semantic work.

Builds MultimodalProcessor skeleton (incl. from_server_args factory);
wires composition in TM.__init__; drops the conditional mm_receiver block
from init_disaggregation; converts _should_dispatch_to_encoder +
_handle_epd_disaggregation_encode_request to @staticmethod with
self: "MultimodalProcessor" annotation; applies body rewrites; rewrites
callers to TokenizerManager.<method>(self.multimodal_processor, ...) form
and self.mm_receiver -> self.multimodal_processor.mm_receiver. Methods
stay on TM in this commit; the next commit's pure cut/paste + caller
prefix replacement (+ privacy flip rename) completes the move.
"""
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
                hf_config=model_config.hf_config,
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


def _method_ranges(text: str, class_name: str, method_name: str):
    tree = ast.parse(text)
    func_types = (ast.FunctionDef, ast.AsyncFunctionDef)
    for cls in ast.walk(tree):
        if isinstance(cls, ast.ClassDef) and cls.name == class_name:
            for i, node in enumerate(cls.body):
                if isinstance(node, func_types) and node.name == method_name:
                    start = node.lineno - 1
                    if node.decorator_list:
                        start = node.decorator_list[0].lineno - 1
                    body_start = node.body[0].lineno - 1
                    if i + 1 < len(cls.body):
                        end = cls.body[i + 1].lineno - 1
                        nxt = cls.body[i + 1]
                        if isinstance(nxt, func_types + (ast.ClassDef,)) and nxt.decorator_list:
                            end = nxt.decorator_list[0].lineno - 1
                    else:
                        end = node.end_lineno
                    return start, body_start, end
    raise ValueError(f"{class_name}.{method_name} not found")


# Replacement headers: @staticmethod + self: "MultimodalProcessor" typing.
NEW_SHOULD_HEADER = '''    @staticmethod
    def _should_dispatch_to_encoder(
        self: "MultimodalProcessor",
        obj: Union[GenerateReqInput, EmbeddingReqInput],
    ) -> bool:
'''

NEW_HANDLE_HEADER = '''    @staticmethod
    def _handle_epd_disaggregation_encode_request(
        self: "MultimodalProcessor",
        obj: Union[GenerateReqInput, EmbeddingReqInput],
    ):
'''


def _rewrite_method(
    text: str,
    *,
    method_name: str,
    new_header: str,
    body_rewrites: list[tuple[str, str]],
) -> str:
    """Replace the method (decorators + signature + body) with new_header + rewritten body."""
    s, body_s, e = _method_ranges(text, "TokenizerManager", method_name)
    lines = text.splitlines(keepends=True)
    body_text = "".join(lines[body_s:e])
    for old, new in body_rewrites:
        body_text = body_text.replace(old, new)
    new_method = new_header + body_text
    return "".join(lines[:s]) + new_method + "".join(lines[e:])


def transform(wt: Path) -> None:
    tm = wt / "python/sglang/srt/managers/tokenizer_manager.py"
    new = wt / "python/sglang/srt/managers/tokenizer_manager_components/multimodal_processor_owner.py"
    new.write_text(SKELETON)

    text = tm.read_text()

    # Drop the conditional mm_receiver assignment in init_disaggregation
    # (composition now owns mm_receiver via MultimodalProcessor.from_server_args).
    text = replace_call_site(
        text,
        old=(
            "        # Encoder Disaggregation\n"
            "        if self.server_args.language_only:\n"
            "            self.mm_receiver = create_mm_receiver(\n"
            "                self.server_args,\n"
            "                dtype=self.model_config.dtype,\n"
            "                hf_config=self.model_config.hf_config,\n"
            "            )\n"
        ),
        new="",
    )

    text = insert_after(
        text,
        anchor="from sglang.srt.managers.tokenizer_control_mixin import TokenizerControlMixin\n",
        addition="from sglang.srt.managers.tokenizer_manager_components.multimodal_processor_owner import MultimodalProcessor\n",
    )

    # Composition wiring.
    text = wire_component_init(
        text,
        attr="multimodal_processor",
        before_attr="tokenized_request_builder",
        construction=(
            "        self.multimodal_processor = MultimodalProcessor.from_server_args(\n"
            "            server_args=self.server_args,\n"
            "            model_config=self.model_config,\n"
            "            mm_processor=self.mm_processor,\n"
            "        )\n"
        ),
    )

    # Convert _should_dispatch_to_encoder to @staticmethod with self: "MultimodalProcessor"
    # typing; apply body rewrites in-place. Body stays in TM class.
    text = _rewrite_method(
        text,
        method_name="_should_dispatch_to_encoder",
        new_header=NEW_SHOULD_HEADER,
        body_rewrites=[
            (
                "envs.SGLANG_ENCODER_DISPATCH_MIN_ITEMS.get()",
                "self.config.encoder_dispatch_min_items",
            ),
        ],
    )

    # Convert _handle_epd_disaggregation_encode_request similarly.
    # Inner self._should_dispatch_to_encoder(obj) call is rewritten to
    # TokenizerManager._should_dispatch_to_encoder(self, obj) (class-qualified call
    # per MECH_COMMIT_SPLIT — "脱 self" is reflected in the call site).
    text = _rewrite_method(
        text,
        method_name="_handle_epd_disaggregation_encode_request",
        new_header=NEW_HANDLE_HEADER,
        body_rewrites=[
            (
                "self.server_args.enable_adaptive_dispatch_to_encoder",
                "self.config.enable_adaptive_dispatch_to_encoder",
            ),
            (
                "should_dispatch = self._should_dispatch_to_encoder(obj)",
                "should_dispatch = TokenizerManager._should_dispatch_to_encoder(self, obj)",
            ),
            (
                "self.server_args.encoder_transfer_backend",
                "self.config.encoder_transfer_backend",
            ),
        ],
    )

    # Caller rewrite: self._handle_epd_disaggregation_encode_request(obj)
    # → TokenizerManager._handle_epd_disaggregation_encode_request(self.multimodal_processor, obj)
    text = replace_call_site(
        text,
        old="            self._handle_epd_disaggregation_encode_request(obj)\n",
        new=(
            "            TokenizerManager._handle_epd_disaggregation_encode_request(\n"
            "                self.multimodal_processor, obj\n"
            "            )\n"
        ),
    )

    # Re-emit self.mm_receiver → self.multimodal_processor.mm_receiver at TM-level
    # call sites (mm_receiver is now owned by MP via composition).
    text = text.replace(
        "                    mm_inputs = await self.mm_receiver.recv_mm_data(\n",
        "                    mm_inputs = await self.multimodal_processor.mm_receiver.recv_mm_data(\n",
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
