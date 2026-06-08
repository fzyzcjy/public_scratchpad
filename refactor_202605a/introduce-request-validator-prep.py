#!/usr/bin/env python3
"""Prep: RequestValidator skeleton + composition wiring + in-place staticmethod conversion + caller rewrites."""

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

ID = "introduce-request-validator-prep"
SUBJECT = "Stage inbound-request validation for handoff to RequestValidator"
BODY = """\
Per MECH_COMMIT_SPLIT §"split-class scenario": prep does ALL semantic work.

Builds RequestValidator skeleton; wires composition in TM.__init__;
converts the inbound-request _validate_* methods to @staticmethod
carrying a self: "RequestValidator" annotation; applies body rewrites
(self.server_args.X / self.model_config.X / self.<context_len-etc>
-> self.config.X); rewrites callers to
``TokenizerManager.<method>(self.request_validator, ...)`` form.
Methods stay on TM in this commit; the next commit's pure cut/paste +
caller prefix replacement completes the move.
"""
AREA = "mech_tokenizer_manager"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


SKELETON = '''from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional


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
    config: RequestValidatorConfig
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


def _rewrite_body(body: str) -> str:
    for field in CONFIG_FIELDS_LONG:
        short = field.split(".", 1)[1]
        body = body.replace(f"self.{field}", f"self.config.{short}")
    for field in CONFIG_FIELDS_SHORT:
        body = body.replace(f"self.{field}", f"self.config.{field}")
    return body


def _method_ranges(text: str, class_name: str, method_name: str):
    """Return (start, body_start, end) line indices for a method (incl. decorators)."""
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


# Replacement headers: @staticmethod + self: "RequestValidator" typing.
# Method names keep `_validate_*` prefix in prep; the privacy flip (rename to
# `validate_one` etc.) happens in MOVE per scope-induced rename convention.
NEW_HEADERS = {
    "_validate_one_request": (
        '    @staticmethod\n'
        '    def _validate_one_request(\n'
        '        self: "RequestValidator",\n'
        '        obj: Union[GenerateReqInput, EmbeddingReqInput],\n'
        '        input_ids: List[int],\n'
        '    ) -> None:\n'
    ),
    "_validate_mm_limits": (
        '    @staticmethod\n'
        '    def _validate_mm_limits(\n'
        '        self: "RequestValidator",\n'
        '        obj: Union[GenerateReqInput, EmbeddingReqInput],\n'
        '    ) -> None:\n'
    ),
    "_validate_for_matryoshka_dim": (
        '    @staticmethod\n'
        '    def _validate_for_matryoshka_dim(\n'
        '        self: "RequestValidator", obj: EmbeddingReqInput\n'
        '    ) -> None:\n'
    ),
    "_validate_input_ids_in_vocab": (
        '    @staticmethod\n'
        '    def _validate_input_ids_in_vocab(\n'
        '        self: "RequestValidator",\n'
        '        input_ids: Union[List[int], List[List[int]]],\n'
        '        vocab_size: int,\n'
        '    ) -> None:\n'
        '        # Handle both single sequence and batch of sequences\n'
    ),
    "_validate_batch_tokenization_constraints": (
        '    @staticmethod\n'
        '    def _validate_batch_tokenization_constraints(\n'
        '        self: "RequestValidator",\n'
        '        batch_size: int,\n'
        '        obj: Union[GenerateReqInput, EmbeddingReqInput],\n'
        '    ) -> None:\n'
    ),
}


def _rewrite_method(text: str, method_name: str) -> str:
    s, body_s, e = _method_ranges(text, "TokenizerManager", method_name)
    lines = text.splitlines(keepends=True)
    body_text = "".join(lines[body_s:e])
    body_text = _rewrite_body(body_text)
    # Internal call: self._validate_for_matryoshka_dim(obj)
    #   -> TokenizerManager._validate_for_matryoshka_dim(self, obj)
    # The leading `self` is intentional: in prep self is "RequestValidator"-typed,
    # and TM.<method>(self, ...) preserves the class-qualified caller convention.
    body_text = body_text.replace(
        "self._validate_for_matryoshka_dim(obj)",
        "TokenizerManager._validate_for_matryoshka_dim(self, obj)",
    )
    new_method = NEW_HEADERS[method_name] + body_text
    return "".join(lines[:s]) + new_method + "".join(lines[e:])


def transform(wt: Path) -> None:
    tm = wt / "python/sglang/srt/managers/tokenizer_manager.py"
    new = wt / "python/sglang/srt/managers/tokenizer_manager_components/request_validator.py"
    new.write_text(SKELETON)

    text = tm.read_text()
    text = insert_after(
        text,
        anchor="from sglang.srt.managers.tokenizer_control_mixin import TokenizerControlMixin\n",
        addition=(
            "from sglang.srt.managers.tokenizer_manager_components.request_validator import (\n"
            "    RequestValidator,\n"
            "    RequestValidatorConfig,\n"
            ")\n"
        ),
    )

    # Composition wiring.
    text = wire_component_init(
        text,
        attr="request_validator",
        before_attr="score_request_handler",
        construction=(
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
        ),
    )

    # Convert all 5 _validate_* methods to @staticmethod with self: "RequestValidator" typing.
    # Apply body rewrites in-place. Bodies stay in TM class.
    for method_name in (
        "_validate_one_request",
        "_validate_mm_limits",
        "_validate_for_matryoshka_dim",
        "_validate_input_ids_in_vocab",
        "_validate_batch_tokenization_constraints",
    ):
        text = _rewrite_method(text, method_name)

    # Caller rewrites: 4 sites in TM use these methods.
    text = replace_call_site(
        text,
        old="        self._validate_one_request(obj, input_ids)",
        new="        TokenizerManager._validate_one_request(self.request_validator, obj, input_ids)",
    )
    text = replace_call_site(
        text,
        old="            self._validate_one_request(obj[i], input_ids_list[i])",
        new="            TokenizerManager._validate_one_request(self.request_validator, obj[i], input_ids_list[i])",
    )
    text = replace_call_site(
        text,
        old="                self._validate_mm_limits(obj)",
        new="                TokenizerManager._validate_mm_limits(self.request_validator, obj)",
    )
    text = replace_call_site(
        text,
        old="        self._validate_batch_tokenization_constraints(batch_size, obj)",
        new="        TokenizerManager._validate_batch_tokenization_constraints(self.request_validator, batch_size, obj)",
    )

    tm.write_text(text)

    # The manual batch-encode test drives the staged validator method; switch
    # its calls to the staticmethod convention at this commit (the move
    # collapses them onto request_validator).
    import re as _re

    test_file = wt / "test/manual/test_tokenizer_batch_encode.py"
    if test_file.exists():
        tt = test_file.read_text()
        tt = _re.sub(
            r"self\.tokenizer_manager\._validate_batch_tokenization_constraints\(\s*([^,]+),\s*([^)]+?)\s*\)",
            r"TokenizerManager._validate_batch_tokenization_constraints(\n"
            r"                self.tokenizer_manager.request_validator, \1, \2\n"
            r"            )",
            tt,
        )
        test_file.write_text(tt)


if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        area_branch=AREA_BRANCH,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
