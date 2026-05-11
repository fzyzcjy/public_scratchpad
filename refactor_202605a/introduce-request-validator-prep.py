#!/usr/bin/env python3
"""Inplace prep for ``introduce-request-validator``: build the
``RequestValidator`` (+ ``RequestValidatorConfig``) skeleton, instantiate
``self.request_validator`` in ``TokenizerManager.__init__``, convert 5
validate methods to ``@staticmethod`` with ``self: "RequestValidator"``,
rewrite bodies ``self.<server_args|model_config|...>.X`` -> ``self.config.X``
and apply the rename / kw-only privacy flip per design.

Callers updated to ``TokenizerManager.<method>(self.request_validator, ...)``.

The 5 methods stay inside TokenizerManager in this commit; physical cut +
paste to ``RequestValidator`` body happens in
``introduce-request-validator-move`` (pure prefix-strip move).
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
    find_method_lines,
    insert_after,
    replace_call_site,
)
from _runner import run_pr

ID = "introduce-request-validator-prep"
SUBJECT = "Build RequestValidator skeleton + @staticmethod prep (prep for move)"
BODY = """\
Inplace prep for the ``introduce-request-validator`` mech move.

- Create ``managers/request_validator.py`` with
  ``RequestValidatorConfig`` (dataclass of 12 config fields) and an empty
  ``RequestValidator`` dataclass (single ``config`` field). No methods yet.
- Instantiate ``self.request_validator = RequestValidator(config=...)`` in
  ``TokenizerManager.__init__``.
- In ``TokenizerManager``, convert 5 validate methods to ``@staticmethod``
  with ``self: "RequestValidator"`` type annotation:
    _validate_one_request
    _validate_mm_limits
    _validate_for_matryoshka_dim
    _validate_input_ids_in_vocab
    _validate_batch_tokenization_constraints
- Rewrite bodies ``self.server_args.X`` / ``self.model_config.X`` /
  bare ``self.context_len`` etc. -> ``self.config.X``. Apply the privacy /
  kw-only rename per design:
    _validate_one_request                    -> validate_one
    _validate_input_ids_in_vocab             -> validate_input_ids_in_vocab
    _validate_batch_tokenization_constraints -> validate_batch_tokenization_constraints
  ``_validate_mm_limits`` / ``_validate_for_matryoshka_dim`` stay private.
- Callers (4 sites) rewritten to
  ``TokenizerManager.<method>(self.request_validator, ...)`` (class-qualified
  call), making the move-commit caller rewrite a pure prefix replacement.

Body bytes byte-identical wrt the post-move state (modulo decorator + the
``self: "RequestValidator"`` -> ``self`` simplification in the move
commit).
"""
AREA = "mech_tokenizer_manager"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


VALIDATOR_HEADER = '''from __future__ import annotations

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


INIT_INSERT = '''        # Request validator
        self.request_validator = RequestValidator(
            config=RequestValidatorConfig(
                context_len=self.context_len,
                num_reserved_tokens=self.num_reserved_tokens,
                is_generation=self.is_generation,
                validate_total_tokens=self.validate_total_tokens,
                allow_auto_truncate=self.server_args.allow_auto_truncate,
                enable_return_hidden_states=self.server_args.enable_return_hidden_states,
                enable_custom_logit_processor=self.server_args.enable_custom_logit_processor,
                limit_mm_data_per_request=self.server_args.limit_mm_data_per_request,
                is_matryoshka=self.model_config.is_matryoshka,
                matryoshka_dimensions=self.model_config.matryoshka_dimensions,
                hidden_size=self.model_config.hidden_size,
                model_path=self.model_config.model_path,
            ),
        )

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


def _rewrite_body(text: str) -> str:
    """Rewrite ``self.server_args.X`` / ``self.model_config.X`` / bare
    ``self.context_len`` etc. -> ``self.config.X`` inside one method block."""
    for field in CONFIG_FIELDS_LONG:
        short = field.split(".", 1)[1]
        text = text.replace(f"self.{field}", f"self.config.{short}")
    for field in CONFIG_FIELDS_SHORT:
        text = text.replace(f"self.{field}", f"self.config.{field}")
    return text


def _retype_static_multiline(
    method_text: str,
    *,
    old_name: str,
    new_name: str,
    add_kwonly_star: bool,
) -> str:
    """Multi-line signature form. Old:
        ``    def <old>(\n        self, <arg>:`` ...
    New:
        ``    @staticmethod\n    def <new>(\n        self: "RequestValidator", [*, ]<arg>:`` ...
    """
    old_anchor = f"    def {old_name}(\n        self, "
    if old_anchor not in method_text:
        raise RuntimeError(f"signature shape mismatch for {old_name}")
    star = "*, " if add_kwonly_star else ""
    new_anchor = (
        f"    @staticmethod\n"
        f"    def {new_name}(\n"
        f'        self: "RequestValidator", {star}'
    )
    return method_text.replace(old_anchor, new_anchor, 1)


def _retype_static_oneline(
    method_text: str,
    *,
    old_name: str,
    new_name: str,
) -> str:
    """Single-line signature form: ``    def <old>(self, <arg>: ...)``.
    Insert ``@staticmethod`` decorator and retype ``self``.
    """
    old_anchor = f"    def {old_name}(self, "
    if old_anchor not in method_text:
        raise RuntimeError(f"oneline signature shape mismatch for {old_name}")
    new_anchor = (
        f"    @staticmethod\n"
        f"    def {new_name}(self: \"RequestValidator\", "
    )
    return method_text.replace(old_anchor, new_anchor, 1)


def transform(wt: Path) -> None:
    tm = wt / "python/sglang/srt/managers/tokenizer_manager.py"
    new = wt / "python/sglang/srt/managers/request_validator.py"

    # 1. Create new file with empty RequestValidator + RequestValidatorConfig.
    new.write_text(VALIDATOR_HEADER)

    # 2. Convert 5 methods inplace inside TokenizerManager:
    #    - add @staticmethod
    #    - retype self -> self: "RequestValidator"
    #    - rename + add * kw-only where design dictates
    #    - rewrite body self.<...> -> self.config.<...>
    text = tm.read_text()

    # _validate_one_request -> validate_one (multi-line sig; insert ``*,``)
    s, e = find_method_lines(text, class_name="TokenizerManager", method_name="_validate_one_request")
    lines = text.splitlines(keepends=True)
    method_text = "".join(lines[s:e])
    method_text = _retype_static_multiline(
        method_text,
        old_name="_validate_one_request",
        new_name="validate_one",
        add_kwonly_star=True,
    )
    method_text = _rewrite_body(method_text)
    text = "".join(lines[:s]) + method_text + "".join(lines[e:])

    # _validate_mm_limits stays private; multi-line sig; no kw-only star.
    s, e = find_method_lines(text, class_name="TokenizerManager", method_name="_validate_mm_limits")
    lines = text.splitlines(keepends=True)
    method_text = "".join(lines[s:e])
    method_text = _retype_static_multiline(
        method_text,
        old_name="_validate_mm_limits",
        new_name="_validate_mm_limits",
        add_kwonly_star=False,
    )
    method_text = _rewrite_body(method_text)
    text = "".join(lines[:s]) + method_text + "".join(lines[e:])

    # _validate_for_matryoshka_dim stays private; one-line sig.
    s, e = find_method_lines(text, class_name="TokenizerManager", method_name="_validate_for_matryoshka_dim")
    lines = text.splitlines(keepends=True)
    method_text = "".join(lines[s:e])
    method_text = _retype_static_oneline(
        method_text,
        old_name="_validate_for_matryoshka_dim",
        new_name="_validate_for_matryoshka_dim",
    )
    method_text = _rewrite_body(method_text)
    text = "".join(lines[:s]) + method_text + "".join(lines[e:])

    # _validate_input_ids_in_vocab -> validate_input_ids_in_vocab (multi-line; kw-only).
    s, e = find_method_lines(text, class_name="TokenizerManager", method_name="_validate_input_ids_in_vocab")
    lines = text.splitlines(keepends=True)
    method_text = "".join(lines[s:e])
    method_text = _retype_static_multiline(
        method_text,
        old_name="_validate_input_ids_in_vocab",
        new_name="validate_input_ids_in_vocab",
        add_kwonly_star=True,
    )
    method_text = _rewrite_body(method_text)
    text = "".join(lines[:s]) + method_text + "".join(lines[e:])

    # _validate_batch_tokenization_constraints -> validate_batch_tokenization_constraints
    # (multi-line; kw-only).
    s, e = find_method_lines(
        text,
        class_name="TokenizerManager",
        method_name="_validate_batch_tokenization_constraints",
    )
    lines = text.splitlines(keepends=True)
    method_text = "".join(lines[s:e])
    method_text = _retype_static_multiline(
        method_text,
        old_name="_validate_batch_tokenization_constraints",
        new_name="validate_batch_tokenization_constraints",
        add_kwonly_star=True,
    )
    method_text = _rewrite_body(method_text)
    text = "".join(lines[:s]) + method_text + "".join(lines[e:])

    # 3. Add import + wire ctor.
    text = insert_after(
        text,
        anchor="from sglang.srt.managers.tokenizer_control_mixin import TokenizerControlMixin\n",
        addition=(
            "from sglang.srt.managers.request_validator import (\n"
            "    RequestValidator,\n"
            "    RequestValidatorConfig,\n"
            ")\n"
        ),
    )
    text = replace_call_site(
        text,
        old=(
            "        # Score request handler\n"
            "        self.score_request_handler = ScoreRequestHandler(\n"
        ),
        new=(
            INIT_INSERT
            + "        # Score request handler\n"
            "        self.score_request_handler = ScoreRequestHandler(\n"
        ),
    )

    # 4. Caller rewrites: self.<old>(...) -> TokenizerManager.<new>(self.request_validator, ...).
    # _validate_one_request: 2 sites.
    text = replace_call_site(
        text,
        old="        self._validate_one_request(obj, input_ids)",
        new=(
            "        TokenizerManager.validate_one(\n"
            "            self.request_validator, obj=obj, input_ids=input_ids\n"
            "        )"
        ),
    )
    text = replace_call_site(
        text,
        old="            self._validate_one_request(obj[i], input_ids_list[i])",
        new=(
            "            TokenizerManager.validate_one(\n"
            "                self.request_validator, obj=obj[i], input_ids=input_ids_list[i]\n"
            "            )"
        ),
    )
    # _validate_mm_limits: 1 site; stays positional (private helper).
    text = replace_call_site(
        text,
        old="                self._validate_mm_limits(obj)",
        new="                TokenizerManager._validate_mm_limits(self.request_validator, obj)",
    )
    # _validate_batch_tokenization_constraints: 1 site.
    text = replace_call_site(
        text,
        old="        self._validate_batch_tokenization_constraints(batch_size, obj)",
        new=(
            "        TokenizerManager.validate_batch_tokenization_constraints(\n"
            "            self.request_validator, batch_size=batch_size, obj=obj\n"
            "        )"
        ),
    )
    # _validate_for_matryoshka_dim: 1 site (inside _validate_one_request body).
    # After the body rewrite this is now inside the @staticmethod block;
    # self.<helper>(obj) needs to become TokenizerManager.<helper>(self, obj)
    # so that, in the move commit, it collapses to self._validate_for_matryoshka_dim(obj).
    text = replace_call_site(
        text,
        old="            self._validate_for_matryoshka_dim(obj)",
        new="            TokenizerManager._validate_for_matryoshka_dim(self, obj)",
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
