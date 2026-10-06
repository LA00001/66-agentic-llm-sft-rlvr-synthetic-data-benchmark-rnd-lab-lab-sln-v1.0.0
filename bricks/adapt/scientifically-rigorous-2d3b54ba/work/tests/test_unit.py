from __future__ import annotations

import importlib.util
from pathlib import Path

TARGET = "scientifically-rigorous-2d3b54ba"
CORE = Path("src") / "bricks" / TARGET / "core.py"
spec = importlib.util.spec_from_file_location("candidate_core", CORE)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)


def experiment_spec():
    return {
        "experiment_id": "sft-code-eval-001",
        "hypothesis": "SFT checkpoint improves exact task success over the frozen baseline.",
        "primary_metric": "success",
        "baseline": "baseline",
        "treatment": "sft",
        "baseline_checkpoint_id": "base-model@sha256:111",
        "trained_checkpoint_id": "sft-model@sha256:222",
        "expected_treatment_share": 0.5,
        "srm_alpha": 0.01,
        "guardrails": [{"metric": "unsafe_rate", "direction": "max_increase", "limit": 0.02}],
        "acceptance_criterion": {
            "alpha": 0.05,
            "min_absolute_uplift": 0.10,
            "require_ci_above_zero": True
        }
    }


def balanced_records():
    rows = []
    for i in range(100):
        rows.append({"sample_id": f"b-{i}", "variant": "baseline", "success": 1 if i < 40 else 0, "unsafe_rate": 0.01})
    for i in range(100):
        rows.append({"sample_id": f"t-{i}", "variant": "sft", "success": 1 if i < 70 else 0, "unsafe_rate": 0.015})
    return rows


result = module.execute({"experiment_spec": experiment_spec(), "records": balanced_records()})
assert result["experiment_spec"]["hypothesis"].startswith("SFT checkpoint")
assert result["checkpoint_links"]["baseline_checkpoint_id"] == "base-model@sha256:111"
assert result["checkpoint_links"]["trained_checkpoint_id"] == "sft-model@sha256:222"
assert result["design_validation"]["srm"]["valid"] is True
assert result["comparison"]["baseline_n"] == 100
assert result["comparison"]["treatment_n"] == 100
assert result["comparison"]["baseline_rate"] == 0.4
assert result["comparison"]["treatment_rate"] == 0.7
assert result["comparison"]["absolute_uplift"] == 0.3
assert result["comparison"]["p_value"] < 0.05
assert result["comparison"]["confidence_interval_95"][0] > 0.0
assert result["guardrail_results"][0]["passed"] is True
assert result["accepted"] is True
assert result["verdict"] == "ACCEPT_TREATMENT"

bad_records = []
for i in range(190):
    bad_records.append({"variant": "baseline", "success": i % 2, "unsafe_rate": 0.01})
for i in range(10):
    bad_records.append({"variant": "sft", "success": i % 2, "unsafe_rate": 0.01})
try:
    module.execute({"experiment_spec": experiment_spec(), "records": bad_records})
except ValueError as exc:
    assert "sample ratio mismatch" in str(exc)
else:
    raise AssertionError("SRM-invalid experiment must fail explicitly")
