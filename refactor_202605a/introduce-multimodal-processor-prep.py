#!/usr/bin/env python3
"""Inplace prep for ``introduce-multimodal-processor``: create the empty
``MultimodalProcessor`` class skeleton in
``managers/multimodal_processor_owner.py``, instantiate
``self.multimodal_processor = MultimodalProcessor(...)`` in
``TokenizerManager.__init__`` (after the existing ``mm_receiver``
initialization), convert 2 methods
(``_should_dispatch_to_encoder`` / ``_handle_epd_disaggregation_encode_request``)
to ``@staticmethod`` with ``self: "MultimodalProcessor"`` annotation,
rewrite the single external caller to
``TokenizerManager._handle_epd_disaggregation_encode_request(self.multimodal_processor, ...)``,
and rewrite intra-class ``self.mm_receiver`` reads throughout
``tokenizer_manager.py`` to ``self.multimodal_processor.mm_receiver``.

Body bytes byte-identical wrt the post-move state (modulo decorator + the
``def foo(self: "MultimodalProcessor", ...)`` -> ``def foo(self, ...)``
signature simplification in the move commit). The single cross-method
call ``self._should_dispatch_to_encoder(obj)`` becomes
``TokenizerManager._should_dispatch_to_encoder(self, obj)`` in prep so
that the move-step caller rewrite is a pure prefix collapse.

Privacy flip + ``MultimodalProcessorConfig`` grouping + ``from_server_args``
factory are deferred to follow-up nonmech commits per MECH_COMMIT_SPLIT
``fancy reshape`` rule; this prep keeps the minimum scaffolding needed to
move the two methods.
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

ID = "introduce-multimodal-processor-prep"
SUBJECT = "Build MultimodalProcessor skeleton + @staticmethod prep (prep for move)"
BODY = """\
Inplace prep for the ``introduce-multimodal-processor`` mech move.

- Create ``managers/multimodal_processor_owner.py`` with a
  ``MultimodalProcessor`` class (4 fields: ``server_args``,
  ``model_config``, ``mm_processor``, ``mm_receiver``). No methods yet.
- In ``TokenizerManager.__init__``, after the ``init_disaggregation``
  call (which still owns the conditional ``self.mm_receiver = ...``
  block), construct ``self.multimodal_processor = MultimodalProcessor(...)``
  borrowing the same ``mm_processor`` / ``mm_receiver`` references.
- In TokenizerManager, convert 2 methods
  (``_should_dispatch_to_encoder`` / ``_handle_epd_disaggregation_encode_request``)
  to ``@staticmethod`` with ``self: "MultimodalProcessor"`` annotation.
  Bodies byte-identical except the one intra-class call site
  ``self._should_dispatch_to_encoder(obj)`` ->
  ``TokenizerManager._should_dispatch_to_encoder(self, obj)``.
- External caller rewritten to
  ``TokenizerManager._handle_epd_disaggregation_encode_request(self.multimodal_processor, obj)``.
- All ``self.mm_receiver`` reads throughout ``tokenizer_manager.py``
  rewritten to ``self.multimodal_processor.mm_receiver``. The conditional
  assignment ``self.mm_receiver = create_mm_receiver(...)`` in
  ``init_disaggregation`` stays put for now and is read by the new
  ``MultimodalProcessor`` ctor via attribute access at construction time
  (after ``init_disaggregation`` has run).

The 2 methods stay inside ``TokenizerManager`` in this commit; physical
cut + paste to ``MultimodalProcessor`` body happens in
``introduce-multimodal-processor-move``.

Privacy flip (``_should_dispatch_to_encoder`` ->
``should_dispatch_to_encoder``), the rename
``_handle_epd_disaggregation_encode_request`` ->
``maybe_dispatch_to_encoder``, and the ``MultimodalProcessorConfig``
grouping / ``from_server_args`` factory are deferred to follow-up
nonmech commits per MECH_COMMIT_SPLIT.
"""
AREA = "mech_tokenizer_manager"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


PROCESSOR_HEADER = '''from __future__ import annotations

from typing import Any, Optional

from sglang.srt.configs.model_config import ModelConfig
from sglang.srt.server_args import ServerArgs


class MultimodalProcessor:
    """Owner of ``mm_processor`` / ``mm_receiver`` references and the EPD
    dispatch routing methods. Skeleton only at this commit; methods land in
    the follow-up ``introduce-multimodal-processor-move`` commit."""

    def __init__(
        self,
        *,
        server_args: ServerArgs,
        model_config: ModelConfig,
        mm_processor: Optional[Any],
        mm_receiver: Optional[Any],
    ) -> None:
        self.server_args = server_args
        self.model_config = model_config
        self.mm_processor = mm_processor
        self.mm_receiver = mm_receiver
'''


INIT_INSERT = '''        self.multimodal_processor = MultimodalProcessor(
            server_args=self.server_args,
            model_config=self.model_config,
            mm_processor=self.mm_processor,
            mm_receiver=getattr(self, "mm_receiver", None),
        )

'''


def transform(wt: Path) -> None:
    tm = wt / "python/sglang/srt/managers/tokenizer_manager.py"
    owner = wt / "python/sglang/srt/managers/multimodal_processor_owner.py"

    # 1. Create new file with skeleton class.
    owner.write_text(PROCESSOR_HEADER)

    # 2. In TokenizerManager, convert 2 methods to @staticmethod inplace.
    text = tm.read_text()

    # _should_dispatch_to_encoder: add @staticmethod, type-flip self.
    s, e = find_method_lines(
        text, class_name="TokenizerManager", method_name="_should_dispatch_to_encoder"
    )
    lines = text.splitlines(keepends=True)
    method_text = "".join(lines[s:e])
    if "    def _should_dispatch_to_encoder(\n        self, " not in method_text:
        raise RuntimeError("_should_dispatch_to_encoder signature shape unexpected")
    new_method = method_text.replace(
        "    def _should_dispatch_to_encoder(\n        self, ",
        '    @staticmethod\n    def _should_dispatch_to_encoder(\n        self: "MultimodalProcessor", ',
    )
    text = "".join(lines[:s]) + new_method + "".join(lines[e:])

    # _handle_epd_disaggregation_encode_request: add @staticmethod, type-flip self,
    # plus the single cross-method call gets class-qualified.
    s, e = find_method_lines(
        text,
        class_name="TokenizerManager",
        method_name="_handle_epd_disaggregation_encode_request",
    )
    lines = text.splitlines(keepends=True)
    method_text = "".join(lines[s:e])
    if (
        "    def _handle_epd_disaggregation_encode_request(\n        self, "
        not in method_text
    ):
        raise RuntimeError(
            "_handle_epd_disaggregation_encode_request signature shape unexpected"
        )
    new_method = method_text.replace(
        "    def _handle_epd_disaggregation_encode_request(\n        self, ",
        '    @staticmethod\n    def _handle_epd_disaggregation_encode_request(\n        self: "MultimodalProcessor", ',
    )
    new_method = replace_call_site(
        new_method,
        old="                should_dispatch = self._should_dispatch_to_encoder(obj)\n",
        new="                should_dispatch = TokenizerManager._should_dispatch_to_encoder(self, obj)\n",
    )
    text = "".join(lines[:s]) + new_method + "".join(lines[e:])

    # 3. Add import for MultimodalProcessor.
    text = insert_after(
        text,
        anchor="from sglang.srt.managers.multimodal_processor import get_mm_processor, import_processors\n",
        addition="from sglang.srt.managers.multimodal_processor_owner import MultimodalProcessor\n",
    )

    # 4. Instantiate MultimodalProcessor in TM.__init__, immediately after the
    # init_disaggregation() call (which is where self.mm_receiver gets set).
    text = replace_call_site(
        text,
        old="        self.init_disaggregation()\n",
        new="        self.init_disaggregation()\n\n" + INIT_INSERT,
    )

    # 5. External caller: ``self._handle_epd_disaggregation_encode_request(obj)``
    # -> ``TokenizerManager._handle_epd_disaggregation_encode_request(self.multimodal_processor, obj)``.
    text = replace_call_site(
        text,
        old="            self._handle_epd_disaggregation_encode_request(obj)\n",
        new=(
            "            TokenizerManager._handle_epd_disaggregation_encode_request(\n"
            "                self.multimodal_processor, obj\n"
            "            )\n"
        ),
    )

    # 6. All ``self.mm_receiver`` reads -> ``self.multimodal_processor.mm_receiver``.
    # The assignment ``self.mm_receiver = create_mm_receiver(...)`` in
    # init_disaggregation stays put — MultimodalProcessor ctor pulls the value
    # via ``getattr(self, "mm_receiver", None)`` after init_disaggregation runs.
    # Skip the assignment LHS; rewrite only read sites.
    text = text.replace(
        "await self.mm_receiver.recv_mm_data(",
        "await self.multimodal_processor.mm_receiver.recv_mm_data(",
    )
    text = text.replace(
        "self.mm_receiver.send_encode_request(",
        "self.multimodal_processor.mm_receiver.send_encode_request(",
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
