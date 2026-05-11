#!/usr/bin/env python3
"""Prep: add _handle_batch_request method to ResponseEmitter (body same as the inline segment in TM)."""

# /// script
# requires-python = ">=3.10"
# dependencies = ["typer"]
# ///

import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from _runner import run_pr

ID = "extract-handle-batch-request-wait-yield-prep"
SUBJECT = "Prep ResponseEmitter._handle_batch_request: add method stub"
BODY = "Per MECH_COMMIT_SPLIT: add new method to ResponseEmitter. Inline segment in TM untouched until move."
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


def transform(wt: Path) -> None:
    emitter = wt / "python/sglang/srt/managers/response_emitter.py"
    text = emitter.read_text()
    emitter.write_text(text.rstrip() + "\n" + WAIT_YIELD_EMITTER_METHOD)


if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        area_branch=AREA_BRANCH,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
