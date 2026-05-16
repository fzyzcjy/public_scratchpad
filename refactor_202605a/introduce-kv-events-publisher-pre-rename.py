#!/usr/bin/env python3
"""Pre-rename for ``introduce-kv-events-publisher``: drop the leading ``_``
on the affected methods so they expose a public API matching the sister
manager forms that arrive in ``-prep`` / ``-move``.

- ``_emit_kv_metrics`` → ``emit_kv_metrics``
- ``_publish_kv_events`` → ``publish_kv_events``

This commit is **rename only** — method bodies are byte-identical. All
callsites (internal mixin calls + external Scheduler / on_idle call) are
updated in the same commit so the tree stays runnable.
"""

# /// script
# requires-python = ">=3.10"
# dependencies = ["typer"]
# ///

import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from _helpers import replace_call_site  # noqa: F401  (kept for parity)
from _runner import run_pr

ID = "introduce-kv-events-publisher-pre-rename"
SUBJECT = "Make emit_kv_metrics and publish_kv_events public"
BODY = """\
Privacy flip pre-rename for the ``introduce-kv-events-publisher`` mech
move. ``SchedulerMetricsMixin`` methods are made public ahead of the
sister split because the sister API they will expose is public.

- ``_emit_kv_metrics`` → ``emit_kv_metrics``
- ``_publish_kv_events`` → ``publish_kv_events``

Body byte-identical. Callsites updated in the mixin
(``report_prefill_stats`` / ``report_decode_stats``) and in
``scheduler.py`` ``on_idle`` (moved here in the on-idle move commit).
"""
AREA = "mech_scheduler"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


def transform(wt: Path) -> None:
    src = wt / "python/sglang/srt/observability/scheduler_metrics_mixin.py"
    sched = wt / "python/sglang/srt/managers/scheduler.py"

    # Mixin: definition + internal callsites.
    text = src.read_text()
    text = text.replace(
        "    def _emit_kv_metrics(self: Scheduler):",
        "    def emit_kv_metrics(self: Scheduler):",
    )
    text = text.replace(
        "    def _publish_kv_events(self: Scheduler):",
        "    def publish_kv_events(self: Scheduler):",
    )
    text = text.replace(
        "            self._emit_kv_metrics()\n",
        "            self.emit_kv_metrics()\n",
    )
    text = text.replace(
        "        self._publish_kv_events()\n",
        "        self.publish_kv_events()\n",
    )
    src.write_text(text)

    # Scheduler.on_idle (moved here in C8) calls self._publish_kv_events().
    text = sched.read_text()
    text = text.replace(
        "        self._publish_kv_events()\n",
        "        self.publish_kv_events()\n",
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
