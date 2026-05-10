#!/usr/bin/env python3
"""Rename ``RemoteInstanceWeightTransport`` fields + methods to drop the
``remote_instance_transfer_engine_`` prefix that's redundant once the
class name itself carries the ``RemoteInstance`` semantic.

| kind    | 旧                                              | 新                          |
|---------|-------------------------------------------------|-----------------------------|
| field   | ``remote_instance_transfer_engine``             | ``engine``                  |
| field   | ``remote_instance_transfer_engine_session_id``  | ``session_id``              |
| field   | ``remote_instance_transfer_engine_weight_info`` | ``weight_info``             |
| method  | ``remote_instance_init_transfer_engine``        | ``init_engine``             |
| method  | ``_register_to_engine_info_bootstrap``          | ``register_to_bootstrap``   |
| method  | ``_publish_modelexpress_metadata``              | ``publish_to_modelexpress`` |

Caller sites: ~10 in ``model_runner.py`` (mostly via
``self.remote_instance_weight_transport.X``). The
``self.loader.remote_instance_transfer_engine_weight_info`` access
happens on a *different* object (the loader) and is left alone.

Substitution order: longest-name-first so prefix-substring renames don't
half-rewrite the longer ones.

Usage:
    uv run --python 3.12 rwt-mech-rename.py run
    uv run --python 3.12 rwt-mech-rename.py verify
"""

# /// script
# requires-python = ">=3.10"
# dependencies = ["typer"]
# ///

import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from _runner import run_pr

ID = "rwt-mech-rename"
SUBJECT = "Rename RemoteInstanceWeightTransport fields + methods"
BODY = ""
AREA = "mech_model_runner"
BASE = "tom_refactor_202605a/primary/mech_model_runner/nem-mech-frozen"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


# Inside the source file: rename self.X + ctor kwargs + method def lines.
# Order: longest first (so ``remote_instance_transfer_engine_session_id``
# rewires before bare ``remote_instance_transfer_engine``).
_INSIDE_SUBS = [
    # field renames (self.X)
    ("self.remote_instance_transfer_engine_session_id", "self.session_id"),
    ("self.remote_instance_transfer_engine_weight_info", "self.weight_info"),
    ("self.remote_instance_transfer_engine", "self.engine"),
    # method def lines (longest first)
    ("def remote_instance_init_transfer_engine", "def init_engine"),
    ("def _register_to_engine_info_bootstrap", "def register_to_bootstrap"),
    ("def _publish_modelexpress_metadata", "def publish_to_modelexpress"),
    # internal method calls
    ("self.remote_instance_init_transfer_engine(", "self.init_engine("),
    ("self._register_to_engine_info_bootstrap(", "self.register_to_bootstrap("),
    ("self._publish_modelexpress_metadata(", "self.publish_to_modelexpress("),
]


# Outside callers: scoped to ``remote_instance_weight_transport.X`` so we
# don't accidentally rename the loader's same-named attribute.
_OUTSIDE_SUBS = [
    (
        "remote_instance_weight_transport.remote_instance_transfer_engine_session_id",
        "remote_instance_weight_transport.session_id",
    ),
    (
        "remote_instance_weight_transport.remote_instance_transfer_engine_weight_info",
        "remote_instance_weight_transport.weight_info",
    ),
    (
        "remote_instance_weight_transport.remote_instance_init_transfer_engine",
        "remote_instance_weight_transport.init_engine",
    ),
    (
        "remote_instance_weight_transport.remote_instance_transfer_engine",
        "remote_instance_weight_transport.engine",
    ),
    (
        "remote_instance_weight_transport._register_to_engine_info_bootstrap",
        "remote_instance_weight_transport.register_to_bootstrap",
    ),
    (
        "remote_instance_weight_transport._publish_modelexpress_metadata",
        "remote_instance_weight_transport.publish_to_modelexpress",
    ),
]


def transform(wt: Path) -> None:
    src = wt / "python/sglang/srt/model_executor/remote_instance_weight_transport.py"
    text = src.read_text()
    for old, new in _INSIDE_SUBS:
        text = text.replace(old, new)
    src.write_text(text)

    mr = wt / "python/sglang/srt/model_executor/model_runner.py"
    text = mr.read_text()
    for old, new in _OUTSIDE_SUBS:
        text = text.replace(old, new)
    mr.write_text(text)


if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        area_branch=AREA_BRANCH,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
