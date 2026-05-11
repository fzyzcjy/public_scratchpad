#!/usr/bin/env python3
"""Prep stage for extract-kernel-warmup (MECH_COMMIT_SPLIT §"二段式"):

Reshape ``ModelRunner.kernel_warmup`` and ``ModelRunner._flashinfer_autotune``
toward free-function form. Both become ``@staticmethod`` + kwarg-only with
many ``self.X`` reads rewritten to kwargs. ``_flashinfer_autotune`` is also
renamed to ``_run_flashinfer_autotune`` (per kw-mech-rename absorption — verb
leading reads truer). Inner call sites use class-qualified form.
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

ID = "extract-kernel-warmup-prep"
SUBJECT = "Prep kernel_warmup + _run_flashinfer_autotune for extraction"
BODY = ""
AREA = "mech_model_runner"
BASE = "tom_refactor_202605a/primary/mech_model_runner/extract-autotune-helpers-move"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


def _reshape(text: str, *, method_name: str, sig_old: str, sig_new: str, subs: list[tuple[str, str]]) -> str:
    start, end = find_method_lines(text, class_name="ModelRunner", method_name=method_name)
    lines = text.splitlines(keepends=True)
    method = "".join(lines[start:end])
    method = method.replace(sig_old, sig_new, 1)
    for old, new in subs:
        method = method.replace(old, new)
    return "".join(lines[:start]) + method + "".join(lines[end:])


def transform(wt: Path) -> None:
    mr = wt / "python/sglang/srt/model_executor/model_runner.py"
    text = mr.read_text()

    # ---- Reshape kernel_warmup (still in ModelRunner). ----
    kw_kwargs = (
        "        *,\n"
        "        device: str,\n"
        "        server_args: ServerArgs,\n"
        "        spec_algorithm: SpeculativeAlgorithm,\n"
        "        is_draft_worker: bool,\n"
        "        model_config: ModelConfig,\n"
        "        dtype: torch.dtype,\n"
        "        forward_stream: torch.cuda.Stream,\n"
        "        req_to_token_pool_size: int,\n"
        "        tp_rank: int,\n"
        "        tp_size: int,\n"
        "        pp_rank: int,\n"
        "        pp_size: int,\n"
        "        dp_rank: int,\n"
        "        dp_size: int,\n"
        "        moe_ep_size: int,\n"
        "        dummy_run_callable,\n"
    )
    text = _reshape(
        text,
        method_name="kernel_warmup",
        sig_old="    def kernel_warmup(self):\n",
        sig_new=f"    @staticmethod\n    def kernel_warmup(\n{kw_kwargs}    ):\n",
        subs=[
            # Inner call to _flashinfer_autotune — rewrite to class-qualified
            # form with the renamed identifier (kw-mech-rename absorbed here).
            (
                "        ):\n            self._flashinfer_autotune()\n",
                "        ):\n"
                "            ModelRunner._run_flashinfer_autotune(\n"
                "                server_args=server_args,\n"
                "                model_config=model_config,\n"
                "                dtype=dtype,\n"
                "                device=device,\n"
                "                forward_stream=forward_stream,\n"
                "                req_to_token_pool_size=req_to_token_pool_size,\n"
                "                tp_rank=tp_rank,\n"
                "                tp_size=tp_size,\n"
                "                pp_rank=pp_rank,\n"
                "                pp_size=pp_size,\n"
                "                dp_rank=dp_rank,\n"
                "                dp_size=dp_size,\n"
                "                moe_ep_size=moe_ep_size,\n"
                "                dummy_run_callable=dummy_run_callable,\n"
                "            )\n",
            ),
            ("self.device", "device"),
            ("self.server_args", "server_args"),
            ("self.spec_algorithm", "spec_algorithm"),
            ("self.is_draft_worker", "is_draft_worker"),
        ],
    )

    # ---- Reshape _flashinfer_autotune → _run_flashinfer_autotune. ----
    fa_kwargs = (
        "        *,\n"
        "        server_args: ServerArgs,\n"
        "        model_config: ModelConfig,\n"
        "        dtype: torch.dtype,\n"
        "        device: str,\n"
        "        forward_stream: torch.cuda.Stream,\n"
        "        req_to_token_pool_size: int,\n"
        "        tp_rank: int,\n"
        "        tp_size: int,\n"
        "        pp_rank: int,\n"
        "        pp_size: int,\n"
        "        dp_rank: int,\n"
        "        dp_size: int,\n"
        "        moe_ep_size: int,\n"
        "        dummy_run_callable,\n"
    )
    text = _reshape(
        text,
        method_name="_flashinfer_autotune",
        sig_old="    def _flashinfer_autotune(self):\n",
        sig_new=f"    @staticmethod\n    def _run_flashinfer_autotune(\n{fa_kwargs}    ):\n",
        subs=[
            (
                "self._dummy_run(batch_size=self.req_to_token_pool.size)",
                "dummy_run_callable(batch_size=req_to_token_pool_size)",
            ),
            ("self.server_args", "server_args"),
            ("self.model_config", "model_config"),
            ("self.forward_stream", "forward_stream"),
            ("self.dtype", "dtype"),
            ("self.device", "device"),
            ("self.tp_rank", "tp_rank"),
            ("self.tp_size", "tp_size"),
            ("self.pp_rank", "pp_rank"),
            ("self.pp_size", "pp_size"),
            ("self.dp_rank", "dp_rank"),
            ("self.dp_size", "dp_size"),
            ("self.moe_ep_size", "moe_ep_size"),
        ],
    )

    # ---- External caller: kernel_warmup() in initialize(). ----
    text = replace_call_site(
        text,
        old="            self.kernel_warmup()\n",
        new=(
            "            ModelRunner.kernel_warmup(\n"
            "                device=self.device,\n"
            "                server_args=self.server_args,\n"
            "                spec_algorithm=self.spec_algorithm,\n"
            "                is_draft_worker=self.is_draft_worker,\n"
            "                model_config=self.model_config,\n"
            "                dtype=self.dtype,\n"
            "                forward_stream=self.forward_stream,\n"
            "                req_to_token_pool_size=self.req_to_token_pool.size,\n"
            "                tp_rank=self.tp_rank,\n"
            "                tp_size=self.tp_size,\n"
            "                pp_rank=self.pp_rank,\n"
            "                pp_size=self.pp_size,\n"
            "                dp_rank=self.dp_rank,\n"
            "                dp_size=self.dp_size,\n"
            "                moe_ep_size=self.moe_ep_size,\n"
            "                dummy_run_callable=self._dummy_run,\n"
            "            )\n"
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
