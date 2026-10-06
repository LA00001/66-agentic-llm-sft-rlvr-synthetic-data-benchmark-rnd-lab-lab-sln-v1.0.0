from __future__ import annotations

import importlib.util
from pathlib import Path

TARGET = "scientifically-rigorous-2d3b54ba"
CORE = Path("src") / "bricks" / TARGET / "core.py"
spec = importlib.util.spec_from_file_location("candidate_core", CORE)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)

experiment = {
    "experiment_id": "rlvr-agent-eval-004",
    "hypothesis": "The trained checkpoint increases verified task success without exceeding the latency guardrail.",
    "primary_metric": "verified_success",
    "baseline": "baseline",
    "treatment": "rlvr",
    "baseline_checkpoint_id": "gigacode-base@rev-001",
    "trained_checkpoint_id": "gigacode-rlvr@rev-017",
    "expected_treatment_share": 0.5,
    "srm_alpha": 0.01,
    "guardrails": [{"metric": "latency_seconds", "direction": "max_increase", "limit": 0.25}],
    "acceptance_criterion": {"alpha": 0.05, "min_absolute_uplift": 0.10, "require_ci_above_zero": True}
}
records = []
for i in range(120):
    records.append({"variant": "baseline", "verified_success": 1 if i < 54 else 0, "latency_seconds": 1.0})
for i in range(120):
    records.append({"variant": "rlvr", "verified_success": 1 if i < 84 else 0, "latency_seconds": 1.1})

first = module.execute({"experiment_spec": experiment, "records": records})
second = module.execute({"experiment_spec": experiment, "records": records})

assert first == second
assert set(first) == {
    "experiment_id",
    "protocol",
    "experiment_spec",
    "experiment_spec_sha256",
    "dataset_sha256",
    "checkpoint_links",
    "design_validation",
    "primary_metric",
    "comparison",
    "guardrail_results",
    "acceptance_evidence",
    "verdict",
    "accepted"
}
assert first["protocol"] == "pre_registered_baseline_vs_treatment_v1"
assert len(first["experiment_spec_sha256"]) == 64
assert len(first["dataset_sha256"]) == 64
assert first["primary_metric"] == "verified_success"
assert first["checkpoint_links"] == {
    "baseline_checkpoint_id": "gigacode-base@rev-001",
    "trained_checkpoint_id": "gigacode-rlvr@rev-017"
}
assert isinstance(first["comparison"]["p_value"], float)
assert len(first["comparison"]["confidence_interval_95"]) == 2
assert first["design_validation"]["valid"] is True
assert first["acceptance_evidence"]["statistical_significance_met"] is True
assert first["acceptance_evidence"]["confidence_interval_requirement_met"] is True
assert first["accepted"] is True
assert first["verdict"] == "ACCEPT_TREATMENT"
