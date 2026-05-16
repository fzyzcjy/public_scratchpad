"""One-shot batch SUBJECT rewrite for the mech_scheduler chain.

Reads the SUBJECT mapping below and replaces each script's
``SUBJECT = "..."`` literal in place. Uses libcst-style ast walk for
the locator and a regex-based replacement that survives both single
and double quotes.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

NEW_SUBJECTS: dict[str, str] = {
    "extract-get-draft-kv-pool-prep": "Decouple _get_draft_kv_pool from self before extraction",
    "extract-get-draft-kv-pool-move": "Move get_draft_kv_pool to mem_cache.kv_cache_builder",
    "extract-maybe-register-hicache-draft-prep": "Decouple _maybe_register_hicache_draft from self",
    "extract-maybe-register-hicache-draft-move": "Move maybe_register_hicache_draft to mem_cache.kv_cache_builder",
    "extract-build-kv-cache-pre-prep": "Hoist hisparse and decode-offload setup out of init_cache_with_memory_pool",
    "extract-build-kv-cache-prep": "Reshape init_cache_with_memory_pool to match the future build_kv_cache signature",
    "extract-build-kv-cache-move": "Move build_kv_cache to mem_cache.kv_cache_builder",
    "init-mode-conditional-defaults": "Pre-declare mode-conditional Scheduler fields with explicit defaults",
    "introduce-scheduler-request-receiver-prep": "Add SchedulerRequestReceiver and route request-ingress state through it",
    "introduce-scheduler-request-receiver-move": "Move request-ingress methods to SchedulerRequestReceiver",
    "migrate-dp-attn-mixin-prep": "Introduce SchedulerDPAttnAdapter to own DP-attention state",
    "migrate-dp-attn-mixin-move": "Move DP-attention adapter methods to SchedulerDPAttnAdapter",
    "migrate-profiler-mixin-pre-rename": "Mark init_profile/start_profile/stop_profile/profile as private",
    "migrate-profiler-mixin-pre-prep": "Inline init_profiler into Scheduler.__init__",
    "migrate-profiler-mixin-prep": "Stand up SchedulerProfilerManager; migrate profiler state to it",
    "migrate-profiler-mixin-move": "Move profiler controls to SchedulerProfilerManager",
    "migrate-update-weights-mixin-pre-prep1": "Park self.offload_tags next to the upcoming weight-updater constructor",
    "migrate-update-weights-mixin-pre-prep2": "Wrap weight-update RPC dispatch tuples in lambdas",
    "migrate-update-weights-mixin-prep": "Carve out SchedulerWeightUpdaterManager for weight-update state",
    "migrate-update-weights-mixin-move": "Move weight-update RPC handlers to SchedulerWeightUpdaterManager",
    "move-on-idle-to-scheduler-main": "Move on_idle from runtime_checker mixin into Scheduler",
    "introduce-pool-stats-observer-prep": "Add SchedulerPoolStatsObserver and route pool-stats state through it",
    "introduce-pool-stats-observer-move": "Move pool-stats sampling to SchedulerPoolStatsObserver",
    "introduce-invariant-checker-pre-prep": "Move create_scheduler_watchdog from runtime_checker mixin to scheduler.py",
    "introduce-invariant-checker-prep": "Introduce SchedulerInvariantChecker to own invariant-check state",
    "introduce-invariant-checker-move": "Move invariant checks to SchedulerInvariantChecker and retire runtime_checker mixin",
    "introduce-kv-events-publisher-pre-rename": "Make emit_kv_metrics and publish_kv_events public",
    "introduce-kv-events-publisher-prep": "Stand up SchedulerKvEventsPublisher; migrate KV-event state to it",
    "introduce-kv-events-publisher-move": "Move KV-cache event emission to SchedulerKvEventsPublisher",
    "introduce-load-inquirer-prep": "Carve out SchedulerLoadInquirer for queue-load state",
    "introduce-load-inquirer-move": "Move queue-load reporting to SchedulerLoadInquirer",
    "introduce-metrics-reporter-pre-rename": "Mark update_lora_metrics and calculate_utilization as private",
    "introduce-metrics-reporter-prep": "Add SchedulerMetricsReporter and route metrics state through it",
    "introduce-metrics-reporter-move": "Move metrics reporting to SchedulerMetricsReporter and retire metrics mixin",
    "move-maybe-log-idle-metrics-to-metrics-reporter": "Move idle-metrics logging to SchedulerMetricsReporter",
    "introduce-logprob-result-processor-pre-rename": "Make _calculate_num_input_logprobs public",
    "introduce-logprob-result-processor-prep": "Introduce SchedulerLogprobResultProcessor to own logprob state",
    "introduce-logprob-result-processor-move": "Move logprob assembly to SchedulerLogprobResultProcessor",
    "introduce-output-streamer-prep": "Stand up SchedulerOutputStreamer; migrate output-streaming state to it",
    "introduce-output-streamer-move": "Move output streaming to SchedulerOutputStreamer",
    "introduce-batch-result-processor-prep": "Carve out SchedulerBatchResultProcessor for batch-result state",
    "introduce-batch-result-processor-move": "Move batch-result processing to SchedulerBatchResultProcessor and retire output_processor mixin",
    "move-free-items-from-scheduler-py": "Move module-level helpers out of scheduler.py",
    "cleanup-scheduler-py-free-items": "Delete the now-unused is_work_request from scheduler.py",
}


def _find_subject_node(tree: ast.Module) -> ast.Assign:
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name) and target.id == "SUBJECT":
                return node
    raise ValueError("no top-level SUBJECT assignment found")


def _rewrite(path: Path, new_subject: str) -> tuple[str, str]:
    source = path.read_text()
    tree = ast.parse(source)
    node = _find_subject_node(tree)
    if not isinstance(node.value, ast.Constant) or not isinstance(node.value.value, str):
        raise ValueError(f"{path.name}: SUBJECT is not a string literal")
    old_subject = node.value.value

    if old_subject == new_subject:
        return old_subject, new_subject

    pattern = re.compile(r'^(SUBJECT\s*=\s*)(".*?"|\'.*?\')\s*$', re.MULTILINE)
    matches = pattern.findall(source)
    if len(matches) != 1:
        raise ValueError(f"{path.name}: expected 1 SUBJECT line, found {len(matches)}")

    replacement_literal = (
        '"' + new_subject.replace("\\", "\\\\").replace('"', '\\"') + '"'
    )
    new_source = pattern.sub(lambda m: m.group(1) + replacement_literal, source, count=1)

    # Sanity check: round-trip through ast and confirm new SUBJECT matches.
    new_tree = ast.parse(new_source)
    new_node = _find_subject_node(new_tree)
    assert isinstance(new_node.value, ast.Constant)
    assert new_node.value.value == new_subject, (
        f"{path.name}: round-trip failed: {new_node.value.value!r} != {new_subject!r}"
    )

    path.write_text(new_source)
    return old_subject, new_subject


def main() -> int:
    missing: list[str] = []
    changes: list[tuple[str, str, str]] = []
    for chain_id, new_subject in NEW_SUBJECTS.items():
        path = HERE / f"{chain_id}.py"
        if not path.exists():
            missing.append(chain_id)
            continue
        old, new = _rewrite(path, new_subject)
        marker = "skip" if old == new else "renamed"
        changes.append((chain_id, marker, f"{old!r} -> {new!r}"))

    for chain_id, marker, msg in changes:
        print(f"[{marker}] {chain_id}: {msg}")

    if missing:
        print("\nMISSING:")
        for chain_id in missing:
            print(f"  {chain_id}")
        return 1

    print(f"\nDone: {len(changes)} scripts processed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
