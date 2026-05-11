#!/usr/bin/env python3
"""Mechanical move for ``introduce-request-validator``: cut 5
``@staticmethods`` from ``TokenizerManager``, paste them into the
``RequestValidator`` class body. Drop ``@staticmethod`` decorators,
simplify ``self: "RequestValidator"`` -> ``self``, rewrite callers via
pure prefix replacement:

  ``TokenizerManager.<method>(self.request_validator, ...)``
  -> ``self.request_validator.<method>(...)``

Inside the moved ``validate_one`` body, the intra-validator call
  ``TokenizerManager._validate_for_matryoshka_dim(self, obj)``
collapses to
  ``self._validate_for_matryoshka_dim(obj)``.
"""

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
SUBJECT = "Move 5 validate methods into RequestValidator class body"
BODY = """\
Mechanical cut + paste for the ``introduce-request-validator`` mech move.

Cut 5 ``@staticmethods`` from ``TokenizerManager``:
  validate_one
  _validate_mm_limits
  _validate_for_matryoshka_dim
  validate_input_ids_in_vocab
  validate_batch_tokenization_constraints
and paste them into the ``RequestValidator`` class body in
``managers/request_validator.py``.

Drop ``@staticmethod`` decorators; simplify
``self: "RequestValidator"`` type annotation to bare ``self`` (in class
context the type is implicit). Method bodies otherwise byte-identical.

Caller rewrites (pure prefix replacement) in tokenizer_manager.py:
  ``TokenizerManager.validate_one(self.request_validator, ...)``
  -> ``self.request_validator.validate_one(...)``
(and similarly for the other 3 caller sites)

Inside the moved ``validate_one`` body (now in request_validator.py), the
intra-validator call ``TokenizerManager._validate_for_matryoshka_dim(self, obj)``
collapses to ``self._validate_for_matryoshka_dim(obj)``.
"""
AREA = "mech_tokenizer_manager"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


def _strip_staticmethod_typeflip(method_text: str, *, target_class: str) -> str:
    """Drop @staticmethod and the ``self: "TargetClass"`` annotation."""
    text = method_text.replace("    @staticmethod\n", "", 1)
    text = text.replace(f'self: "{target_class}"', "self")
    return text


# Method names AFTER prep (i.e. post-rename).
# Order = bottom-up in the post-prep file. The prep renames are:
#   _validate_one_request                    -> validate_one
#   _validate_input_ids_in_vocab             -> validate_input_ids_in_vocab
#   _validate_batch_tokenization_constraints -> validate_batch_tokenization_constraints
# _validate_mm_limits / _validate_for_matryoshka_dim keep their names.
METHOD_NAMES_SOURCE_ORDER = (
    "validate_one",
    "_validate_mm_limits",
    "_validate_for_matryoshka_dim",
    "validate_input_ids_in_vocab",
    "validate_batch_tokenization_constraints",
)


def transform(wt: Path) -> None:
    tm = wt / "python/sglang/srt/managers/tokenizer_manager.py"
    rv = wt / "python/sglang/srt/managers/request_validator.py"

    # 1. Cut the 5 staticmethods bottom-up. Compute all line ranges first,
    #    then sort descending by start line so successive cuts stay valid.
    name_to_range = {}
    src_text = tm.read_text()
    for n in METHOD_NAMES_SOURCE_ORDER:
        name_to_range[n] = find_method_lines(
            src_text, class_name="TokenizerManager", method_name=n
        )

    blocks = {}
    for n in sorted(METHOD_NAMES_SOURCE_ORDER, key=lambda nn: -name_to_range[nn][0]):
        s, e = find_method_lines(
            tm.read_text(), class_name="TokenizerManager", method_name=n
        )
        block = cut_lines(tm, s, e)
        block = _strip_staticmethod_typeflip(block, target_class="RequestValidator")
        blocks[n] = block

    # 2. Append into RequestValidator class body in source order. The existing
    #    class body ends with ``config: RequestValidatorConfig`` followed by a
    #    blank line at EOF; methods carry their own 4-space class indent.
    rtext = rv.read_text()
    appended = "\n".join(blocks[n].rstrip() for n in METHOD_NAMES_SOURCE_ORDER)
    rv.write_text(rtext.rstrip() + "\n\n" + appended + "\n")

    # 3. Pure prefix replacement on callers in tokenizer_manager.py.
    # Each replacement folds away the ``TokenizerManager.<method>`` qualifier
    # and the explicit ``self.request_validator, `` first arg in one step.
    text = tm.read_text()
    text = replace_call_site(
        text,
        old=(
            "TokenizerManager.validate_one(\n"
            "            self.request_validator, "
        ),
        new=(
            "self.request_validator.validate_one(\n"
            "            "
        ),
    )
    text = replace_call_site(
        text,
        old=(
            "TokenizerManager.validate_one(\n"
            "                self.request_validator, "
        ),
        new=(
            "self.request_validator.validate_one(\n"
            "                "
        ),
    )
    text = replace_call_site(
        text,
        old="TokenizerManager._validate_mm_limits(self.request_validator, ",
        new="self.request_validator._validate_mm_limits(",
    )
    text = replace_call_site(
        text,
        old=(
            "TokenizerManager.validate_batch_tokenization_constraints(\n"
            "            self.request_validator, "
        ),
        new=(
            "self.request_validator.validate_batch_tokenization_constraints(\n"
            "            "
        ),
    )

    tm.write_text(text)

    # 4. Intra-validator call inside the now-relocated validate_one body.
    rtext = rv.read_text()
    rtext = replace_call_site(
        rtext,
        old="TokenizerManager._validate_for_matryoshka_dim(self, obj)",
        new="self._validate_for_matryoshka_dim(obj)",
    )
    rv.write_text(rtext)


if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        area_branch=AREA_BRANCH,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
