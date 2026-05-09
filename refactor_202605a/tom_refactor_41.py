#!/usr/bin/env python3
"""Cut `_register_to_engine_info_bootstrap` from ModelRunner; append it to
`RemoteInstanceWeightTransport`. Update caller directly to delegate via
`self.remote_instance_weight_transport`.
"""

import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.append(str(HERE))
sys.path.append(".claude/skills/mechanical-refactor-verify")
from _helpers import append_to_file, cut_lines, find_method_lines
from mechanical_refactor_verify_utils import git_add_and_commit, verify_mechanical_refactor

BASE_COMMIT = "tom_refactor/40"
TARGET_COMMIT = "tom_refactor/41"


def transform(dir_root: Path) -> None:
    mr = dir_root / "python/sglang/srt/model_executor/model_runner.py"
    transport = dir_root / "python/sglang/srt/model_executor/remote_instance_weight_transport.py"

    start, end = find_method_lines(mr.read_text(), class_name="ModelRunner", method_name="_register_to_engine_info_bootstrap")
    method_text = cut_lines(mr, start, end)
    method_text = method_text.replace("self.remote_instance_weight_transport.", "self.")
    append_to_file(transport, method_text.rstrip() + "\n", separator="\n")

    text = mr.read_text()
    text = text.replace(
        "self._register_to_engine_info_bootstrap()",
        "self.remote_instance_weight_transport._register_to_engine_info_bootstrap()",
    )
    mr.write_text(text)

    git_add_and_commit(
        "Migrate _register_to_engine_info_bootstrap to RemoteInstanceWeightTransport",
        cwd=str(dir_root),
    )


if __name__ == "__main__":
    verify_mechanical_refactor(base_commit=BASE_COMMIT, target_commit=TARGET_COMMIT, transform=transform)
