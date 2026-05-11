#!/usr/bin/env python3
"""In-place prep for moving _calculate_spec_decoding_metrics out of
TokenizerManager.

Make it @staticmethod with explicit ``speculative_num_draft_tokens`` kwarg.
Body stays in TM class; the next commit ``move-spec-decoding-meta-move``
physically relocates it.
"""

# /// script
# requires-python = ">=3.10"
# dependencies = ["typer"]
# ///

import ast
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from _helpers import replace_call_site
from _runner import run_pr

ID = "move-spec-decoding-meta-prep"
SUBJECT = "Prep _calculate_spec_decoding_metrics for move: staticmethod + explicit speculative_num_draft_tokens"
BODY = """\
In-place prep per MECH_COMMIT_SPLIT:
  - Add @staticmethod decorator
  - Drop ``self``; pass ``speculative_num_draft_tokens`` as kwarg
  - Single caller switches to ``TokenizerManager._calculate_spec_decoding_metrics(...)``

No behavior change. Body stays inside TokenizerManager class.
"""
AREA = "mech_tokenizer_manager"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


NEW_HEADER = '''    @staticmethod
    def _calculate_spec_decoding_metrics(
        meta_info: Dict[str, Any],
        *,
        recv_obj: Union[
            BatchStrOutput,
            BatchEmbeddingOutput,
            BatchTokenIDOutput,
        ],
        i: int,
        speculative_num_draft_tokens: int,
    ) -> None:
'''


def _method_ranges(text, class_name, method_name):
    tree = ast.parse(text)
    func_types = (ast.FunctionDef, ast.AsyncFunctionDef)
    for cls in ast.walk(tree):
        if isinstance(cls, ast.ClassDef) and cls.name == class_name:
            for i, node in enumerate(cls.body):
                if isinstance(node, func_types) and node.name == method_name:
                    start = node.lineno - 1
                    if node.decorator_list:
                        start = node.decorator_list[0].lineno - 1
                    body_start = node.body[0].lineno - 1
                    if i + 1 < len(cls.body):
                        end = cls.body[i + 1].lineno - 1
                        nxt = cls.body[i + 1]
                        if isinstance(nxt, func_types + (ast.ClassDef,)) and nxt.decorator_list:
                            end = nxt.decorator_list[0].lineno - 1
                    else:
                        end = node.end_lineno
                    return start, body_start, end
    raise ValueError(f"{class_name}.{method_name} not found")


def transform(wt: Path) -> None:
    tm = wt / "python/sglang/srt/managers/tokenizer_manager.py"
    text = tm.read_text()

    s, body_s, e = _method_ranges(text, "TokenizerManager", "_calculate_spec_decoding_metrics")
    lines = text.splitlines(keepends=True)
    body_text = "".join(lines[body_s:e])
    body_text = body_text.replace(
        "self.server_args.speculative_num_draft_tokens",
        "speculative_num_draft_tokens",
    )

    new_method = NEW_HEADER + body_text
    new_text = "".join(lines[:s]) + new_method + "".join(lines[e:])

    # Caller (single, inside _handle_batch_output, 20-space indent based on script).
    new_text = replace_call_site(
        new_text,
        old="self._calculate_spec_decoding_metrics(meta_info, recv_obj, i)",
        new=(
            "TokenizerManager._calculate_spec_decoding_metrics(\n"
            "                        meta_info,\n"
            "                        recv_obj=recv_obj,\n"
            "                        i=i,\n"
            "                        speculative_num_draft_tokens=self.server_args.speculative_num_draft_tokens,\n"
            "                    )"
        ),
    )

    tm.write_text(new_text)


if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        area_branch=AREA_BRANCH,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
