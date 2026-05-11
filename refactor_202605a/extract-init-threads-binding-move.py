#!/usr/bin/env python3
"""Move stage for extract-init-threads-binding (MECH_COMMIT_SPLIT §"二段式"):

Pure cut+paste into ``utils/numa_utils.py``. Body byte-equivalent.
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
    append_to_file,
    cut_lines,
    dedent_method_to_function,
    find_method_lines,
    insert_after,
    replace_call_site,
)
from _runner import run_pr

ID = "extract-init-threads-binding-move"
SUBJECT = "Move init_threads_binding to utils.numa_utils (cut+paste)"
BODY = ""
AREA = "mech_model_runner"
BASE = "tom_refactor_202605a/primary/mech_model_runner/extract-init-threads-binding-prep"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


def transform(wt: Path) -> None:
    mr = wt / "python/sglang/srt/model_executor/model_runner.py"
    nu = wt / "python/sglang/srt/utils/numa_utils.py"

    start, end = find_method_lines(
        mr.read_text(), class_name="ModelRunner", method_name="init_threads_binding"
    )
    method_text = cut_lines(mr, start, end)
    lines = method_text.splitlines(keepends=True)
    assert lines[0].strip() == "@staticmethod"
    function_text = dedent_method_to_function("".join(lines[1:]))

    nu_text = nu.read_text()
    nu_text = replace_call_site(
        nu_text,
        old="from sglang.srt.utils import is_cuda",
        new="from sglang.srt.utils import get_cpu_ids_by_node, is_cuda",
    )
    nu.write_text(nu_text)
    append_to_file(nu, function_text)

    text = mr.read_text()
    text = replace_call_site(
        text,
        old="ModelRunner.init_threads_binding(",
        new="init_threads_binding(",
    )
    text = replace_call_site(text, old="    get_cpu_ids_by_node,\n", new="")
    text = insert_after(
        text,
        anchor="from sglang.srt.utils.network import NetworkAddress, get_local_ip_auto\n",
        addition="from sglang.srt.utils.numa_utils import init_threads_binding\n",
    )
    mr.write_text(text)


if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        area_branch=AREA_BRANCH,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
