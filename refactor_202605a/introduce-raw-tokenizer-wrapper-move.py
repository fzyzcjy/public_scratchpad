#!/usr/bin/env python3
"""Move: cut init_tokenizer_and_processor + InputFormat from TM; external entrypoint rewrites."""

# /// script
# requires-python = ">=3.10"
# dependencies = ["typer"]
# ///

import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from _helpers import cut_lines, find_class_lines, find_method_lines
from _runner import run_pr

ID = "introduce-raw-tokenizer-wrapper-move"
SUBJECT = "Move RawTokenizerWrapper: cut init_tokenizer_and_processor + InputFormat; rewire external callers"
BODY = """\
Pure cut/paste move per MECH_COMMIT_SPLIT (factory variant: target
body was already materialized in prep, so this commit only deletes the
source-side orphans + does mechanical caller prefix rewrites).

Cuts ``init_tokenizer_and_processor`` (orphan after prep wired
composition through ``RawTokenizerWrapper.from_server_args``) and the
``InputFormat`` enum (its canonical home is now raw_tokenizer_wrapper.py)
from TokenizerManager. External entrypoint / template_manager / test /
docs callers are pure-prefix-rewritten from
``tokenizer_manager.<field>`` →
``tokenizer_manager.raw_tokenizer_wrapper.<field>`` (and the same for
``tm.<field>`` / ``self.tm.<field>`` test patterns); test mocks pick up
the new attribute. No body rewrites.
"""
AREA = "mech_tokenizer_manager"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


def transform(wt: Path) -> None:
    tm = wt / "python/sglang/srt/managers/tokenizer_manager.py"

    s, e = find_method_lines(
        tm.read_text(), class_name="TokenizerManager", method_name="init_tokenizer_and_processor"
    )
    cut_lines(tm, s, e)

    text = tm.read_text()
    if "class InputFormat(Enum):\n" in text:
        s, e = find_class_lines(text, class_name="InputFormat")
        cut_lines(tm, s, e)

    # External callers (entrypoints/, template_manager.py, tests, docs).
    import glob
    external_files = [Path(p) for p in glob.glob(
        str(wt / "python/sglang/srt/entrypoints/**/*.py"), recursive=True
    )]
    external_files.append(wt / "python/sglang/srt/managers/template_manager.py")
    external_files += [Path(p) for p in glob.glob(
        str(wt / "test/registered/**/*.py"), recursive=True
    )]
    external_files += [Path(p) for p in glob.glob(
        str(wt / "docs/**/*.ipynb"), recursive=True
    )]
    external_files += [Path(p) for p in glob.glob(
        str(wt / "docs_new/**/*.ipynb"), recursive=True
    )]
    for f in external_files:
        if not f.exists():
            continue
        t = f.read_text()
        t = re.sub(
            r"\btokenizer_manager\.tokenizer\b",
            "tokenizer_manager.raw_tokenizer_wrapper.tokenizer",
            t,
        )
        t = re.sub(
            r"\btokenizer_manager\.processor\b",
            "tokenizer_manager.raw_tokenizer_wrapper.processor",
            t,
        )
        if "test/" in str(f) or "_test.py" in str(f) or "test_" in f.name:
            t = re.sub(
                r"\bself\.tm\.tokenizer\b",
                "self.tm.raw_tokenizer_wrapper.tokenizer",
                t,
            )
            t = re.sub(
                r"(?<![\w.])tm\.tokenizer\b",
                "tm.raw_tokenizer_wrapper.tokenizer",
                t,
            )
            t = re.sub(
                r"^(        self\.tokenizer = Mock\(\)\n)",
                r"\1"
                r"        self.raw_tokenizer_wrapper = Mock()\n"
                r"        self.raw_tokenizer_wrapper.tokenizer = self.tokenizer\n",
                t,
                flags=re.MULTILINE,
            )
            t = re.sub(
                r"(\s+)(\w+) = Mock\(spec=TokenizerManager\)\n",
                lambda m: m.group(0) + f"{m.group(1)}{m.group(2)}.raw_tokenizer_wrapper = Mock()\n",
                t,
            )
        f.write_text(t)


if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        area_branch=AREA_BRANCH,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
