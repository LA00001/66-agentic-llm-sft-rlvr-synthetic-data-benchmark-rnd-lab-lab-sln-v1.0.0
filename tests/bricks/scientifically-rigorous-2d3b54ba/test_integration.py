from __future__ import annotations

import importlib.util
from pathlib import Path

TARGET = "scientifically-rigorous-2d3b54ba"
CORE = Path("src") / "bricks" / TARGET / "core.py"
spec = importlib.util.spec_from_file_location("candidate_core", CORE)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)


def make_payload(treatment_successes: int, treatment_latency: float = 1.05):
    experiment_spec = {
        "experiment_id": "domain-agent-sft-comparison",
        "hypothesis": "Domain SFT increases verified agent task completion relative to the frozen baseline while preserving latency.",
        "primary_metric": "verified_success",
        "baseline": "base",
        "treatment": "trained",
        "baseline_checkpoint_id": "agent-base@checkpoint-12000",
        "trained_checkpoint_id": "agent-sft@checkpoint-18500",
        "expected_treatment_share": 0.5,
        "srm_alpha": 0.01,
        "guardrails": [{"metric": "latency_seconds", "direction": "max_increase", "limit": 0.20}],
        "acceptance_criterion": {
            "alpha": 0.05,
            "min_absolute_uplift": 0.10,
            "require_ci_above_zero": True
        }
    }
    records = []
    for i in range(150):
        records.append({
            "task_id": f"base-{i:03d}",
            "variant": "base",
            "verified_success": 1 if i < 60 else 0,
            "latency_seconds": 1.0
        })
    for i in range(150):
        records.append({
            "task_id": f"trained-{i:03d}",
            "variant": "trained",
            "verified_success": 1 if i < treatment_successes else 0,
            "latency_seconds": treatment_latency
        })
    return {"experiment_spec": experiment_spec, "records": records}


strong = module.execute(make_payload(105))
repeat = module.execute(make_payload(105))
assert strong == repeat
assert strong["comparison"]["baseline_rate"] == 0.4
assert strong["comparison"]["treatment_rate"] == 0.7
assert strong["comparison"]["absolute_uplift"] == 0.3
assert strong["comparison"]["p_value"] < 0.05
assert strong["comparison"]["confidence_interval_95"][0] > 0.0
assert strong["design_validation"]["srm"]["valid"] is True
assert strong["accepted"] is True
assert strong["verdict"] == "ACCEPT_TREATMENT"

weak = module.execute(make_payload(66))
assert weak["comparison"]["treatment_rate"] == 0.44
assert weak["comparison"]["absolute_uplift"] == 0.04
assert weak["accepted"] is False
assert weak["verdict"] == "REJECT_INSUFFICIENT_EVIDENCE"

unsafe = module.execute(make_payload(105, treatment_latency=1.30))
assert unsafe["guardrail_results"][0]["passed"] is False
assert unsafe["accepted"] is False
assert unsafe["verdict"] == "REJECT_GUARDRAIL"

assert strong["experiment_spec"]["hypothesis"] == "Domain SFT increases verified agent task completion relative to the frozen baseline while preserving latency."
assert strong["experiment_spec"]["acceptance_criterion"]["min_absolute_uplift"] == 0.10
assert strong["checkpoint_links"]["baseline_checkpoint_id"] == "agent-base@checkpoint-12000"
assert strong["checkpoint_links"]["trained_checkpoint_id"] == "agent-sft@checkpoint-18500"
