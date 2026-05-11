#!/usr/bin/env python3
"""Move 5 validate methods to RequestValidator."""

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

ID = "introduce-request-validator-move"
SUBJECT = "Move validate methods to RequestValidator"
BODY = """\
Cut 5 _validate_* methods from TokenizerManager into RequestValidator.
Privacy flip per design (private helper -> new class public API):
  _validate_one_request -> validate_one
  _validate_input_ids_in_vocab -> validate_input_ids_in_vocab
  _validate_batch_tokenization_constraints -> validate_batch_tokenization_constraints
  _validate_mm_limits / _validate_for_matryoshka_dim stay private.

Body rewrites: self.server_args.X / self.model_config.X / self.<context_len-etc>
-> self.config.X. Callers in TM updated to self.request_validator.<...>.
"""
AREA = "mech_tokenizer_manager"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


EXTRA_IMPORTS = '''import logging
from typing import Union

from sglang.srt.managers.io_struct import EmbeddingReqInput, GenerateReqInput

logger = logging.getLogger(__name__)
'''


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
    rv = wt / "python/sglang/srt/managers/request_validator.py"

    method_names = (
        "_validate_one_request",
        "_validate_mm_limits",
        "_validate_for_matryoshka_dim",
        "_validate_input_ids_in_vocab",
        "_validate_batch_tokenization_constraints",
    )
    name_to_range = {}
    for n in method_names:
        s, e = find_method_lines(tm.read_text(), class_name="TokenizerManager", method_name=n)
        name_to_range[n] = (s, e)
    cut_blocks = {}
    for n in sorted(method_names, key=lambda nn: -name_to_range[nn][0]):
        s, e = find_method_lines(tm.read_text(), class_name="TokenizerManager", method_name=n)
        cut_blocks[n] = cut_lines(tm, s, e)

    def rewrite_body(body: str) -> str:
        for field in CONFIG_FIELDS_LONG:
            short = field.split(".", 1)[1]
            body = body.replace(f"self.{field}", f"self.config.{short}")
        for field in CONFIG_FIELDS_SHORT:
            body = body.replace(f"self.{field}", f"self.config.{field}")
        return body

    validate_one = rewrite_body(cut_blocks["_validate_one_request"]).replace(
        "def _validate_one_request(\n        self, obj: Union[GenerateReqInput, EmbeddingReqInput], input_ids: List[int]\n    ) -> None:",
        "def validate_one(\n        self, *, obj: Union[GenerateReqInput, EmbeddingReqInput], input_ids: List[int]\n    ) -> None:",
    )
    validate_mm_limits = rewrite_body(cut_blocks["_validate_mm_limits"])
    validate_matryoshka = rewrite_body(cut_blocks["_validate_for_matryoshka_dim"])
    validate_input_ids_in_vocab = rewrite_body(cut_blocks["_validate_input_ids_in_vocab"]).replace(
        "def _validate_input_ids_in_vocab(\n        self, input_ids: Union[List[int], List[List[int]]], vocab_size: int\n    ) -> None:",
        "def validate_input_ids_in_vocab(\n        self, *, input_ids: Union[List[int], List[List[int]]], vocab_size: int\n    ) -> None:",
    )
    validate_batch_constraints = rewrite_body(cut_blocks["_validate_batch_tokenization_constraints"]).replace(
        "def _validate_batch_tokenization_constraints(\n        self, batch_size: int, obj: Union[GenerateReqInput, EmbeddingReqInput]\n    ) -> None:",
        "def validate_batch_tokenization_constraints(\n        self, *, batch_size: int, obj: Union[GenerateReqInput, EmbeddingReqInput]\n    ) -> None:",
    )

    rv_text = rv.read_text()
    rv_text = rv_text.replace(
        "from dataclasses import dataclass\n",
        "from dataclasses import dataclass\n\n" + EXTRA_IMPORTS,
    )
    rv.write_text(
        rv_text.rstrip()
        + "\n"
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

    # Caller updates in TM.
    text = tm.read_text()
    text = text.replace(
        "        self._validate_one_request(obj, input_ids)",
        "        self.request_validator.validate_one(obj=obj, input_ids=input_ids)",
    )
    text = text.replace(
        "            self._validate_one_request(obj[i], input_ids_list[i])",
        "            self.request_validator.validate_one(obj=obj[i], input_ids=input_ids_list[i])",
    )
    text = replace_call_site(
        text,
        old="                self._validate_mm_limits(obj)",
        new="                self.request_validator._validate_mm_limits(obj)",
    )
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
