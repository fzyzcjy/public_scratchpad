#!/usr/bin/env python3
"""Move (pure cut/paste): relocate ``init_tokenizer_and_processor`` +
``_get_processor_wrapper`` + ``_determine_tensor_transport_mode`` from
TokenizerManager to ``raw_tokenizer_wrapper.py``.

Per MECH_COMMIT_SPLIT §"反模式：prep 大段加代码 + move 大段删代码"——this
commit's diff should be: TM −body, RTW +body, byte-equivalent. The
@property facade introduced in prep absorbs all external callers; no
caller rewrites in entrypoints / template_manager / tests / docs.
"""

# /// script
# requires-python = ">=3.10"
# dependencies = ["typer"]
# ///

import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from _helpers import cut_lines, find_function_lines, find_method_lines, replace_call_site
from _runner import run_pr

ID = "introduce-raw-tokenizer-wrapper-move"
SUBJECT = "Hand tokenizer/processor ownership over to RawTokenizerWrapper"
BODY = """\
Pure cut/paste move per MECH_COMMIT_SPLIT. Cuts:

  - ``TokenizerManager.init_tokenizer_and_processor`` (@staticmethod
    in prep) → ``RawTokenizerWrapper.init_tokenizer_and_processor``
    (instance method, drop @staticmethod, restore plain ``self``)
  - module-level helpers ``_get_processor_wrapper`` and
    ``_determine_tensor_transport_mode`` from tokenizer_manager.py →
    raw_tokenizer_wrapper.py module top-level

Updates imports in both files (move what the body needs, drop what TM
no longer uses). No external caller rewrites — the @property facade on
TokenizerManager (added in prep) absorbs every ``tm.tokenizer`` /
``tm.processor`` / ``tm.mm_processor`` access. InputFormat enum + the
4 tokenize-pipeline helpers move in the follow-up
``rtw-move-tokenize-helpers`` commit.
"""
AREA = "mech_tokenizer_manager"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


RTW_BODY_IMPORTS = """import os

from sglang.srt.configs.model_config import ModelConfig
from sglang.srt.environ import envs
from sglang.srt.managers.mm_utils import TensorTransportMode
from sglang.srt.managers.multimodal_processor import (
    get_mm_processor,
    import_processors,
)
from sglang.srt.server_args import ServerArgs
from sglang.srt.utils.hf_transformers_utils import (
    get_processor,
    get_tokenizer,
    get_tokenizer_from_processor,
)
"""

RTW_LOGGER_BLOCK = """
import logging

logger = logging.getLogger(__name__)
"""


def transform(wt: Path) -> None:
    tm = wt / "python/sglang/srt/managers/tokenizer_manager.py"
    rtw = wt / "python/sglang/srt/managers/tokenizer_manager_components/raw_tokenizer_wrapper.py"

    # ---- 1. Cut the @staticmethod init_tokenizer_and_processor body from TM.
    s, e = find_method_lines(
        tm.read_text(),
        class_name="TokenizerManager",
        method_name="init_tokenizer_and_processor",
    )
    method_text = cut_lines(tm, s, e)

    # Strip @staticmethod + restore plain self (RawTokenizerWrapper instance).
    method_text = method_text.replace("    @staticmethod\n", "", 1)
    method_text = method_text.replace('self: "RawTokenizerWrapper",', "self,")
    method_text = method_text.replace('self: "RawTokenizerWrapper"\n', "self\n")

    # ---- 2. Cut module-level helpers from TM.
    text = tm.read_text()
    s, e = find_function_lines(text, function_name="_get_processor_wrapper")
    helper1 = cut_lines(tm, s, e)
    text = tm.read_text()
    s, e = find_function_lines(text, function_name="_determine_tensor_transport_mode")
    helper2 = cut_lines(tm, s, e)

    # ---- 3. Inject imports + helpers + the method into RTW.
    rtw_text = rtw.read_text()
    rtw_text = rtw_text.replace(
        "from sglang.srt.managers.async_dynamic_batch_tokenizer import AsyncDynamicbatchTokenizer\n",
        "from sglang.srt.managers.async_dynamic_batch_tokenizer import AsyncDynamicbatchTokenizer\n\n"
        + RTW_BODY_IMPORTS
        + RTW_LOGGER_BLOCK,
    )
    # Append helpers at module level (before the class).
    # Insert at end of file then re-class-merge: simplest is append after class.
    # Helpers reference ``server_args`` / ``ServerArgs`` only.
    body_to_append = helper1.rstrip() + "\n\n\n" + helper2.rstrip() + "\n\n"
    rtw_text = rtw_text.rstrip() + "\n\n\n" + body_to_append
    # Append method inside the class — find the trailing close of dataclass body.
    # The class only has fields; method goes at the end of the class block.
    # Strategy: append method after class closing, then move it under the class.
    # Cleaner: insert method body just before the helpers we just appended.
    # But the class has slots=True so we can't add methods? Actually slots+kw_only
    # allows methods — slots just restricts instance attrs.
    # We'll insert into class body: anchor on
    # ``async_dynamic_batch_tokenizer: Optional[AsyncDynamicbatchTokenizer] = None``
    # which is the last class field.
    rtw_text = rtw_text.replace(
        "    async_dynamic_batch_tokenizer: Optional[AsyncDynamicbatchTokenizer] = None\n",
        "    async_dynamic_batch_tokenizer: Optional[AsyncDynamicbatchTokenizer] = None\n"
        + "\n"
        + method_text.rstrip()
        + "\n",
    )
    rtw.write_text(rtw_text)

    # ---- 4. TM caller rewrite: composition wiring used the prep-stage
    # ``TokenizerManager.init_tokenizer_and_processor(self.raw_tokenizer_wrapper, ...)``
    # form. After move, collapse to instance method call.
    text = tm.read_text()
    text = text.replace(
        "        TokenizerManager.init_tokenizer_and_processor(\n"
        "            self.raw_tokenizer_wrapper,\n"
        "            server_args=self.server_args,\n"
        "            model_config=self.model_config,\n"
        "        )",
        "        self.raw_tokenizer_wrapper.init_tokenizer_and_processor(\n"
        "            server_args=self.server_args,\n"
        "            model_config=self.model_config,\n"
        "        )",
    )
    tm.write_text(text)

    # ---- 5. mm_utils.py lazily imports the relocated _determine_tensor_transport_mode
    # from tokenizer_manager; repoint it at its new home (raw_tokenizer_wrapper).
    mm_utils = wt / "python/sglang/srt/managers/mm_utils.py"
    mm_text = mm_utils.read_text()
    mm_text = replace_call_site(
        mm_text,
        old=(
            "        from sglang.srt.managers.tokenizer_manager import (\n"
            "            _determine_tensor_transport_mode,\n"
            "        )\n"
        ),
        new=(
            "        from sglang.srt.managers.tokenizer_manager_components.raw_tokenizer_wrapper import (\n"
            "            _determine_tensor_transport_mode,\n"
            "        )\n"
        ),
    )
    mm_utils.write_text(mm_text)


if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        area_branch=AREA_BRANCH,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
