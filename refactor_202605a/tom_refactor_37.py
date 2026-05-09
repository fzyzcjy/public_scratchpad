#!/usr/bin/env python3
"""Cut `kernel_warmup` and `_flashinfer_autotune` from ModelRunner; paste as
free functions in existing `model_executor/kernel_warmup.py`. Forward
`self._dummy_run` as `dummy_run_callable: Callable` (R4 concession).
ModelRunner methods DELETED; the sole external caller in `initialize()`
is updated to call the free function.
"""

import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.append(str(HERE))
sys.path.append(".claude/skills/mechanical-refactor-verify")
from _helpers import (
    append_to_file,
    cut_lines,
    dedent_method_to_function,
    find_method_lines,
    insert_after,
    replace_call_site,
)
from mechanical_refactor_verify_utils import (
    git_add_and_commit,
    verify_mechanical_refactor,
)

BASE_COMMIT = "tom_refactor/36"
TARGET_COMMIT = "tom_refactor/37"


def transform(dir_root: Path) -> None:
    mr = dir_root / "python/sglang/srt/model_executor/model_runner.py"
    kw = dir_root / "python/sglang/srt/model_executor/kernel_warmup.py"

    # ---- Extend kernel_warmup.py imports for Callable + logging. ----
    kw_text = kw.read_text()
    kw_text = replace_call_site(
        kw_text,
        old="from typing import Optional\n",
        new="import logging\nfrom typing import Callable, Optional\n",
    )
    kw_text = insert_after(
        kw_text,
        anchor="from sglang.srt.speculative.spec_info import SpeculativeAlgorithm\n",
        addition="\nlogger = logging.getLogger(__name__)\n",
    )
    kw.write_text(kw_text)

    # ---- Cut kernel_warmup. ----
    start, end = find_method_lines(
        mr.read_text(), class_name="ModelRunner", method_name="kernel_warmup"
    )
    method_text = cut_lines(mr, start, end)
    fn = dedent_method_to_function(method_text)
    fn = fn.replace(
        "def kernel_warmup(self):\n",
        "def kernel_warmup(\n"
        "    *,\n"
        "    device: str,\n"
        "    server_args: ServerArgs,\n"
        "    spec_algorithm: SpeculativeAlgorithm,\n"
        "    is_draft_worker: bool,\n"
        "    model_config: ModelConfig,\n"
        "    dtype: torch.dtype,\n"
        "    forward_stream: torch.cuda.Stream,\n"
        "    req_to_token_pool_size: int,\n"
        "    tp_rank: int,\n"
        "    tp_size: int,\n"
        "    pp_rank: int,\n"
        "    pp_size: int,\n"
        "    dp_rank: Optional[int],\n"
        "    dp_size: int,\n"
        "    moe_ep_size: int,\n"
        "    dummy_run_callable: Callable[..., None],\n"
        ") -> None:\n",
    )
    fn = fn.replace("self.device", "device")
    fn = fn.replace("self.server_args", "server_args")
    fn = fn.replace("self.spec_algorithm", "spec_algorithm")
    fn = fn.replace("self.is_draft_worker", "is_draft_worker")
    fn = fn.replace(
        "    ):\n        self._flashinfer_autotune()\n",
        "    ):\n"
        "        _flashinfer_autotune(\n"
        "            server_args=server_args,\n"
        "            model_config=model_config,\n"
        "            dtype=dtype,\n"
        "            device=device,\n"
        "            forward_stream=forward_stream,\n"
        "            req_to_token_pool_size=req_to_token_pool_size,\n"
        "            tp_rank=tp_rank,\n"
        "            tp_size=tp_size,\n"
        "            pp_rank=pp_rank,\n"
        "            pp_size=pp_size,\n"
        "            dp_rank=dp_rank,\n"
        "            dp_size=dp_size,\n"
        "            moe_ep_size=moe_ep_size,\n"
        "            dummy_run_callable=dummy_run_callable,\n"
        "        )\n",
    )
    append_to_file(kw, fn)

    # ---- Cut _flashinfer_autotune. ----
    start, end = find_method_lines(
        mr.read_text(), class_name="ModelRunner", method_name="_flashinfer_autotune"
    )
    method_text = cut_lines(mr, start, end)
    fn = dedent_method_to_function(method_text)
    fn = fn.replace(
        "def _flashinfer_autotune(self):\n",
        "def _flashinfer_autotune(\n"
        "    *,\n"
        "    server_args: ServerArgs,\n"
        "    model_config: ModelConfig,\n"
        "    dtype: torch.dtype,\n"
        "    device: str,\n"
        "    forward_stream: torch.cuda.Stream,\n"
        "    req_to_token_pool_size: int,\n"
        "    tp_rank: int,\n"
        "    tp_size: int,\n"
        "    pp_rank: int,\n"
        "    pp_size: int,\n"
        "    dp_rank: Optional[int],\n"
        "    dp_size: int,\n"
        "    moe_ep_size: int,\n"
        "    dummy_run_callable: Callable[..., None],\n"
        ") -> None:\n",
    )
    # Substitute self.X → kwarg references throughout the body. Do longer
    # paths first so they don't get partially eaten by shorter ones.
    fn = fn.replace("self._dummy_run(batch_size=self.req_to_token_pool.size)",
                    "dummy_run_callable(batch_size=req_to_token_pool_size)")
    fn = fn.replace("self.server_args", "server_args")
    fn = fn.replace("self.model_config", "model_config")
    fn = fn.replace("self.forward_stream", "forward_stream")
    fn = fn.replace("self.dtype", "dtype")
    fn = fn.replace("self.device", "device")
    fn = fn.replace("self.tp_rank", "tp_rank")
    fn = fn.replace("self.tp_size", "tp_size")
    fn = fn.replace("self.pp_rank", "pp_rank")
    fn = fn.replace("self.pp_size", "pp_size")
    fn = fn.replace("self.dp_rank", "dp_rank")
    fn = fn.replace("self.dp_size", "dp_size")
    fn = fn.replace("self.moe_ep_size", "moe_ep_size")
    append_to_file(kw, fn)

    # ---- Update model_runner.py: caller in initialize() + import. ----
    text = mr.read_text()

    text = replace_call_site(
        text,
        old="            self.kernel_warmup()\n",
        new=(
            "            kernel_warmup(\n"
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

    # Extend the existing kernel_warmup import to also pull in `kernel_warmup`.
    old_import = (
        "from sglang.srt.model_executor.kernel_warmup import (\n"
        "    _flashinfer_autotune_cache_path,\n"
        "    _should_run_flashinfer_autotune,\n"
        ")\n"
    )
    new_import = (
        "from sglang.srt.model_executor.kernel_warmup import (\n"
        "    _flashinfer_autotune_cache_path,\n"
        "    _should_run_flashinfer_autotune,\n"
        "    kernel_warmup,\n"
        ")\n"
    )
    text = replace_call_site(text, old=old_import, new=new_import)

    mr.write_text(text)

    git_add_and_commit(
        "Extract kernel_warmup and _flashinfer_autotune to free functions",
        cwd=str(dir_root),
    )


if __name__ == "__main__":
    verify_mechanical_refactor(
        base_commit=BASE_COMMIT,
        target_commit=TARGET_COMMIT,
        transform=transform,
    )
