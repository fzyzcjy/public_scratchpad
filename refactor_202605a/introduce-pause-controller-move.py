#!/usr/bin/env python3
"""Mechanical move for ``introduce-pause-controller``: cut 4 @staticmethods
from TokenizerManager, paste them into the ``PauseController`` class body
in ``managers/pause_controller.py``. Drop ``@staticmethod`` decorators,
simplify ``self: "PauseController"`` type annotation back to bare ``self``,
rewrite callers ``TokenizerManager.foo(self.pause_controller, ...)`` ->
``self.pause_controller.foo(...)`` (pure prefix transformation).

Also flip ``__post_init__`` from the forwarding lambda back to direct
``self._handle_abort_req`` registration now that ``_handle_abort_req`` lives
on PauseController.
"""

# /// script
# requires-python = ">=3.10"
# dependencies = ["typer"]
# ///

import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from _helpers import cut_lines, find_method_lines, replace_call_site
from _runner import run_pr

ID = "introduce-pause-controller-move"
SUBJECT = "Move 4 methods into PauseController class body"
BODY = """\
Mechanical cut + paste for the ``introduce-pause-controller`` mech move.

Cut ``pause_generation`` / ``continue_generation`` / ``abort_request`` /
``_handle_abort_req`` (@staticmethods after prep) from TokenizerManager and
paste them into the ``PauseController`` class body in
``managers/pause_controller.py``.

Drop ``@staticmethod`` decorators; simplify ``self: "PauseController"``
type annotation to bare ``self``. Inter-method calls inside the bodies
revert from ``TokenizerManager.<m>(self, ...)`` -> ``self.<m>(...)`` (pure
prefix transformation; symmetric reversal of the prep edit).

External callers all updated:
  ``TokenizerManager.foo(self.pause_controller, ...)`` ->
  ``self.pause_controller.foo(...)``
  ``TokenizerManager.foo(tokenizer_manager.pause_controller, ...)`` ->
  ``tokenizer_manager.pause_controller.foo(...)``
(pure prefix transformation; nothing inside the parens changes).

Also flip ``PauseController.__post_init__`` from the forwarding lambda
``lambda recv_obj: TokenizerManager._handle_abort_req(self, recv_obj)``
back to the direct ``self._handle_abort_req`` registration now that
``_handle_abort_req`` is a method on PauseController.
"""
AREA = "mech_tokenizer_manager"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


CLUSTER_METHODS = (
    "pause_generation",
    "continue_generation",
    "abort_request",
    "_handle_abort_req",
)


def _strip_staticmethod_typeflip(method_text: str) -> str:
    """Drop @staticmethod decorator and the ``self: "PauseController"`` annotation."""
    text = method_text.replace("    @staticmethod\n", "", 1)
    text = text.replace('self: "PauseController"', "self")
    return text


def _revert_intercluster_calls(body: str) -> str:
    """Reverse the prep-stage class-qualification:
    ``TokenizerManager.<m>(self, `` -> ``self.<m>(``. Pure prefix transform."""
    for name in CLUSTER_METHODS:
        body = body.replace(
            f"TokenizerManager.{name}(self, ",
            f"self.{name}(",
        )
    return body


def transform(wt: Path) -> None:
    tm = wt / "python/sglang/srt/managers/tokenizer_manager.py"
    control_mixin = wt / "python/sglang/srt/managers/tokenizer_control_mixin.py"
    multi_mixin = wt / "python/sglang/srt/managers/multi_tokenizer_mixin.py"
    pause_file = wt / "python/sglang/srt/managers/pause_controller.py"

    # 1. Cut all 4 staticmethods from TM (bottom-up so line ranges stay valid).
    name_to_start = {}
    for n in CLUSTER_METHODS:
        s, _ = find_method_lines(tm.read_text(), class_name="TokenizerManager", method_name=n)
        name_to_start[n] = s
    method_blocks: dict[str, str] = {}
    for n in sorted(CLUSTER_METHODS, key=lambda nn: -name_to_start[nn]):
        s, e = find_method_lines(tm.read_text(), class_name="TokenizerManager", method_name=n)
        block = cut_lines(tm, s, e)
        block = _strip_staticmethod_typeflip(block)
        block = _revert_intercluster_calls(block)
        method_blocks[n] = block

    # 2. Append into PauseController class body (preserve original source order).
    ordered_blocks = [method_blocks[n] for n in CLUSTER_METHODS]
    ptext = pause_file.read_text()
    ptext = ptext.rstrip() + "\n\n" + "\n".join(b.rstrip() for b in ordered_blocks) + "\n"
    pause_file.write_text(ptext)

    # 3. Flip __post_init__ back to direct registration now that the method
    #    lives on PauseController. Also drop the lazy TokenizerManager import.
    pause_file.write_text(
        replace_call_site(
            pause_file.read_text(),
            old=(
                "    def __post_init__(self) -> None:\n"
                "        # During prep, ``_handle_abort_req`` still lives on TokenizerManager\n"
                "        # as a @staticmethod with ``self: PauseController``; forward through it\n"
                "        # via a lambda. The move commit replaces this with\n"
                "        # ``self.dispatcher._mapping[AbortReq] = self._handle_abort_req``.\n"
                "        from sglang.srt.managers.tokenizer_manager import TokenizerManager\n"
                "\n"
                "        self.dispatcher._mapping[AbortReq] = (\n"
                "            lambda recv_obj: TokenizerManager._handle_abort_req(self, recv_obj)\n"
                "        )\n"
            ),
            new=(
                "    def __post_init__(self) -> None:\n"
                "        # TypeBasedDispatcher has no public register(); poke private _mapping.\n"
                "        self.dispatcher._mapping[AbortReq] = self._handle_abort_req\n"
            ),
        )
    )

    # 4. Caller rewrites — pure prefix transformation across all files that
    #    were touched in prep. The prep step emitted exactly these forms.
    def rewire(t: str) -> str:
        for name in ("pause_generation", "continue_generation", "abort_request"):
            t = t.replace(
                f"TokenizerManager.{name}(self.pause_controller, ",
                f"self.pause_controller.{name}(",
            )
            t = t.replace(
                f"TokenizerManager.{name}(tokenizer_manager.pause_controller, ",
                f"tokenizer_manager.pause_controller.{name}(",
            )
        return t

    for f in (tm, control_mixin, multi_mixin):
        f.write_text(rewire(f.read_text()))

    # 5. Entrypoints — same pure prefix transformation.
    import glob

    for fpath in glob.glob(str(wt / "python/sglang/srt/entrypoints/**/*.py"), recursive=True):
        f = Path(fpath)
        f.write_text(rewire(f.read_text()))


if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        area_branch=AREA_BRANCH,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
