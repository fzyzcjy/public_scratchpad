#!/usr/bin/env python3
"""Reproducible transform for tom_refactor/28.

DEFERRED: `update_weights_from_ipc` cannot be migrated minimally because its
body constructs `SGLangCheckpointEngineWorkerExtensionImpl(self)`, passing the
entire `ModelRunner` (i.e. the god-class reference) into the worker extension
constructor. Replacing that with a free function would either (a) keep the
god-class hand-off intact at a different call site (which only relocates the
problem), or (b) require redesigning the
`SGLangCheckpointEngineWorkerExtensionImpl` interface to accept a narrower set
of dependencies (a non-mechanical change explicitly out of scope for this
strict-minimal PR).

This PR is intentionally a no-op stub. The migration will be revisited once
the checkpoint-engine worker extension is refactored to take explicit
dependencies instead of `ModelRunner` itself.

Run from the repo root:
    python3 /tmp/transform_update_weights_from_ipc.py
"""

import sys
from pathlib import Path

sys.path.append(".claude/skills/mechanical-refactor-verify")
from mechanical_refactor_verify_utils import (
    verify_mechanical_refactor,
    git_add_and_commit,
)

BASE_COMMIT = "tom_refactor/27"
TARGET_COMMIT = "tom_refactor/28"


def transform(dir_root: Path) -> None:
    # Intentionally empty: see module docstring for rationale.
    return


if __name__ == "__main__":
    verify_mechanical_refactor(
        base_commit=BASE_COMMIT,
        target_commit=TARGET_COMMIT,
        transform=transform,
    )
