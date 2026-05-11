#!/usr/bin/env python3
"""In-place prep for moving _init_req_state out of TokenizerManager.

Make _init_req_state a @staticmethod with explicit kwargs (no self).
Body stays in TokenizerManager class; subsequent commit ``move-init-req-move``
will physically relocate it. Callers updated to
``TokenizerManager._init_req_state(...)`` (class-qualified).
"""

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

ID = "move-init-req-prep"
SUBJECT = "Prep _init_req_state for move: staticmethod + explicit kwargs"
BODY = """\
In-place prep per MECH_COMMIT_SPLIT before the physical move:

  - Add @staticmethod decorator
  - Drop ``self``; pass ``rid_to_state``, ``enable_trace``, ``disagg_mode``
    as explicit args
  - Three caller sites switch to ``TokenizerManager._init_req_state(...)``
    (class-qualified call), making the pure-prefix replacement in the
    next commit byte-symmetric.

No behavior change. Body stays inside TokenizerManager class.
"""
AREA = "mech_tokenizer_manager"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


# Replacement signature header (with @staticmethod). 4-space class indent.
NEW_HEADER = '''    @staticmethod
    def _init_req_state(
        rid_to_state: Dict[str, ReqState],
        *,
        obj: Union[GenerateReqInput, EmbeddingReqInput],
        request: Optional[fastapi.Request] = None,
        enable_trace: bool,
        disagg_mode: DisaggregationMode,
    ) -> None:
'''


def _method_ranges(text: str, class_name: str, method_name: str):
    """Return (start_line, body_start_line, end_line) for the named method.

    All 0-indexed half-open. ``start_line`` includes any decorators.
    ``body_start_line`` is the line of the first body statement (after ``):``).
    ``end_line`` is the line after the method.
    """
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


def transform(wt: Path) -> None:
    tm = wt / "python/sglang/srt/managers/tokenizer_manager.py"
    text = tm.read_text()

    s, body_s, e = _method_ranges(text, "TokenizerManager", "_init_req_state")
    lines = text.splitlines(keepends=True)
    body_text = "".join(lines[body_s:e])

    # Body rewrites: drop self.X reads in favour of the new explicit args.
    body_text = body_text.replace("self.server_args.enable_trace", "enable_trace")
    body_text = body_text.replace("self.rid_to_state", "rid_to_state")
    body_text = body_text.replace("self.disaggregation_mode", "disagg_mode")

    new_method = NEW_HEADER + body_text
    new_text = "".join(lines[:s]) + new_method + "".join(lines[e:])

    # Callers: switch ``self._init_req_state(...)`` -> ``TokenizerManager._init_req_state(...)``
    # with explicit kwargs.
    new_text = replace_call_site(
        new_text,
        old="        self._init_req_state(obj, request)",
        new=(
            "        TokenizerManager._init_req_state(\n"
            "            self.rid_to_state,\n"
            "            obj=obj,\n"
            "            request=request,\n"
            "            enable_trace=self.server_args.enable_trace,\n"
            "            disagg_mode=self.disaggregation_mode,\n"
            "        )"
        ),
    )
    new_text = new_text.replace(
        "                self._init_req_state(tmp_obj)\n",
        (
            "                TokenizerManager._init_req_state(\n"
            "                    self.rid_to_state,\n"
            "                    obj=tmp_obj,\n"
            "                    enable_trace=self.server_args.enable_trace,\n"
            "                    disagg_mode=self.disaggregation_mode,\n"
            "                )\n"
        ),
    )
    new_text = new_text.replace(
        "                    self._init_req_state(tmp_obj)\n",
        (
            "                    TokenizerManager._init_req_state(\n"
            "                        self.rid_to_state,\n"
            "                        obj=tmp_obj,\n"
            "                        enable_trace=self.server_args.enable_trace,\n"
            "                        disagg_mode=self.disaggregation_mode,\n"
            "                    )\n"
        ),
    )

    tm.write_text(new_text)


if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        area_branch=AREA_BRANCH,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
