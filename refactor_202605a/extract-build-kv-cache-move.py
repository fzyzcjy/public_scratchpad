#!/usr/bin/env python3
"""Mechanical move for ``extract-build-kv-cache``: cut the @staticmethod
``build_kv_cache`` from Scheduler, append to
``mem_cache/kv_cache_builder.py``. Drop ``@staticmethod``, dedent 4
spaces, rewrite sole caller's ``Scheduler.build_kv_cache(`` → ``kv_cache_builder.build_kv_cache(``.

Body bytes byte-equivalent with prep modulo dedent + decorator removal.
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
    ensure_imports,
    find_method_lines,
    replace_call_site,
)
from _runner import run_pr

ID = "extract-build-kv-cache-move"
SUBJECT = "Move build_kv_cache to mem_cache.kv_cache_builder"
BODY = """\
Mechanical cut + paste for the ``extract-build-kv-cache`` mech move.

Cut ``Scheduler.build_kv_cache`` (@staticmethod after the prep commit)
and append to ``mem_cache/kv_cache_builder.py``. Drop ``@staticmethod``
decorator; dedent body to module level. Body bytes byte-equivalent.

Sole caller in ``Scheduler.__init__`` updated from
``Scheduler.build_kv_cache(...)`` → ``kv_cache_builder.build_kv_cache(...)``
(pure prefix replacement).
"""
AREA = "mech_scheduler"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


def transform(wt: Path) -> None:
    sched = wt / "python/sglang/srt/managers/scheduler.py"
    kvc = wt / "python/sglang/srt/mem_cache/kv_cache_builder.py"

    # Cut @staticmethod from Scheduler.
    s, e = find_method_lines(
        sched.read_text(),
        class_name="Scheduler",
        method_name="build_kv_cache",
    )
    method_text = cut_lines(sched, s, e)

    function_text = method_text.replace("    @staticmethod\n", "", 1)
    function_text = dedent_method_to_function(function_text)

    append_to_file(kvc, function_text)

    # Re-inject imports the function body needs (prep wrote these; ruff F401
    # stripped them while the body wasn't yet present).
    kvc_text = kvc.read_text()
    kvc_text = ensure_imports(
        kvc_text,
        runtime={
            "typing": "Optional",
            "sglang.srt.configs.model_config": "ModelImpl",
            "sglang.srt.environ": "envs",
            "sglang.srt.managers.mm_utils": "init_mm_embedding_cache",
            "sglang.srt.mem_cache.cache_init_params": "CacheInitParams",
            "sglang.srt.mem_cache.radix_cache": "RadixCache",
            "sglang.srt.model_loader.utils": "get_resolved_model_impl",
            "sglang.srt.session.streaming_session": "StreamingSession",
        },
        type_checking={
            "sglang.srt.configs.model_config": "ModelConfig",
            "sglang.srt.distributed.parallel_state": "GroupCoordinator",
            "sglang.srt.distributed.parallel_state_wrapper": "ParallelState",
            "sglang.srt.mem_cache.base_prefix_cache": "BasePrefixCache",
            "torch.distributed": "ProcessGroup",
        },
    )
    kvc.write_text(kvc_text)

    # Pure prefix replace for the caller.
    text = sched.read_text()
    text = replace_call_site(
        text,
        old="Scheduler.build_kv_cache(",
        new="kv_cache_builder.build_kv_cache(",
    )
    sched.write_text(text)


if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        area_branch=AREA_BRANCH,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
