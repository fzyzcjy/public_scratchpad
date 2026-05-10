#!/usr/bin/env python3
"""Introduce RequestValidator owner class.

Move 5 validate methods (_validate_one_request / _validate_mm_limits /
_validate_for_matryoshka_dim / _validate_input_ids_in_vocab /
_validate_batch_tokenization_constraints) from TokenizerManager into a new
@dataclass(frozen=True, slots=True, kw_only=True) RequestValidator with a
single config field.

Privacy flips per request_validator.md ch3 (allowed by EXECUTION_GUIDE
private->new-class-public-API exception):
  _validate_one_request                   -> validate_one
  _validate_input_ids_in_vocab            -> validate_input_ids_in_vocab
  _validate_batch_tokenization_constraints -> validate_batch_tokenization_constraints
  _validate_mm_limits / _validate_for_matryoshka_dim stay private.

Callers in TokenizerManager update to self.request_validator.<...>.
"""

# /// script
# requires-python = ">=3.10"
# dependencies = ["typer"]
# ///

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

ID = "introduce-request-validator"
SUBJECT = "Introduce RequestValidator and move 5 validate methods"
BODY = """\
Move 5 validate methods from TokenizerManager into a new
@dataclass(frozen=True, slots=True, kw_only=True) RequestValidator class
with a single RequestValidatorConfig field.

The class lives in managers/inputs/request_validator.py. Body bodies
rewrite self.X -> self.config.X for the dependent fields (context_len,
num_reserved_tokens, is_generation, validate_total_tokens, allow_auto_truncate,
enable_return_hidden_states, enable_custom_logit_processor,
limit_mm_data_per_request, is_matryoshka, matryoshka_dimensions, hidden_size,
model_path).

Method names are renamed per design (privacy flip allowed when private
helper -> new class public API):
  _validate_one_request                    -> validate_one
  _validate_input_ids_in_vocab             -> validate_input_ids_in_vocab
  _validate_batch_tokenization_constraints -> validate_batch_tokenization_constraints
  _validate_mm_limits / _validate_for_matryoshka_dim keep underscore (private).

TokenizerManager.__init__ constructs self.request_validator. Three caller
sites update to self.request_validator.<method>(...).
"""
AREA = "mech_tokenizer_manager"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


HEADER = '''from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Union

from sglang.srt.managers.io_struct import EmbeddingReqInput, GenerateReqInput

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True, kw_only=True)
class RequestValidatorConfig:
    context_len: int
    num_reserved_tokens: int
    is_generation: bool
    validate_total_tokens: bool
    allow_auto_truncate: bool
    enable_return_hidden_states: bool
    enable_custom_logit_processor: bool
    limit_mm_data_per_request: Optional[Dict[str, int]]
    is_matryoshka: bool
    matryoshka_dimensions: Optional[List[int]]
    hidden_size: int
    model_path: str


@dataclass(frozen=True, slots=True, kw_only=True)
class RequestValidator:
    """Request consistency / length / vocab / quota validation."""

    config: RequestValidatorConfig

'''


# Keys whose self.<X> reference must rewrite to self.config.<X> inside the moved bodies.
# Order matters for substring overlap (longest first).
CONFIG_FIELDS_LONG = (
    "server_args.allow_auto_truncate",
    "server_args.enable_return_hidden_states",
    "server_args.enable_custom_logit_processor",
    "server_args.limit_mm_data_per_request",
    "model_config.is_matryoshka",
    "model_config.matryoshka_dimensions",
    "model_config.hidden_size",
    "model_config.model_path",
)
CONFIG_FIELDS_SHORT = (
    "context_len",
    "num_reserved_tokens",
    "validate_total_tokens",
    "is_generation",
)


def transform(wt: Path) -> None:
    tm = wt / "python/sglang/srt/managers/tokenizer_manager.py"
    new = wt / "python/sglang/srt/managers/inputs/request_validator.py"

    # Cut bottom-up so earlier line ranges stay valid.
    method_names = (
        "_validate_one_request",
        "_validate_mm_limits",
        "_validate_for_matryoshka_dim",
        "_validate_input_ids_in_vocab",
        "_validate_batch_tokenization_constraints",
    )
    # Locate, sort by start line desc, then cut.
    name_to_range = {}
    for n in method_names:
        s, e = find_method_lines(tm.read_text(), class_name="TokenizerManager", method_name=n)
        name_to_range[n] = (s, e)

    cut_blocks = {}
    for n in sorted(method_names, key=lambda nn: -name_to_range[nn][0]):
        s, e = find_method_lines(tm.read_text(), class_name="TokenizerManager", method_name=n)
        cut_blocks[n] = cut_lines(tm, s, e)

    def rewrite_body(body: str) -> str:
        # self.server_args.<field> / self.model_config.<field> -> self.config.<field>
        for field in CONFIG_FIELDS_LONG:
            short = field.split(".", 1)[1]
            body = body.replace(f"self.{field}", f"self.config.{short}")
        # bare self.context_len etc. -> self.config.context_len
        # Use word-boundary-style anchors to avoid clobbering longer matches; we
        # rely on the LONG list having already consumed the longer prefixes.
        for field in CONFIG_FIELDS_SHORT:
            body = body.replace(f"self.{field}", f"self.config.{field}")
        return body

    # Rename signatures (privacy flip per design).
    def rename_signature(body: str, *, old: str, new: str) -> str:
        return body.replace(f"def {old}(\n", f"def {new}(\n").replace(
            f"def {old}(self, ", f"def {new}(self, "
        )

    # Build the renamed bodies.
    validate_one = rewrite_body(cut_blocks["_validate_one_request"])
    validate_one = validate_one.replace(
        "def _validate_one_request(\n        self, obj: Union[GenerateReqInput, EmbeddingReqInput], input_ids: List[int]\n    ) -> None:",
        "def validate_one(\n        self, *, obj: Union[GenerateReqInput, EmbeddingReqInput], input_ids: List[int]\n    ) -> None:",
    )

    validate_mm_limits = rewrite_body(cut_blocks["_validate_mm_limits"])

    validate_matryoshka = rewrite_body(cut_blocks["_validate_for_matryoshka_dim"])

    validate_input_ids_in_vocab = rewrite_body(cut_blocks["_validate_input_ids_in_vocab"])
    validate_input_ids_in_vocab = validate_input_ids_in_vocab.replace(
        "def _validate_input_ids_in_vocab(\n        self, input_ids: Union[List[int], List[List[int]]], vocab_size: int\n    ) -> None:",
        "def validate_input_ids_in_vocab(\n        self, *, input_ids: Union[List[int], List[List[int]]], vocab_size: int\n    ) -> None:",
    )

    validate_batch_constraints = rewrite_body(cut_blocks["_validate_batch_tokenization_constraints"])
    validate_batch_constraints = validate_batch_constraints.replace(
        "def _validate_batch_tokenization_constraints(\n        self, batch_size: int, obj: Union[GenerateReqInput, EmbeddingReqInput]\n    ) -> None:",
        "def validate_batch_tokenization_constraints(\n        self, *, batch_size: int, obj: Union[GenerateReqInput, EmbeddingReqInput]\n    ) -> None:",
    )

    # Compose new file. Order: validate_one (entry), then helpers + the two other
    # public APIs in original file order.
    new.write_text(
        HEADER
        + validate_one.rstrip()
        + "\n\n"
        + validate_mm_limits.rstrip()
        + "\n\n"
        + validate_matryoshka.rstrip()
        + "\n\n"
        + validate_input_ids_in_vocab.rstrip()
        + "\n\n"
        + validate_batch_constraints.rstrip()
        + "\n"
    )

    # ===== tokenizer_manager.py: caller updates + ctor wiring =====
    text = tm.read_text()

    # Add import
    text = insert_after(
        text,
        anchor="from sglang.srt.managers.tokenizer_control_mixin import TokenizerControlMixin\n",
        addition=(
            "from sglang.srt.managers.inputs.request_validator import (\n"
            "    RequestValidator,\n"
            "    RequestValidatorConfig,\n"
            ")\n"
        ),
    )

    # Wire validator construction in __init__: insert just before init_request_dispatcher() block.
    text = replace_call_site(
        text,
        old=(
            "        # Score request handler\n"
            "        self.score_request_handler = ScoreRequestHandler(\n"
        ),
        new=(
            "        # Request validator\n"
            "        self.request_validator = RequestValidator(\n"
            "            config=RequestValidatorConfig(\n"
            "                context_len=self.context_len,\n"
            "                num_reserved_tokens=self.num_reserved_tokens,\n"
            "                is_generation=self.is_generation,\n"
            "                validate_total_tokens=self.validate_total_tokens,\n"
            "                allow_auto_truncate=self.server_args.allow_auto_truncate,\n"
            "                enable_return_hidden_states=self.server_args.enable_return_hidden_states,\n"
            "                enable_custom_logit_processor=self.server_args.enable_custom_logit_processor,\n"
            "                limit_mm_data_per_request=self.server_args.limit_mm_data_per_request,\n"
            "                is_matryoshka=self.model_config.is_matryoshka,\n"
            "                matryoshka_dimensions=self.model_config.matryoshka_dimensions,\n"
            "                hidden_size=self.model_config.hidden_size,\n"
            "                model_path=self.model_config.model_path,\n"
            "            ),\n"
            "        )\n"
            "\n"
            "        # Score request handler\n"
            "        self.score_request_handler = ScoreRequestHandler(\n"
        ),
    )

    # Caller site updates.
    # _validate_one_request: 2 sites, both with positional args.
    text = text.replace(
        "        self._validate_one_request(obj, input_ids)",
        "        self.request_validator.validate_one(obj=obj, input_ids=input_ids)",
    )
    text = text.replace(
        "            self._validate_one_request(obj[i], input_ids_list[i])",
        "            self.request_validator.validate_one(obj=obj[i], input_ids=input_ids_list[i])",
    )
    # _validate_mm_limits: 1 site, called from inside MM branch (still on facade).
    text = replace_call_site(
        text,
        old="                self._validate_mm_limits(obj)",
        new="                self.request_validator._validate_mm_limits(obj)",
    )
    # _validate_batch_tokenization_constraints: 1 site.
    text = replace_call_site(
        text,
        old="        self._validate_batch_tokenization_constraints(batch_size, obj)",
        new="        self.request_validator.validate_batch_tokenization_constraints(\n"
            "            batch_size=batch_size, obj=obj\n"
            "        )",
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
