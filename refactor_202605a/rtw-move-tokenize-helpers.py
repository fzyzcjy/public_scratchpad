#!/usr/bin/env python3
"""Move (pure cut/paste): 4 tokenize-pipeline helpers relocate from
TokenizerManager to RawTokenizerWrapper.

Per MECH_COMMIT_SPLIT §"拆 class 场景": prep
(rtw-prep-tokenize-helpers) already did all semantic work — staticmethod
conversion, body rewrites, intra-cluster class-qualification, external
caller rewrites, typing imports. This commit only:

  - cuts the 4 @staticmethod methods from TokenizerManager
  - drops @staticmethod + restores plain ``self`` + folds the intra-cluster
    qualifier back to ``self.`` (now sibling instance methods)
  - pastes into RawTokenizerWrapper
  - rewrites external callers from
    ``TokenizerManager._helper(self.raw_tokenizer_wrapper, ...)`` →
    ``self.raw_tokenizer_wrapper._helper(...)``.
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
    find_class_lines,
    find_method_lines,
    rewrite_intra_class_calls,
)
from _runner import run_pr

ID = "rtw-move-tokenize-helpers"
SUBJECT = "Hand tokenize-pipeline helpers over to RawTokenizerWrapper"
BODY = """\
Pure cut/paste move per MECH_COMMIT_SPLIT. Cuts 4 @staticmethod helpers
(``_detect_input_format`` / ``_prepare_tokenizer_input`` /
``_extract_tokenizer_results`` / ``_tokenize_texts``) from TM; pastes
into RawTokenizerWrapper (drop @staticmethod, restore plain ``self``,
collapse intra-cluster ``TokenizerManager._x(self, ...)`` calls back to
``self._x(...)`` — they are sibling instance methods on the new owner).

External caller prefix replacement in TM:
``TokenizerManager._helper(self.raw_tokenizer_wrapper, ...)`` →
``self.raw_tokenizer_wrapper._helper(...)``.
"""
AREA = "mech_tokenizer_manager"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


HELPER_NAMES = (
    "_detect_input_format",
    "_prepare_tokenizer_input",
    "_extract_tokenizer_results",
    "_tokenize_texts",
)


def transform(wt: Path) -> None:
    tm = wt / "python/sglang/srt/managers/tokenizer_manager.py"
    rtw = wt / "python/sglang/srt/managers/raw_tokenizer_wrapper.py"

    # ---- 0. Expand raw_tokenizer_wrapper.py's typing import to cover the
    # post-move signatures (Tuple / Union / List). Strip any trailing
    # ``# noqa`` comment before parsing names so it doesn't become an import.
    import re as _re

    rtw_text = rtw.read_text()
    m = _re.search(r"from typing import ([^\n]+)\n", rtw_text)
    if m is None:
        raise RuntimeError("from typing import line not found in raw_tokenizer_wrapper.py")
    rest = m.group(1)
    comment = ""
    if "#" in rest:
        names_part, comment = rest.split("#", 1)
        comment = "  #" + comment.rstrip()
    else:
        names_part = rest
    current = {n.strip() for n in names_part.split(",") if n.strip()}
    needed = {"Any", "List", "Optional", "Tuple", "Union"}
    merged = sorted(current | needed)
    new_line = f"from typing import {', '.join(merged)}{comment}\n"
    rtw_text = rtw_text.replace(m.group(0), new_line, 1)
    # Also need ``Enum`` for InputFormat moved in this commit.
    if "from enum import Enum" not in rtw_text:
        rtw_text = rtw_text.replace(
            "from dataclasses import dataclass\n",
            "from dataclasses import dataclass\nfrom enum import Enum\n",
        )
    rtw.write_text(rtw_text)

    # ---- 0b. Cut the InputFormat enum from TM and append to RTW. The 4 helper
    # bodies reference ``InputFormat.SINGLE_STRING`` etc., so it must be in RTW
    # scope before the helpers arrive.
    tm_text = tm.read_text()
    if "class InputFormat(Enum):\n" in tm_text:
        s, e = find_class_lines(tm_text, class_name="InputFormat")
        input_format_text = cut_lines(tm, s, e)
        rtw_text = rtw.read_text().rstrip() + "\n\n\n" + input_format_text.rstrip() + "\n"
        rtw.write_text(rtw_text)

    # ---- 1. Cut bottom-up so earlier line ranges stay valid.
    name_to_start = {}
    for name in HELPER_NAMES:
        s, _ = find_method_lines(tm.read_text(), class_name="TokenizerManager", method_name=name)
        name_to_start[name] = s
    cut_blocks = {}
    for name in sorted(HELPER_NAMES, key=lambda n: -name_to_start[n]):
        s, e = find_method_lines(tm.read_text(), class_name="TokenizerManager", method_name=name)
        cut_blocks[name] = cut_lines(tm, s, e)

    def strip(body: str) -> str:
        body = body.replace("    @staticmethod\n", "", 1)
        body = body.replace('self: "RawTokenizerWrapper",', "self,")
        body = body.replace('self: "RawTokenizerWrapper"', "self")
        body = rewrite_intra_class_calls(
            body,
            source_classes=["TokenizerManager"],
            target_class="RawTokenizerWrapper",
            methods=list(HELPER_NAMES),
        )
        return body

    # ---- 2. Paste into RawTokenizerWrapper in original file order.
    rtw_text = rtw.read_text().rstrip() + "\n"
    for name in HELPER_NAMES:
        rtw_text += "\n" + strip(cut_blocks[name])
    if not rtw_text.endswith("\n"):
        rtw_text += "\n"
    rtw.write_text(rtw_text)

    # ---- 3. External caller prefix replacement in TM. Use regex to absorb
    # both single-line and black-wrapped multi-line forms (the prep-stage
    # text often exceeds 88 chars and gets reflowed across two lines).
    text = tm.read_text()
    for name in HELPER_NAMES:
        # single-line: ``TokenizerManager.<n>(self.raw_tokenizer_wrapper, ARGS``
        text = _re.sub(
            rf"TokenizerManager\.{_re.escape(name)}\(\s*self\.raw_tokenizer_wrapper,\s*",
            f"self.raw_tokenizer_wrapper.{name}(",
            text,
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
