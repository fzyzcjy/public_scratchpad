#!/usr/bin/env python3
"""Prep: fold the remaining weight ops into WeightUpdaterController (in-place staticmethod conversion + caller rewrites)."""

# /// script
# requires-python = ">=3.10"
# dependencies = ["typer"]
# ///

import ast
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from _helpers import replace_call_site
from _runner import run_pr

ID = "wuc-absorb-prep"
SUBJECT = "Stage remaining weight ops for handoff to WeightUpdaterController"
BODY = """\
Per MECH_COMMIT_SPLIT §"split-class scenario": prep does ALL semantic work.

Folds the rest of the weight family into WeightUpdaterController, mirroring
the scheduler-side SchedulerWeightUpdaterManager scope (the two remote-instance
send-group methods stay on TokenizerControlMixin, matching the scheduler's own
exclusion). The methods (``init_weights_update_group`` /
``destroy_weights_update_group`` / ``update_weights_from_distributed`` /
``update_weights_from_tensor`` / ``update_weights_from_ipc`` /
``get_weights_by_name`` / ``release_memory_occupation`` /
``resume_memory_occupation`` / ``check_weights``) become ``@staticmethod`` with
``self: "WeightUpdaterController"`` annotation, staying on TokenizerControlMixin
for this commit. The controller gains a field per fan-out communicator, plugged
after init_communicators alongside the corpus/lora forwarders (the dispatch
registration is untouched). Body rewrites reroute ``self.is_pause`` to the
injected ``is_pause_getter`` and class-qualify the intra-controller version-bump
call. Entrypoints (engine.py / http_server.py) switch to the class-qualified
form so the next commit's caller change is a pure prefix replacement.
"""
AREA = "mech_tokenizer_manager"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


# Methods folded into the controller (order = canonical paste order in -move).
_METHODS = (
    "init_weights_update_group",
    "destroy_weights_update_group",
    "update_weights_from_distributed",
    "update_weights_from_tensor",
    "update_weights_from_ipc",
    "get_weights_by_name",
    "release_memory_occupation",
    "resume_memory_occupation",
    "check_weights",
)


def _method_ranges(text: str, class_name: str, method_name: str):
    tree = ast.parse(text)
    func_types = (ast.FunctionDef, ast.AsyncFunctionDef)
    for cls in ast.walk(tree):
        if isinstance(cls, ast.ClassDef) and cls.name == class_name:
            for i, node in enumerate(cls.body):
                if isinstance(node, func_types) and node.name == method_name:
                    start = node.lineno - 1
                    if node.decorator_list:
                        start = node.decorator_list[0].lineno - 1
                    body_start = node.body[0].lineno - 1
                    if i + 1 < len(cls.body):
                        end = cls.body[i + 1].lineno - 1
                        nxt = cls.body[i + 1]
                        if isinstance(nxt, func_types + (ast.ClassDef,)) and nxt.decorator_list:
                            end = nxt.decorator_list[0].lineno - 1
                    else:
                        end = node.end_lineno
                    return start, body_start, end
    raise ValueError(f"{class_name}.{method_name} not found")


def _rewrite_body(body_text: str) -> str:
    """Reroute facade reads + class-qualify the intra-controller version bump."""
    # is_pause is now reached through the injected getter on the controller.
    body_text = body_text.replace(
        "is_paused = self.is_pause\n", "is_paused = self.is_pause_getter()\n"
    )
    # The version bump targets _update_weight_version_if_provided, already a
    # controller method (landed with the disk extraction). Class-qualify it now;
    # -move folds it back to a sibling self-call.
    body_text = body_text.replace(
        "self.weight_updater_controller._update_weight_version_if_provided(\n"
        "                obj.weight_version\n"
        "            )",
        "WeightUpdaterController._update_weight_version_if_provided(\n"
        "                self, obj.weight_version\n"
        "            )",
    )
    return body_text


def _retype_method(text: str, method_name: str) -> str:
    """Prepend @staticmethod and retype self to the controller, programmatically
    (header taken from the live source, not a hardcoded literal)."""
    s, body_s, e = _method_ranges(text, "TokenizerControlMixin", method_name)
    lines = text.splitlines(keepends=True)
    header = "".join(lines[s:body_s])
    header = header.replace(
        "        self: TokenizerManager,\n",
        '        self: "WeightUpdaterController",\n',
        1,
    )
    header = "    @staticmethod\n" + header
    body_text = _rewrite_body("".join(lines[body_s:e]))
    return "".join(lines[:s]) + header + body_text + "".join(lines[e:])


def transform(wt: Path) -> None:
    tm = wt / "python/sglang/srt/managers/tokenizer_manager.py"
    control_mixin = wt / "python/sglang/srt/managers/tokenizer_control_mixin.py"
    controller = (
        wt
        / "python/sglang/srt/managers/tokenizer_manager_components/weight_updater_controller.py"
    )

    # ---- controller: declare a field per fan-out communicator ----
    ctrl_text = controller.read_text()
    comm_fields = "".join(
        f"    {m}_communicator: Any = None  # set after facade.init_communicators\n"
        for m in _METHODS
    )
    ctrl_text = replace_call_site(
        ctrl_text,
        old="    model_update_tmp: List[Any] = field(default_factory=list)\n",
        new="    model_update_tmp: List[Any] = field(default_factory=list)\n" + comm_fields,
    )
    controller.write_text(ctrl_text)

    # ---- TM: plug the communicators after init_communicators ----
    text = tm.read_text()
    backfill = "".join(
        f"        self.weight_updater_controller.{m}_communicator = (\n"
        f"            self.{m}_communicator\n"
        f"        )\n"
        for m in _METHODS
    )
    text = replace_call_site(
        text,
        old="        self.init_communicators(self.server_args)\n",
        new="        self.init_communicators(self.server_args)\n" + backfill,
    )
    tm.write_text(text)

    # ---- TokenizerControlMixin: retype the 9 methods ----
    cm_text = control_mixin.read_text()
    for name in _METHODS:
        cm_text = _retype_method(cm_text, name)
    control_mixin.write_text(cm_text)

    # ---- Entrypoint callers: class-qualify (prep), -move flips the prefix ----
    engine = wt / "python/sglang/srt/entrypoints/engine.py"
    http_server = wt / "python/sglang/srt/entrypoints/http_server.py"

    text = engine.read_text()
    for m in _METHODS:
        text = text.replace(
            f"self.tokenizer_manager.{m}(",
            f"TokenizerManager.{m}(self.tokenizer_manager.weight_updater_controller, ",
        )
    engine.write_text(text)

    text = http_server.read_text()
    for m in _METHODS:
        text = text.replace(
            f"_global_state.tokenizer_manager.{m}(",
            f"TokenizerManager.{m}(_global_state.tokenizer_manager.weight_updater_controller, ",
        )
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
