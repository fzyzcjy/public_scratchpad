#!/usr/bin/env python3
"""Move 4 tokenize-orchestration methods to RequestPreparer."""

# /// script
# requires-python = ">=3.10"
# dependencies = ["typer"]
# ///

import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from _helpers import cut_lines, find_method_lines
from _runner import run_pr

ID = "introduce-request-preparer-move"
SUBJECT = "Move tokenize-orchestration methods to RequestPreparer"
BODY = """\
Cut 4 methods (_tokenize_one_request, _batch_tokenize_and_process,
_should_use_batch_tokenization, _batch_has_text) from TM into
RequestPreparer. Body rewrites: self.server_args.X / self.is_generation /
self.max_req_input_len / hf_config.architectures -> self.config.X.

5 caller sites in facade updated to go through self.request_preparer._<m>(...).
"""
AREA = "mech_tokenizer_manager"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


EXTRA_IMPORTS = '''import logging
from typing import Any, Union

from sglang.srt.environ import envs
from sglang.srt.managers.embed_types import PositionalEmbeds  # noqa: F401
from sglang.srt.managers.io_struct import (
    EmbeddingReqInput,
    GenerateReqInput,
    TokenizedEmbeddingReqInput,
    TokenizedGenerateReqInput,
)
from sglang.srt.managers.schedule_batch import MultimodalDataItem

logger = logging.getLogger(__name__)
'''


def transform(wt: Path) -> None:
    tm = wt / "python/sglang/srt/managers/tokenizer_manager.py"
    rp = wt / "python/sglang/srt/managers/request_preparer.py"

    method_names = (
        "_tokenize_one_request",
        "_batch_tokenize_and_process",
        "_should_use_batch_tokenization",
        "_batch_has_text",
    )
    name_to_range = {}
    for n in method_names:
        s, e = find_method_lines(tm.read_text(), class_name="TokenizerManager", method_name=n)
        name_to_range[n] = (s, e)
    cut_blocks = {}
    for n in sorted(method_names, key=lambda nn: -name_to_range[nn][0]):
        s, e = find_method_lines(tm.read_text(), class_name="TokenizerManager", method_name=n)
        cut_blocks[n] = cut_lines(tm, s, e)

    def rewrite(body: str) -> str:
        body = body.replace("self.server_args.disable_radix_cache", "self.config.disable_radix_cache")
        body = body.replace("self.server_args.language_only", "self.config.language_only")
        body = body.replace("self.server_args.encoder_transfer_backend", "self.config.encoder_transfer_backend")
        body = body.replace("self.server_args.enable_tokenizer_batch_encode", "self.config.enable_tokenizer_batch_encode")
        body = body.replace("self.server_args.enable_dp_attention", "self.config.enable_dp_attention")
        body = body.replace("self.is_generation", "self.config.is_generation")
        body = body.replace("self.max_req_input_len", "self.config.max_req_input_len")
        body = body.replace(
            "self.model_config.hf_config.architectures",
            "self.config.architectures",
        )
        return body

    rewritten = [rewrite(cut_blocks[n]) for n in method_names]
    methods_text = "\n\n".join(b.rstrip() for b in rewritten) + "\n"

    rp_text = rp.read_text()
    rp_text = rp_text.replace(
        "from dataclasses import dataclass\n",
        "from dataclasses import dataclass\n\n" + EXTRA_IMPORTS,
    )
    rp.write_text(rp_text.rstrip() + "\n" + methods_text)

    # Caller updates.
    text = tm.read_text()
    text = text.replace(
        "                tokenized_obj = await self._tokenize_one_request(obj)\n",
        "                tokenized_obj = await self.request_preparer._tokenize_one_request(obj)\n",
    )
    text = text.replace(
        "                        tokenized_obj = await self._tokenize_one_request(tmp_obj)\n",
        "                        tokenized_obj = await self.request_preparer._tokenize_one_request(tmp_obj)\n",
    )
    text = text.replace(
        "                *(self._tokenize_one_request(obj) for obj in objs)\n",
        "                *(self.request_preparer._tokenize_one_request(obj) for obj in objs)\n",
    )
    text = text.replace(
        "                tokenized_objs = await self._batch_tokenize_and_process(batch_size, obj)\n",
        "                tokenized_objs = await self.request_preparer._batch_tokenize_and_process(batch_size, obj)\n",
    )
    text = text.replace(
        "            if self._should_use_batch_tokenization(batch_size, obj):\n",
        "            if self.request_preparer._should_use_batch_tokenization(batch_size, obj):\n",
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
