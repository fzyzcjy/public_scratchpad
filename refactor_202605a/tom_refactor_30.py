#!/usr/bin/env python3
"""Cut `save_remote_model`, `save_sharded_model`, `get_weights_by_name` from
ModelRunner; paste as free functions in `weight_exporter.py`. Update
tp_worker.py and scheduler_update_weights_mixin.py call sites.

Usage:
    uv run --python 3.12 tom_refactor_30.py run
    uv run --python 3.12 tom_refactor_30.py verify
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
    dedent_method_to_function,
    find_method_lines,
    insert_after,
    replace_call_site,
)
from _runner import run_pr

BASE = "tom_refactor/29"
TARGET = "tom_refactor/30"


def transform(wt: Path) -> None:
    sys.path.insert(0, str(wt / ".claude/skills/mechanical-refactor-verify"))
    from mechanical_refactor_verify_utils import git_add_and_commit

    mr = wt / "python/sglang/srt/model_executor/model_runner.py"
    we = wt / "python/sglang/srt/model_executor/weight_exporter.py"
    tw = wt / "python/sglang/srt/managers/tp_worker.py"
    sm = wt / "python/sglang/srt/managers/scheduler_update_weights_mixin.py"

    s, e = find_method_lines(
        mr.read_text(), class_name="ModelRunner", method_name="save_sharded_model"
    )
    sharded_text = (
        dedent_method_to_function(cut_lines(mr, s, e))
        .replace(
            "def save_sharded_model(\n"
            "    self, path: str, pattern: Optional[str] = None, max_size: Optional[int] = None\n"
            "):",
            "def save_sharded_model(\n"
            "    *,\n"
            "    model,\n"
            "    path: str,\n"
            "    pattern: Optional[str] = None,\n"
            "    max_size: Optional[int] = None,\n"
            "):",
        )
        .replace("self.model", "model")
    )

    s, e = find_method_lines(
        mr.read_text(), class_name="ModelRunner", method_name="save_remote_model"
    )
    remote_text = (
        dedent_method_to_function(cut_lines(mr, s, e))
        .replace(
            "def save_remote_model(self, url: str):",
            "def save_remote_model(*, model, model_path, url: str):",
        )
        .replace(
            "RemoteModelLoader.save_model(self.model, self.model_config.model_path, url)",
            "RemoteModelLoader.save_model(model, model_path, url)",
        )
    )

    s, e = find_method_lines(
        mr.read_text(), class_name="ModelRunner", method_name="get_weights_by_name"
    )
    gwbn_text = (
        dedent_method_to_function(cut_lines(mr, s, e))
        .replace(
            "def get_weights_by_name(\n"
            "    self, name: str, truncate_size: int = 100\n"
            ") -> Optional[torch.Tensor]:",
            "def get_weights_by_name(\n"
            "    *,\n"
            "    model,\n"
            "    tp_size,\n"
            "    name: str,\n"
            "    truncate_size: int = 100,\n"
            ") -> Optional[torch.Tensor]:",
        )
        .replace(
            "self.model.get_weights_by_name(\n"
            "            name, truncate_size, tp_size=self.tp_size\n"
            "        )",
            "model.get_weights_by_name(\n"
            "            name, truncate_size, tp_size=tp_size\n"
            "        )",
        )
    )

    append_to_file(we, remote_text + "\n" + sharded_text + "\n" + gwbn_text)

    # tp_worker.py already imports `weight_exporter` (added in /29); just
    # rewrite the call site.
    text = tw.read_text()
    if "from sglang.srt.model_executor import weight_exporter\n" not in text:
        text = insert_after(
            text,
            anchor="from sglang.srt.model_executor.forward_batch_info import ForwardBatch, PPProxyTensors\n",
            addition="from sglang.srt.model_executor import weight_exporter\n",
        )
    text = replace_call_site(
        text,
        old=(
            "        parameter = self.model_runner.get_weights_by_name(\n"
            "            recv_req.name, recv_req.truncate_size\n"
            "        )\n"
        ),
        new=(
            "        parameter = weight_exporter.get_weights_by_name(\n"
            "            model=self.model_runner.model,\n"
            "            tp_size=self.model_runner.tp_size,\n"
            "            name=recv_req.name,\n"
            "            truncate_size=recv_req.truncate_size,\n"
            "        )\n"
        ),
    )
    tw.write_text(text)

    text = sm.read_text()
    if "from sglang.srt.model_executor import weight_exporter\n" not in text:
        text = "from sglang.srt.model_executor import weight_exporter\n" + text
    text = replace_call_site(
        text,
        old="        self.tp_worker.model_runner.save_remote_model(url)\n",
        new=(
            "        weight_exporter.save_remote_model(\n"
            "            model=self.tp_worker.model_runner.model,\n"
            "            model_path=self.tp_worker.model_runner.model_config.model_path,\n"
            "            url=url,\n"
            "        )\n"
        ),
    )
    text = replace_call_site(
        text,
        old="            self.draft_worker.model_runner.save_remote_model(draft_url)\n",
        new=(
            "            weight_exporter.save_remote_model(\n"
            "                model=self.draft_worker.model_runner.model,\n"
            "                model_path=self.draft_worker.model_runner.model_config.model_path,\n"
            "                url=draft_url,\n"
            "            )\n"
        ),
    )
    text = replace_call_site(
        text,
        old=(
            "        self.tp_worker.model_runner.save_sharded_model(\n"
            '            path=params["path"],\n'
            '            pattern=params["pattern"],\n'
            '            max_size=params["max_size"],\n'
            "        )\n"
        ),
        new=(
            "        weight_exporter.save_sharded_model(\n"
            "            model=self.tp_worker.model_runner.model,\n"
            '            path=params["path"],\n'
            '            pattern=params["pattern"],\n'
            '            max_size=params["max_size"],\n'
            "        )\n"
        ),
    )
    sm.write_text(text)

    git_add_and_commit(
        "Extract weight save and get_weights_by_name to free functions in weight_exporter",
        cwd=str(wt),
    )


if __name__ == "__main__":
    run_pr(transform=transform, base=BASE, target=TARGET)
