#!/usr/bin/env python3
"""Prep stage for extract-autotune-helpers (MECH_COMMIT_SPLIT §"二段式"):

Reshape two leaf methods on ModelRunner toward free-function form:
``_should_run_flashinfer_autotune`` and ``_flashinfer_autotune_cache_path``.
Both become ``@staticmethod`` + kwarg-only; their three / eleven ``self.X``
reads become kwargs. Both in-class call sites become class-qualified.
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

ID = "extract-autotune-helpers-prep"
SUBJECT = "Prep _should_run_flashinfer_autotune and _flashinfer_autotune_cache_path for extraction"
BODY = ""
AREA = "mech_model_runner"
BASE = "tom_refactor_202605a/primary/mech_model_runner/drop-hybrid-arch-delegates"
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

    text = _reshape(
        text,
        method_name="_should_run_flashinfer_autotune",
        sig_old="    def _should_run_flashinfer_autotune(self) -> bool:\n",
        sig_new=(
            "    @staticmethod\n"
            "    def _should_run_flashinfer_autotune(\n"
            "        *,\n"
            "        server_args: ServerArgs,\n"
            "        spec_algorithm: SpeculativeAlgorithm,\n"
            "        is_draft_worker: bool,\n"
            "    ) -> bool:\n"
        ),
        subs=[
            ("self.server_args", "server_args"),
            ("self.spec_algorithm", "spec_algorithm"),
            ("self.is_draft_worker", "is_draft_worker"),
        ],
    )

    text = _reshape(
        text,
        method_name="_flashinfer_autotune_cache_path",
        sig_old="    def _flashinfer_autotune_cache_path(self) -> Path:\n",
        sig_new=(
            "    @staticmethod\n"
            "    def _flashinfer_autotune_cache_path(\n"
            "        *,\n"
            "        server_args: ServerArgs,\n"
            "        model_config: ModelConfig,\n"
            "        dtype: torch.dtype,\n"
            "        device: str,\n"
            "        tp_rank: int,\n"
            "        tp_size: int,\n"
            "        pp_rank: int,\n"
            "        pp_size: int,\n"
            "        dp_rank: int,\n"
            "        dp_size: int,\n"
            "        moe_ep_size: int,\n"
            "    ) -> Path:\n"
        ),
        subs=[
            ("torch.cuda.get_device_capability(self.device)", "torch.cuda.get_device_capability(device)"),
            ("self.server_args", "server_args"),
            ("self.dtype", "dtype"),
            ("self.tp_size", "tp_size"),
            ("self.pp_size", "pp_size"),
            ("self.dp_size", "dp_size"),
            ("self.moe_ep_size", "moe_ep_size"),
            ("self.model_config", "model_config"),
            ("self.tp_rank", "tp_rank"),
            ("self.pp_rank", "pp_rank"),
            ("self.dp_rank", "dp_rank"),
        ],
    )

    # In-class call sites (still inside ``kernel_warmup`` / ``_flashinfer_autotune``
    # on ModelRunner). Switch to class-qualified form.
    text = replace_call_site(
        text,
        old="if self._should_run_flashinfer_autotune():",
        new=(
            "if ModelRunner._should_run_flashinfer_autotune(\n"
            "            server_args=self.server_args,\n"
            "            spec_algorithm=self.spec_algorithm,\n"
            "            is_draft_worker=self.is_draft_worker,\n"
            "        ):"
        ),
    )
    text = replace_call_site(
        text,
        old="cache_path = self._flashinfer_autotune_cache_path()",
        new=(
            "cache_path = ModelRunner._flashinfer_autotune_cache_path(\n"
            "            server_args=self.server_args,\n"
            "            model_config=self.model_config,\n"
            "            dtype=self.dtype,\n"
            "            device=self.device,\n"
            "            tp_rank=self.tp_rank,\n"
            "            tp_size=self.tp_size,\n"
            "            pp_rank=self.pp_rank,\n"
            "            pp_size=self.pp_size,\n"
            "            dp_rank=self.dp_rank,\n"
            "            dp_size=self.dp_size,\n"
            "            moe_ep_size=self.moe_ep_size,\n"
            "        )"
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
