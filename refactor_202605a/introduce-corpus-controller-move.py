#!/usr/bin/env python3
"""Mechanical move for ``introduce-corpus-controller``: cut 3
@staticmethods from ``TokenizerControlMixin``, paste them into the
``CorpusController`` class body. Drop ``@staticmethod`` decorators,
simplify ``def foo(self: "CorpusController", ...)`` →
``def foo(self, ...)``, rewrite callers
``TokenizerManager.add_external_corpus(self.corpus_controller, ...)`` →
``self.corpus_controller.add_external_corpus(...)`` (pure prefix
replacement). External entrypoints in ``http_server.py`` get the same
prefix collapse.
"""

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

ID = "introduce-corpus-controller-move"
SUBJECT = "Move 3 methods into CorpusController class body"
BODY = """\
Mechanical cut + paste for the ``introduce-corpus-controller`` mech move.

Cut ``add_external_corpus`` / ``remove_external_corpus`` /
``list_external_corpora`` (@staticmethods after prep) from
``TokenizerControlMixin`` and paste them into the ``CorpusController``
class body in ``managers/corpus_controller.py``.

Drop ``@staticmethod`` decorators; simplify ``self: "CorpusController"``
type annotation to bare ``self`` (in class context the type is implicit).
Method bodies otherwise byte-identical.

All callers updated:
  ``TokenizerManager.add_external_corpus(self.corpus_controller, ...)`` →
  ``self.corpus_controller.add_external_corpus(...)``
  (and the 2 sibling methods).
Entrypoint callers:
  ``TokenizerManager.add_external_corpus(tokenizer_manager.corpus_controller, ...)`` →
  ``tokenizer_manager.corpus_controller.add_external_corpus(...)``
(pure prefix transformation in both cases).
"""
AREA = "mech_tokenizer_manager"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


METHOD_NAMES = (
    "add_external_corpus",
    "remove_external_corpus",
    "list_external_corpora",
)


def _strip_staticmethod_typeflip(method_text: str, *, target_class: str) -> str:
    """Drop @staticmethod and the ``self: TargetClass`` annotation."""
    text = method_text.replace("    @staticmethod\n", "", 1)
    text = text.replace(
        f"self: \"{target_class}\"",
        "self",
    )
    return text


def transform(wt: Path) -> None:
    control_mixin = wt / "python/sglang/srt/managers/tokenizer_control_mixin.py"
    corpus = wt / "python/sglang/srt/managers/corpus_controller.py"
    http_server = wt / "python/sglang/srt/entrypoints/http_server.py"
    tm = wt / "python/sglang/srt/managers/tokenizer_manager.py"

    # Cut 3 methods (bottom-up to keep upstream line numbers stable).
    name_to_start = {}
    text = control_mixin.read_text()
    for name in METHOD_NAMES:
        s, _ = find_method_lines(text, class_name="TokenizerControlMixin", method_name=name)
        name_to_start[name] = s

    method_blocks = {}
    for name in sorted(METHOD_NAMES, key=lambda nn: -name_to_start[nn]):
        s, e = find_method_lines(
            control_mixin.read_text(),
            class_name="TokenizerControlMixin",
            method_name=name,
        )
        block = cut_lines(control_mixin, s, e)
        block = _strip_staticmethod_typeflip(block, target_class="CorpusController")
        method_blocks[name] = block

    # Append into CorpusController class body in source order.
    rtext = corpus.read_text()
    ordered = "".join(method_blocks[n] for n in METHOD_NAMES)
    corpus.write_text(rtext.rstrip() + "\n\n" + ordered.rstrip() + "\n")

    # Caller rewrites in http_server.py: pure prefix transformation.
    # Prep emitted three exact forms; move collapses each one.
    text = http_server.read_text()
    text = text.replace(
        "await TokenizerManager.add_external_corpus(\n"
        "        _global_state.tokenizer_manager.corpus_controller, obj\n"
        "    )",
        "await _global_state.tokenizer_manager.corpus_controller.add_external_corpus(\n"
        "        obj\n"
        "    )",
    )
    text = text.replace(
        "await TokenizerManager.remove_external_corpus(\n"
        "        _global_state.tokenizer_manager.corpus_controller, corpus_id\n"
        "    )",
        "await _global_state.tokenizer_manager.corpus_controller.remove_external_corpus(\n"
        "        corpus_id\n"
        "    )",
    )
    text = text.replace(
        "await TokenizerManager.list_external_corpora(\n"
        "        _global_state.tokenizer_manager.corpus_controller\n"
        "    )",
        "await _global_state.tokenizer_manager.corpus_controller.list_external_corpora()",
    )
    http_server.write_text(text)

    # Internal callers in tokenizer_manager.py / tokenizer_control_mixin.py:
    # none exist for these 3 methods (they're external-only endpoints), but
    # apply a safe no-op-if-absent replace so the script stays robust to
    # upstream additions.
    for f in [tm, control_mixin]:
        ftext = f.read_text()
        for name in METHOD_NAMES:
            ftext = ftext.replace(
                f"TokenizerManager.{name}(self.corpus_controller, ",
                f"self.corpus_controller.{name}(",
            )
            ftext = ftext.replace(
                f"TokenizerManager.{name}(self.corpus_controller)",
                f"self.corpus_controller.{name}()",
            )
        f.write_text(ftext)


if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        area_branch=AREA_BRANCH,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
