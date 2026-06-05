#!/usr/bin/env python3
"""Apply the ``large-class-init-style`` skill to ``TokenizerManager.__init__``.

The component-introduction commits each inlined a structured construction
(``self.<comp> = <Component>(...)``) into ``__init__``. The skill
(.claude/skills/large-class-init-style/SKILL.md) requires ``__init__`` to be an
orchestrator: a sequence of ``self.init_*()`` calls, one helper per overridable
unit, with no structured construction inlined.

This final pass extracts each component construction out of ``__init__`` into an
``init_<comp>`` helper method and replaces the inline block with
``self.init_<comp>()`` (keeping the existing leading comment on the call, matching
the reference shape). It runs last, on the fully-assembled ``__init__``, so it
does not disturb the interdependent anchors the earlier prep commits rely on.
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
from _runner import run_pr

ID = "apply-large-class-init-style"
SUBJECT = "Wire TokenizerManager components via init_* helpers"
BODY = """\
Apply the large-class-init-style skill: TokenizerManager.__init__ must be an
orchestrator of self.init_*() calls, one helper per overridable unit, with no
structured construction inlined. The component-introduction commits inlined
each self.<comp> = <Component>(...) block; this pass extracts every one into an
init_<comp> method and replaces the inline block with self.init_<comp>()
(keeping the leading comment on the call). __init__ call order — and hence the
self.* dependency ordering — is preserved.
"""
AREA = "mech_tokenizer_manager"
BASE = "main"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


# Components inlined into __init__ by the chain, each now extracted into an
# init_<attr> helper. ``raw_tokenizer_wrapper`` is special: its construction is
# two statements (``RawTokenizerWrapper()`` + ``.init_tokenizer_and_processor``)
# which are grouped into a single helper.
COMPONENT_ATTRS = (
    "raw_tokenizer_wrapper",
    "lora_controller",
    "multimodal_processor",
    "tokenized_request_builder",
    "request_metrics_recorder",
    "weight_disk_update_controller",
    "corpus_controller",
    "output_processor",
    "response_emitter",
    "session_controller",
    "request_log_manager",
    "request_validator",
    "request_preparer",
    "score_request_handler",
    "batch_request_dispatcher",
)

METHOD_ANCHOR = "    def init_model_config(self):\n"


def _find_init(tree: ast.Module) -> ast.FunctionDef:
    for cls in ast.walk(tree):
        if isinstance(cls, ast.ClassDef) and cls.name == "TokenizerManager":
            for node in cls.body:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "__init__":
                    return node
    raise RuntimeError("TokenizerManager.__init__ not found")


def _is_self_attr_assign(stmt: ast.stmt, attr: str) -> bool:
    return (
        isinstance(stmt, ast.Assign)
        and len(stmt.targets) == 1
        and isinstance(stmt.targets[0], ast.Attribute)
        and isinstance(stmt.targets[0].value, ast.Name)
        and stmt.targets[0].value.id == "self"
        and stmt.targets[0].attr == attr
    )


def transform(wt: Path) -> None:
    tm = wt / "python/sglang/srt/managers/tokenizer_manager.py"
    src = tm.read_text()
    tree = ast.parse(src)
    init = _find_init(tree)
    lines = src.splitlines(keepends=True)

    # Locate each component's construction statement(s) in __init__.
    body = init.body
    spans: dict[str, tuple[int, int]] = {}  # attr -> (start0, end0_exclusive)
    for i, stmt in enumerate(body):
        for attr in COMPONENT_ATTRS:
            if _is_self_attr_assign(stmt, attr):
                first, last = stmt, stmt
                # raw_tokenizer_wrapper: fold the following
                # ``self.raw_tokenizer_wrapper.init_tokenizer_and_processor(...)``
                # call into the same helper.
                if attr == "raw_tokenizer_wrapper" and i + 1 < len(body):
                    nxt = body[i + 1]
                    if (
                        isinstance(nxt, ast.Expr)
                        and isinstance(nxt.value, ast.Call)
                        and isinstance(nxt.value.func, ast.Attribute)
                        and nxt.value.func.attr == "init_tokenizer_and_processor"
                    ):
                        last = nxt
                spans[attr] = (first.lineno - 1, last.end_lineno)
                break

    missing = [a for a in COMPONENT_ATTRS if a not in spans]
    if missing:
        raise RuntimeError(f"component constructions not found in __init__: {missing}")

    # Build replacements bottom-up so earlier line indices stay valid. Keep the
    # leading comment line(s) in __init__ (the call inherits them, matching the
    # ``# Init X`` + ``self.init_x()`` reference shape).
    new_lines = list(lines)
    methods: dict[str, str] = {}
    for attr in sorted(spans, key=lambda a: -spans[a][0]):
        start0, end0 = spans[attr]
        body_block = "".join(lines[start0:end0])
        methods[attr] = f"    def init_{attr}(self):\n{body_block}"
        new_lines[start0:end0] = [f"        self.init_{attr}()\n"]

    new_src = "".join(new_lines)

    # Insert the helpers (in __init__ call order) just before init_model_config.
    call_order = sorted(spans, key=lambda a: spans[a][0])
    methods_block = "\n".join(methods[a].rstrip() + "\n" for a in call_order) + "\n"
    if METHOD_ANCHOR not in new_src:
        raise RuntimeError("init_model_config anchor not found for method insertion")
    new_src = new_src.replace(METHOD_ANCHOR, methods_block + METHOD_ANCHOR, 1)

    tm.write_text(new_src)


if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        area_branch=AREA_BRANCH,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
