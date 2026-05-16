#!/usr/bin/env python3
"""Mech move: relocate module-level free items out of ``scheduler.py``.

The items are byte-identical-relocated; no rename, no signature change.

| # | Item | Target |
|---|---|---|
| 1 | ``EmbeddingBatchResult`` | ``managers/utils.py`` (next to ``GenerationBatchResult``) |
| 2 | ``validate_dflash_request`` | ``speculative/dflash_utils.py`` |
| 3 | ``create_scheduler_watchdog`` | ``scheduler_components/invariant_checker.py`` |
| 4 | ``IdleSleeper`` | ``scheduler_components/idle_sleeper.py`` (new) |
| 5 | ``is_health_check_generate_req`` | ``managers/utils.py`` (fixes ``tokenizer_manager`` reverse-import) |
| 6 | ``SenderWrapper`` | ``scheduler_components/output_sender.py`` (new) |

Body bytes preserved; only imports rewritten. Follow-up commit
(``cleanup-scheduler-py-free-items``) deletes dead-code
``is_work_request``.
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
    ensure_imports,
    find_class_lines,
    find_function_lines,
    replace_call_site,
)
from _runner import run_pr

ID = "move-free-items-from-scheduler-py"
SUBJECT = "Move module-level helpers out of scheduler.py"
BODY = """\
Pure mechanical relocation of module-level free items out of
``scheduler.py``. Each item is byte-identical-relocated; no rename, no
signature change.

| Item | Target |
|---|---|
| ``EmbeddingBatchResult`` | ``managers/utils.py`` (alongside ``GenerationBatchResult``) |
| ``validate_dflash_request`` | ``speculative/dflash_utils.py`` |
| ``create_scheduler_watchdog`` | ``scheduler_components/invariant_checker.py`` |
| ``IdleSleeper`` | ``scheduler_components/idle_sleeper.py`` (new file) |
| ``is_health_check_generate_req`` | ``managers/utils.py`` (fixes reverse-import from ``tokenizer_manager``) |
| ``SenderWrapper`` | ``scheduler_components/output_sender.py`` (new file) |

Caller-site impact: only import-path rewrites.

A follow-up commit (``cleanup-scheduler-py-free-items``) deletes the
dead-code ``is_work_request`` function (zero callers codebase-wide).
"""
AREA = "mech_scheduler"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


def _move_embedding_batch_result(wt: Path) -> None:
    sched = wt / "python/sglang/srt/managers/scheduler.py"
    utils = wt / "python/sglang/srt/managers/utils.py"
    batch_result_processor = wt / "python/sglang/srt/managers/scheduler_components/batch_result_processor.py"
    metrics_reporter = wt / "python/sglang/srt/managers/scheduler_components/metrics_reporter.py"

    s, e = find_class_lines(sched.read_text(), class_name="EmbeddingBatchResult")
    block = cut_lines(sched, s, e)
    append_to_file(utils, block, separator="\n\n")

    # utils.py uses ``import dataclasses`` / ``@dataclasses.dataclass``;
    # the moved class uses bare ``@dataclass``. Add a from-import to support
    # the existing decorator without altering the class body.
    utils_text = utils.read_text()
    utils_text = replace_call_site(
        utils_text,
        old="import dataclasses\n",
        new="import dataclasses\nfrom dataclasses import dataclass\n",
    )
    utils.write_text(utils_text)

    # scheduler.py: extend the existing utils import.
    sched_text = sched.read_text()
    sched_text = replace_call_site(
        sched_text,
        old="from sglang.srt.managers.utils import GenerationBatchResult, validate_input_length\n",
        new=(
            "from sglang.srt.managers.utils import (\n"
            "    EmbeddingBatchResult,\n"
            "    GenerationBatchResult,\n"
            "    validate_input_length,\n"
            ")\n"
        ),
    )
    sched.write_text(sched_text)

    # batch_result_processor.py: ensure the TYPE_CHECKING block imports the
    # 2 result classes from utils.
    text = batch_result_processor.read_text()
    text = ensure_imports(
        text,
        type_checking={
            "sglang.srt.managers.utils": (
                "EmbeddingBatchResult",
                "GenerationBatchResult",
            ),
        },
    )
    batch_result_processor.write_text(text)

    # metrics_reporter.py: keep Scheduler from scheduler, switch
    # EmbeddingBatchResult source to utils.
    text = metrics_reporter.read_text()
    text = ensure_imports(
        text,
        type_checking={
            "sglang.srt.managers.scheduler": "Scheduler",
            "sglang.srt.managers.utils": "EmbeddingBatchResult",
        },
    )
    metrics_reporter.write_text(text)


def _move_validate_dflash_request(wt: Path) -> None:
    sched = wt / "python/sglang/srt/managers/scheduler.py"
    dflash_utils = wt / "python/sglang/srt/speculative/dflash_utils.py"

    s, e = find_function_lines(sched.read_text(), function_name="validate_dflash_request")
    block = cut_lines(sched, s, e)
    append_to_file(dflash_utils, block, separator="\n\n")

    # dflash_utils.py: add the Req import it now needs.
    text = dflash_utils.read_text()
    text = replace_call_site(
        text,
        old="from sglang.srt.layers.quantization.unquant import UnquantizedLinearMethod\n",
        new=(
            "from sglang.srt.layers.quantization.unquant import UnquantizedLinearMethod\n"
            "from sglang.srt.managers.schedule_batch import Req\n"
        ),
    )
    dflash_utils.write_text(text)

    # scheduler.py: re-import the moved function.
    sched_text = sched.read_text()
    sched_text = replace_call_site(
        sched_text,
        old="from sglang.srt.speculative.spec_info import SpeculativeAlgorithm\n",
        new=(
            "from sglang.srt.speculative.dflash_utils import validate_dflash_request\n"
            "from sglang.srt.speculative.spec_info import SpeculativeAlgorithm\n"
        ),
    )
    sched.write_text(sched_text)


def _move_create_scheduler_watchdog(wt: Path) -> None:
    sched = wt / "python/sglang/srt/managers/scheduler.py"
    invariant_checker = wt / "python/sglang/srt/managers/scheduler_components/invariant_checker.py"

    s, e = find_function_lines(sched.read_text(), function_name="create_scheduler_watchdog")
    block = cut_lines(sched, s, e)
    append_to_file(invariant_checker, block, separator="\n\n")

    # invariant_checker.py: add WatchdogRaw runtime import and Scheduler
    # TYPE_CHECKING import.
    text = invariant_checker.read_text()
    text = ensure_imports(
        text,
        runtime={"sglang.srt.utils.watchdog": "WatchdogRaw"},
        type_checking={"sglang.srt.managers.scheduler": "Scheduler"},
    )
    invariant_checker.write_text(text)

    # scheduler.py: extend existing invariant_checker import to include
    # ``create_scheduler_watchdog``.
    sched_text = sched.read_text()
    sched_text = replace_call_site(
        sched_text,
        old=(
            "from sglang.srt.managers.scheduler_components.invariant_checker import (\n"
            "    SchedulerInvariantChecker,\n"
            ")\n"
        ),
        new=(
            "from sglang.srt.managers.scheduler_components.invariant_checker import (\n"
            "    SchedulerInvariantChecker,\n"
            "    create_scheduler_watchdog,\n"
            ")\n"
        ),
    )
    sched.write_text(sched_text)


IDLE_SLEEPER_CLASS = '''\
@dataclass(kw_only=True, slots=True)
class IdleSleeper:
    """
    In setups which have long inactivity periods it is desirable to reduce
    system power consumption when sglang does nothing. This would lead not only
    to power savings, but also to more CPU thermal headroom when a request
    eventually comes. This is important in cases when multiple GPUs are connected
    as each GPU would otherwise pin one thread at 100% CPU usage.

    The simplest solution is to use zmq.Poller on all sockets that may receive
    data that needs handling immediately.
    """

    sockets: Any
    last_empty_time: float = field(default_factory=real_time)
    poller: Any = None
    empty_cache_interval: int = 0

    def __post_init__(self) -> None:
        self.poller = zmq.Poller()
        for s in self.sockets:
            self.poller.register(s, zmq.POLLIN)

        self.empty_cache_interval = envs.SGLANG_EMPTY_CACHE_INTERVAL.get()

    def maybe_sleep(self):
        self.poller.poll(1000)
        if (
            self.empty_cache_interval > 0
            and real_time() - self.last_empty_time > self.empty_cache_interval
        ):
            self.last_empty_time = real_time()
            empty_device_cache()
'''


def _move_idle_sleeper(wt: Path) -> None:
    sched = wt / "python/sglang/srt/managers/scheduler.py"
    idle_sleeper = wt / "python/sglang/srt/managers/scheduler_components/idle_sleeper.py"

    s, e = find_class_lines(sched.read_text(), class_name="IdleSleeper")
    cut_lines(sched, s, e)

    new_file_text = (
        "from dataclasses import dataclass, field\n"
        "from typing import Any\n\n"
        "import zmq\n\n"
        "from sglang.srt.environ import envs\n"
        "from sglang.srt.observability.req_time_stats import real_time\n"
        "from sglang.srt.utils import empty_device_cache\n\n\n"
    ) + IDLE_SLEEPER_CLASS
    idle_sleeper.write_text(new_file_text)

    # scheduler.py: add IdleSleeper import alongside invariant_checker and
    # rewrite the positional call site to the kw_only form.
    sched_text = sched.read_text()
    sched_text = replace_call_site(
        sched_text,
        old=(
            "from sglang.srt.managers.scheduler_components.invariant_checker import (\n"
            "    SchedulerInvariantChecker,\n"
            "    create_scheduler_watchdog,\n"
            ")\n"
        ),
        new=(
            "from sglang.srt.managers.scheduler_components.idle_sleeper import IdleSleeper\n"
            "from sglang.srt.managers.scheduler_components.invariant_checker import (\n"
            "    SchedulerInvariantChecker,\n"
            "    create_scheduler_watchdog,\n"
            ")\n"
        ),
    )
    sched_text = replace_call_site(
        sched_text,
        old=(
            "                self.idle_sleeper = IdleSleeper(\n"
            "                    [\n"
            "                        self.recv_from_tokenizer,\n"
            "                        self.recv_from_rpc,\n"
            "                    ]\n"
            "                )\n"
        ),
        new=(
            "                self.idle_sleeper = IdleSleeper(\n"
            "                    sockets=[\n"
            "                        self.recv_from_tokenizer,\n"
            "                        self.recv_from_rpc,\n"
            "                    ],\n"
            "                )\n"
        ),
    )
    sched.write_text(sched_text)


def _move_is_health_check(wt: Path) -> None:
    sched = wt / "python/sglang/srt/managers/scheduler.py"
    utils = wt / "python/sglang/srt/managers/utils.py"
    tokenizer_manager = wt / "python/sglang/srt/managers/tokenizer_manager.py"

    s, e = find_function_lines(sched.read_text(), function_name="is_health_check_generate_req")
    block = cut_lines(sched, s, e)
    append_to_file(utils, block, separator="\n\n")

    # utils.py: add HEALTH_CHECK_RID_PREFIX import (function body uses it).
    utils_text = utils.read_text()
    utils_text = replace_call_site(
        utils_text,
        old="from sglang.srt.eplb.expert_distribution import ExpertDistributionMetrics\n",
        new=(
            "from sglang.srt.constants import HEALTH_CHECK_RID_PREFIX\n"
            "from sglang.srt.eplb.expert_distribution import ExpertDistributionMetrics\n"
        ),
    )
    utils.write_text(utils_text)

    # scheduler.py: pull is_health_check_generate_req from utils alongside
    # the other utils symbols.
    sched_text = sched.read_text()
    sched_text = replace_call_site(
        sched_text,
        old=(
            "from sglang.srt.managers.utils import (\n"
            "    EmbeddingBatchResult,\n"
            "    GenerationBatchResult,\n"
            "    validate_input_length,\n"
            ")\n"
        ),
        new=(
            "from sglang.srt.managers.utils import (\n"
            "    EmbeddingBatchResult,\n"
            "    GenerationBatchResult,\n"
            "    is_health_check_generate_req,\n"
            "    validate_input_length,\n"
            ")\n"
        ),
    )
    sched.write_text(sched_text)

    # tokenizer_manager.py: fix the reverse-import (was importing from
    # scheduler — now sources from utils).
    tm_text = tokenizer_manager.read_text()
    tm_text = replace_call_site(
        tm_text,
        old="from sglang.srt.managers.scheduler import is_health_check_generate_req\n",
        new="from sglang.srt.managers.utils import is_health_check_generate_req\n",
    )
    tokenizer_manager.write_text(tm_text)


def _move_sender_wrapper(wt: Path) -> None:
    sched = wt / "python/sglang/srt/managers/scheduler.py"
    output_sender = wt / "python/sglang/srt/managers/scheduler_components/output_sender.py"

    s, e = find_class_lines(sched.read_text(), class_name="SenderWrapper")
    block = cut_lines(sched, s, e)

    new_file_text = (
        "from typing import Optional, Union\n\n"
        "import zmq\n\n"
        "from sglang.srt.managers.io_struct import BaseBatchReq, BaseReq\n\n\n"
    ) + block
    output_sender.write_text(new_file_text)

    # scheduler.py: add SenderWrapper import alongside output_streamer.
    sched_text = sched.read_text()
    sched_text = replace_call_site(
        sched_text,
        old="from sglang.srt.managers.scheduler_components.idle_sleeper import IdleSleeper\n",
        new=(
            "from sglang.srt.managers.scheduler_components.idle_sleeper import IdleSleeper\n"
            "from sglang.srt.managers.scheduler_components.output_sender import SenderWrapper\n"
        ),
    )
    sched.write_text(sched_text)


def transform(wt: Path) -> None:
    _move_embedding_batch_result(wt)
    _move_validate_dflash_request(wt)
    _move_create_scheduler_watchdog(wt)
    _move_idle_sleeper(wt)
    _move_is_health_check(wt)
    _move_sender_wrapper(wt)


if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        area_branch=AREA_BRANCH,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
