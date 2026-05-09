#!/usr/bin/env python3
"""Reproducible transform: extract `ModelRunner.init_threads_binding` to a free
function `init_threads_binding` in `sglang.srt.utils.numa_utils`.
Strict-minimal mechanical move:
- KEEP function name as `init_threads_binding` (no rename to
  `resolve_cpu_omp_binding`).
- NO docstring added (original had none).
- NO type annotations on parameters.
- Body byte-identical with `self.X` -> kwarg / local-var substitutions, and a
  trailing `return local_omp_cpuid`. The if/else structure and log ordering
  stay untouched.
- ModelRunner method is deleted entirely; the sole caller in `initialize()` is
  rewritten to call the free function directly. This avoids a method-vs-free
  function name clash inside ModelRunner.

Run from the repo root:
    python3 /tmp/transform_init_threads_binding.py
"""

import sys
from pathlib import Path

sys.path.append(".claude/skills/mechanical-refactor-verify")
from mechanical_refactor_verify_utils import (
    verify_mechanical_refactor,
    git_add_and_commit,
)

BASE_COMMIT = "tom_refactor/19"
TARGET_COMMIT = "tom_refactor/20"


def transform(dir_root: Path) -> None:
    # --- Step 1: Add init_threads_binding free function to numa_utils.py ---
    nu = dir_root / "python/sglang/srt/utils/numa_utils.py"
    text = nu.read_text()

    # Add `get_cpu_ids_by_node` to the existing `from sglang.srt.utils import is_cuda`
    # line. Do NOT add typing imports — no annotations are added.
    text = text.replace(
        "from sglang.srt.utils import is_cuda",
        "from sglang.srt.utils import get_cpu_ids_by_node, is_cuda",
    )

    # Append the new free function. Body byte-identical to the original method
    # body with these substitutions ONLY:
    #   self.tp_size  -> tp_size
    #   self.tp_rank  -> tp_rank
    #   self.local_omp_cpuid = X  -> local_omp_cpuid = X
    # Keep if/else structure and log ordering UNCHANGED. Add `return local_omp_cpuid`
    # at the end.
    text = text.rstrip() + (
        "\n\n\ndef init_threads_binding(\n"
        "    *,\n"
        "    tp_rank,\n"
        "    tp_size,\n"
        "):\n"
        '    omp_cpuids = os.environ.get("SGLANG_CPU_OMP_THREADS_BIND", "all")\n'
        "    cpu_ids_by_node = get_cpu_ids_by_node()\n"
        "    n_numa_node = len(cpu_ids_by_node)\n"
        '    if omp_cpuids == "all":\n'
        "        assert tp_size <= n_numa_node, (\n"
        '            f"SGLANG_CPU_OMP_THREADS_BIND is not set, in this case, "\n'
        '            f"tp_size {tp_size} should be smaller than or equal to number of numa node on the machine {n_numa_node}. "\n'
        '            f"If you need tp_size to be larger than number of numa node, please set the CPU cores for each tp rank via SGLANG_CPU_OMP_THREADS_BIND explicitly. "\n'
        '            f"For example, on a machine with 2 numa nodes, where core 0-31 are on numa node 0 and core 32-63 are on numa node 1, "\n'
        '            f"it is suggested to use -tp 2 and bind tp rank 0 to core 0-31 and tp rank 1 to core 32-63. "\n'
        '            f"This is the default behavior if SGLANG_CPU_OMP_THREADS_BIND is not set and it is the same as setting SGLANG_CPU_OMP_THREADS_BIND=0-31|32-63. "\n'
        '            f"If you do need tp_size to be larger than the number of numa nodes, you could set SGLANG_CPU_OMP_THREADS_BIND explicitly for example SGLANG_CPU_OMP_THREADS_BIND=0-15|16-31|32-47|48-63 and run with -tp 4. "\n'
        '            f"If you don\'t want each tp rank to use all the cores on one numa node, you could set for example SGLANG_CPU_OMP_THREADS_BIND=0-15|32-47 and run with -tp 2."\n'
        "        )\n"
        "        if tp_size < n_numa_node:\n"
        "            logger.warning(\n"
        '                f"Detected the current machine has {n_numa_node} numa nodes available, but tp_size is set to {tp_size}, so only {tp_size} numa nodes are used."\n'
        "            )\n"
        "        local_omp_cpuid = cpu_ids_by_node[tp_rank]\n"
        "    else:\n"
        '        threads_bind_list = omp_cpuids.split("|")\n'
        "        assert tp_size == len(threads_bind_list), (\n"
        '            f"SGLANG_CPU_OMP_THREADS_BIND setting must be aligned with TP size parameter ({tp_size}). "\n'
        '            f"Please double check your settings."\n'
        "        )\n"
        "        local_omp_cpuid = threads_bind_list[tp_rank]\n"
        "        if tp_size > n_numa_node:\n"
        "            logger.warning(\n"
        '                f"TP size ({tp_size})is larger than numa node number ({n_numa_node}), "\n'
        '                f"in this case the available memory amount of each rank cannot be determined in prior. "\n'
        '                f"Please set proper `--max-total-tokens` to avoid the out-of-memory error."\n'
        "            )\n"
        "    return local_omp_cpuid\n"
    )
    nu.write_text(text)

    # --- Step 2: Update model_runner.py ---
    mr = dir_root / "python/sglang/srt/model_executor/model_runner.py"
    text = mr.read_text()

    # Delete the method entirely.
    old_method = (
        "    def init_threads_binding(self):\n"
        '        omp_cpuids = os.environ.get("SGLANG_CPU_OMP_THREADS_BIND", "all")\n'
        "        cpu_ids_by_node = get_cpu_ids_by_node()\n"
        "        n_numa_node = len(cpu_ids_by_node)\n"
        '        if omp_cpuids == "all":\n'
        "            assert self.tp_size <= n_numa_node, (\n"
        '                f"SGLANG_CPU_OMP_THREADS_BIND is not set, in this case, "\n'
        '                f"tp_size {self.tp_size} should be smaller than or equal to number of numa node on the machine {n_numa_node}. "\n'
        '                f"If you need tp_size to be larger than number of numa node, please set the CPU cores for each tp rank via SGLANG_CPU_OMP_THREADS_BIND explicitly. "\n'
        '                f"For example, on a machine with 2 numa nodes, where core 0-31 are on numa node 0 and core 32-63 are on numa node 1, "\n'
        '                f"it is suggested to use -tp 2 and bind tp rank 0 to core 0-31 and tp rank 1 to core 32-63. "\n'
        '                f"This is the default behavior if SGLANG_CPU_OMP_THREADS_BIND is not set and it is the same as setting SGLANG_CPU_OMP_THREADS_BIND=0-31|32-63. "\n'
        '                f"If you do need tp_size to be larger than the number of numa nodes, you could set SGLANG_CPU_OMP_THREADS_BIND explicitly for example SGLANG_CPU_OMP_THREADS_BIND=0-15|16-31|32-47|48-63 and run with -tp 4. "\n'
        '                f"If you don\'t want each tp rank to use all the cores on one numa node, you could set for example SGLANG_CPU_OMP_THREADS_BIND=0-15|32-47 and run with -tp 2."\n'
        "            )\n"
        "            if self.tp_size < n_numa_node:\n"
        "                logger.warning(\n"
        '                    f"Detected the current machine has {n_numa_node} numa nodes available, but tp_size is set to {self.tp_size}, so only {self.tp_size} numa nodes are used."\n'
        "                )\n"
        "            self.local_omp_cpuid = cpu_ids_by_node[self.tp_rank]\n"
        "        else:\n"
        '            threads_bind_list = omp_cpuids.split("|")\n'
        "            assert self.tp_size == len(threads_bind_list), (\n"
        '                f"SGLANG_CPU_OMP_THREADS_BIND setting must be aligned with TP size parameter ({self.tp_size}). "\n'
        '                f"Please double check your settings."\n'
        "            )\n"
        "            self.local_omp_cpuid = threads_bind_list[self.tp_rank]\n"
        "            if self.tp_size > n_numa_node:\n"
        "                logger.warning(\n"
        '                    f"TP size ({self.tp_size})is larger than numa node number ({n_numa_node}), "\n'
        '                    f"in this case the available memory amount of each rank cannot be determined in prior. "\n'
        '                    f"Please set proper `--max-total-tokens` to avoid the out-of-memory error."\n'
        "                )\n\n"
    )
    assert old_method in text, "init_threads_binding method not found"
    text = text.replace(old_method, "")

    # Update the caller in initialize() to call the free function directly.
    text = text.replace(
        '        # Init OpenMP threads binding for CPU\n'
        '        if self.device == "cpu":\n'
        "            self.init_threads_binding()",
        '        # Init OpenMP threads binding for CPU\n'
        '        if self.device == "cpu":\n'
        "            self.local_omp_cpuid = init_threads_binding(\n"
        "                tp_rank=self.tp_rank, tp_size=self.tp_size\n"
        "            )",
    )

    # Remove `get_cpu_ids_by_node,\n` from the model_runner imports — no longer used.
    text = text.replace("    get_cpu_ids_by_node,\n", "")

    # Add `from sglang.srt.utils.numa_utils import init_threads_binding` import
    # (alphabetical position right after sglang.srt.utils.network).
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
