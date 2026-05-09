#!/usr/bin/env python3
"""Reproducible transform for tom_refactor/27.

DEFERRED: `update_weights_from_tensor` cannot be migrated minimally because
its body depends on two module-private helpers defined inside
`model_runner.py`:

    _unwrap_tensor(tensor, tp_rank, device)
    _model_load_weights_direct(model, named_tensors)

Migrating the method to `weight_updater.py` would require either (a) importing
those helpers from `model_runner.py` (creates a cycle since model_runner already
imports from weight_updater), (b) duplicating them in weight_updater.py
(violates the byte-identical / no-rename strict-minimal rule), or (c) injecting
them as Callable kwargs (control-flow restructuring beyond what the strict
contract allows for this PR).

`_update_weights_from_flattened_bucket` is internal to
`update_weights_from_tensor` and is not migrated separately because its only
caller is the method that itself cannot be migrated.

This PR is intentionally a no-op stub. The migration will be revisited once
`_unwrap_tensor` / `_model_load_weights_direct` have been relocated in a
dedicated mechanical move.

Run from the repo root:
    python3 /tmp/transform_update_weights_from_tensor.py
"""

import sys
from pathlib import Path

sys.path.append(".claude/skills/mechanical-refactor-verify")
from mechanical_refactor_verify_utils import (
    verify_mechanical_refactor,
    git_add_and_commit,
)

BASE_COMMIT = "tom_refactor/26"
TARGET_COMMIT = "tom_refactor/27"


def transform(dir_root: Path) -> None:
    # Intentionally empty: see module docstring for rationale.
    return


if __name__ == "__main__":
    verify_mechanical_refactor(
        base_commit=BASE_COMMIT,
        target_commit=TARGET_COMMIT,
        transform=transform,
    )
