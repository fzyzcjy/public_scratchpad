#!/usr/bin/env python3
"""Move (pure cut/paste): PauseController methods relocate from TM to target class.

Per MECH_COMMIT_SPLIT: physical-move step. The class skeleton, composition
wiring, staticmethod conversion, body rewrites, __post_init__ lambda
forwarding, and all class-qualified caller forms already landed in
``introduce-pause-controller-prep``.
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
    replace_call_site,
    rewrite_intra_class_calls,
)
from _runner import run_pr

ID = "introduce-pause-controller-move"
SUBJECT = "Hand generation pause/abort over to PauseController"
BODY = """\
Pure physical move per MECH_COMMIT_SPLIT. Cut the 4 @staticmethod methods
(pause_generation, continue_generation, abort_request, _handle_abort_req)
from TokenizerManager; paste into PauseController (drop @staticmethod,
``self: "PauseController"`` -> plain ``self``). Bodies are byte-identical
to the prep-installed bodies. Flip __post_init__ back from the
``lambda x: TokenizerManager._handle_abort_req(self, x)`` forwarder to a
direct ``self._handle_abort_req`` reference. Caller prefix replacement:
``TokenizerManager.<method>(self.pause_controller, ...)`` ->
``self.pause_controller.<method>(...)``;
``TokenizerManager.<method>(tokenizer_manager.pause_controller, ...)`` ->
``tokenizer_manager.pause_controller.<method>(...)`` in entrypoints. The
in-class cross-call ``TokenizerManager.abort_request(self, ...)`` ->
``self.abort_request(...)`` (now an instance method on PauseController).
"""
AREA = "mech_tokenizer_manager"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


EXTRA_IMPORTS = '''import logging

from sglang.srt.managers import logprob_ops
from sglang.srt.managers.io_struct import (
    ContinueGenerationReqInput,
    PauseGenerationReqInput,
)
from sglang.srt.managers.scheduler import is_health_check_generate_req

logger = logging.getLogger(__name__)
'''


def transform(wt: Path) -> None:
    tm = wt / "python/sglang/srt/managers/tokenizer_manager.py"
    pc = wt / "python/sglang/srt/managers/pause_controller.py"

    # Cut bottom-up to preserve line numbers between cuts. ``_handle_abort_req``
    # was privacy-flipped to ``handle_abort_req`` in prep.
    method_names = (
        "pause_generation",
        "continue_generation",
        "abort_request",
        "handle_abort_req",
    )
    name_to_range = {}
    for n in method_names:
        s, e = find_method_lines(tm.read_text(), class_name="TokenizerManager", method_name=n)
        name_to_range[n] = (s, e)
    cut_blocks = {}
    for n in sorted(method_names, key=lambda nn: -name_to_range[nn][0]):
        s, e = find_method_lines(tm.read_text(), class_name="TokenizerManager", method_name=n)
        cut_blocks[n] = cut_lines(tm, s, e)

    # Strip @staticmethod + restore plain self; flip intra-class call qualifier.
    def strip_staticmethod_and_self_type(block: str) -> str:
        block = block.replace("    @staticmethod\n", "", 1)
        block = block.replace('self: "PauseController", ', "self, ")
        block = block.replace('self: "PauseController"', "self")
        block = rewrite_intra_class_calls(
            block,
            source_classes=["TokenizerManager"],
            target_class="PauseController",
            methods=list(method_names),
        )
        return block

    bodies = [strip_staticmethod_and_self_type(cut_blocks[n]) for n in method_names]
    methods_text = "\n" + "\n".join(b.rstrip() for b in bodies) + "\n"

    pc_text = pc.read_text()
    # Inject extra imports after dataclasses import.
    pc_text = pc_text.replace(
        "from dataclasses import dataclass, field\n",
        "from dataclasses import dataclass, field\n\n" + EXTRA_IMPORTS,
    )
    pc.write_text(pc_text.rstrip() + "\n" + methods_text)

    # Collapse the prep-stage lambda forwarder in TM's init_request_dispatcher
    # entry to a direct method ref on the controller.
    text = tm.read_text()
    text = replace_call_site(
        text,
        old=(
            "                (\n"
            "                    AbortReq,\n"
            "                    lambda x: TokenizerManager.handle_abort_req(\n"
            "                        self.pause_controller, x\n"
            "                    ),\n"
            "                ),\n"
        ),
        new="                (AbortReq, self.pause_controller.handle_abort_req),\n",
    )

    # Caller prefix replacement in TM: TokenizerManager.<m>(self.pause_controller, ...) -> self.pause_controller.<m>(...).
    for m in ("abort_request", "pause_generation", "continue_generation", "handle_abort_req"):
        text = text.replace(
            f"TokenizerManager.{m}(self.pause_controller, ",
            f"self.pause_controller.{m}(",
        )
    tm.write_text(text)

    # Same in mixin files (control_mixin, multi_mixin).
    for fname in ("tokenizer_control_mixin.py", "multi_tokenizer_mixin.py"):
        f = wt / "python/sglang/srt/managers" / fname
        t = f.read_text()
        for m in ("abort_request", "pause_generation", "continue_generation", "handle_abort_req"):
            t = t.replace(
                f"TokenizerManager.{m}(self.pause_controller, ",
                f"self.pause_controller.{m}(",
            )
        f.write_text(t)

    # Entrypoints: TokenizerManager.<m>(tokenizer_manager.pause_controller, ...) -> tokenizer_manager.pause_controller.<m>(...).
    import glob

    import re as _re
    for fpath in glob.glob(str(wt / "python/sglang/srt/entrypoints/**/*.py"), recursive=True):
        f = Path(fpath)
        t = f.read_text()
        original = t
        for m in ("abort_request", "pause_generation", "continue_generation"):
            # Bare form: TokenizerManager.<m>(tokenizer_manager.pause_controller, ...)
            t = t.replace(
                f"TokenizerManager.{m}(tokenizer_manager.pause_controller, ",
                f"tokenizer_manager.pause_controller.{m}(",
            )
            # Prefixed form: TokenizerManager.<m>(<prefix>.tokenizer_manager.pause_controller, ...)
            t = _re.sub(
                rf"TokenizerManager\.{_re.escape(m)}\(\s*\n?(\s*)([\w.]+)\.tokenizer_manager\.pause_controller,\s*",
                lambda mat, _meth=m: f"{mat.group(2)}.tokenizer_manager.pause_controller.{_meth}(\n{mat.group(1)}",
                t,
            )
            t = _re.sub(
                rf"TokenizerManager\.{_re.escape(m)}\(([\w.]+)\.tokenizer_manager\.pause_controller, ",
                lambda mat, _meth=m: f"{mat.group(1)}.tokenizer_manager.pause_controller.{_meth}(",
                t,
            )
        if t != original:
            # Drop the prep-injected import only if no other reference to
            # ``TokenizerManager`` remains in this file (e.g. as a type
            # annotation on a constructor parameter). Otherwise we'd reintroduce
            # an F821 in lint.
            t_after = t.replace(
                "from sglang.srt.managers.tokenizer_manager import TokenizerManager\n",
                "",
                1,
            )
            if "TokenizerManager" in t_after:
                # Still referenced — keep the import.
                t = t
            else:
                t = t_after
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
