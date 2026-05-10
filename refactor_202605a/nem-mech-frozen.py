#!/usr/bin/env python3
"""Convert ``NgramEmbeddingManager`` to
``@dataclass(frozen=True, slots=True, kw_only=True)``.

After ``nem-mech-rename``, the class has a handwritten ``__init__``
that just copies 4 kwargs to ``self``. Replace it with the dataclass-
generated ``__init__`` — the 4 instance vars are pure reads after the
ctor (no other ``self.X = ...`` writes anywhere in the file), so
``frozen=True`` is safe.

Usage:
    uv run --python 3.12 nem-mech-frozen.py run
    uv run --python 3.12 nem-mech-frozen.py verify
"""

# /// script
# requires-python = ">=3.10"
# dependencies = ["typer"]
# ///

import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from _helpers import insert_after, replace_call_site
from _runner import run_pr

ID = "nem-mech-frozen"
SUBJECT = "NgramEmbeddingManager: @dataclass(frozen, slots, kw_only)"
BODY = ""
AREA = "mech_model_runner"
BASE = "tom_refactor_202605a/primary/mech_model_runner/nem-mech-rename"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


def transform(wt: Path) -> None:
    src = wt / "python/sglang/srt/layers/n_gram_embedding_manager.py"
    text = src.read_text()
    if "from dataclasses import dataclass" not in text:
        text = insert_after(
            text,
            anchor="from typing import TYPE_CHECKING, Optional\n",
            addition="from dataclasses import dataclass\n",
        )
    text = replace_call_site(
        text,
        old=(
            "class NgramEmbeddingManager:\n"
            "\n"
            "    def __init__(\n"
            "        self,\n"
            "        *,\n"
            "        enabled: bool,\n"
            "        table: Optional[torch.Tensor],\n"
            "        n: int,\n"
            "        k: int,\n"
            "    ):\n"
            "        self.enabled = enabled\n"
            "        self.table = table\n"
            "        self.n = n\n"
            "        self.k = k\n"
        ),
        new=(
            "@dataclass(frozen=True, slots=True, kw_only=True)\n"
            "class NgramEmbeddingManager:\n"
            "    enabled: bool\n"
            "    table: Optional[torch.Tensor]\n"
            "    n: int\n"
            "    k: int\n"
        ),
    )
    src.write_text(text)


if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        area_branch=AREA_BRANCH,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
