#!/usr/bin/env python3
"""Reproducible transform: extract `update_weights_from_distributed` and
`_update_bucketed_weights_from_distributed` from `ModelRunner` into free
functions in `sglang.srt.model_executor.weight_updater`. The ModelRunner
methods become 1-line delegates that pass the minimal state explicitly via
kwargs (`model`, `_model_update_group`, `device`).

Run from the repo root:
    python3 /tmp/transform_update_weights_from_distributed.py
"""

import sys
from pathlib import Path

sys.path.append(".claude/skills/mechanical-refactor-verify")
from mechanical_refactor_verify_utils import (
    verify_mechanical_refactor,
    git_add_and_commit,
)

BASE_COMMIT = "tom_refactor/25"
TARGET_COMMIT = "tom_refactor/26"


APPENDED_FREE_FUNCTIONS = '''

from sglang.srt.weight_sync.tensor_bucket import FlattenedTensorBucket


def update_weights_from_distributed(
    *,
    model,
    _model_update_group,
    device,
    names,
    dtypes,
    shapes,
    group_name,
    load_format=None,
):
    """
    Update specific parameter in the model weights online
    through `_model_update_group` process group.

    Args:
        name: the name of the parameter to be updated.
        dtype: the data type of the parameter to be updated.
        shape: the shape of the parameter to be updated.
    """

    assert group_name in _model_update_group, (
        f"Group {group_name} not in {list(_model_update_group.keys())}. "
        "Please call `init_weights_update_group` first."
    )

    if load_format == "flattened_bucket":
        return _update_bucketed_weights_from_distributed(
            model=model,
            _model_update_group=_model_update_group,
            device=device,
            names=names,
            dtypes=dtypes,
            shapes=shapes,
            group_name=group_name,
        )
    try:
        weights = []
        handles = []
        for name, dtype, shape in zip(names, dtypes, shapes):
            target_dtype = (
                dtype if isinstance(dtype, torch.dtype) else getattr(torch, dtype)
            )
            weight = torch.empty(shape, dtype=target_dtype, device=device)
            handles.append(
                torch.distributed.broadcast(
                    weight,
                    src=0,
                    group=_model_update_group[group_name],
                    async_op=True,
                )
            )
            weights.append((name, weight))
        for handle in handles:
            handle.wait()

        model.load_weights(weights)
        return True, "Succeeded to update parameter online."

    except Exception as e:
        error_msg = (
            f"Failed to update parameter online: {e}. "
            f"The full weights of the ModelRunner are partially updated. "
            f"Please discard the whole weights."
        )
        logger.error(error_msg)
        return False, error_msg


def _update_bucketed_weights_from_distributed(
    *, model, _model_update_group, device, names, dtypes, shapes, group_name
):
    try:
        named_tensors = []
        for name, dtype, shape in zip(names, dtypes, shapes):
            target_dtype = (
                dtype if isinstance(dtype, torch.dtype) else getattr(torch, dtype)
            )
            named_tensors.append(
                (name, torch.empty(shape, dtype=target_dtype, device=device))
            )
        bucket = FlattenedTensorBucket(named_tensors=named_tensors)
        flattened_tensor = bucket.get_flattened_tensor()
        torch.distributed.broadcast(
            flattened_tensor,
            src=0,
            group=_model_update_group[group_name],
        )
        reconstructed_tensors = bucket.reconstruct_tensors()
        model.load_weights(reconstructed_tensors)
        return True, f"Succeeded to update parameter online."
    except Exception as e:
        error_msg = (
            f"Failed to update parameter online: {e}. "
            f"The full weights of the ModelRunner are partially updated. "
            f"Please discard the whole weights."
        )
        logger.error(error_msg)
        return False, error_msg
'''


def transform(dir_root: Path) -> None:
    # --- Step 1: append the two free functions to weight_updater.py ---
    new_file = dir_root / "python/sglang/srt/model_executor/weight_updater.py"
    text = new_file.read_text()
    text = text.rstrip() + "\n" + APPENDED_FREE_FUNCTIONS
    new_file.write_text(text)

    # --- Step 2: update model_runner.py ---
    mr = dir_root / "python/sglang/srt/model_executor/model_runner.py"
    text = mr.read_text()

    # Add update_weights_from_distributed import. /24 uses two separate import
    # statements (one per name) due to formatting, so just append a third.
    old_imp = (
        "from sglang.srt.model_executor.weight_updater import (\n"
        "    init_weights_update_group as _free_init_weights_update_group,\n"
        ")\n"
    )
    new_imp = (
        "from sglang.srt.model_executor.weight_updater import (\n"
        "    init_weights_update_group as _free_init_weights_update_group,\n"
        ")\n"
        "from sglang.srt.model_executor.weight_updater import (\n"
        "    update_weights_from_distributed as _free_update_weights_from_distributed,\n"
        ")\n"
    )
    assert old_imp in text, "weight_updater import block not found"
    text = text.replace(old_imp, new_imp)

    # Replace update_weights_from_distributed body with delegate.
    old_distributed = (
        '    def update_weights_from_distributed(\n'
        '        self,\n'
        '        names,\n'
        '        dtypes,\n'
        '        shapes,\n'
        '        group_name,\n'
        '        load_format: Optional[str] = None,\n'
        '    ):\n'
        '        """\n'
        '        Update specific parameter in the model weights online\n'
        '        through `_model_update_group` process group.\n'
        '\n'
        '        Args:\n'
        '            name: the name of the parameter to be updated.\n'
        '            dtype: the data type of the parameter to be updated.\n'
        '            shape: the shape of the parameter to be updated.\n'
        '        """\n'
        '\n'
        '        assert group_name in self._model_update_group, (\n'
        '            f"Group {group_name} not in {list(self._model_update_group.keys())}. "\n'
        '            "Please call `init_weights_update_group` first."\n'
        '        )\n'
        '\n'
        '        if load_format == "flattened_bucket":\n'
        '            return self._update_bucketed_weights_from_distributed(\n'
        '                names, dtypes, shapes, group_name\n'
        '            )\n'
        '        try:\n'
        '            weights = []\n'
        '            handles = []\n'
        '            for name, dtype, shape in zip(names, dtypes, shapes):\n'
        '                target_dtype = (\n'
        '                    dtype if isinstance(dtype, torch.dtype) else getattr(torch, dtype)\n'
        '                )\n'
        '                weight = torch.empty(shape, dtype=target_dtype, device=self.device)\n'
        '                handles.append(\n'
        '                    torch.distributed.broadcast(\n'
        '                        weight,\n'
        '                        src=0,\n'
        '                        group=self._model_update_group[group_name],\n'
        '                        async_op=True,\n'
        '                    )\n'
        '                )\n'
        '                weights.append((name, weight))\n'
        '            for handle in handles:\n'
        '                handle.wait()\n'
        '\n'
        '            self.model.load_weights(weights)\n'
        '            return True, "Succeeded to update parameter online."\n'
        '\n'
        '        except Exception as e:\n'
        '            error_msg = (\n'
        '                f"Failed to update parameter online: {e}. "\n'
        '                f"The full weights of the ModelRunner are partially updated. "\n'
        '                f"Please discard the whole weights."\n'
        '            )\n'
        '            logger.error(error_msg)\n'
        '            return False, error_msg\n'
        '\n'
        '    def _update_bucketed_weights_from_distributed(\n'
        '        self, names, dtypes, shapes, group_name\n'
        '    ):\n'
        '        try:\n'
        '            named_tensors = []\n'
        '            for name, dtype, shape in zip(names, dtypes, shapes):\n'
        '                target_dtype = (\n'
        '                    dtype if isinstance(dtype, torch.dtype) else getattr(torch, dtype)\n'
        '                )\n'
        '                named_tensors.append(\n'
        '                    (name, torch.empty(shape, dtype=target_dtype, device=self.device))\n'
        '                )\n'
        '            bucket = FlattenedTensorBucket(named_tensors=named_tensors)\n'
        '            flattened_tensor = bucket.get_flattened_tensor()\n'
        '            torch.distributed.broadcast(\n'
        '                flattened_tensor,\n'
        '                src=0,\n'
        '                group=self._model_update_group[group_name],\n'
        '            )\n'
        '            reconstructed_tensors = bucket.reconstruct_tensors()\n'
        '            self.model.load_weights(reconstructed_tensors)\n'
        '            return True, f"Succeeded to update parameter online."\n'
        '        except Exception as e:\n'
        '            error_msg = (\n'
        '                f"Failed to update parameter online: {e}. "\n'
        '                f"The full weights of the ModelRunner are partially updated. "\n'
        '                f"Please discard the whole weights."\n'
        '            )\n'
        '            logger.error(error_msg)\n'
        '            return False, error_msg\n'
    )
    new_distributed = (
        '    def update_weights_from_distributed(\n'
        '        self,\n'
        '        names,\n'
        '        dtypes,\n'
        '        shapes,\n'
        '        group_name,\n'
        '        load_format: Optional[str] = None,\n'
        '    ):\n'
        '        return _free_update_weights_from_distributed(\n'
        '            model=self.model,\n'
        '            _model_update_group=self._model_update_group,\n'
        '            device=self.device,\n'
        '            names=names,\n'
        '            dtypes=dtypes,\n'
        '            shapes=shapes,\n'
        '            group_name=group_name,\n'
        '            load_format=load_format,\n'
        '        )\n'
    )
    assert old_distributed in text, "update_weights_from_distributed block not found"
    text = text.replace(old_distributed, new_distributed)

    mr.write_text(text)

    git_add_and_commit(
        "Extract update_weights_from_distributed to free functions in weight_updater",
        cwd=str(dir_root),
    )


if __name__ == "__main__":
    verify_mechanical_refactor(
        base_commit=BASE_COMMIT,
        target_commit=TARGET_COMMIT,
        transform=transform,
    )
