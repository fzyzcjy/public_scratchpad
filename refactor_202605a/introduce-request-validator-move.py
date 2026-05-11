#!/usr/bin/env python3
"""Move (pure cut/paste): RequestValidator methods relocate from TM to target class."""

# /// script
# requires-python = ">=3.10"
# dependencies = ["typer"]
# ///

import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from _helpers import cut_lines, find_method_lines
from _runner import run_pr

ID = "introduce-request-validator-move"
SUBJECT = "Move RequestValidator methods: pure cut/paste + caller prefix replacement"
BODY = """\
Pure physical move per MECH_COMMIT_SPLIT. Cut 5 @staticmethod _validate_*
methods from TokenizerManager; paste into RequestValidator (drop
@staticmethod, replace ``self: "RequestValidator"`` -> plain ``self``).

Privacy flip per design (scope-induced rename — private TM helper becomes
public API of the new class):
  _validate_one_request -> validate_one
  _validate_input_ids_in_vocab -> validate_input_ids_in_vocab
  _validate_batch_tokenization_constraints -> validate_batch_tokenization_constraints
  _validate_mm_limits / _validate_for_matryoshka_dim stay private.

Caller prefix replacement:
  TokenizerManager._validate_one_request(self.request_validator, ...)
    -> self.request_validator.validate_one(obj=..., input_ids=...)
  TokenizerManager._validate_mm_limits(self.request_validator, ...)
    -> self.request_validator._validate_mm_limits(...)
  TokenizerManager._validate_batch_tokenization_constraints(self.request_validator, ...)
    -> self.request_validator.validate_batch_tokenization_constraints(batch_size=..., obj=...)
Internal call inside validate_one collapses
  TokenizerManager._validate_for_matryoshka_dim(self, obj)
    -> self._validate_for_matryoshka_dim(obj)
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
    rv = wt / "python/sglang/srt/managers/request_validator.py"

    method_names = (
        "_validate_one_request",
        "_validate_mm_limits",
        "_validate_for_matryoshka_dim",
        "_validate_input_ids_in_vocab",
        "_validate_batch_tokenization_constraints",
    )

    # Cut bottom-up to keep line numbers stable.
    name_to_range = {}
    for n in method_names:
        s, e = find_method_lines(tm.read_text(), class_name="TokenizerManager", method_name=n)
        name_to_range[n] = (s, e)
    cut_blocks = {}
    for n in sorted(method_names, key=lambda nn: -name_to_range[nn][0]):
        s, e = find_method_lines(tm.read_text(), class_name="TokenizerManager", method_name=n)
        cut_blocks[n] = cut_lines(tm, s, e)

    def strip_static_self(block: str) -> str:
        # Drop @staticmethod decorator (+ its line) and `self: "RequestValidator"` annotation;
        # the leftover signature already has the right positional layout.
        block = block.replace("    @staticmethod\n", "", 1)
        block = block.replace('self: "RequestValidator",', "self,")
        return block

    # Privacy-flip renames (scope-induced). Single-call replacement on the def line is enough
    # because each method's name appears at most once inside its own block (in `def NAME(`).
    validate_one = strip_static_self(cut_blocks["_validate_one_request"]).replace(
        "def _validate_one_request(", "def validate_one(", 1
    )
    # Collapse internal call that prep turned into TokenizerManager._validate_for_matryoshka_dim(self, obj).
    validate_one = validate_one.replace(
        "TokenizerManager._validate_for_matryoshka_dim(self, obj)",
        "self._validate_for_matryoshka_dim(obj)",
    )

    validate_mm_limits = strip_static_self(cut_blocks["_validate_mm_limits"])
    validate_matryoshka = strip_static_self(cut_blocks["_validate_for_matryoshka_dim"])
    validate_input_ids_in_vocab = strip_static_self(cut_blocks["_validate_input_ids_in_vocab"]).replace(
        "def _validate_input_ids_in_vocab(", "def validate_input_ids_in_vocab(", 1
    )
    validate_batch_constraints = strip_static_self(cut_blocks["_validate_batch_tokenization_constraints"]).replace(
        "def _validate_batch_tokenization_constraints(",
        "def validate_batch_tokenization_constraints(",
        1,
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

    # Caller prefix replacement: TokenizerManager.<method>(self.request_validator, ...)
    #                            -> self.request_validator.<new_name>(...)
    text = tm.read_text()
    text = text.replace(
        "        TokenizerManager._validate_one_request(self.request_validator, obj, input_ids)",
        "        self.request_validator.validate_one(obj=obj, input_ids=input_ids)",
    )
    text = text.replace(
        "            TokenizerManager._validate_one_request(self.request_validator, obj[i], input_ids_list[i])",
        "            self.request_validator.validate_one(obj=obj[i], input_ids=input_ids_list[i])",
    )
    text = text.replace(
        "                TokenizerManager._validate_mm_limits(self.request_validator, obj)",
        "                self.request_validator._validate_mm_limits(obj)",
    )
    text = text.replace(
        "        TokenizerManager._validate_batch_tokenization_constraints(self.request_validator, batch_size, obj)",
        "        self.request_validator.validate_batch_tokenization_constraints(\n"
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
