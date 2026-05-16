#!/usr/bin/env python3
"""Pre-declare mode-conditional Scheduler fields with ``None`` defaults so
they always exist on the instance, regardless of disaggregation / mm /
mlx mode. Subsequent ``init_disaggregation`` / ``init_mm`` /
``init_overlap`` paths overwrite when applicable.

Establishes the "field always exists" invariant **before** the sister-
introducing prep commits (C4 onwards) run, so each sister ctor / Callable
getter can read ``self.X`` directly without
``getattr(self, "X", DEFAULT)`` defenses (which violate
``coding-style.md``).

Per ``MECH_COMMIT_SPLIT.md`` "trivial single-commit mech" exception (row 3
of the exception table): trivial ``getattr`` → direct attribute access
prep, single commit, no prep+move split.
"""

# /// script
# requires-python = ">=3.10"
# dependencies = ["typer"]
# ///

import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from _helpers import replace_call_site
from _runner import run_pr

ID = "init-mode-conditional-defaults"
SUBJECT = "Pre-declare mode-conditional Scheduler fields with None defaults"
BODY = """\
Pre-declare six mode-conditional Scheduler fields with ``None`` /
``False`` defaults at the top of ``Scheduler.__init__``:

- ``self.mm_receiver`` — populated by ``init_disaggregation`` under mm mode
- ``self.disagg_prefill_bootstrap_queue`` — populated under disagg-prefill mode
- ``self.disagg_prefill_inflight_queue`` — populated under disagg-prefill mode
- ``self.disagg_decode_prealloc_queue`` — populated under disagg-decode mode
- ``self.disagg_decode_transfer_queue`` — populated under disagg-decode mode
- ``self.enable_overlap_mlx`` — re-assigned unconditionally just below; the
  pre-init is harmless (overwritten on the very next line) but kept for
  symmetry with the disagg / mm fields so the upcoming sister-introducing
  commits can write ``self.enable_overlap_mlx`` everywhere without a
  ``getattr`` fallback.

These fields are read eagerly by sister-component ctors that the next
mech commits (C4 ``introduce-scheduler-request-receiver-prep`` onwards)
will introduce. Without this pre-init, those eager reads would either
need ``getattr(self, "X", DEFAULT)`` defenses (violates
``coding-style.md``) or only-work-in-mode-X conditional logic. With this
pre-init, every read site can use plain ``self.X``.

Single commit, single logical change: establish "field always exists"
invariant. Follows ``MECH_COMMIT_SPLIT.md`` "trivial ``getattr`` → direct
attr access" single-commit exception.
"""
AREA = "mech_scheduler"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


# Inserted immediately after ``self.init_ipc_channels(port_args)\n`` — a
# stable anchor that exists in scheduler.py at this chain position and is
# unaffected by upstream C14 metrics-reporter-prep (which only replaces
# ``self.init_metrics(...)`` higher up). The location is well before
# ``init_disaggregation`` / ``init_mm`` / ``init_overlap``, so subsequent
# mode-specific population paths still overwrite the defaults.
DEFAULTS_BLOCK = """\

        self.mm_receiver = None
        self.disagg_prefill_bootstrap_queue = None
        self.disagg_prefill_inflight_queue = None
        self.disagg_decode_prealloc_queue = None
        self.disagg_decode_transfer_queue = None
        self.enable_overlap_mlx = False
"""


def transform(wt: Path) -> None:
    sched = wt / "python/sglang/srt/managers/scheduler.py"
    text = sched.read_text()
    text = replace_call_site(
        text,
        old="        self.init_ipc_channels(port_args)\n",
        new="        self.init_ipc_channels(port_args)\n" + DEFAULTS_BLOCK,
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
