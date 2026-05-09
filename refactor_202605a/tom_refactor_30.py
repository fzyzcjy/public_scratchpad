#!/usr/bin/env python3
"""Cut `save_remote_model`, `save_sharded_model`, `get_weights_by_name` from
ModelRunner; paste as free functions in `weight_exporter.py`. Update tp_worker
and scheduler_update_weights_mixin call sites.
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
)
from mechanical_refactor_verify_utils import (
    git_add_and_commit,
    verify_mechanical_refactor,
)

BASE_COMMIT = "tom_refactor/29"
TARGET_COMMIT = "tom_refactor/30"


def transform(dir_root: Path) -> None:
    mr = dir_root / "python/sglang/srt/model_executor/model_runner.py"
    we = dir_root / "python/sglang/srt/model_executor/weight_exporter.py"
    tw = dir_root / "python/sglang/srt/managers/tp_worker.py"
    sm = dir_root / "python/sglang/srt/managers/scheduler_update_weights_mixin.py"

    s, e = find_method_lines(mr.read_text(), class_name="ModelRunner", method_name="save_sharded_model")
    sharded_text = dedent_method_to_function(cut_lines(mr, s, e)).replace(
        "def save_sharded_model(\n    self, path: str, pattern: Optional[str] = None, max_size: Optional[int] = None\n):",
        "def save_sharded_model(\n    *, model, path, pattern=None, max_size=None,\n):",
    ).replace("self.model", "model")

    s, e = find_method_lines(mr.read_text(), class_name="ModelRunner", method_name="save_remote_model")
    remote_text = dedent_method_to_function(cut_lines(mr, s, e)).replace(
        "def save_remote_model(self, url: str):",
        "def save_remote_model(*, model, model_path, url):",
    ).replace(
        "RemoteModelLoader.save_model(self.model, self.model_config.model_path, url)",
        "RemoteModelLoader.save_model(model, model_path, url)",
    )

    s, e = find_method_lines(mr.read_text(), class_name="ModelRunner", method_name="get_weights_by_name")
    gwbn_text = dedent_method_to_function(cut_lines(mr, s, e)).replace(
        "def get_weights_by_name(\n    self, name: str, truncate_size: int = 100\n) -> Optional[torch.Tensor]:",
        "def get_weights_by_name(*, model, tp_size, name, truncate_size=100):",
    ).replace(
        "self.model.get_weights_by_name(\n            name, truncate_size, tp_size=self.tp_size\n        )",
        "model.get_weights_by_name(\n            name, truncate_size, tp_size=tp_size\n        )",
    )

    append_to_file(we, remote_text + "\n" + sharded_text + "\n" + gwbn_text)

    text = tw.read_text()
    text = text.replace(
        "    send_weights_to_remote_instance as _free_send_weights_to_remote_instance,\n)\n",
        "    send_weights_to_remote_instance as _free_send_weights_to_remote_instance,\n)\n"
        "from sglang.srt.model_executor.weight_exporter import (\n"
        "    get_weights_by_name as _free_get_weights_by_name,\n"
        "    save_remote_model as _free_save_remote_model,\n"
        "    save_sharded_model as _free_save_sharded_model,\n"
        ")\n",
    )
    text = text.replace(
        "        parameter = self.model_runner.get_weights_by_name(\n"
        "            recv_req.name, recv_req.truncate_size\n"
        "        )\n",
        "        parameter = _free_get_weights_by_name(\n"
        "            model=self.model_runner.model,\n"
        "            tp_size=self.model_runner.tp_size,\n"
        "            name=recv_req.name,\n"
        "            truncate_size=recv_req.truncate_size,\n"
        "        )\n",
    )
    tw.write_text(text)

    text = sm.read_text()
    text = text.replace(
        "        self.tp_worker.model_runner.save_remote_model(url)\n",
        "        _free_save_remote_model(\n"
        "            model=self.tp_worker.model_runner.model,\n"
        "            model_path=self.tp_worker.model_runner.model_config.model_path,\n"
        "            url=url,\n"
        "        )\n",
    )
    text = text.replace(
        "            self.draft_worker.model_runner.save_remote_model(draft_url)\n",
        "            _free_save_remote_model(\n"
        "                model=self.draft_worker.model_runner.model,\n"
        "                model_path=self.draft_worker.model_runner.model_config.model_path,\n"
        "                url=draft_url,\n"
        "            )\n",
    )
    text = text.replace(
        "        self.tp_worker.model_runner.save_sharded_model(\n"
        "            path=params[\"path\"],\n"
        "            pattern=params[\"pattern\"],\n"
        "            max_size=params[\"max_size\"],\n"
        "        )\n",
        "        _free_save_sharded_model(\n"
        "            model=self.tp_worker.model_runner.model,\n"
        "            path=params[\"path\"],\n"
        "            pattern=params[\"pattern\"],\n"
        "            max_size=params[\"max_size\"],\n"
        "        )\n",
    )
    text = (
        "from sglang.srt.model_executor.weight_exporter import (\n"
        "    save_remote_model as _free_save_remote_model,\n"
        "    save_sharded_model as _free_save_sharded_model,\n"
        ")\n" + text
    )
    sm.write_text(text)

    git_add_and_commit(
        "Extract weight save and get_weights_by_name to free functions in weight_exporter",
        cwd=str(dir_root),
    )


if __name__ == "__main__":
    verify_mechanical_refactor(
        base_commit=BASE_COMMIT,
        target_commit=TARGET_COMMIT,
        transform=transform,
    )
