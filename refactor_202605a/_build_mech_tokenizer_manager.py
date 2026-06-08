#!/usr/bin/env python3
"""Build tom_refactor_202605a/primary/mech_tokenizer_manager from `<id>.py` scripts.

Mirrors `_build_mech_model_runner.py`. See PR_CHAIN.md / CLAUDE.md (refactor-sprint).
"""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).parent
REPO = Path("/Users/tom/main/workspaces/ws-main/worktrees/sglang-dev-a")
WT = Path("/tmp/refactor-wt-mech-tokenizer-manager")
BASE = "main"
CHAIN_BRANCH = "tom_refactor_202605a/primary/mech_tokenizer_manager"
SKILL_PATH = REPO / ".claude/skills/mechanical-refactor-verify"


# Chain ordering (per plan §V2.2). Each entry = `<id>` of `<id>.py` script.
ORDER: list[str] = [
    # Stage 0 — 基础设施
    "move-req-state",
    "move-init-req-prep",
    "move-init-req-move",
    "move-logprob-ops-prep",
    "move-logprob-ops-move",
    "move-request-tracing-prep",
    "move-request-tracing-move",
    "move-spec-decoding-meta-prep",
    "move-spec-decoding-meta-move",
    # Stage 1 — score handler early
    "introduce-score-request-handler-prep",
    "introduce-score-request-handler-move",
    # Stage 2 — inputs
    "introduce-raw-tokenizer-wrapper-prep",
    "introduce-raw-tokenizer-wrapper-move",
    "rtw-prep-tokenize-helpers",
    "rtw-move-tokenize-helpers",
    "introduce-request-validator-prep",
    "introduce-request-validator-move",
    "introduce-tokenized-request-builder-prep",
    "introduce-tokenized-request-builder-move",
    "introduce-multimodal-processor-prep",
    "introduce-multimodal-processor-move",
    "introduce-request-preparer-prep",
    "introduce-request-preparer-move",
    # Stage 3 — observability
    "introduce-request-log-manager-prep",
    "introduce-request-log-manager-move",
    "introduce-request-metrics-recorder-prep",
    "introduce-request-metrics-recorder-move",
    # Stage 4 — control (session first; splits init_request_dispatcher)
    "introduce-session-controller-prep",
    "introduce-session-controller-move",
    "introduce-weight-updater-controller-prep",
    "introduce-weight-updater-controller-move",
    "introduce-lora-controller-prep",
    "introduce-lora-controller-move",
    "introduce-corpus-controller-prep",
    "introduce-corpus-controller-move",
    # Stage 5 — outputs
    "introduce-output-processor-prep",
    "introduce-output-processor-move",
    "introduce-response-emitter-prep",
    "introduce-response-emitter-move",
    # Stage 6 — _handle_batch_request 切段
    "extract-handle-batch-request-wait-yield",
    # Stage 8 — BatchRequestDispatcher 抽出
    "introduce-batch-request-dispatcher-prep",
    "introduce-batch-request-dispatcher-move",
    # Stage 7 — MM 分支抽出 (deferred — script TBD; non-canonical complexity per plan §V2.6)
    # "mmp-extract-tokenize-branch",
]


# PR grouping for the sglang-single-commit-pr-chain tool: script id ->
# (pr_id, sub_id). Grouped commits get subjects ``<pr_id>(<sub_id>): <subject>``
# and the LAST member of each group (in ORDER) carries a ``PR-Title:`` trailer
# with the umbrella title from PR_TITLES, so each group lands as ONE PR.
# Ids not listed stay singleton PRs (``<id>: <subject>``). Group members must be
# contiguous in ORDER.
PR_GROUPS: dict[str, tuple[str, str]] = {
    # Stage 0 — all free-helper moves land as one PR.
    "move-req-state": ("move-tm-free-helpers", "req-state"),
    "move-init-req-prep": ("move-tm-free-helpers", "init-req-prep"),
    "move-init-req-move": ("move-tm-free-helpers", "init-req-move"),
    "move-logprob-ops-prep": ("move-tm-free-helpers", "logprob-ops-prep"),
    "move-logprob-ops-move": ("move-tm-free-helpers", "logprob-ops-move"),
    "move-request-tracing-prep": ("move-tm-free-helpers", "request-tracing-prep"),
    "move-request-tracing-move": ("move-tm-free-helpers", "request-tracing-move"),
    "move-spec-decoding-meta-prep": ("move-tm-free-helpers", "spec-decoding-meta-prep"),
    "move-spec-decoding-meta-move": ("move-tm-free-helpers", "spec-decoding-meta-move"),
    # Component extractions — each prep+move pair lands as one PR.
    "introduce-score-request-handler-prep": ("introduce-score-request-handler", "prep"),
    "introduce-score-request-handler-move": ("introduce-score-request-handler", "move"),
    "introduce-raw-tokenizer-wrapper-prep": ("introduce-raw-tokenizer-wrapper", "prep"),
    "introduce-raw-tokenizer-wrapper-move": ("introduce-raw-tokenizer-wrapper", "move"),
    "rtw-prep-tokenize-helpers": ("introduce-raw-tokenizer-wrapper", "helpers-prep"),
    "rtw-move-tokenize-helpers": ("introduce-raw-tokenizer-wrapper", "helpers-move"),
    "introduce-request-validator-prep": ("introduce-request-validator", "prep"),
    "introduce-request-validator-move": ("introduce-request-validator", "move"),
    "introduce-tokenized-request-builder-prep": ("introduce-tokenized-request-builder", "prep"),
    "introduce-tokenized-request-builder-move": ("introduce-tokenized-request-builder", "move"),
    "introduce-multimodal-processor-prep": ("introduce-multimodal-processor", "prep"),
    "introduce-multimodal-processor-move": ("introduce-multimodal-processor", "move"),
    "introduce-request-preparer-prep": ("introduce-request-preparer", "prep"),
    "introduce-request-preparer-move": ("introduce-request-preparer", "move"),
    "introduce-request-log-manager-prep": ("introduce-request-log-manager", "prep"),
    "introduce-request-log-manager-move": ("introduce-request-log-manager", "move"),
    "introduce-request-metrics-recorder-prep": ("introduce-request-metrics-recorder", "prep"),
    "introduce-request-metrics-recorder-move": ("introduce-request-metrics-recorder", "move"),
    "introduce-session-controller-prep": ("introduce-session-controller", "prep"),
    "introduce-session-controller-move": ("introduce-session-controller", "move"),
    "introduce-weight-updater-controller-prep": ("introduce-weight-updater-controller", "prep"),
    "introduce-weight-updater-controller-move": ("introduce-weight-updater-controller", "move"),
    "introduce-lora-controller-prep": ("introduce-lora-controller", "prep"),
    "introduce-lora-controller-move": ("introduce-lora-controller", "move"),
    "introduce-corpus-controller-prep": ("introduce-corpus-controller", "prep"),
    "introduce-corpus-controller-move": ("introduce-corpus-controller", "move"),
    "introduce-output-processor-prep": ("introduce-output-processor", "prep"),
    "introduce-output-processor-move": ("introduce-output-processor", "move"),
    "introduce-response-emitter-prep": ("introduce-response-emitter", "prep"),
    "introduce-response-emitter-move": ("introduce-response-emitter", "move"),
    "extract-handle-batch-request-wait-yield": ("introduce-response-emitter", "wait-yield"),
    "introduce-batch-request-dispatcher-prep": ("introduce-batch-request-dispatcher", "prep"),
    "introduce-batch-request-dispatcher-move": ("introduce-batch-request-dispatcher", "move"),
}

PR_TITLES: dict[str, str] = {
    "move-tm-free-helpers": "Move TokenizerManager free helpers into tokenizer_manager_components",
    "introduce-score-request-handler": "Extract ScoreRequestHandler from TokenizerManager",
    "introduce-raw-tokenizer-wrapper": "Extract RawTokenizerWrapper from TokenizerManager",
    "introduce-request-validator": "Extract RequestValidator from TokenizerManager",
    "introduce-tokenized-request-builder": "Extract TokenizedRequestBuilder from TokenizerManager",
    "introduce-multimodal-processor": "Extract MultimodalProcessor from TokenizerManager",
    "introduce-request-preparer": "Extract RequestPreparer from TokenizerManager",
    "introduce-request-log-manager": "Extract RequestLogManager from TokenizerManager",
    "introduce-request-metrics-recorder": "Extract RequestMetricsRecorder from TokenizerManager",
    "introduce-session-controller": "Extract SessionController from TokenizerManager",
    "introduce-weight-updater-controller": "Extract WeightUpdaterController from TokenizerManager",
    "introduce-lora-controller": "Extract LoraController from TokenizerManager",
    "introduce-corpus-controller": "Extract CorpusController from TokenizerManager",
    "introduce-output-processor": "Extract OutputProcessor from TokenizerManager",
    "introduce-response-emitter": "Extract ResponseEmitter from TokenizerManager",
    "introduce-batch-request-dispatcher": "Extract BatchRequestDispatcher from TokenizerManager",
}


def _group_last_ids() -> set[str]:
    """The ORDER-wise last member of each PR group (carries the PR-Title trailer)."""
    last: dict[str, str] = {}
    for chain_id in ORDER:
        if chain_id in PR_GROUPS:
            last[PR_GROUPS[chain_id][0]] = chain_id
    return set(last.values())


GROUP_LAST_IDS: set[str] = _group_last_ids()


def run(cmd: list[str], *, cwd: Path, check: bool = True) -> str:
    print(f"$ {' '.join(cmd)}", flush=True)
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=check)
    if result.stdout:
        print(result.stdout, end="", flush=True)
    if result.stderr:
        print(result.stderr, end="", flush=True)
    return result.stdout + result.stderr


def make_worktree() -> None:
    if WT.exists():
        run(["git", "worktree", "remove", "--force", str(WT)], cwd=REPO, check=False)
        if WT.exists():
            shutil.rmtree(WT)
    run(["git", "fetch", "upstream", BASE], cwd=REPO)
    run(["git", "worktree", "add", "--detach", str(WT), f"upstream/{BASE}"], cwd=REPO)


def load_script(id: str):
    script_path = HERE / f"{id}.py"
    if not script_path.exists():
        raise FileNotFoundError(f"missing transform script: {script_path}")
    spec = importlib.util.spec_from_file_location(f"_chain_{id.replace('-', '_')}", script_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def commit_message(*, id: str, subject: str, body: str) -> str:
    body_clean = (body or "").rstrip()
    if id in PR_GROUPS:
        pr_id, sub_id = PR_GROUPS[id]
        parts = [f"{pr_id}({sub_id}): {subject}"]
    else:
        parts = [f"{id}: {subject}"]
    if body_clean:
        parts.extend(["", body_clean])
    parts.extend(["", f"Refactor chain ID: {id}"])
    if id in GROUP_LAST_IDS:
        parts.append(f"PR-Title: {PR_TITLES[PR_GROUPS[id][0]]}")
    return "\n".join(parts) + "\n"


def run_pre_commit(wt: Path) -> None:
    files = run(["git", "diff", "--name-only", "HEAD~1", "HEAD"], cwd=wt).split()
    if not files:
        return
    run(["pre-commit", "run", "--files", *files], cwd=wt, check=False)
    porcelain = run(["git", "status", "--porcelain"], cwd=wt).strip()
    if porcelain:
        run(["git", "add", "-A"], cwd=wt)
        run(["git", "commit", "--amend", "--no-edit", "--quiet"], cwd=wt)


def backup_old_chain_head() -> None:
    """Tag current upstream/<CHAIN_BRANCH> HEAD before force-push (per PR_CHAIN.md)."""
    run(["git", "fetch", "upstream", CHAIN_BRANCH], cwd=REPO, check=False)
    sha = run(
        ["git", "rev-parse", "--verify", "--quiet", f"upstream/{CHAIN_BRANCH}"],
        cwd=REPO,
        check=False,
    ).strip()
    if not sha:
        print(f"\n=== no existing upstream/{CHAIN_BRANCH} — skipping backup tag ===", flush=True)
        return
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")
    area = CHAIN_BRANCH.split("/")[-1]
    tag_name = f"backup/{timestamp}/{area}"
    print(f"\n=== backing up old upstream/{CHAIN_BRANCH} ({sha[:12]}) as {tag_name} on origin ===", flush=True)
    run(["git", "tag", tag_name, sha], cwd=REPO)
    run(["git", "push", "origin", f"refs/tags/{tag_name}"], cwd=REPO)


def main() -> None:
    if str(HERE) not in sys.path:
        sys.path.insert(0, str(HERE))
    if SKILL_PATH.exists() and str(SKILL_PATH) not in sys.path:
        sys.path.insert(0, str(SKILL_PATH))

    make_worktree()
    for id in ORDER:
        print(f"\n=== {id} ===", flush=True)
        module = load_script(id)
        subject = getattr(module, "SUBJECT", "")
        body = getattr(module, "BODY", "")
        if not subject:
            raise RuntimeError(f"{id}.py is missing SUBJECT")
        module.transform(WT)
        msg = commit_message(id=id, subject=subject, body=body)
        run(["git", "add", "-A"], cwd=WT)
        run(["git", "commit", "-m", msg, "--quiet"], cwd=WT)
        run_pre_commit(WT)

    # Final all-files pre-commit pass to match CI behavior. CI runs
    # ``pre-commit run --all-files``; the per-commit run only sees changed
    # files and can miss formatting drift in files isort/black retouches
    # later. Amend any auto-fix into the LAST commit so the chain HEAD is
    # CI-clean.
    print("\n=== final --all-files pre-commit pass ===", flush=True)
    run(["pre-commit", "run", "--all-files"], cwd=WT, check=False)
    porcelain = run(["git", "status", "--porcelain"], cwd=WT).strip()
    if porcelain:
        run(["git", "add", "-A"], cwd=WT)
        run(["git", "commit", "--amend", "--no-edit", "--quiet"], cwd=WT)

    print("\n=== chain built. final HEAD ===", flush=True)
    run(["git", "log", "--oneline", "-32"], cwd=WT)
    head = run(["git", "rev-parse", "HEAD"], cwd=WT).strip()
    backup_old_chain_head()
    print(
        f"\nTo publish, force-push the chain head:\n"
        f"  git -C {WT} push -f upstream HEAD:refs/heads/{CHAIN_BRANCH}\n"
        f"(HEAD={head[:12]})\n",
        flush=True,
    )


if __name__ == "__main__":
    main()
