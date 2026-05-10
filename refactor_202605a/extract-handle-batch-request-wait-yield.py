#!/usr/bin/env python3
"""Extract the wait+yield segment of _handle_batch_request into ResponseEmitter.

Per response_emitter.md ch3.1: facade _handle_batch_request keeps the
tokenize+send orchestration but the trailing wait+yield segment moves to
ResponseEmitter._handle_batch_request(obj, rids, generators, request).
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
    replace_call_site,
)
from _runner import run_pr

ID = "extract-handle-batch-request-wait-yield"
SUBJECT = "Extract _handle_batch_request wait+yield segment into ResponseEmitter"
BODY = """\
Cut the trailing wait+yield segment of TokenizerManager._handle_batch_request
(roughly 22 LOC starting at the # Wait for all requests comment) and
relocate it as ResponseEmitter._handle_batch_request(obj, *, rids,
generators, request). Facade _handle_batch_request retains the tokenize +
send orchestration and ends with an async-for loop yielding from the
emitter's new method.

Per response_emitter.md ch3.1 PR1 form. ch3.2 split into iter_batch +
sub-handler restructuring is Ch2.
"""
AREA = "mech_tokenizer_manager"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


WAIT_YIELD_OLD = """        # Wait for all requests
        is_stream = hasattr(obj, "stream") and obj.stream
        if not is_stream:
            outputs = await asyncio.gather(*(gen.__anext__() for gen in generators))
            yield outputs
        else:
            rid_to_index = {rid: i for i, rid in enumerate(rids)}
            task_map = {asyncio.create_task(gen.__anext__()): gen for gen in generators}
            while task_map:
                done, _ = await asyncio.wait(
                    task_map.keys(), return_when=asyncio.FIRST_COMPLETED
                )

                for task in done:
                    gen = task_map.pop(task)
                    try:
                        result = task.result()
                        result["index"] = rid_to_index[result["meta_info"]["id"]]
                        yield result
                        new_task = asyncio.create_task(gen.__anext__())
                        task_map[new_task] = gen
                    except StopAsyncIteration:
                        pass
"""

WAIT_YIELD_FACADE_NEW = """        async for x in self.response_emitter._handle_batch_request(
            obj, rids=rids, generators=generators, request=request
        ):
            yield x
"""


WAIT_YIELD_EMITTER_METHOD = '''
    async def _handle_batch_request(
        self,
        obj,
        *,
        rids,
        generators,
        request=None,
    ):
        """Wait for all per-request generators and yield outputs (single or stream)."""
        is_stream = hasattr(obj, "stream") and obj.stream
        if not is_stream:
            outputs = await asyncio.gather(*(gen.__anext__() for gen in generators))
            yield outputs
        else:
            rid_to_index = {rid: i for i, rid in enumerate(rids)}
            task_map = {asyncio.create_task(gen.__anext__()): gen for gen in generators}
            while task_map:
                done, _ = await asyncio.wait(
                    task_map.keys(), return_when=asyncio.FIRST_COMPLETED
                )

                for task in done:
                    gen = task_map.pop(task)
                    try:
                        result = task.result()
                        result["index"] = rid_to_index[result["meta_info"]["id"]]
                        yield result
                        new_task = asyncio.create_task(gen.__anext__())
                        task_map[new_task] = gen
                    except StopAsyncIteration:
                        pass
'''


def transform(wt: Path) -> None:
    tm = wt / "python/sglang/srt/managers/tokenizer_manager.py"
    emitter = wt / "python/sglang/srt/managers/outputs/response_emitter.py"

    text = tm.read_text()
    text = replace_call_site(text, old=WAIT_YIELD_OLD, new=WAIT_YIELD_FACADE_NEW)
    tm.write_text(text)

    # Append new method to ResponseEmitter class.
    text = emitter.read_text()
    text = text.rstrip() + "\n" + WAIT_YIELD_EMITTER_METHOD
    emitter.write_text(text)


if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        area_branch=AREA_BRANCH,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
