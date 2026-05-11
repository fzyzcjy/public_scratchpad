#!/usr/bin/env python3
"""Prep stage for extract-dummy-run (MECH_COMMIT_SPLIT §"二段式"):

Reshape ``ModelRunner._dummy_run`` toward free-function form. ``@staticmethod``
+ kwarg-only signature with 10 params (8 ``self.X`` + ``batch_size`` +
``run_ctx``); body's 8 ``self.X`` reads rewritten to bare kwarg names.
The ``dummy_run_callable`` callback in ``initialize()`` becomes a lambda
capturing the 8 fields. Privacy flip: the leading underscore drops at
extraction (free function, not a private method).
"""

# /// script
# requires-python = ">=3.10"
# dependencies = ["typer"]
# ///

import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from _helpers import find_method_lines, replace_call_site
from _runner import run_pr

ID = "extract-dummy-run-prep"
SUBJECT = "Prep _dummy_run for extraction: @staticmethod + kwargs + drop privacy"
BODY = ""
AREA = "mech_model_runner"
BASE = "tom_refactor_202605a/primary/mech_model_runner/extract-kernel-warmup-move"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


_KWARGS = (
    "        *,\n"
    "        batch_size: int,\n"
    "        is_generation: bool,\n"
    "        spec_algorithm: SpeculativeAlgorithm,\n"
    "        is_draft_worker: bool,\n"
    "        server_args: ServerArgs,\n"
    "        attn_backend: object,\n"
    "        device: str,\n"
    "        model: torch.nn.Module,\n"
    "        model_config: ModelConfig,\n"
    "        req_to_token_pool,\n"
    "        token_to_kv_pool,\n"
    "        lora_manager,\n"
    "        tp_group,\n"
    "        run_ctx=None,\n"
)


def transform(wt: Path) -> None:
    mr = wt / "python/sglang/srt/model_executor/model_runner.py"
    text = mr.read_text()

    start, end = find_method_lines(text, class_name="ModelRunner", method_name="_dummy_run")
    lines = text.splitlines(keepends=True)
    method = "".join(lines[start:end])
    method = method.replace(
        "    def _dummy_run(self, batch_size: int, run_ctx=None):\n",
        f"    @staticmethod\n    def dummy_run(\n{_KWARGS}    ):\n",
        1,
    )
    # Body subs: each ``self.X`` (12 fields) → bare kwarg. Order:
    # longer/more-specific first so ``self.model_config`` doesn't get
    # half-rewritten by ``self.model``.
    for name in (
        "is_generation",
        "spec_algorithm",
        "is_draft_worker",
        "server_args",
        "attn_backend",
        "device",
        "model_config",
        "req_to_token_pool",
        "token_to_kv_pool",
        "lora_manager",
        "tp_group",
        "model",
    ):
        method = method.replace(f"self.{name}", name)
    text = "".join(lines[:start]) + method + "".join(lines[end:])

    # Callback in initialize(): bound-method form → lambda capturing 8 fields.
    text = replace_call_site(
        text,
        old="                dummy_run_callable=self._dummy_run,\n",
        new=(
            "                dummy_run_callable=lambda batch_size: ModelRunner.dummy_run(\n"
            "                    batch_size=batch_size,\n"
            "                    is_generation=self.is_generation,\n"
            "                    spec_algorithm=self.spec_algorithm,\n"
            "                    is_draft_worker=self.is_draft_worker,\n"
            "                    server_args=self.server_args,\n"
            "                    attn_backend=self.attn_backend,\n"
            "                    device=self.device,\n"
            "                    model=self.model,\n"
            "                    model_config=self.model_config,\n"
            "                    req_to_token_pool=self.req_to_token_pool,\n"
            "                    token_to_kv_pool=self.token_to_kv_pool,\n"
            "                    lora_manager=self.lora_manager,\n"
            "                    tp_group=self.tp_group,\n"
            "                    run_ctx=None,\n"
            "                ),\n"
        ),
    )
    mr.write_text(text)


if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        area_branch=AREA_BRANCH,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
