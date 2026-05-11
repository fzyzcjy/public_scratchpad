#!/usr/bin/env python3
"""Pre-rename for ``migrate-profiler-mixin``: add the leading ``_`` on 4
mixin methods so they become private inside the upcoming
``SchedulerProfilerManager``:

- ``init_profile``  → ``_init_profile``
- ``start_profile`` → ``_start_profile``
- ``stop_profile``  → ``_stop_profile``
- ``profile``       → ``_profile``

This commit is **rename only** — method bodies are byte-identical. All
internal cross-method callsites (within the mixin) are updated in the same
commit so the tree stays runnable.
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

ID = "migrate-profiler-mixin-pre-rename"
SUBJECT = "Add leading _ on init_profile/start_profile/stop_profile/profile (pre-rename for profiler-mixin)"
BODY = """\
Privacy flip pre-rename for the ``migrate-profiler-mixin`` mech move.
Four ``SchedulerProfilerMixin`` methods are made private because their
post-move home (``SchedulerProfilerManager``) treats them as ``_*``
helpers; the lifecycle is driven by the manager's owner via composition.

- ``init_profile``  → ``_init_profile``
- ``start_profile`` → ``_start_profile``
- ``stop_profile``  → ``_stop_profile``
- ``profile``       → ``_profile``

Body byte-identical. Internal cross-method callsites within the mixin
body updated to the renamed forms.
"""
AREA = "mech_scheduler"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


def transform(wt: Path) -> None:
    mixin = wt / "python/sglang/srt/managers/scheduler_profiler_mixin.py"
    test_profile = wt / "test/registered/unit/utils/test_profile_merger.py"

    text = mixin.read_text()

    # Method definitions: rename only.
    text = text.replace("    def init_profile(\n", "    def _init_profile(\n")
    text = text.replace("    def start_profile(\n", "    def _start_profile(\n")
    text = text.replace("    def stop_profile(\n", "    def _stop_profile(\n")
    text = text.replace(
        "    def profile(self: Scheduler, recv_req: ProfileReq):",
        "    def _profile(self: Scheduler, recv_req: ProfileReq):",
    )

    # Internal cross-method calls — rewrite to the renamed forms.
    text = text.replace("self.init_profile(", "self._init_profile(")
    text = text.replace("self.start_profile(", "self._start_profile(")
    text = text.replace("self.stop_profile(", "self._stop_profile(")

    mixin.write_text(text)

    # Test fixture: switch the ``init_profile`` reference to ``_init_profile``.
    test_text = test_profile.read_text()
    test_text = test_text.replace(
        "sig = inspect.signature(SchedulerProfilerMixin.init_profile)",
        "sig = inspect.signature(SchedulerProfilerMixin._init_profile)",
    )
    test_profile.write_text(test_text)


if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        area_branch=AREA_BRANCH,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
