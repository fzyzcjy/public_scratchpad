#!/usr/bin/env python3
"""Move ``resolve_language_model`` free function from ``model_runner.py`` to
``model_loader/utils.py``.

Per `module_level.md`, ``resolve_language_model`` is a model-object probe
(unwraps multimodal / wrapper classes to the language-model submodule) and
does not belong on ModelRunner. The natural home is ``model_loader/utils.py``
which already hosts model-loading helpers and imports ``torch`` + ``nn``.

- Cut the function via ``find_function_lines`` + ``cut_lines``.
- Append to ``model_loader/utils.py`` byte-for-byte. ``nn`` is already
  imported there; no extra imports needed.
- ``model_runner.py``: add a top-level ``from sglang.srt.model_loader.utils
  import resolve_language_model`` so the existing kwarg pass-through at the
  call site (``init_piecewise_cuda_graphs(..., resolve_language_model=
  resolve_language_model)``) keeps resolving to the same symbol.
- The local-import call site in ``fp4_kv_cache_quant_method.py`` is rewired
  to the new module path.

Usage:
    uv run --python 3.12 move-resolve-language-model.py run
    uv run --python 3.12 move-resolve-language-model.py verify
"""

# /// script
# requires-python = ">=3.10"
# dependencies = ["typer"]
# ///

import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from _helpers import (
    append_to_file,
    cut_lines,
    find_function_lines,
    insert_after,
    replace_call_site,
)
from _runner import run_pr

ID = "move-resolve-language-model"
SUBJECT = "Move resolve_language_model from model_runner.py to model_loader/utils.py"
BODY = ""
AREA = "mech_model_runner"
BASE = "tom_refactor_202605a/raw/mech_model_runner/move-rank-zero-filter"
TARGET = f"tom_refactor_202605a/raw/{AREA}/{ID}"


def transform(wt: Path) -> None:
    mr = wt / "python/sglang/srt/model_executor/model_runner.py"
    ml_utils = wt / "python/sglang/srt/model_loader/utils.py"
    fp4 = wt / "python/sglang/srt/layers/quantization/fp4_kv_cache_quant_method.py"

    s, e = find_function_lines(mr.read_text(), function_name="resolve_language_model")
    func_text = cut_lines(mr, s, e)

    append_to_file(ml_utils, func_text.rstrip() + "\n")

    # ModelRunner still references the symbol at the
    # ``init_piecewise_cuda_graphs`` call site (kwarg pass-through). Add an
    # import so the name resolves; place after the existing ``model_loader``
    # imports cluster (anchor: ``set_default_torch_dtype`` is already imported
    # from the same module elsewhere in the chain, but we use a fresh anchor
    # tied to ModelConfig from ``configs.model_config`` to stay independent).
    text = mr.read_text()
    text = insert_after(
        text,
        anchor="from sglang.srt.constants import GPU_MEMORY_TYPE_WEIGHTS\n",
        addition=(
            "from sglang.srt.model_loader.utils import resolve_language_model\n"
        ),
    )
    mr.write_text(text)

    # fp4 caller: rewrite local-import path.
    text = fp4.read_text()
    text = replace_call_site(
        text,
        old="from sglang.srt.model_executor.model_runner import resolve_language_model",
        new="from sglang.srt.model_loader.utils import resolve_language_model",
    )
    fp4.write_text(text)

if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        target=TARGET,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
