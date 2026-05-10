#!/usr/bin/env python3
"""Move ``update_weights_from_distributed`` and the private helper
``_update_bucketed_weights_from_distributed`` onto ``WeightUpdater``.

- Both methods cut from ModelRunner and pasted (still as instance methods)
  onto WeightUpdater. Bodies rewrite ``self.model`` -> ``self._mr.model`` and
  ``self.device`` -> ``self._mr.device``; ``self._model_update_group`` and
  ``self.weight_updater._model_update_group`` (introduced in /24 for the
  in-class references) both collapse to ``self._model_update_group`` since
  the dict already lives on WeightUpdater.
- Methods deleted from ModelRunner.
- ``tp_worker.py`` caller rewritten to
  ``self.model_runner.weight_updater.update_weights_from_distributed(...)``
  with positional args preserved.

Usage:
    uv run --python 3.12 tom_refactor_26.py run
    uv run --python 3.12 tom_refactor_26.py verify
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
    find_method_lines,
    insert_after,
    replace_call_site,
)
from _runner import run_pr

BASE = "tom_refactor/25"
TARGET = "tom_refactor/26"


def _rewrite_self(method_text: str) -> str:
    """Convert ModelRunner-side ``self.X`` references inside the cut body to
    use the WeightUpdater back-ref (``self._mr.X``). Order matters: the
    longer ``self.weight_updater._model_update_group`` substring (introduced
    by /24 to keep ModelRunner compilable) must collapse to
    ``self._model_update_group`` -- the dict is already a WeightUpdater field.
    """
    method_text = method_text.replace(
        "self.weight_updater._model_update_group", "self._model_update_group"
    )
    method_text = method_text.replace("self.model.load_weights", "self._mr.model.load_weights")
    method_text = method_text.replace("self.device", "self._mr.device")
    return method_text


def transform(wt: Path) -> None:
    sys.path.insert(0, str(wt / ".claude/skills/mechanical-refactor-verify"))
    from mechanical_refactor_verify_utils import git_add_and_commit

    mr = wt / "python/sglang/srt/model_executor/model_runner.py"
    wu = wt / "python/sglang/srt/model_executor/weight_updater.py"
    tw = wt / "python/sglang/srt/managers/tp_worker.py"

    # Cut bottom-up so earlier line ranges stay valid.
    s, e = find_method_lines(
        mr.read_text(),
        class_name="ModelRunner",
        method_name="_update_bucketed_weights_from_distributed",
    )
    bucketed_text = _rewrite_self(cut_lines(mr, s, e))

    s, e = find_method_lines(
        mr.read_text(),
        class_name="ModelRunner",
        method_name="update_weights_from_distributed",
    )
    # ``update_weights_from_distributed`` body calls
    # ``self._update_bucketed_weights_from_distributed(...)`` -- that helper
    # also moves to WeightUpdater so the call stays intact (no rewrite).
    uwd_text = _rewrite_self(cut_lines(mr, s, e))

    # weight_updater.py: import ``FlattenedTensorBucket`` for the new method
    # body, then append both methods inside the class.
    text = wu.read_text()
    # Pre-commit's isort merged `get_available_gpu_memory` and
    # `init_custom_process_group` into a single `from sglang.srt.utils import`
    # line. Anchor on that combined form (the canonical sorted output).
    text = insert_after(
        text,
        anchor="from sglang.srt.utils import get_available_gpu_memory, init_custom_process_group\n",
        addition="from sglang.srt.weight_sync.tensor_bucket import FlattenedTensorBucket\n",
    )
    wu.write_text(text)
    append_to_file(
        wu,
        uwd_text.rstrip() + "\n\n" + bucketed_text.rstrip() + "\n",
        separator="\n",
    )

    # tp_worker.py: rewrite caller.
    text = tw.read_text()
    text = replace_call_site(
        text,
        old="        success, message = self.model_runner.update_weights_from_distributed(\n",
        new="        success, message = self.model_runner.weight_updater.update_weights_from_distributed(\n",
    )
    tw.write_text(text)

    git_add_and_commit(
        "Move update_weights_from_distributed onto WeightUpdater",
        cwd=str(wt),
    )


if __name__ == "__main__":
    run_pr(transform=transform, base=BASE, target=TARGET)
