#!/usr/bin/env python3
"""Inplace prep for ``introduce-output-streamer``: create empty
``SchedulerOutputStreamer`` class skeleton, instantiate on Scheduler,
convert 6 stream methods on ``SchedulerOutputProcessorMixin`` to
``@staticmethod`` with ``self: "SchedulerOutputStreamer"`` type annotation,
rewrite callers, apply 3 privacy flips, and wire the receiver shim
+ Callable lambda passthroughs.

PRAGMATIC DEVIATION: The Callable lambda passthroughs
(``enable_hicache_storage=lambda: self.enable_hicache_storage`` and
``load_inquirer_get_loads=lambda req: self.load_inquirer.get_loads(...)``)
and the corresponding body substitutions (``self.enable_hicache_storage``
→ ``self.enable_hicache_storage()`` and the regex-based
``load_inquirer.get_loads(...)`` collapse) are strictly fancy reshape per
``MECH_COMMIT_SPLIT.md``. We place them here in prep to keep the chain
buildable and the moved bodies byte-identical for the upcoming -move step.
Documented inline below and in this commit body.
"""

# /// script
# requires-python = ">=3.10"
# dependencies = ["typer"]
# ///

import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from _helpers import find_method_lines, insert_after, replace_call_site
from _runner import run_pr

ID = "introduce-output-streamer-prep"
SUBJECT = "Stand up SchedulerOutputStreamer; migrate output-streaming state to it"
BODY = """\
Inplace prep for the ``introduce-output-streamer`` mech move.

- Create ``scheduler_components/output_streamer.py`` with an empty
  ``SchedulerOutputStreamer`` class (ctor takes the collaborators
  ``send_to_detokenizer`` + ``tree_cache``, configs ``ps`` /
  ``server_args`` / ``is_generation`` / ``stream_interval`` /
  ``spec_algorithm`` / ``disaggregation_mode``, and Callables
  ``enable_hicache_storage`` + ``load_inquirer_get_loads``).
- Instantiate ``self.output_streamer = SchedulerOutputStreamer(...)`` in
  ``Scheduler.__init__`` immediately after the ``logprob_computer`` ctor.
- In ``SchedulerOutputProcessorMixin``, convert the stream methods
  (``_get_storage_backend_type``, ``_get_cached_tokens_details``,
  ``stream_output``, ``_trigger_crash_for_tests``,
  ``stream_output_generation``, ``stream_output_embedding``) to
  ``@staticmethod`` with ``self: "SchedulerOutputStreamer"`` type
  annotation. Drop ``: Scheduler`` annotation.
- Body substitutions:
  - ``self.enable_hicache_storage`` (read-as-bool) →
    ``self.enable_hicache_storage()`` (now Callable getter on streamer).
  - ``self.load_inquirer.get_loads(...)`` multi-kwarg call → single-arg
    ``self.load_inquirer_get_loads(GetLoadsReqInput(include=["core"]))``
    (kwargs wrapped by the lambda passed in Scheduler init insert).
- Privacy flips: ``_get_cached_tokens_details`` →
  ``get_cached_tokens_details``, ``stream_output_generation`` →
  ``_stream_output_generation``, ``stream_output_embedding`` →
  ``_stream_output_embedding``. Definitions + intra-mixin callsites.
- Cross-commit fix: rewire receiver shim
  ``stream_output=self.stream_output`` →
  ``stream_output=lambda *a, **kw: self.output_streamer.stream_output(*a, **kw)``
  (the receiver class itself unchanged; receiver ctor runs earlier in
  ``__init__`` so we need a lazy lambda).
- Callsites updated: the remaining output_processor mixin body
  (``self.stream_output`` calls + ``self._get_cached_tokens_details``),
  the Scheduler hot-path (``self.stream_output(``), and external
  callers (``disaggregation/prefill.py``, ``dllm/mixin/scheduler.py``).

PRAGMATIC DEVIATION (per ``MECH_COMMIT_SPLIT.md``): the Callable lambda
ctor kwargs + their body substitutions are strictly fancy reshape and
should live in a follow-up nonmech commit. We bundle them into this prep
to keep the chain buildable while the bodies stay verbatim across the
``-move`` step.

The converted methods stay inside the mixin in this commit; physical
cut + paste to ``SchedulerOutputStreamer`` body happens in
``introduce-output-streamer-move``.
"""
AREA = "mech_scheduler"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


TARGET_FILE_HEADER = '''\
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

import torch
import zmq

from sglang.srt.disaggregation.utils import DisaggregationMode
from sglang.srt.distributed.parallel_state_wrapper import ParallelState
from sglang.srt.environ import envs
from sglang.srt.managers.io_struct import (
    BatchEmbeddingOutput,
    BatchTokenIDOutput,
    GetLoadsReqInput,
    GetLoadsReqOutput,
)
from sglang.srt.managers.schedule_batch import BaseFinishReason, Req
from sglang.srt.mem_cache.base_prefix_cache import BasePrefixCache
from sglang.srt.server_args import ServerArgs
from sglang.srt.speculative.spec_info import SpeculativeAlgorithm


logger = logging.getLogger(__name__)


DEFAULT_FORCE_STREAM_INTERVAL = envs.SGLANG_FORCE_STREAM_INTERVAL.get()


@dataclass(kw_only=True, slots=True)
class SchedulerOutputStreamer:
    send_to_detokenizer: zmq.Socket
    tree_cache: BasePrefixCache
    ps: ParallelState
    server_args: ServerArgs
    is_generation: bool
    spec_algorithm: SpeculativeAlgorithm
    disaggregation_mode: DisaggregationMode
    enable_hicache_storage: Callable[[], bool]
    load_inquirer_get_loads: Callable[..., Any]
    _test_stream_output_count: int = 0
'''


SCHEDULER_INIT_INSERT = """\
        self.output_streamer = SchedulerOutputStreamer(
            send_to_detokenizer=self.send_to_detokenizer,
            tree_cache=self.tree_cache,
            ps=self.ps,
            server_args=self.server_args,
            is_generation=self.is_generation,
            spec_algorithm=self.spec_algorithm,
            disaggregation_mode=self.disaggregation_mode,
            enable_hicache_storage=lambda: self.enable_hicache_storage,
            load_inquirer_get_loads=lambda req: self.load_inquirer.get_loads(req),
        )

"""


METHODS = [
    "_get_storage_backend_type",
    "_get_cached_tokens_details",
    "stream_output",
    "_trigger_crash_for_tests",
    "stream_output_generation",
    "stream_output_embedding",
]


def transform(wt: Path) -> None:
    sched = wt / "python/sglang/srt/managers/scheduler.py"
    mixin = wt / "python/sglang/srt/managers/scheduler_output_processor_mixin.py"
    target = wt / "python/sglang/srt/managers/scheduler_components/output_streamer.py"

    # 1. Create skeleton target file.
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(TARGET_FILE_HEADER)

    # 2. Convert 6 methods on the mixin to @staticmethod with type-flipped
    #    self: "SchedulerOutputStreamer".
    text = mixin.read_text()

    for name in METHODS:
        s, e = find_method_lines(
            text,
            class_name="SchedulerOutputProcessorMixin",
            method_name=name,
        )
        lines = text.splitlines(keepends=True)
        method_text = "".join(lines[s:e])

        single_line_sig = f"    def {name}(self: Scheduler, "
        single_line_no_args = f"    def {name}(self: Scheduler)"
        multi_line_sig = f"    def {name}(\n        self: Scheduler,"
        bare_self_args = f"    def {name}(self, "
        bare_self_no_args = f"    def {name}(self)"
        bare_self_multi = f"    def {name}(\n        self,"

        if single_line_sig in method_text:
            new_method = method_text.replace(
                single_line_sig,
                f"    @staticmethod\n    def {name}(self: \"SchedulerOutputStreamer\", ",
                1,
            )
        elif single_line_no_args in method_text:
            new_method = method_text.replace(
                single_line_no_args,
                f"    @staticmethod\n    def {name}(self: \"SchedulerOutputStreamer\")",
                1,
            )
        elif multi_line_sig in method_text:
            new_method = method_text.replace(
                multi_line_sig,
                f"    @staticmethod\n    def {name}(\n        self: \"SchedulerOutputStreamer\",",
                1,
            )
        elif bare_self_args in method_text:
            new_method = method_text.replace(
                bare_self_args,
                f"    @staticmethod\n    def {name}(self: \"SchedulerOutputStreamer\", ",
                1,
            )
        elif bare_self_no_args in method_text:
            new_method = method_text.replace(
                bare_self_no_args,
                f"    @staticmethod\n    def {name}(self: \"SchedulerOutputStreamer\")",
                1,
            )
        elif bare_self_multi in method_text:
            new_method = method_text.replace(
                bare_self_multi,
                f"    @staticmethod\n    def {name}(\n        self: \"SchedulerOutputStreamer\",",
                1,
            )
        else:
            raise RuntimeError(
                f"signature shape for {name} unrecognized; sample: {method_text[:200]!r}"
            )

        # Body substitutions confined to this method block (Callable shims).
        # These are placed here in prep so move can keep bodies byte-identical.
        # ``_get_cached_tokens_details`` reads ``self.enable_hicache_storage``
        # as a bool; once the field becomes a Callable getter on the streamer
        # the raw read is always truthy, so it MUST be invoked. The streaming
        # methods share the same substitution.
        if name in (
            "_get_cached_tokens_details",
            "stream_output",
            "stream_output_generation",
            "stream_output_embedding",
        ):
            new_method = new_method.replace(
                "self.enable_hicache_storage", "self.enable_hicache_storage()"
            )
            # ``self.enable_hicache_storage`` may already appear without
            # trailing args; the replace runs once per occurrence — fine.

        # Collapse load_inquirer.get_loads(...) call into single-arg shim.
        # The call appears in `stream_output_generation` (privacy-flipped to
        # `_stream_output_generation` later in prep, but at this point the
        # body's original method name is still in scope).
        if name in ("stream_output", "stream_output_generation"):
            import re as _re_body
            # multi-line form (DOTALL .*? allows nested parens).
            new_method = _re_body.sub(
                r"        load = self\.load_inquirer\.get_loads\(\n.*?\n        \)",
                '        load = self.load_inquirer_get_loads(GetLoadsReqInput(include=["core"]))',
                new_method,
                flags=_re_body.DOTALL,
            )

        text = "".join(lines[:s]) + new_method + "".join(lines[e:])

    # 3. Privacy flips on definitions + intra-mixin internal callsites.
    text = text.replace(
        "    def _get_cached_tokens_details(",
        "    def get_cached_tokens_details(",
    )
    text = text.replace(
        "    def stream_output_generation(",
        "    def _stream_output_generation(",
    )
    text = text.replace(
        "    def stream_output_embedding(",
        "    def _stream_output_embedding(",
    )
    # Intra-mixin internal callsites for the renamed defs.
    text = text.replace(
        "self._get_cached_tokens_details(",
        "self.get_cached_tokens_details(",
    )
    text = text.replace(
        "self.stream_output_generation(",
        "self._stream_output_generation(",
    )
    text = text.replace(
        "self.stream_output_embedding(",
        "self._stream_output_embedding(",
    )

    # 4. Callsite rewrites in the mixin body for the 6 methods that will
    #    move. Form: ``self.<m>(self.output_streamer, ...)``.
    callsite_methods = [
        "stream_output",
        "get_cached_tokens_details",
        "_stream_output_generation",
        "_stream_output_embedding",
    ]
    for m in callsite_methods:
        text = text.replace(
            f"self.{m}(",
            f"self.{m}(self.output_streamer, ",
        )

    # Drop ``stream_interval`` ctor field → read via
    # ``self.server_args.stream_interval``. The single occurrence in this
    # mixin lives inside ``_stream_output_generation`` (a method being
    # moved); no other reference exists at base of mech_preflight, so a
    # plain text.replace is scope-safe.
    text = text.replace(
        "self.stream_interval", "self.server_args.stream_interval"
    )

    # 4b. Retarget calls that live INSIDE the now-converted static methods.
    # Their ``self`` already IS the streamer, so ``self.X(self.output_streamer,
    # ...)`` form (left over from the section-4 blanket) is wrong: there is no
    # ``self.output_streamer`` on the streamer, and the method must be reached
    # via class qualification with ``self`` as the first arg.
    #
    # Inside ``stream_output``:
    text = text.replace(
        "        if self.is_generation:\n"
        "            self._stream_output_generation(\n"
        "                self.output_streamer, reqs, return_logprob, skip_req\n"
        "            )\n"
        "        else:  # embedding or reward model\n"
        "            self._stream_output_embedding(self.output_streamer, reqs)\n"
        "\n"
        "        if envs.SGLANG_TEST_CRASH_AFTER_STREAM_OUTPUTS.get() > 0:\n"
        "            self._trigger_crash_for_tests(\n"
        "                envs.SGLANG_TEST_CRASH_AFTER_STREAM_OUTPUTS.get()\n"
        "            )\n",
        "        if self.is_generation:\n"
        "            SchedulerOutputProcessorMixin._stream_output_generation(\n"
        "                self, reqs, return_logprob, skip_req\n"
        "            )\n"
        "        else:  # embedding or reward model\n"
        "            SchedulerOutputProcessorMixin._stream_output_embedding(self, reqs)\n"
        "\n"
        "        if envs.SGLANG_TEST_CRASH_AFTER_STREAM_OUTPUTS.get() > 0:\n"
        "            SchedulerOutputProcessorMixin._trigger_crash_for_tests(\n"
        "                self, envs.SGLANG_TEST_CRASH_AFTER_STREAM_OUTPUTS.get()\n"
        "            )\n",
    )
    # Inside ``_stream_output_generation`` and ``_stream_output_embedding``
    # (same call pattern appears in both):
    text = text.replace(
        "                cached_tokens_details.append(\n"
        "                    self.get_cached_tokens_details(self.output_streamer, req)\n"
        "                )\n",
        "                cached_tokens_details.append(\n"
        "                    SchedulerOutputProcessorMixin.get_cached_tokens_details(self, req)\n"
        "                )\n",
    )
    # Inside ``get_cached_tokens_details`` (``_get_storage_backend_type`` is
    # NOT in callsite_methods so no ``self.output_streamer,`` was injected):
    text = text.replace(
        'details["storage_backend"] = self._get_storage_backend_type()',
        'details["storage_backend"] = SchedulerOutputProcessorMixin._get_storage_backend_type(self)',
    )

    # Add TYPE_CHECKING import for the new TargetClass so the
    # ``self: "SchedulerOutputStreamer"`` annotation resolves under pyflakes.
    if "from sglang.srt.managers.scheduler_components.output_streamer import SchedulerOutputStreamer" not in text:
        text = text.replace(
            "if TYPE_CHECKING:\n",
            "if TYPE_CHECKING:\n"
            "    from sglang.srt.managers.scheduler_components.output_streamer import SchedulerOutputStreamer\n",
            1,
        )

    mixin.write_text(text)

    # 5. Scheduler: add import + ctor.
    text = sched.read_text()
    text = insert_after(
        text,
        anchor="from sglang.srt.managers.scheduler_components.logprob_result_processor import (\n    SchedulerLogprobResultProcessor,\n)\n",
        addition=(
            "from sglang.srt.managers.scheduler_components.output_streamer import (\n"
            "    SchedulerOutputStreamer,\n"
            ")\n"
        ),
    )
    # Insert streamer ctor right after the logprob_computer ctor.
    text = insert_after(
        text,
        anchor=(
            "        self.logprob_result_processor = SchedulerLogprobResultProcessor(\n"
            "            server_args=self.server_args,\n"
            "            model_config=self.model_config,\n"
            "        )\n\n"
        ),
        addition=SCHEDULER_INIT_INSERT,
    )
    # Hot-path callsite in Scheduler (event_loop_overlap_disagg_*).
    # ``self.stream_output(...)`` → ``self.stream_output(self.output_streamer, ...)``.
    # NOTE: this MUST run before the receiver-shim lambda rewrite below — otherwise
    # the bare ``self.stream_output(`` pattern would match inside the lambda body
    # we just emitted and double-inject ``self.output_streamer,``.
    text = text.replace(
        "self.stream_output(", "self.stream_output(self.output_streamer, "
    )
    # Cross-commit fix: receiver shim ``stream_output=self.stream_output`` →
    # lazy lambda using the static-bound sister form. The lambda defers
    # binding until invocation, by which point output_streamer exists; the
    # final collapse to ``self.output_streamer.stream_output(...)`` happens
    # in -move once the method body lives on the streamer class.
    text = text.replace(
        "            stream_output=self.stream_output,\n",
        "            stream_output=lambda *a, **kw: self.stream_output(self.output_streamer, *a, **kw),\n",
    )
    sched.write_text(text)

    # 6. External callers (disaggregation/prefill.py, dllm/mixin/scheduler.py).
    for f in [
        wt / "python/sglang/srt/disaggregation/prefill.py",
        wt / "python/sglang/srt/dllm/mixin/scheduler.py",
    ]:
        ftext = f.read_text()
        ftext = ftext.replace(
            "self.stream_output(",
            "self.stream_output(self.output_streamer, ",
        )
        f.write_text(ftext)

    # 7. Disagg queue-class callers (live on disaggregation/{decode,prefill}.py
    # but hold a ``self.scheduler`` back-reference, not the Scheduler/mixin
    # ``self``). Route via the transitional static-bound sister form
    # ``self.scheduler.stream_output(self.scheduler.output_streamer, ...)``;
    # ``stream_output`` still lives on the mixin at this prep tip and only
    # collapses to ``self.scheduler.output_streamer.stream_output(...)`` in
    # the upcoming -move commit.
    for f in [
        wt / "python/sglang/srt/disaggregation/prefill.py",
        wt / "python/sglang/srt/disaggregation/decode.py",
    ]:
        ftext = f.read_text()
        ftext = ftext.replace(
            "self.scheduler.stream_output(",
            "self.scheduler.stream_output(self.scheduler.output_streamer, ",
        )
        f.write_text(ftext)


if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        area_branch=AREA_BRANCH,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
