#!/usr/bin/env python3
"""Mechanical move for ``introduce-request-preparer``: cut 4
@staticmethods from TokenizerManager, paste them into the
``RequestPreparer`` class body. Drop ``@staticmethod`` decorators,
simplify ``def foo(self: "RequestPreparer", ...)`` -> ``def foo(self, ...)``,
rewrite callers
``TokenizerManager.<m>(self.request_preparer, ...)`` ->
``self.request_preparer.<m>(...)`` (pure prefix transformation).
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

ID = "introduce-request-preparer-move"
SUBJECT = "Move 4 tokenize-orchestration methods into RequestPreparer class body"
BODY = """\
Mechanical cut + paste for the ``introduce-request-preparer`` mech move.

Cut ``_tokenize_one_request`` / ``_batch_tokenize_and_process`` /
``_should_use_batch_tokenization`` / ``_batch_has_text`` (@staticmethods
after prep) from TokenizerManager and paste them into the
``RequestPreparer`` class body in ``managers/request_preparer.py``.

Drop ``@staticmethod`` decorators; simplify ``self: "RequestPreparer"``
type annotation to bare ``self`` (in class context the type is implicit).
Method bodies otherwise byte-identical.

All 5 callers updated:
  ``TokenizerManager.<m>(self.request_preparer, ...)`` ->
  ``self.request_preparer.<m>(...)``
(pure prefix transformation).
"""
AREA = "mech_tokenizer_manager"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


METHOD_NAMES = (
    "_tokenize_one_request",
    "_batch_tokenize_and_process",
    "_should_use_batch_tokenization",
    "_batch_has_text",
)


def _strip_staticmethod_typeflip(method_text: str) -> str:
    """Drop ``    @staticmethod\\n`` decorator and the
    ``self: "RequestPreparer"`` annotation, restoring a bare instance method
    signature. Body bytes unchanged.
    """
    text = method_text.replace("    @staticmethod\n", "", 1)
    text = text.replace('self: "RequestPreparer"', "self")
    return text


def transform(wt: Path) -> None:
    tm = wt / "python/sglang/srt/managers/tokenizer_manager.py"
    preparer = wt / "python/sglang/srt/managers/request_preparer.py"

    # Cut 4 methods bottom-up so earlier ranges stay valid.
    name_to_start: dict[str, int] = {}
    for name in METHOD_NAMES:
        s, _ = find_method_lines(
            tm.read_text(), class_name="TokenizerManager", method_name=name
        )
        name_to_start[name] = s

    cut_blocks: dict[str, str] = {}
    for name in sorted(METHOD_NAMES, key=lambda n: -name_to_start[n]):
        s, e = find_method_lines(
            tm.read_text(), class_name="TokenizerManager", method_name=name
        )
        block = cut_lines(tm, s, e)
        cut_blocks[name] = _strip_staticmethod_typeflip(block)

    # Append into preparer class body in source order. Each block already has
    # 4-space indent matching the class body.
    blocks_in_order = [cut_blocks[n] for n in METHOD_NAMES]
    ptext = preparer.read_text()
    ptext = ptext.rstrip() + "\n\n" + "".join(b.rstrip() + "\n\n" for b in blocks_in_order).rstrip() + "\n"
    preparer.write_text(ptext)

    # Caller rewrites: pure prefix transformation in tokenizer_manager.py.
    text = tm.read_text()
    for name in METHOD_NAMES:
        text = replace_call_site(
            text,
            old=f"TokenizerManager.{name}(self.request_preparer, ",
            new=f"self.request_preparer.{name}(",
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
