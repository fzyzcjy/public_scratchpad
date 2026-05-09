#!/usr/bin/env python3
"""Reproducible transform for tom_refactor/25.

DEFERRED: `update_weights_from_disk` cannot be migrated minimally because its
body performs four direct write-backs to ModelRunner state:

    self.model = model
    self.server_args.model_path = model_path
    self.server_args.load_format = load_format
    self.load_config = load_config

A free function would either need to (a) take a `model_runner` reference (which
violates the R4 rule banning god-class reverse coupling), (b) return the four
new values for the caller to write back (which restructures control flow and
violates rule 4 of the strict-minimal contract), or (c) duplicate the helper
closures `get_weight_iter` / `model_load_weights` outside ModelRunner. None of
those is a strict-minimal mechanical move, so this PR is intentionally a no-op
stub. The migration will be revisited once the model/server_args writebacks
have been refactored independently.

Run from the repo root:
    python3 /tmp/transform_update_weights_from_disk.py
"""

import sys
from pathlib import Path

sys.path.append(".claude/skills/mechanical-refactor-verify")
from mechanical_refactor_verify_utils import (
    verify_mechanical_refactor,
    git_add_and_commit,
)

BASE_COMMIT = "tom_refactor/24"
TARGET_COMMIT = "tom_refactor/25"


def transform(dir_root: Path) -> None:
    # Intentionally empty: see module docstring for rationale.
    return


if __name__ == "__main__":
    verify_mechanical_refactor(
        base_commit=BASE_COMMIT,
        target_commit=TARGET_COMMIT,
        transform=transform,
    )
