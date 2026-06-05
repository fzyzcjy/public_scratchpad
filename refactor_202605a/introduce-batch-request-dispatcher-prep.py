#!/usr/bin/env python3
"""Prep: BatchRequestDispatcher skeleton + composition wiring + TM-internal
helper extraction. Body of ``_handle_batch_request_dispatch`` stays on TM
(byte-equivalent to the prep-stage ``_handle_batch_request`` prefix); -move
cuts and pastes it into BatchRequestDispatcher.dispatch().

Per MECH_COMMIT_SPLIT §"反模式：prep 大段加代码 + move 大段删代码"——this
is the canonical split of the user's a5fe2036 single-commit form. prep here
only emits a small skeleton + composition + an in-TM extraction; the body
move happens in -move.
"""

# /// script
# requires-python = ">=3.10"
# dependencies = ["typer"]
# ///

import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from _helpers import insert_after, replace_call_site, wire_component_init
from _runner import run_pr

ID = "introduce-batch-request-dispatcher-prep"
SUBJECT = "Stage batch-request dispatch for handoff to BatchRequestDispatcher"
BODY = """\
Per MECH_COMMIT_SPLIT §"拆 class 场景": prep does ALL semantic work.

Builds BatchRequestDispatcher skeleton (dataclass fields only — no
``dispatch`` body); wires composition in TM.__init__ at the end of the
owner-class block (BatchRequestDispatcher depends on request_preparer,
response_emitter, rid_to_state and TM's _send_one_request /
_send_batch_request callables — all set earlier).

Inside TM, refactors ``_handle_batch_request`` into:
  - new non-generator helper ``_handle_batch_request_dispatch(self, obj, request)``
    holding the entire prefix body, ending in ``return generators, rids``;
    body bytes are identical to the pre-prep generator's prefix.
  - the original ``_handle_batch_request`` collapses to a 7-line facade
    that calls the helper and yields from response_emitter.

The follow-up -move commit cuts ``_handle_batch_request_dispatch`` from
TM, pastes into BatchRequestDispatcher as ``dispatch``, applies the
minimal self-field rewrites (``self._send_*`` → ``self.send_*``;
``self.server_args.enable_trace`` → ``self.config.enable_trace``;
``self.disaggregation_mode`` → ``self.config.disaggregation_mode``),
flips the facade call to ``self.batch_request_dispatcher.dispatch(...)``,
and drops the orphan imports (copy / nullcontext /
input_blocker_guard_region).
"""
AREA = "mech_tokenizer_manager"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


SKELETON = '''from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict

from sglang.srt.disaggregation.utils import DisaggregationMode
from sglang.srt.managers.tokenizer_manager_components.request_preparer import RequestPreparer
from sglang.srt.managers.tokenizer_manager_components.request_state import ReqState
from sglang.srt.managers.tokenizer_manager_components.response_emitter import ResponseEmitter


@dataclass(frozen=True, slots=True, kw_only=True)
class BatchRequestDispatcherConfig:
    enable_trace: bool
    disaggregation_mode: DisaggregationMode


@dataclass(frozen=True, slots=True, kw_only=True)
class BatchRequestDispatcher:
    request_preparer: RequestPreparer
    response_emitter: ResponseEmitter
    rid_to_state: Dict[str, ReqState]
    send_to_scheduler: Any
    send_one_request: Callable[..., None]
    send_batch_request: Callable[..., None]
    config: BatchRequestDispatcherConfig
'''


def transform(wt: Path) -> None:
    tm = wt / "python/sglang/srt/managers/tokenizer_manager.py"
    new = wt / "python/sglang/srt/managers/tokenizer_manager_components/batch_request_dispatcher.py"
    new.write_text(SKELETON)

    text = tm.read_text()

    # ---- 1. Import the new class into TM. Anchor on a stable late-in-chain
    # import that survives all earlier refactor commits.
    text = insert_after(
        text,
        anchor=(
            "from sglang.srt.managers.tokenizer_manager_components.corpus_controller import (\n"
            "    CorpusController,\n"
            "    CorpusControllerConfig,\n"
            ")\n"
        ),
        addition=(
            "from sglang.srt.managers.tokenizer_manager_components.batch_request_dispatcher import (\n"
            "    BatchRequestDispatcher,\n"
            "    BatchRequestDispatcherConfig,\n"
            ")\n"
        ),
    )

    # ---- 2. Refactor _handle_batch_request: extract a non-generator helper
    # ``_handle_batch_request_dispatch`` containing the entire prefix body
    # (byte-equivalent to current bytes), ending in ``return generators, rids``;
    # ``_handle_batch_request`` collapses to a 7-line facade.
    #
    # Pre-image: the existing 100-line body. Post-image: helper + facade.
    OLD_HANDLE_BATCH_REQUEST = '''    async def _handle_batch_request(
        self,
        obj: Union[GenerateReqInput, EmbeddingReqInput],
        request: Optional[fastapi.Request] = None,
    ):
        batch_size = obj.batch_size

        generators = []
        rids = []
        if getattr(obj, "parallel_sample_num", 1) == 1:
            if self.request_preparer._should_use_batch_tokenization(batch_size, obj):
                tokenized_objs = (
                    await self.request_preparer._batch_tokenize_and_process(
                        batch_size, obj
                    )
                )
                self._send_batch_request(tokenized_objs)

                # Set up generators for each request in the batch
                for i in range(batch_size):
                    tmp_obj = obj[i]
                    state = self.rid_to_state[tmp_obj.rid]
                    if tmp_obj.return_prompt_token_ids:
                        state.prompt_token_ids = list(tokenized_objs[i].input_ids)
                    generators.append(
                        self.response_emitter._wait_one_response(tmp_obj, request)
                    )
                    rids.append(tmp_obj.rid)
            else:
                # Sequential tokenization and processing
                with (
                    input_blocker_guard_region(send_to_scheduler=self.send_to_scheduler)
                    if get_bool_env_var("SGLANG_ENABLE_COLOCATED_BATCH_GEN")
                    else nullcontext()
                ):
                    for i in range(batch_size):
                        tmp_obj = obj[i]
                        tokenized_obj = (
                            await self.request_preparer._tokenize_one_request(tmp_obj)
                        )
                        state = self.rid_to_state[tmp_obj.rid]
                        if tmp_obj.return_prompt_token_ids:
                            state.prompt_token_ids = list(tokenized_obj.input_ids)
                        self._send_one_request(tokenized_obj)
                        generators.append(
                            self.response_emitter._wait_one_response(tmp_obj, request)
                        )
                        rids.append(tmp_obj.rid)
        else:
            # FIXME: When using batch and parallel_sample_num together, the perf is not optimal.
            if batch_size > 128:
                logger.warning(
                    "Sending a single large batch with parallel sampling (n > 1) has not been well optimized. "
                    "The performance might be better if you just duplicate the requests n times or use "
                    "many threads to send them one by one with parallel sampling (n > 1)."
                )

            # Tokenize all requests
            objs = [obj[i] for i in range(batch_size)]
            tokenized_objs = await asyncio.gather(
                *(self.request_preparer._tokenize_one_request(obj) for obj in objs)
            )

            # Cache the common prefix for parallel sampling
            for i in range(batch_size):
                tmp_obj = copy.copy(objs[i])
                tokenized_obj = copy.copy(tokenized_objs[i])
                # Ensure independent mm_items so wrap_shm_features won't mutate the original
                if hasattr(tokenized_obj, "mm_inputs") and tokenized_obj.mm_inputs:
                    tokenized_obj.mm_inputs = copy.copy(tokenized_obj.mm_inputs)
                    tokenized_obj.mm_inputs.mm_items = [
                        copy.copy(item) for item in tokenized_obj.mm_inputs.mm_items
                    ]
                tokenized_obj.rid = tmp_obj.regenerate_rid()
                tokenized_obj.sampling_params = copy.copy(tokenized_obj.sampling_params)
                tokenized_obj.sampling_params.max_new_tokens = 0
                tokenized_obj.stream = False
                init_req(
                    self.rid_to_state,
                    obj=tmp_obj,
                    enable_trace=self.server_args.enable_trace,
                    disagg_mode=self.disaggregation_mode,
                )
                self._send_one_request(tokenized_obj)
                await self.response_emitter._wait_one_response(
                    tmp_obj, request
                ).__anext__()

            # Expand requests, assign new rids for them, and send them
            for i in range(batch_size):
                for _ in range(obj.parallel_sample_num):
                    tmp_obj = copy.copy(objs[i])
                    tokenized_obj = copy.copy(tokenized_objs[i])
                    # Ensure independent mm_items so wrap_shm_features won't mutate the original
                    if hasattr(tokenized_obj, "mm_inputs") and tokenized_obj.mm_inputs:
                        tokenized_obj.mm_inputs = copy.copy(tokenized_obj.mm_inputs)
                        tokenized_obj.mm_inputs.mm_items = [
                            copy.copy(item) for item in tokenized_obj.mm_inputs.mm_items
                        ]
                    tokenized_obj.rid = tmp_obj.regenerate_rid()
                    init_req(
                        self.rid_to_state,
                        obj=tmp_obj,
                        enable_trace=self.server_args.enable_trace,
                        disagg_mode=self.disaggregation_mode,
                    )
                    state = self.rid_to_state[tmp_obj.rid]
                    tokenized_obj.time_stats = state.time_stats
                    if tmp_obj.return_prompt_token_ids:
                        state.prompt_token_ids = list(tokenized_objs[i].input_ids)
                    self._send_one_request(tokenized_obj)
                    generators.append(
                        self.response_emitter._wait_one_response(tmp_obj, request)
                    )
                    rids.append(tmp_obj.rid)

                self.rid_to_state[objs[i].rid].time_stats.set_finished_time()
                del self.rid_to_state[objs[i].rid]

        async for x in self.response_emitter._handle_batch_request(
            obj, rids=rids, generators=generators, request=request
        ):
            yield x
'''

    # Build the new helper + facade from the OLD body. The helper body is the
    # OLD body up to (but not including) the ``async for`` tail, then a
    # ``return generators, rids`` line; the facade wraps it.
    OLD_TAIL = (
        "        async for x in self.response_emitter._handle_batch_request(\n"
        "            obj, rids=rids, generators=generators, request=request\n"
        "        ):\n"
        "            yield x\n"
    )
    assert OLD_TAIL in OLD_HANDLE_BATCH_REQUEST
    helper_prefix_body = OLD_HANDLE_BATCH_REQUEST.split(OLD_TAIL)[0]
    # Drop the original ``async def _handle_batch_request(...)`` header from the
    # prefix; we re-emit it under the helper name.
    OLD_HEADER = (
        "    async def _handle_batch_request(\n"
        "        self,\n"
        "        obj: Union[GenerateReqInput, EmbeddingReqInput],\n"
        "        request: Optional[fastapi.Request] = None,\n"
        "    ):\n"
    )
    assert helper_prefix_body.startswith(OLD_HEADER)
    helper_inner = helper_prefix_body[len(OLD_HEADER):].rstrip("\n")

    NEW_HELPER_PLUS_FACADE = (
        "    async def _handle_batch_request_dispatch(\n"
        "        self,\n"
        "        obj: Union[GenerateReqInput, EmbeddingReqInput],\n"
        "        request: Optional[fastapi.Request] = None,\n"
        "    ):\n"
        f"{helper_inner}\n"
        "\n"
        "        return generators, rids\n"
        "\n"
        "    async def _handle_batch_request(\n"
        "        self,\n"
        "        obj: Union[GenerateReqInput, EmbeddingReqInput],\n"
        "        request: Optional[fastapi.Request] = None,\n"
        "    ):\n"
        "        generators, rids = await self._handle_batch_request_dispatch(\n"
        "            obj, request\n"
        "        )\n"
        "        async for x in self.response_emitter._handle_batch_request(\n"
        "            obj, rids=rids, generators=generators, request=request\n"
        "        ):\n"
        "            yield x\n"
    )

    text = replace_call_site(text, old=OLD_HANDLE_BATCH_REQUEST, new=NEW_HELPER_PLUS_FACADE)

    # ---- 3. Composition wiring: append at the end of the owner-class block,
    # just before ``self.init_request_dispatcher()``. ScoreRequestHandler is the
    # last owner-class wired before init_request_dispatcher, so anchor on it.
    text = wire_component_init(
        text,
        attr="batch_request_dispatcher",
        construction=(
            "        self.batch_request_dispatcher = BatchRequestDispatcher(\n"
            "            request_preparer=self.request_preparer,\n"
            "            response_emitter=self.response_emitter,\n"
            "            rid_to_state=self.rid_to_state,\n"
            "            send_to_scheduler=self.send_to_scheduler,\n"
            "            send_one_request=self._send_one_request,\n"
            "            send_batch_request=self._send_batch_request,\n"
            "            config=BatchRequestDispatcherConfig(\n"
            "                enable_trace=self.server_args.enable_trace,\n"
            "                disaggregation_mode=self.disaggregation_mode,\n"
            "            ),\n"
            "        )\n"
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
