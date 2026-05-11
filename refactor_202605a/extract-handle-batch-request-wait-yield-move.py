#!/usr/bin/env python3
"""Move: replace inline segment in TM._handle_batch_request with call to ResponseEmitter's new method."""

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

ID = "extract-handle-batch-request-wait-yield-move"
SUBJECT = "Move: TM._handle_batch_request delegates wait+yield to ResponseEmitter"
BODY = "Replace inline wait+yield segment in TM._handle_batch_request with delegation to self.response_emitter._handle_batch_request."
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


def transform(wt: Path) -> None:
    tm = wt / "python/sglang/srt/managers/tokenizer_manager.py"
    text = tm.read_text()
    text = replace_call_site(text, old=WAIT_YIELD_OLD, new=WAIT_YIELD_FACADE_NEW)
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
