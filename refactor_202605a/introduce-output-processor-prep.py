#!/usr/bin/env python3
"""Prep: OutputProcessor skeleton + composition wiring + in-place staticmethod conversion + caller rewrite."""

# /// script
# requires-python = ">=3.10"
# dependencies = ["typer"]
# ///

import ast
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from _helpers import insert_after, replace_call_site, wire_component_init
from _runner import run_pr

ID = "introduce-output-processor-prep"
SUBJECT = "Stage batch-output handling for handoff to OutputProcessor"
BODY = """\
Per MECH_COMMIT_SPLIT §"拆 class 场景": prep does ALL semantic work.

Builds OutputProcessor skeleton; wires composition in TM.__init__;
converts _handle_batch_output (~247 LOC) to @staticmethod with
self: "OutputProcessor" annotation; applies body rewrites
(server_args.X -> config.X, enable_metrics -> config.enable_metrics,
raw_tokenizer_wrapper.tokenizer -> self.tokenizer,
crash_dump_folder -> request_log_manager.crash_dump_folder,
served_model_name -> config.served_model_name); rewrites caller in
handle_loop to TokenizerManager._handle_batch_output(self.output_processor, ...)
form. Method stays on TM in this commit; the next commit's pure
cut/paste + caller prefix replacement completes the move.
"""
AREA = "mech_tokenizer_manager"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


SKELETON = '''from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

from sglang.srt.managers.tokenizer_manager_components.lora_controller import LoraController
from sglang.srt.managers.tokenizer_manager_components.request_log_manager import RequestLogManager
from sglang.srt.managers.tokenizer_manager_components.request_metrics_recorder import RequestMetricsRecorder
from sglang.srt.managers.tokenizer_manager_components.request_state import ReqState


@dataclass(frozen=True, slots=True, kw_only=True)
class OutputProcessorConfig:
    batch_notify_size: int
    incremental_streaming_output: bool
    enable_metrics: bool
    skip_tokenizer_init: bool
    speculative_algorithm: str
    speculative_num_draft_tokens: int
    dp_size: int
    enable_lora: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class OutputProcessor:
    rid_to_state: Dict[str, ReqState]
    tokenizer: Optional[Any]
    request_metrics_recorder: RequestMetricsRecorder
    request_log_manager: RequestLogManager
    lora_controller: LoraController
    send_to_scheduler: Any
    get_weight_version: Callable[[], Optional[str]]
    get_served_model_name: Callable[[], str]
    config: OutputProcessorConfig
'''


def _method_ranges(text: str, class_name: str, method_name: str):
    tree = ast.parse(text)
    func_types = (ast.FunctionDef, ast.AsyncFunctionDef)
    for cls in ast.walk(tree):
        if isinstance(cls, ast.ClassDef) and cls.name == class_name:
            for i, node in enumerate(cls.body):
                if isinstance(node, func_types) and node.name == method_name:
                    start = node.lineno - 1
                    if node.decorator_list:
                        start = node.decorator_list[0].lineno - 1
                    body_start = node.body[0].lineno - 1
                    if i + 1 < len(cls.body):
                        end = cls.body[i + 1].lineno - 1
                        nxt = cls.body[i + 1]
                        if isinstance(nxt, func_types + (ast.ClassDef,)) and nxt.decorator_list:
                            end = nxt.decorator_list[0].lineno - 1
                    else:
                        end = node.end_lineno
                    return start, body_start, end
    raise ValueError(f"{class_name}.{method_name} not found")


# Replacement header for _handle_batch_output: @staticmethod + self: TargetClass typing.
NEW_HANDLE_HEADER = '''    @staticmethod
    async def _handle_batch_output(
        self: "OutputProcessor",
        recv_obj: Union[
            BatchStrOutput,
            BatchEmbeddingOutput,
            BatchTokenIDOutput,
        ],
    ):
'''


def transform(wt: Path) -> None:
    tm = wt / "python/sglang/srt/managers/tokenizer_manager.py"
    new = wt / "python/sglang/srt/managers/tokenizer_manager_components/output_processor.py"
    new.write_text(SKELETON)

    text = tm.read_text()
    text = insert_after(
        text,
        anchor="from sglang.srt.managers.tokenizer_control_mixin import TokenizerControlMixin\n",
        addition=(
            "from sglang.srt.managers.tokenizer_manager_components.output_processor import (\n"
            "    OutputProcessor,\n"
            "    OutputProcessorConfig,\n"
            ")\n"
        ),
    )

    # Composition wiring.
    text = wire_component_init(
        text,
        attr="output_processor",
        before_attr="session_controller",
        construction=(
            "        self.output_processor = OutputProcessor(\n"
            "            rid_to_state=self.rid_to_state,\n"
            "            tokenizer=self.tokenizer,\n"
            "            request_metrics_recorder=self.request_metrics_recorder,\n"
            "            request_log_manager=self.request_log_manager,\n"
            "            lora_controller=self.lora_controller,\n"
            "            send_to_scheduler=self.send_to_scheduler,\n"
            "            get_weight_version=lambda: self.server_args.weight_version,\n"
            "            get_served_model_name=lambda: self.served_model_name,\n"
            "            config=OutputProcessorConfig(\n"
            "                batch_notify_size=self.server_args.batch_notify_size,\n"
            "                incremental_streaming_output=self.server_args.incremental_streaming_output,\n"
            "                enable_metrics=self.enable_metrics,\n"
            "                skip_tokenizer_init=self.server_args.skip_tokenizer_init,\n"
            "                speculative_algorithm=self.server_args.speculative_algorithm or '',\n"
            "                speculative_num_draft_tokens=self.server_args.speculative_num_draft_tokens,\n"
            "                dp_size=self.server_args.dp_size,\n"
            "                enable_lora=self.server_args.enable_lora,\n"
            "            ),\n"
            "        )\n"
        ),
    )

    # Convert _handle_batch_output to @staticmethod with self: "OutputProcessor" typing;
    # apply body rewrites in-place. Body stays in TM class.
    s, body_s, e = _method_ranges(text, "TokenizerManager", "_handle_batch_output")
    lines = text.splitlines(keepends=True)
    body_text = "".join(lines[body_s:e])

    # Body rewrites (self.server_args.X / self.enable_metrics / etc. → target class field accesses).
    body_text = body_text.replace("self.server_args.weight_version", "self.get_weight_version()")
    body_text = body_text.replace(
        "self.server_args.incremental_streaming_output",
        "self.config.incremental_streaming_output",
    )
    body_text = body_text.replace("self.server_args.skip_tokenizer_init", "self.config.skip_tokenizer_init")
    body_text = body_text.replace("self.server_args.speculative_algorithm", "self.config.speculative_algorithm")
    body_text = body_text.replace(
        "self.server_args.speculative_num_draft_tokens",
        "self.config.speculative_num_draft_tokens",
    )
    body_text = body_text.replace("self.server_args.dp_size", "self.config.dp_size")
    body_text = body_text.replace("self.server_args.batch_notify_size", "self.config.batch_notify_size")
    body_text = body_text.replace("self.server_args.enable_lora", "self.config.enable_lora")
    body_text = body_text.replace("self.enable_metrics", "self.config.enable_metrics")
    body_text = body_text.replace(
        "served_model_name=self.served_model_name,",
        "served_model_name=self.get_served_model_name(),",
    )
    body_text = body_text.replace("self.crash_dump_folder", "self.request_log_manager.crash_dump_folder")

    new_method = NEW_HANDLE_HEADER + body_text
    text = "".join(lines[:s]) + new_method + "".join(lines[e:])

    # Caller rewrite in handle_loop.
    text = replace_call_site(
        text,
        old="                await self._handle_batch_output(recv_obj)\n",
        new=(
            "                await TokenizerManager._handle_batch_output(\n"
            "                    self.output_processor, recv_obj\n"
            "                )\n"
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
