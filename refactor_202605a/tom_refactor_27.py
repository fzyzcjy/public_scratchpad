#!/usr/bin/env python3
"""Cut `update_weights_from_tensor` + `_update_weights_from_flattened_bucket`
from ModelRunner; also cut module-level helpers `_unwrap_tensor`,
`_model_load_weights_direct` and dataclass `LocalSerializedTensor`. Paste all
five into `weight_updater.py`. Update tp_worker.py call site.
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
    find_class_lines,
    find_function_lines,
    find_method_lines,
)
from mechanical_refactor_verify_utils import (
    git_add_and_commit,
    verify_mechanical_refactor,
)

BASE_COMMIT = "tom_refactor/26"
TARGET_COMMIT = "tom_refactor/27"


def transform(dir_root: Path) -> None:
    mr = dir_root / "python/sglang/srt/model_executor/model_runner.py"
    wu = dir_root / "python/sglang/srt/model_executor/weight_updater.py"
    tw = dir_root / "python/sglang/srt/managers/tp_worker.py"

    # Cut from bottom to top so earlier line ranges stay valid.
    s, e = find_class_lines(mr.read_text(), class_name="LocalSerializedTensor")
    cls_text = cut_lines(mr, s, e)

    s, e = find_function_lines(mr.read_text(), function_name="_unwrap_tensor")
    unwrap_text = cut_lines(mr, s, e)

    s, e = find_function_lines(mr.read_text(), function_name="_model_load_weights_direct")
    direct_text = cut_lines(mr, s, e)

    s, e = find_method_lines(mr.read_text(), class_name="ModelRunner", method_name="_update_weights_from_flattened_bucket")
    fb_text = dedent_method_to_function(cut_lines(mr, s, e)).replace(
        "def _update_weights_from_flattened_bucket(\n    self,\n    flattened_tensor_bucket_dict,\n):",
        "def _update_weights_from_flattened_bucket(\n    *,\n    model,\n    flattened_tensor_bucket_dict,\n):",
    ).replace("self.model.load_weights", "model.load_weights")

    s, e = find_method_lines(mr.read_text(), class_name="ModelRunner", method_name="update_weights_from_tensor")
    uwt_text = dedent_method_to_function(cut_lines(mr, s, e)).replace(
        'def update_weights_from_tensor(\n'
        '    self,\n'
        '    named_tensors: List[Tuple[str, Union[torch.Tensor, "LocalSerializedTensor"]]],\n'
        '    load_format: Optional[str] = None,\n'
        '):',
        'def update_weights_from_tensor(\n'
        '    *,\n'
        '    model,\n'
        '    tp_rank,\n'
        '    device,\n'
        '    custom_weight_loader,\n'
        '    named_tensors,\n'
        '    load_format=None,\n'
        '):',
    ).replace("self.device", "device").replace("self.tp_rank", "tp_rank").replace(
        "self._update_weights_from_flattened_bucket(\n                flattened_tensor_bucket_dict=named_tensors\n            )",
        "_update_weights_from_flattened_bucket(\n                model=model, flattened_tensor_bucket_dict=named_tensors\n            )",
    ).replace("self.server_args.custom_weight_loader", "custom_weight_loader").replace(
        "_model_load_weights_direct(self.model, named_tensors)",
        "_model_load_weights_direct(model, named_tensors)",
    ).replace("self.model.load_weights(named_tensors)", "model.load_weights(named_tensors)")

    appended = (
        "\nfrom dataclasses import dataclass\nfrom typing import List, Tuple\n\n"
        "from sglang.srt.model_loader.weight_utils import default_weight_loader\n"
        "from sglang.srt.utils import MultiprocessingSerializer, dynamic_import\n"
        "from sglang.srt.utils.patch_torch import monkey_patch_torch_reductions\n"
        "from sglang.srt.weight_sync.tensor_bucket import (\n"
        "    FlattenedTensorBucket,\n"
        "    FlattenedTensorMetadata,\n"
        ")\n\n\n"
        + direct_text + "\n" + unwrap_text + "\n" + cls_text + "\n" + fb_text + "\n" + uwt_text
    )
    append_to_file(wu, appended)

    text = mr.read_text()
    text = text.replace(
        "    update_weights_from_distributed as _free_update_weights_from_distributed,\n)\n",
        "    update_weights_from_distributed as _free_update_weights_from_distributed,\n)\n"
        "from sglang.srt.model_executor.weight_updater import (\n"
        "    LocalSerializedTensor,\n"
        ")\n",
    )
    mr.write_text(text)

    text = tw.read_text()
    text = text.replace(
        "from sglang.srt.utils import MultiprocessingSerializer\n",
        "from sglang.srt.utils import MultiprocessingSerializer\n"
        "from sglang.srt.model_executor.weight_updater import (\n"
        "    update_weights_from_tensor as _free_update_weights_from_tensor,\n"
        ")\n",
    )
    text = text.replace(
        "        success, message = self.model_runner.update_weights_from_tensor(\n"
        "            named_tensors=MultiprocessingSerializer.deserialize(\n"
        "                recv_req.serialized_named_tensors[self.tp_rank]\n"
        "            ),\n"
        "            load_format=recv_req.load_format,\n"
        "        )\n",
        "        success, message = _free_update_weights_from_tensor(\n"
        "            model=self.model_runner.model,\n"
        "            tp_rank=self.model_runner.tp_rank,\n"
        "            device=self.model_runner.device,\n"
        "            custom_weight_loader=self.model_runner.server_args.custom_weight_loader,\n"
        "            named_tensors=MultiprocessingSerializer.deserialize(\n"
        "                recv_req.serialized_named_tensors[self.tp_rank]\n"
        "            ),\n"
        "            load_format=recv_req.load_format,\n"
        "        )\n",
    )
    tw.write_text(text)

    git_add_and_commit(
        "Extract update_weights_from_tensor and helpers to weight_updater",
        cwd=str(dir_root),
    )


if __name__ == "__main__":
    verify_mechanical_refactor(
        base_commit=BASE_COMMIT,
        target_commit=TARGET_COMMIT,
        transform=transform,
    )
