#!/usr/bin/env python3
"""Mechanical move of _init_req_state (staticmethod form) out of
TokenizerManager into ``managers/request_state.py`` as free function
``init_req``. Per MECH_COMMIT_SPLIT: only physical relocation + the
scope-induced rename ``_init_req_state`` -> ``init_req`` (leading ``_``
loses meaning at module level).

The prep work (sig reshape, callers to ``TokenizerManager.foo(...)`` form)
already landed in ``move-init-req-prep``.
"""

# /// script
# requires-python = ">=3.10"
# dependencies = ["typer"]
# ///

import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from _helpers import cut_lines, find_method_lines, insert_after, replace_call_site
from _runner import run_pr

ID = "move-init-req-move"
SUBJECT = "Move _init_req_state (now staticmethod) to managers/request_state.py as init_req"
BODY = """\
Physical move only:
  - Cut @staticmethod _init_req_state from TokenizerManager
  - Drop ``@staticmethod`` decorator; dedent body to module level
  - Rename ``_init_req_state`` -> ``init_req`` (scope-induced; leading ``_``
    has no meaning at module level)
  - Append to managers/request_state.py with the additional imports needed
    by the body
  - Update three caller sites: ``TokenizerManager._init_req_state(...)``
    -> ``init_req(...)`` (pure prefix replacement)
"""
AREA = "mech_tokenizer_manager"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


# Additional imports needed once init_req body lives in request_state.py.
EXTRA_IMPORTS = (
    "from typing import Any, Dict, List, Optional, Union\n"
)
EXTRA_IMPORTS_AFTER = (
    "import fastapi\n"
    "\n"
    "from sglang.srt.disaggregation.utils import DisaggregationMode\n"
)
TRACE_IMPORT = (
    "from sglang.srt.observability.trace import extract_trace_headers\n"
)


def transform(wt: Path) -> None:
    tm = wt / "python/sglang/srt/managers/tokenizer_manager.py"
    rs = wt / "python/sglang/srt/managers/request_state.py"

    # Cut the staticmethod from TM.
    s, e = find_method_lines(
        tm.read_text(), class_name="TokenizerManager", method_name="_init_req_state"
    )
    method_text = cut_lines(tm, s, e)

    # Drop @staticmethod line; dedent body 4 spaces (class -> module level).
    lines = method_text.splitlines(keepends=True)
    # Find the @staticmethod decorator line; drop it.
    decorator_idx = next(i for i, l in enumerate(lines) if l.strip() == "@staticmethod")
    lines = lines[:decorator_idx] + lines[decorator_idx + 1 :]
    # Dedent all non-empty lines by 4 spaces.
    dedented = []
    for l in lines:
        if l.startswith("    "):
            dedented.append(l[4:])
        else:
            dedented.append(l)
    fn_text = "".join(dedented)
    # Rename
    fn_text = fn_text.replace("def _init_req_state(", "def init_req(", 1)

    # Append to request_state.py.
    rs_text = rs.read_text()
    # Bring in additional imports.
    rs_text = rs_text.replace(
        "from typing import Any, Dict, List, Union\n",
        "from typing import Any, Dict, List, Optional, Union\n",
    )
    rs_text = rs_text.replace(
        "import dataclasses\n",
        "import dataclasses\n\nimport fastapi\n",
    )
    rs_text = rs_text.replace(
        "from sglang.srt.managers.io_struct import EmbeddingReqInput, GenerateReqInput\n",
        (
            "from sglang.srt.disaggregation.utils import DisaggregationMode\n"
            "from sglang.srt.managers.io_struct import EmbeddingReqInput, GenerateReqInput\n"
        ),
    )
    rs_text = rs_text.replace(
        "from sglang.srt.observability.req_time_stats import APIServerReqTimeStats\n",
        (
            "from sglang.srt.observability.req_time_stats import APIServerReqTimeStats\n"
            "from sglang.srt.observability.trace import extract_trace_headers\n"
        ),
    )
    rs.write_text(rs_text.rstrip() + "\n\n\n" + fn_text.rstrip() + "\n")

    # Update tokenizer_manager.py import + 3 caller sites.
    text = tm.read_text()
    text = text.replace(
        "from sglang.srt.managers.request_state import ReqState\n",
        "from sglang.srt.managers.request_state import ReqState, init_req\n",
    )
    text = replace_call_site(
        text,
        old="TokenizerManager._init_req_state(",
        new="init_req(",
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
