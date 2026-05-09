#!/usr/bin/env python3
"""Reproducible transform: extract `save_remote_model`, `save_sharded_model`,
and `get_weights_by_name` from `ModelRunner` into free functions in
`sglang.srt.model_executor.weight_exporter`. The ModelRunner methods become
1-line delegates that pass the minimal state explicitly via kwargs (`model`,
`model_config_model_path`, `tp_size`).

Run from the repo root:
    python3 /tmp/transform_weight_exporter_save.py
"""

import sys
from pathlib import Path

sys.path.append(".claude/skills/mechanical-refactor-verify")
from mechanical_refactor_verify_utils import (
    verify_mechanical_refactor,
    git_add_and_commit,
)

BASE_COMMIT = "tom_refactor/29"
TARGET_COMMIT = "tom_refactor/30"


APPENDED_FREE_FUNCTIONS = '''

from typing import Optional


def save_remote_model(*, model, model_config_model_path, url):
    from sglang.srt.model_loader.loader import RemoteModelLoader

    logger.info(f"Saving model to {url}")
    RemoteModelLoader.save_model(model, model_config_model_path, url)


def save_sharded_model(
    *, model, path, pattern=None, max_size=None,
):
    from sglang.srt.model_loader.loader import ShardedStateLoader

    logger.info(
        f"Save sharded model to {path} with pattern {pattern} and max_size {max_size}"
    )
    ShardedStateLoader.save_model(model, path, pattern, max_size)


def get_weights_by_name(
    *, model, tp_size, name, truncate_size=100,
):
    """Get the weights of the parameter by its name. Similar to `get_parameter` in Hugging Face.

    Only used for unit test with an unoptimized performance.
    For optimized performance, please use torch.save and torch.load.
    """
    # TODO: (chenyang) Add support for Qwen models.
    try:
        return model.get_weights_by_name(
            name, truncate_size, tp_size=tp_size
        )
    except Exception as e:
        logger.error(f"Error when getting parameter {name}: {e}")
        return None
'''


def transform(dir_root: Path) -> None:
    # --- Step 1: append free functions to weight_exporter.py ---
    new_file = dir_root / "python/sglang/srt/model_executor/weight_exporter.py"
    text = new_file.read_text()
    text = text.rstrip() + "\n" + APPENDED_FREE_FUNCTIONS
    new_file.write_text(text)

    # --- Step 2: update model_runner.py ---
    mr = dir_root / "python/sglang/srt/model_executor/model_runner.py"
    text = mr.read_text()

    # /29 added one import per name. Append three more imports same style.
    old_imp = (
        "from sglang.srt.model_executor.weight_exporter import (\n"
        "    send_weights_to_remote_instance as _free_send_weights_to_remote_instance,\n"
        ")\n"
    )
    new_imp = (
        "from sglang.srt.model_executor.weight_exporter import (\n"
        "    send_weights_to_remote_instance as _free_send_weights_to_remote_instance,\n"
        ")\n"
        "from sglang.srt.model_executor.weight_exporter import (\n"
        "    get_weights_by_name as _free_get_weights_by_name,\n"
        ")\n"
        "from sglang.srt.model_executor.weight_exporter import (\n"
        "    save_remote_model as _free_save_remote_model,\n"
        ")\n"
        "from sglang.srt.model_executor.weight_exporter import (\n"
        "    save_sharded_model as _free_save_sharded_model,\n"
        ")\n"
    )
    assert old_imp in text, "weight_exporter import block not found"
    text = text.replace(old_imp, new_imp)

    # Replace get_weights_by_name body with delegate.
    old_get = (
        "    def get_weights_by_name(\n"
        "        self, name: str, truncate_size: int = 100\n"
        "    ) -> Optional[torch.Tensor]:\n"
        '        """Get the weights of the parameter by its name. Similar to `get_parameter` in Hugging Face.\n'
        "\n"
        "        Only used for unit test with an unoptimized performance.\n"
        "        For optimized performance, please use torch.save and torch.load.\n"
        '        """\n'
        "        # TODO: (chenyang) Add support for Qwen models.\n"
        "        try:\n"
        "            return self.model.get_weights_by_name(\n"
        "                name, truncate_size, tp_size=self.tp_size\n"
        "            )\n"
        "        except Exception as e:\n"
        '            logger.error(f"Error when getting parameter {name}: {e}")\n'
        "            return None\n"
    )
    new_get = (
        "    def get_weights_by_name(\n"
        "        self, name: str, truncate_size: int = 100\n"
        "    ) -> Optional[torch.Tensor]:\n"
        "        return _free_get_weights_by_name(\n"
        "            model=self.model,\n"
        "            tp_size=self.tp_size,\n"
        "            name=name,\n"
        "            truncate_size=truncate_size,\n"
        "        )\n"
    )
    assert old_get in text, "get_weights_by_name body not found"
    text = text.replace(old_get, new_get)

    # Replace save_remote_model body with delegate.
    old_save_remote = (
        "    def save_remote_model(self, url: str):\n"
        "        from sglang.srt.model_loader.loader import RemoteModelLoader\n"
        "\n"
        '        logger.info(f"Saving model to {url}")\n'
        "        RemoteModelLoader.save_model(self.model, self.model_config.model_path, url)\n"
    )
    new_save_remote = (
        "    def save_remote_model(self, url: str):\n"
        "        return _free_save_remote_model(\n"
        "            model=self.model,\n"
        "            model_config_model_path=self.model_config.model_path,\n"
        "            url=url,\n"
        "        )\n"
    )
    assert old_save_remote in text, "save_remote_model body not found"
    text = text.replace(old_save_remote, new_save_remote)

    # Replace save_sharded_model body with delegate.
    old_save_sharded = (
        "    def save_sharded_model(\n"
        "        self, path: str, pattern: Optional[str] = None, max_size: Optional[int] = None\n"
        "    ):\n"
        "        from sglang.srt.model_loader.loader import ShardedStateLoader\n"
        "\n"
        "        logger.info(\n"
        '            f"Save sharded model to {path} with pattern {pattern} and max_size {max_size}"\n'
        "        )\n"
        "        ShardedStateLoader.save_model(self.model, path, pattern, max_size)\n"
    )
    new_save_sharded = (
        "    def save_sharded_model(\n"
        "        self, path: str, pattern: Optional[str] = None, max_size: Optional[int] = None\n"
        "    ):\n"
        "        return _free_save_sharded_model(\n"
        "            model=self.model,\n"
        "            path=path,\n"
        "            pattern=pattern,\n"
        "            max_size=max_size,\n"
        "        )\n"
    )
    assert old_save_sharded in text, "save_sharded_model body not found"
    text = text.replace(old_save_sharded, new_save_sharded)

    mr.write_text(text)

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
