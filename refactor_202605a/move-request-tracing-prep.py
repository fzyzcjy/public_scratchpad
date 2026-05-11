#!/usr/bin/env python3
"""In-place prep for moving convert_to_span_attrs out of TokenizerManager.

Make convert_to_span_attrs a @staticmethod with explicit ``served_model_name``
kwarg; drop the ``self.server_args.enable_trace`` early-return (caller
already gates on ``state.time_stats.trace_ctx.tracing_enable``). Body stays
in TokenizerManager class; the next commit ``move-request-tracing-move``
physically relocates it to ``managers/request_tracing.py``.
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

ID = "move-request-tracing-prep"
SUBJECT = "Prep convert_to_span_attrs for move: staticmethod + explicit served_model_name"
BODY = """\
In-place prep per MECH_COMMIT_SPLIT before the physical move:

  - Add @staticmethod decorator
  - Drop ``self``; pass ``served_model_name`` as explicit kwarg
  - Drop ``self.server_args.enable_trace`` early-return (caller already
    gates on tracing_enable; per request_tracing.md ch4)
  - Caller switches to ``TokenizerManager.convert_to_span_attrs(...)``
    (class-qualified call) so the next commit's caller change is a pure
    prefix replacement.

No behavior change. Body stays inside TokenizerManager class.
"""
AREA = "mech_tokenizer_manager"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


NEW_HEADER = '''    @staticmethod
    def convert_to_span_attrs(
        *,
        state: ReqState,
        recv_obj: Union[
            BatchStrOutput,
            BatchEmbeddingOutput,
            BatchTokenIDOutput,
        ],
        i: int,
        served_model_name: str,
    ) -> Dict[str, Any]:
'''


def _method_ranges(text: str, class_name: str, method_name: str):
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

    s, body_s, e = _method_ranges(text, "TokenizerManager", "convert_to_span_attrs")
    lines = text.splitlines(keepends=True)
    body_text = "".join(lines[body_s:e])

    # Drop early-return guarded by self.server_args.enable_trace.
    body_text = body_text.replace(
        "        if not self.server_args.enable_trace:\n            return span_attrs\n\n",
        "",
    )
    # served_model_name -> arg
    body_text = body_text.replace(
        "span_attrs[SpanAttributes.GEN_AI_RESPONSE_MODEL] = self.served_model_name",
        "span_attrs[SpanAttributes.GEN_AI_RESPONSE_MODEL] = served_model_name",
    )

    new_method = NEW_HEADER + body_text
    new_text = "".join(lines[:s]) + new_method + "".join(lines[e:])

    # Caller (in _handle_batch_output)
    new_text = replace_call_site(
        new_text,
        old="self.convert_to_span_attrs(state, recv_obj, i)",
        new=(
            "TokenizerManager.convert_to_span_attrs(\n"
            "                            state=state,\n"
            "                            recv_obj=recv_obj,\n"
            "                            i=i,\n"
            "                            served_model_name=self.served_model_name,\n"
            "                        )"
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
