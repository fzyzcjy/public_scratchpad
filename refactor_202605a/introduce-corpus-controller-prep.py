#!/usr/bin/env python3
"""Inplace prep for ``introduce-corpus-controller``: create the
``CorpusController`` class skeleton, instantiate in
``TokenizerManager.__init__``, convert 3 methods on
``TokenizerControlMixin`` to ``@staticmethod`` with
``self: CorpusController`` type annotation, rewrite callers to
``TokenizerManager.<method>(self.corpus_controller, ...)``.

Body bytes byte-identical wrt the post-move state (modulo decorator + the
``def foo(self: CorpusController, ...)`` → ``def foo(self, ...)``
signature simplification in the move commit).
"""

# /// script
# requires-python = ">=3.10"
# dependencies = ["typer"]
# ///

import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from _helpers import find_method_lines, insert_after, replace_call_site
from _runner import run_pr

ID = "introduce-corpus-controller-prep"
SUBJECT = "Build CorpusController skeleton + @staticmethod prep (prep for move)"
BODY = """\
Inplace prep for the ``introduce-corpus-controller`` mech move.

- Create ``managers/corpus_controller.py`` with a ``CorpusController``
  dataclass holding the 3 communicators + ``server_args`` + ``tokenizer`` +
  ``auto_create_handle_loop`` (every attribute the moved bodies read,
  name-for-name). No methods yet.
- Instantiate ``self.corpus_controller = CorpusController(...)`` in
  ``TokenizerManager.__init__`` just before the session controller block.
- In ``TokenizerControlMixin``, convert 3 methods
  (``add_external_corpus`` / ``remove_external_corpus`` /
  ``list_external_corpora``) to ``@staticmethod`` with
  ``self: CorpusController`` type annotation. Body bytes unchanged.
- Internal callers stay inside ``TokenizerControlMixin`` (none for these 3
  methods) — only external entrypoints in ``http_server.py`` call them.
- Rewrite entrypoint callers in ``http_server.py``:
  ``tokenizer_manager.add_external_corpus(obj)`` →
  ``TokenizerManager.add_external_corpus(tokenizer_manager.corpus_controller, obj)``
  (and the 2 sibling methods).

The 3 methods stay inside ``TokenizerControlMixin`` in this commit;
physical cut + paste to ``CorpusController`` body happens in
``introduce-corpus-controller-move``.
"""
AREA = "mech_tokenizer_manager"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


CORPUS_HEADER = '''from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass
class CorpusController:
    """add / remove / list external corpus endpoints (n-gram speculative decoding).

    Fields mirror the attributes the moved method bodies read on
    ``TokenizerManager`` — kept name-for-name so the bodies are
    byte-identical before and after the physical move in the next commit.
    """

    add_external_corpus_communicator: Any
    remove_external_corpus_communicator: Any
    list_external_corpora_communicator: Any
    server_args: Any
    tokenizer: Any
    auto_create_handle_loop: Callable[[], None]
'''


INIT_INSERT = '''        self.corpus_controller = CorpusController(
            add_external_corpus_communicator=self.add_external_corpus_communicator,
            remove_external_corpus_communicator=self.remove_external_corpus_communicator,
            list_external_corpora_communicator=self.list_external_corpora_communicator,
            server_args=self.server_args,
            tokenizer=self.tokenizer,
            auto_create_handle_loop=self.auto_create_handle_loop,
        )

'''


def _retype_self_to_corpus_controller(method_text: str, *, method_name: str) -> str:
    """Replace ``self: TokenizerManager`` with ``self: "CorpusController"`` and add @staticmethod."""
    old = f"    async def {method_name}(\n        self: TokenizerManager"
    new = (
        f"    @staticmethod\n"
        f"    async def {method_name}(\n"
        f"        self: \"CorpusController\""
    )
    if old not in method_text:
        raise RuntimeError(
            f"{method_name} signature anchor not found in expected multi-line form"
        )
    return method_text.replace(old, new, 1)


def transform(wt: Path) -> None:
    tm = wt / "python/sglang/srt/managers/tokenizer_manager.py"
    control_mixin = wt / "python/sglang/srt/managers/tokenizer_control_mixin.py"
    corpus = wt / "python/sglang/srt/managers/corpus_controller.py"
    http_server = wt / "python/sglang/srt/entrypoints/http_server.py"

    # 1. Create new file with CorpusController dataclass skeleton.
    corpus.write_text(CORPUS_HEADER)

    # 2. In TokenizerControlMixin, convert 3 methods to @staticmethod inplace.
    text = control_mixin.read_text()
    for name in (
        "add_external_corpus",
        "remove_external_corpus",
        "list_external_corpora",
    ):
        s, e = find_method_lines(text, class_name="TokenizerControlMixin", method_name=name)
        lines = text.splitlines(keepends=True)
        method_text = "".join(lines[s:e])
        new_method = _retype_self_to_corpus_controller(method_text, method_name=name)
        text = "".join(lines[:s]) + new_method + "".join(lines[e:])
    control_mixin.write_text(text)

    # 3. Add import + ctor instantiation in TokenizerManager.
    text = tm.read_text()
    text = insert_after(
        text,
        anchor="from sglang.srt.managers.tokenizer_control_mixin import TokenizerControlMixin\n",
        addition=(
            "from sglang.srt.managers.corpus_controller import CorpusController\n"
        ),
    )
    text = replace_call_site(
        text,
        old=(
            "        # Session controller\n"
            "        self.session_controller = SessionController(\n"
        ),
        new=(
            INIT_INSERT
            + "        # Session controller\n"
            "        self.session_controller = SessionController(\n"
        ),
    )
    tm.write_text(text)

    # 4. Entrypoint caller rewrites in http_server.py.
    text = http_server.read_text()
    text = replace_call_site(
        text,
        old="await _global_state.tokenizer_manager.add_external_corpus(obj)",
        new=(
            "await TokenizerManager.add_external_corpus(\n"
            "        _global_state.tokenizer_manager.corpus_controller, obj\n"
            "    )"
        ),
    )
    text = replace_call_site(
        text,
        old="await _global_state.tokenizer_manager.remove_external_corpus(corpus_id)",
        new=(
            "await TokenizerManager.remove_external_corpus(\n"
            "        _global_state.tokenizer_manager.corpus_controller, corpus_id\n"
            "    )"
        ),
    )
    text = replace_call_site(
        text,
        old="await _global_state.tokenizer_manager.list_external_corpora()",
        new=(
            "await TokenizerManager.list_external_corpora(\n"
            "        _global_state.tokenizer_manager.corpus_controller\n"
            "    )"
        ),
    )
    # TokenizerManager is already imported at the top of http_server.py.
    http_server.write_text(text)


if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        area_branch=AREA_BRANCH,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
