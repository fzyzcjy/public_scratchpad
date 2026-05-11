#!/usr/bin/env python3
"""Move 4 tokenize-pipeline helpers (_detect_input_format /
_prepare_tokenizer_input / _extract_tokenizer_results / _tokenize_texts)
from TokenizerManager into RawTokenizerWrapper. Method names retain leading
underscores in PR1 (per Ch1 rules — drop-underscore is Ch2 PR2).
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
)
from _runner import run_pr

ID = "rtw-move-tokenize-helpers"
SUBJECT = "Move tokenize-pipeline helpers onto RawTokenizerWrapper"
BODY = """\
Cut 4 helper methods (_detect_input_format / _prepare_tokenizer_input /
_extract_tokenizer_results / _tokenize_texts) from TokenizerManager into
RawTokenizerWrapper. Inside the moved bodies the previously rewritten
self.raw_tokenizer_wrapper.<field> references collapse back to self.<field>
(those references are now methods of RawTokenizerWrapper, owning those
fields directly). Three caller sites (tokenizer_manager.py) update to call
self.raw_tokenizer_wrapper._<helper>(...). Method names keep their leading
underscore -- the privacy flip per design (md L34) is deferred to Ch2 PR2.
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

    # Cut bottom-up so earlier line ranges stay valid: largest line numbers first.
    # find_method_lines returns the range each call; we cut last-defined first.
    methods_in_file_order = []
    for name in HELPER_NAMES:
        s, e = find_method_lines(tm.read_text(), class_name="TokenizerManager", method_name=name)
        methods_in_file_order.append((name, s, e))
    # Sort by start line desc
    methods_in_file_order.sort(key=lambda x: -x[1])

    cut_blocks = {}
    for name, s, e in methods_in_file_order:
        # Re-locate (start may shift after earlier cuts).
        s2, e2 = find_method_lines(tm.read_text(), class_name="TokenizerManager", method_name=name)
        cut_blocks[name] = cut_lines(tm, s2, e2)

    # Rewrite self.raw_tokenizer_wrapper.<field> -> self.<field> in moved bodies.
    # (Inside RawTokenizerWrapper they ARE self.X.) Also rewrite cross-helper
    # self._<other_helper> calls to self.<other_helper> -- those stay as-is
    # because they remain instance methods of the same class.
    def collapse_rtw_self(body: str) -> str:
        return body.replace("self.raw_tokenizer_wrapper.", "self.")

    rtw_text = rtw.read_text()
    # The helper bodies use Union / List / Tuple / InputFormat which may have
    # been pruned from the file imports by ruff in the previous (#7) commit
    # because they weren't yet referenced. Re-add them if absent before
    # appending the helpers.
    if "from typing import" in rtw_text:
        # Locate the typing import line and ensure it has all required names.
        # Strip trailing ``# noqa`` comments before parsing names so they don't
        # become "import members" — re-attach after merging.
        import re as _re
        m = _re.search(r"from typing import ([^\n]+)\n", rtw_text)
        if m:
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

    # Append helpers to the RawTokenizerWrapper class in original file order.
    for name in HELPER_NAMES:
        body = collapse_rtw_self(cut_blocks[name])
        rtw_text = rtw_text.rstrip() + "\n\n" + body
    if not rtw_text.endswith("\n"):
        rtw_text += "\n"
    rtw.write_text(rtw_text)

    # Update caller sites in tokenizer_manager.py.
    text = tm.read_text()
    for name in HELPER_NAMES:
        text = text.replace(f"self.{name}(", f"self.raw_tokenizer_wrapper.{name}(")
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
