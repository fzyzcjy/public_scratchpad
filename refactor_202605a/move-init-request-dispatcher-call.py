#!/usr/bin/env python3
"""Move the ``self.init_request_dispatcher()`` call timing earlier in
``TokenizerManager.__init__`` — from the end of __init__ to right after
``self.init_metric_collector_watchdog()``.

Body of ``init_request_dispatcher`` is completely unchanged. Just an
up-down move of the call site. Subsequent owner-class commits register
their handlers via __post_init__ which overwrites the existing dispatcher
entries; each owner-class prep also drops its own entry from
``init_request_dispatcher`` body when its method is about to move out.

This restructure is needed so that subsequent Stage-4 controllers
(SessionController / PauseController / WeightDiskUpdateController /
LoraController / CorpusController) can take ``dispatcher=self._result_dispatcher``
as a composition kwarg.
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

ID = "move-init-request-dispatcher-call"
SUBJECT = "Move init_request_dispatcher() call earlier in TokenizerManager.__init__"
BODY = """\
Pure call-site move: ``self.init_request_dispatcher()`` runs immediately
after ``self.init_metric_collector_watchdog()`` instead of at the end of
``__init__``. ``init_request_dispatcher`` body unchanged.

This lets subsequent owner-class composition wiring pass
``dispatcher=self._result_dispatcher`` as a ctor kwarg.
"""
AREA = "mech_tokenizer_manager"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


def transform(wt: Path) -> None:
    tm = wt / "python/sglang/srt/managers/tokenizer_manager.py"
    text = tm.read_text()

    # Remove the late call (currently at the end of __init__).
    text = replace_call_site(
        text,
        old="        # Init request dispatcher\n        self.init_request_dispatcher()\n",
        new="",
    )

    # Insert the call earlier, right after init_metric_collector_watchdog().
    text = replace_call_site(
        text,
        old="        self.init_metric_collector_watchdog()\n",
        new=(
            "        self.init_metric_collector_watchdog()\n"
            "\n"
            "        # Init request dispatcher (called early so owner-class ctors can\n"
            "        # pass dispatcher=self._result_dispatcher as a kwarg).\n"
            "        self.init_request_dispatcher()\n"
        ),
    )

    tm.write_text(text)


if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        area_branch=AREA_BRANCH,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
