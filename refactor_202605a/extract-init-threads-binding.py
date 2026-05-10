#!/usr/bin/env python3
"""Cut `init_threads_binding` from ModelRunner; paste in utils/numa_utils.py.

Single self-write (`self.local_omp_cpuid = ...`) becomes a return value;
caller writes back at call site.
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

ID = "extract-init-threads-binding"
SUBJECT = "Extract init_threads_binding to free function in utils.numa_utils"
BODY = ""
AREA = "mech_model_runner"
BASE = "tom_refactor_202605a/raw/mech_model_runner/extract-apply-torch-tp"
AREA_BRANCH = f"tom_refactor_202605a/raw/{AREA}"


def transform(wt: Path) -> None:
    mr = wt / "python/sglang/srt/model_executor/model_runner.py"
    nu = wt / "python/sglang/srt/utils/numa_utils.py"

    start, end = find_method_lines(
        mr.read_text(), class_name="ModelRunner", method_name="init_threads_binding"
    )
    function_text = (
        dedent_method_to_function(cut_lines(mr, start, end))
        .replace(
            "def init_threads_binding(self):\n",
            "def init_threads_binding(\n    *,\n    tp_rank: int,\n    tp_size: int,\n):\n",
        )
        .replace("self.tp_size", "tp_size")
        .replace("self.tp_rank", "tp_rank")
        .replace("self.local_omp_cpuid = ", "local_omp_cpuid = ")
    )
    function_text = function_text.rstrip() + "\n    return local_omp_cpuid\n"

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
        old='        if self.device == "cpu":\n            self.init_threads_binding()',
        new=(
            '        if self.device == "cpu":\n'
            "            self.local_omp_cpuid = init_threads_binding(\n"
            "                tp_rank=self.tp_rank, tp_size=self.tp_size\n"
            "            )"
        ),
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
