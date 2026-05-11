#!/usr/bin/env python3
"""Extract the wait+yield segment of ``TokenizerManager._handle_batch_request``
into ``ResponseEmitter._handle_batch_request`` and rewire the call site.

Single-commit extraction (no prep/move split): the inline segment is small,
the new method is added to a class that already exists in the chain, and
the call-site rewrite is a one-shot ~5-line swap — so the canonical
prep+move split would create two trivially-coupled commits where the prep
half adds dead code. Combine them.
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

ID = "extract-handle-batch-request-wait-yield"
SUBJECT = "Extract batch-request wait+yield from TM to ResponseEmitter"
BODY = """\
Add ``_handle_batch_request`` to ResponseEmitter; replace the inline
wait+yield segment in TM's ``_handle_batch_request`` with a delegating
async-for to ``self.response_emitter._handle_batch_request(...)``. Body
bytes of the segment are identical to what now lives on ResponseEmitter
(modulo enclosing method signature).

Squashed prep+move: the prep half (add stub on ResponseEmitter) and the
move half (rewire TM call site) are tightly coupled and each is small;
no intermediate state is independently meaningful.
"""
AREA = "mech_tokenizer_manager"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


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


def transform(wt: Path) -> None:
    emitter = wt / "python/sglang/srt/managers/tokenizer_manager_components/response_emitter.py"
    tm = wt / "python/sglang/srt/managers/tokenizer_manager.py"

    emitter_text = emitter.read_text()
    emitter.write_text(emitter_text.rstrip() + "\n" + WAIT_YIELD_EMITTER_METHOD)

    tm_text = tm.read_text()
    tm_text = replace_call_site(tm_text, old=WAIT_YIELD_OLD, new=WAIT_YIELD_FACADE_NEW)
    tm.write_text(tm_text)


if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        area_branch=AREA_BRANCH,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
