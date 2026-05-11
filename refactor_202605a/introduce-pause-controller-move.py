#!/usr/bin/env python3
"""Move 4 pause/abort methods from TokenizerManager to PauseController.

Per MECH_COMMIT_SPLIT: physical-move step. The class skeleton + composition
wiring already landed in ``introduce-pause-controller-prep``.
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
from _helpers import cut_lines, find_method_lines
from _runner import run_pr

ID = "introduce-pause-controller-move"
SUBJECT = "Move pause/abort methods to PauseController"
BODY = """\
Cut 4 methods (pause_generation, continue_generation, abort_request,
_handle_abort_req) from TokenizerManager. Add them + __post_init__
(AbortReq dispatcher registration) to PauseController.

Body rewrites: self.enable_metrics -> self.config.enable_metrics, etc.

External references self.is_pause / self.is_pause_cond / self.abort_request
rewrite to go via self.pause_controller in tokenizer_manager.py /
tokenizer_control_mixin.py / multi_tokenizer_mixin.py + entrypoints.
"""
AREA = "mech_tokenizer_manager"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


EXTRA_IMPORTS = '''import logging

from sglang.srt.managers import logprob_ops
from sglang.srt.managers.io_struct import (
    AbortReq,
    ContinueGenerationReqInput,
    PauseGenerationReqInput,
)
from sglang.srt.managers.scheduler import is_health_check_generate_req

logger = logging.getLogger(__name__)
'''


POST_INIT = '''
    def __post_init__(self) -> None:
        # TypeBasedDispatcher has no public register(); poke private _mapping.
        self.dispatcher._mapping[AbortReq] = self._handle_abort_req
'''


def transform(wt: Path) -> None:
    tm = wt / "python/sglang/srt/managers/tokenizer_manager.py"
    control_mixin = wt / "python/sglang/srt/managers/tokenizer_control_mixin.py"
    multi_mixin = wt / "python/sglang/srt/managers/multi_tokenizer_mixin.py"
    pc = wt / "python/sglang/srt/managers/pause_controller.py"

    # Cut bottom-up.
    method_names = (
        "pause_generation",
        "continue_generation",
        "abort_request",
        "_handle_abort_req",
    )
    name_to_range = {}
    for n in method_names:
        s, e = find_method_lines(tm.read_text(), class_name="TokenizerManager", method_name=n)
        name_to_range[n] = (s, e)
    cut_blocks = {}
    for n in sorted(method_names, key=lambda nn: -name_to_range[nn][0]):
        s, e = find_method_lines(tm.read_text(), class_name="TokenizerManager", method_name=n)
        cut_blocks[n] = cut_lines(tm, s, e)

    def rewrite_body(body: str) -> str:
        body = body.replace("self.enable_metrics", "self.config.enable_metrics")
        body = body.replace("self.server_args.weight_version", "self.config.weight_version")
        body = body.replace(
            "self.server_args.skip_tokenizer_init",
            "self.config.skip_tokenizer_init",
        )
        body = body.replace(
            "self.raw_tokenizer_wrapper.tokenizer", "self.tokenizer"
        )
        body = body.replace(
            "self.request_metrics_recorder.metrics_collector",
            "self.metrics_collector",
        )
        return body

    bodies = [rewrite_body(cut_blocks[n]) for n in method_names]
    methods_text = POST_INIT + "\n" + "\n\n".join(b.rstrip() for b in bodies) + "\n"

    pc_text = pc.read_text()
    # Inject extra imports after dataclasses import.
    pc_text = pc_text.replace(
        "from dataclasses import dataclass, field\n",
        "from dataclasses import dataclass, field\n\n" + EXTRA_IMPORTS,
    )
    pc.write_text(pc_text.rstrip() + "\n" + methods_text)

    # Caller substitutions (residual self.is_pause / self.abort_request / etc.).
    def rewire(text: str) -> str:
        text = re.sub(r"\bself\.is_pause_cond\b", "self.pause_controller.is_pause_cond", text)
        text = re.sub(r"\bself\.is_pause\b", "self.pause_controller.is_pause", text)
        text = re.sub(r"\bself\.abort_request\(", "self.pause_controller.abort_request(", text)
        return text

    tm.write_text(rewire(tm.read_text()))
    control_mixin.write_text(rewire(control_mixin.read_text()))
    multi_mixin.write_text(rewire(multi_mixin.read_text()))

    # External callers in entrypoints.
    import glob
    for fpath in glob.glob(str(wt / "python/sglang/srt/entrypoints/**/*.py"), recursive=True):
        f = Path(fpath)
        t = f.read_text()
        t = re.sub(
            r"\btokenizer_manager\.abort_request\(",
            "tokenizer_manager.pause_controller.abort_request(",
            t,
        )
        t = re.sub(
            r"\btokenizer_manager\.pause_generation\(",
            "tokenizer_manager.pause_controller.pause_generation(",
            t,
        )
        t = re.sub(
            r"\btokenizer_manager\.continue_generation\(",
            "tokenizer_manager.pause_controller.continue_generation(",
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
