#!/usr/bin/env python3
"""Mechanical move for ``introduce-invariant-checker``: cut the 10
prep-form @staticmethods from ``SchedulerRuntimeCheckerMixin``, paste them
into the ``SchedulerInvariantChecker`` class body. Drop ``@staticmethod``
decorators; simplify ``self: "SchedulerInvariantChecker"`` annotation to
bare ``self``; strip the ``SchedulerRuntimeCheckerMixin.`` prefix from
internal sibling calls (and the explicit ``self`` positional). Rewrite all
callers ``self.<method>(self.invariant_checker, ...)`` →
``self.invariant_checker.<method>(...)`` — pure prefix transformation.
After all 10 methods are gone, drop ``SchedulerRuntimeCheckerMixin`` from
``Scheduler``'s inheritance list and delete the (now-empty) mixin file.
"""

# /// script
# requires-python = ">=3.10"
# dependencies = ["typer"]
# ///

import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from _helpers import cut_lines, find_method_lines, replace_call_site, rewrite_method_call_site
from _runner import run_pr

ID = "introduce-invariant-checker-move"
SUBJECT = "Move 10 check methods into SchedulerInvariantChecker class body; delete runtime_checker mixin"
BODY = """\
Mechanical cut + paste for the ``introduce-invariant-checker`` mech move
(tail commit of the ``SchedulerRuntimeCheckerMixin`` 1:N split).

Cut the 10 methods (9 @staticmethod after prep + the already-static
``_check_pool_invariant``) from ``SchedulerRuntimeCheckerMixin`` and paste
them into the ``SchedulerInvariantChecker`` class body in
``scheduler_components/invariant_checker.py``. Drop ``@staticmethod``
decorators; simplify ``self: "SchedulerInvariantChecker"`` annotation to
bare ``self`` (in class context the type is implicit). Strip the
``SchedulerRuntimeCheckerMixin.<method>(self, ...)`` qualified form on
internal sibling calls to plain ``self.<method>(...)`` (the methods are
now in the same class). Method bodies otherwise byte-identical.

All callers updated:
  ``self.<method>(self.invariant_checker, ...)`` →
  ``self.invariant_checker.<method>(...)``
(pure prefix transformation). 5 callsites in ``scheduler.py``
(``on_idle`` / ``_maybe_log_idle_metrics`` / ``run_batch`` /
``event_loop_overlap``) + 1 callsite in ``create_scheduler_watchdog``
(also in ``scheduler.py`` post-pre-prep).

Final cleanup:
- Drop ``SchedulerRuntimeCheckerMixin`` from ``Scheduler``'s inheritance
  list and from the import in ``scheduler.py``.
- Delete ``python/sglang/srt/managers/scheduler_runtime_checker_mixin.py``
  (now empty after the 10 method bodies are moved out and
  ``create_scheduler_watchdog`` already moved in pre-prep).
"""
AREA = "mech_scheduler"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


# Source-order so the methods land in the target class in the same order
# they appeared in the mixin file (cut bottom-up to preserve line ranges).
METHOD_ORDER = [
    "_check_pool_invariant",
    "_check_full_pool",
    "_check_swa_pool",
    "_check_mamba_pool",
    "_get_total_uncached_sizes",
    "self_check_during_busy",
    "_check_req_pool",
    "_report_leak",
    "_check_all_pools",
    "_check_tree_cache",
]


def _strip_staticmethod_typeflip(method_text: str, *, target_class: str) -> str:
    """Drop @staticmethod, the ``self: TargetClass`` annotation, and the
    ``SchedulerRuntimeCheckerMixin.<sibling>(self, ...)`` qualified form on
    internal sibling calls.

    Sibling-call stripping is regex-based (tolerates single-line and
    multi-line black formatting alike).
    """
    text = method_text.replace("    @staticmethod\n", "", 1)
    text = text.replace(f'self: "{target_class}"', "self")
    # Sibling call with self positional arg: ``SchedulerRuntimeCheckerMixin.foo(self, ...)``
    # → ``self.foo(...)``
    text = re.sub(
        r"SchedulerRuntimeCheckerMixin\.(\w+)\(\s*self\s*(?:,\s*)?",
        r"self.\1(",
        text,
        flags=re.DOTALL,
    )
    # Sibling staticmethod call (no self positional): ``SchedulerRuntimeCheckerMixin.foo(args)``
    # → ``self.foo(args)`` (Python @staticmethod accessed via instance is fine).
    text = re.sub(
        r"SchedulerRuntimeCheckerMixin\.(\w+)\(",
        r"self.\1(",
        text,
    )
    return text


def transform(wt: Path) -> None:
    src = wt / "python/sglang/srt/managers/scheduler_runtime_checker_mixin.py"
    sched = wt / "python/sglang/srt/managers/scheduler.py"
    target = wt / "python/sglang/srt/managers/scheduler_components/invariant_checker.py"

    # 1. Cut the 10 methods from the mixin (bottom-up to keep line ranges valid).
    method_blocks = []
    for name in reversed(METHOD_ORDER):
        s, e = find_method_lines(
            src.read_text(),
            class_name="SchedulerRuntimeCheckerMixin",
            method_name=name,
        )
        block = cut_lines(src, s, e)
        if name == "_check_pool_invariant":
            # _check_pool_invariant was a true @staticmethod in source mixin
            # (not a typeflip-prep). Preserve its decorator. Only strip the
            # sibling-call qualifier (none expected, but keep regex consistent).
            import re as _re
            block = _re.sub(
                r"SchedulerRuntimeCheckerMixin\.(\w+)\(\s*self\s*(?:,\s*)?",
                r"self.\1(",
                block,
                flags=_re.DOTALL,
            )
            block = _re.sub(
                r"SchedulerRuntimeCheckerMixin\.(\w+)\(",
                r"self.\1(",
                block,
            )
        else:
            block = _strip_staticmethod_typeflip(
                block, target_class="SchedulerInvariantChecker"
            )
        method_blocks.append(block)
    method_blocks.reverse()

    # 2. Append into the SchedulerInvariantChecker class body. The skeleton
    # ends with the last ctor assignment; append after that (methods already
    # have 4-space class-body indent).
    rtext = target.read_text()
    rtext = rtext.rstrip() + "\n\n" + "".join(method_blocks).rstrip() + "\n"
    target.write_text(rtext)

    # 3. Drop the now-empty mixin file. Before deleting, verify that nothing
    # is left except the module docstring / imports — the file should be
    # empty of class / function bodies post-cut.
    src.unlink()

    # 4. ``scheduler.py``: drop ``SchedulerRuntimeCheckerMixin`` from the
    # inheritance list and from the import block.
    text = sched.read_text()
    text = replace_call_site(
        text,
        old=(
            "from sglang.srt.managers.scheduler_runtime_checker_mixin import (\n"
            "    SchedulerRuntimeCheckerMixin,\n"
            ")\n"
        ),
        new="",
    )
    text = replace_call_site(text, old="    SchedulerRuntimeCheckerMixin,\n", new="")

    # 5. Caller rewrites: ``<receiver>.<method>(<receiver>.invariant_checker, ...)``
    # → ``<receiver>.invariant_checker.<method>(...)``. ``<receiver>`` is
    # ``self`` (most call sites) or ``scheduler`` (inside create_scheduler_watchdog).
    for receiver_method in [
        ("self", "_check_all_pools"),
        ("self", "_report_leak"),
        ("self", "_check_req_pool"),
        ("self", "_check_tree_cache"),
        ("self", "self_check_during_busy"),
        ("scheduler", "_check_all_pools"),
    ]:
        receiver, method = receiver_method
        if receiver == "self":
            try:
                text = rewrite_method_call_site(
                    text, method_name=method, target_attr="invariant_checker"
                )
            except ValueError:
                pass
        else:
            # ``scheduler`` receiver — manual regex (rewrite_method_call_site is
            # ``self``-hardcoded).
            pattern_nargs = (
                rf"{re.escape(receiver)}\.{re.escape(method)}\(\s*"
                rf"{re.escape(receiver)}\.invariant_checker,\s*"
            )
            pattern_noargs = (
                rf"{re.escape(receiver)}\.{re.escape(method)}\(\s*"
                rf"{re.escape(receiver)}\.invariant_checker\s*\)"
            )
            text = re.sub(
                pattern_noargs,
                f"{receiver}.invariant_checker.{method}()",
                text,
            )
            text = re.sub(
                pattern_nargs,
                f"{receiver}.invariant_checker.{method}(",
                text,
            )

    sched.write_text(text)


if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        area_branch=AREA_BRANCH,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
