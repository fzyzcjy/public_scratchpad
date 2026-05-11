#!/usr/bin/env python3
"""Move pool_configurator.py from model_executor/ into the new
model_runner_components/ subdir. Create the subdir with an empty __init__.py.

Updates all cross-codebase imports to use the new path. The Python file at the
old location is removed.

This script must run BEFORE any other chain step that touches
pool_configurator (extract-hybrid-arch-props, drop-hybrid-arch-delegates,
introduce-rwt-skeleton, kvc-introduce-skeleton) — place it at the head of
the ORDER list in `_build_mech_model_runner.py`.

Usage:
    uv run --python 3.12 move-pool-configurator.py run
    uv run --python 3.12 move-pool-configurator.py verify
"""

# /// script
# requires-python = ">=3.10"
# dependencies = ["typer"]
# ///

import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from _runner import run_pr

ID = "move-pool-configurator"
SUBJECT = "Move pool_configurator into new model_runner_components/ subdir"
BODY = ""
AREA = "mech_model_runner"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


# Files that import from the old location at preflight time.
# kv_cache_configurator mixin has a function-local import inside
# ``_resolve_memory_pool_config``; it gets cut+pasted into the dataclass
# during kvc-migrate-configure, so rewriting it here in the mixin source
# is what gets the new path into the dataclass body.
_IMPORTERS = [
    "python/sglang/srt/managers/tp_worker.py",
    "python/sglang/srt/model_executor/model_runner.py",
    "python/sglang/srt/model_executor/model_runner_kv_cache_mixin.py",
    "python/sglang/srt/speculative/frozen_kv_mtp_worker.py",
    "test/registered/unit/model_executor/test_pool_configurator.py",
]


def transform(wt: Path) -> None:
    old = wt / "python/sglang/srt/model_executor/pool_configurator.py"
    new_dir = wt / "python/sglang/srt/model_executor/model_runner_components"
    new = new_dir / "pool_configurator.py"

    # 1) Move the file. Keep contents byte-for-byte; this is a pure path move.
    new_dir.mkdir(parents=True, exist_ok=True)
    (new_dir / "__init__.py").write_text("")
    new.write_text(old.read_text())
    old.unlink()

    # 2) Rewrite imports in the rest of the codebase.
    for rel in _IMPORTERS:
        f = wt / rel
        text = f.read_text()
        text = text.replace(
            "from sglang.srt.model_executor.pool_configurator",
            "from sglang.srt.model_executor.model_runner_components.pool_configurator",
        )
        f.write_text(text)


if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        area_branch=AREA_BRANCH,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
