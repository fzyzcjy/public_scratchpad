#!/usr/bin/env python3
"""Cut `init_threads_binding` from ModelRunner; paste in utils/numa_utils.py."""

import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.append(str(HERE))
sys.path.append(".claude/skills/mechanical-refactor-verify")
from _helpers import (
    append_to_file,
    cut_lines,
    dedent_method_to_function,
    find_method_lines,
)
from mechanical_refactor_verify_utils import (
    git_add_and_commit,
    verify_mechanical_refactor,
)

BASE_COMMIT = "tom_refactor/19"
TARGET_COMMIT = "tom_refactor/20"


def transform(dir_root: Path) -> None:
    mr = dir_root / "python/sglang/srt/model_executor/model_runner.py"
    nu = dir_root / "python/sglang/srt/utils/numa_utils.py"

    start, end = find_method_lines(
        mr.read_text(), class_name="ModelRunner", method_name="init_threads_binding"
    )
    method_text = cut_lines(mr, start, end)
    function_text = dedent_method_to_function(method_text)
    function_text = function_text.replace(
        "def init_threads_binding(self):\n",
        "def init_threads_binding(\n    *,\n    tp_rank,\n    tp_size,\n):\n",
    )
    function_text = function_text.replace("self.tp_size", "tp_size")
    function_text = function_text.replace("self.tp_rank", "tp_rank")
    function_text = function_text.replace(
        "self.local_omp_cpuid = ", "local_omp_cpuid = "
    )
    function_text = function_text.rstrip() + "\n    return local_omp_cpuid\n"

    nu_text = nu.read_text()
    nu_text = nu_text.replace(
        "from sglang.srt.utils import is_cuda",
        "from sglang.srt.utils import get_cpu_ids_by_node, is_cuda",
    )
    nu.write_text(nu_text)
    append_to_file(nu, function_text)

    text = mr.read_text()
    text = text.replace(
        '        if self.device == "cpu":\n            self.init_threads_binding()',
        '        if self.device == "cpu":\n'
        "            self.local_omp_cpuid = init_threads_binding(\n"
        "                tp_rank=self.tp_rank, tp_size=self.tp_size\n"
        "            )",
    )
    text = text.replace("    get_cpu_ids_by_node,\n", "")
    text = text.replace(
        "from sglang.srt.utils.network import NetworkAddress, get_local_ip_auto\n",
        "from sglang.srt.utils.network import NetworkAddress, get_local_ip_auto\n"
        "from sglang.srt.utils.numa_utils import init_threads_binding\n",
    )
    mr.write_text(text)

    git_add_and_commit(
        "Extract init_threads_binding to free function in utils.numa_utils",
        cwd=str(dir_root),
    )


if __name__ == "__main__":
    verify_mechanical_refactor(
        base_commit=BASE_COMMIT,
        target_commit=TARGET_COMMIT,
        transform=transform,
    )
