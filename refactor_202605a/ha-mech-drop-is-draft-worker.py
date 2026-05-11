#!/usr/bin/env python3
"""Drop the ``is_draft_worker: bool`` kwarg from
``configs.hybrid_arch.mamba2_config`` / ``mambaish_config``.

The same bit is reachable via ``model_config.is_draft_model`` (already a
field on ``ModelConfig``); the kwarg was redundant. Dropping it tightens
both signatures and removes the ``is_draft_worker=...`` boilerplate at
~7 caller sites.

Body change (mamba2_config only): ``is_draft_worker`` →
``model_config.is_draft_model`` (one usage in the NemotronH branch).
``mambaish_config`` only forwarded the kwarg into mamba2_config; that
forward goes away.

Caller sites use a regex to drop the ``, is_draft_worker=<expr>``
sub-token from every ``mamba2_config(...)`` / ``mambaish_config(...)``
call across the codebase.

Usage:
    uv run --python 3.12 ha-mech-drop-is-draft-worker.py run
    uv run --python 3.12 ha-mech-drop-is-draft-worker.py verify
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
from _runner import run_pr

ID = "ha-mech-drop-is-draft-worker"
SUBJECT = "Drop is_draft_worker kwarg from hybrid_arch helpers"
BODY = ""
AREA = "mech_model_runner"
BASE = "tom_refactor_202605a/primary/mech_model_runner/kw-mech-rename"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


# Files known to have ``mamba2_config(...)`` / ``mambaish_config(...)`` calls
# with the kwarg — including the def file itself (needs signature edits).
_FILES_TO_PATCH = [
    "python/sglang/srt/configs/hybrid_arch.py",
    "python/sglang/srt/layers/attention/attention_registry.py",
    "python/sglang/srt/layers/attention/hybrid_linear_attn_backend.py",
    "python/sglang/srt/managers/scheduler.py",
    "python/sglang/srt/model_executor/pool_configurator.py",
    "python/sglang/srt/model_executor/model_runner_kv_cache_mixin.py",
    "python/sglang/srt/speculative/eagle_worker.py",
    "python/sglang/srt/speculative/eagle_worker_v2.py",
    "python/sglang/srt/speculative/frozen_kv_mtp_worker.py",
]


def _drop_call_kwarg(text: str) -> str:
    """Inside every ``mamba2_config(...)`` / ``mambaish_config(...)`` call
    body, drop the ``, is_draft_worker=<expr>`` substring (handles both
    inline and black-wrapped multi-line forms)."""
    def repl(m: "re.Match") -> str:
        return re.sub(
            r",\s*is_draft_worker=[a-zA-Z0-9_.\[\]]+\s*",
            "",
            m.group(0),
        )

    return re.sub(
        r"\bmam(?:ba2|baish)_config\([^()]*\)",
        repl,
        text,
        flags=re.DOTALL,
    )


def transform(wt: Path) -> None:
    # 1) Patch hybrid_arch.py — drop signature kwarg + body usage.
    ha = wt / "python/sglang/srt/configs/hybrid_arch.py"
    text = ha.read_text()
    # Drop ``    *,\n    is_draft_worker: bool,\n`` from both defs.
    text = text.replace(
        "    *,\n    is_draft_worker: bool,\n",
        "",
    )
    # Body: replace ``is_draft_worker`` token with ``model_config.is_draft_model``.
    text = text.replace(
        "if isinstance(config, NemotronHConfig) and is_draft_worker:",
        "if isinstance(config, NemotronHConfig) and model_config.is_draft_model:",
    )
    # mambaish_config no longer needs the forward — handled by the generic
    # caller-side regex below.
    text = _drop_call_kwarg(text)
    ha.write_text(text)

    # 2) Drop the kwarg at every other caller.
    for relpath in _FILES_TO_PATCH:
        if relpath == "python/sglang/srt/configs/hybrid_arch.py":
            continue
        path = wt / relpath
        # File may not exist on the current chain (e.g. the mixin file was
        # deleted by ``kvc-drop-mixin-inheritance``). Skip silently in that
        # case — there can be no callers to rewrite if the file is gone.
        if not path.exists():
            continue
        path.write_text(_drop_call_kwarg(path.read_text()))


if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        area_branch=AREA_BRANCH,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
