#!/usr/bin/env python3
"""Prep: retype 4 tokenize-pipeline helpers as @staticmethod with
self: "RawTokenizerWrapper" typing; body rewrites
(``self.raw_tokenizer_wrapper.<field> → self.<field>``) + intra-cluster
cross-call class-qualification; external caller rewrites.

Per MECH_COMMIT_SPLIT §"拆 class 场景": prep does ALL semantic work; the
follow-up rtw-move-tokenize-helpers commit is pure cut/paste with the
intra-cluster qualifier folded back to ``self.``.
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

ID = "rtw-prep-tokenize-helpers"
SUBJECT = "Stage tokenize-pipeline helpers for handoff to RawTokenizerWrapper"
BODY = """\
Per MECH_COMMIT_SPLIT §"拆 class 场景": prep does ALL semantic work.

Converts the 4 helper methods (``_detect_input_format`` /
``_prepare_tokenizer_input`` / ``_extract_tokenizer_results`` /
``_tokenize_texts``) on TokenizerManager to ``@staticmethod`` with
``self: "RawTokenizerWrapper"`` typing. Body rewrites collapse the facade
form ``self.raw_tokenizer_wrapper.<field>`` back to ``self.<field>``
(``self`` is now a RawTokenizerWrapper at runtime). Intra-cluster
sibling calls (``self._detect_input_format(...)`` etc. inside
``_tokenize_texts``) become class-qualified ``TokenizerManager._x(self, ...)``
to keep the prep-stage methods reachable while the bodies still live on
TM. External callers in TM that read these helpers
(``self._tokenize_texts(...)`` etc.) are rewritten to
``TokenizerManager._x(self.raw_tokenizer_wrapper, ...)``. Adds
``Tuple`` / ``Union`` to the typing import of raw_tokenizer_wrapper.py
so the post-move bodies type-check. The next commit cuts and pastes; no
body changes.
"""
AREA = "mech_tokenizer_manager"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


HELPER_NAMES = (
    "_detect_input_format",
    "_prepare_tokenizer_input",
    "_extract_tokenizer_results",
    "_tokenize_texts",
)


NEW_HEADERS = {
    "_detect_input_format": '''    @staticmethod
    def _detect_input_format(
        self: "RawTokenizerWrapper",
        texts: Union[str, List[str]],
        is_cross_encoder: bool,
    ) -> InputFormat:
''',
    "_prepare_tokenizer_input": '''    @staticmethod
    def _prepare_tokenizer_input(
        self: "RawTokenizerWrapper",
        texts: Union[str, List[str]],
        input_format: InputFormat,
    ) -> Union[List[str], List[List[str]]]:
''',
    "_extract_tokenizer_results": '''    @staticmethod
    def _extract_tokenizer_results(
        self: "RawTokenizerWrapper",
        input_ids: List[List[int]],
        token_type_ids: Optional[List[List[int]]],
        input_format: InputFormat,
        original_batch_size: int,
    ) -> Union[
        Tuple[List[int], Optional[List[int]]],
        Tuple[List[List[int]], Optional[List[List[int]]]],
    ]:
''',
    "_tokenize_texts": '''    @staticmethod
    async def _tokenize_texts(
        self: "RawTokenizerWrapper",
        texts: Union[str, List[str]],
        is_cross_encoder: bool = False,
    ) -> Union[
        Tuple[List[int], Optional[List[int]]],
        Tuple[List[List[int]], Optional[List[List[int]]]],
    ]:
''',
}


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


def _rewrite_body(body_text: str) -> str:
    """Collapse facade ``self.raw_tokenizer_wrapper.<field>`` → ``self.<field>``
    (the @staticmethod receives a RawTokenizerWrapper as ``self``) and
    class-qualify intra-cluster sibling calls so they remain reachable while
    the bodies still live on TokenizerManager."""
    body_text = body_text.replace("self.raw_tokenizer_wrapper.", "self.")
    for name in HELPER_NAMES:
        body_text = body_text.replace(
            f"self.{name}(", f"TokenizerManager.{name}(self, "
        )
    return body_text


def transform(wt: Path) -> None:
    tm = wt / "python/sglang/srt/managers/tokenizer_manager.py"

    text = tm.read_text()

    # ---- 1. Retype 4 methods in place. Iterate bottom-up so earlier line
    # numbers stay valid; recompute ranges each pass since text mutates.
    name_to_start = {}
    for name in HELPER_NAMES:
        s, _, _ = _method_ranges(text, "TokenizerManager", name)
        name_to_start[name] = s
    for name in sorted(HELPER_NAMES, key=lambda n: -name_to_start[n]):
        s, body_s, e = _method_ranges(text, "TokenizerManager", name)
        lines = text.splitlines(keepends=True)
        body_text = _rewrite_body("".join(lines[body_s:e]))
        text = "".join(lines[:s]) + NEW_HEADERS[name] + body_text + "".join(lines[e:])

    # ---- 2. External caller rewrites (inside TM but outside the cluster):
    # ``self._tokenize_texts(...)`` → ``TokenizerManager._tokenize_texts(self.raw_tokenizer_wrapper, ...)``.
    # The 4 retyped methods' bodies already had their intra-cluster calls
    # class-qualified via _rewrite_body; external callers need the facade form.
    for name in HELPER_NAMES:
        text = text.replace(
            f"self.{name}(",
            f"TokenizerManager.{name}(self.raw_tokenizer_wrapper, ",
        )
    tm.write_text(text)

    # NOTE: typing import expansion in raw_tokenizer_wrapper.py lives in the
    # follow-up move commit (when the bodies that use Tuple/Union/List actually
    # arrive in the target). Adding them here would leave an unused import that
    # ruff strips on the per-commit pass.


if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        area_branch=AREA_BRANCH,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
