from __future__ import annotations

from math import erfc, sqrt
from typing import Any
import hashlib
import json
import pandas as pd

_REQUIRED_SPEC_FIELDS = (
    "experiment_id",
    "hypothesis",
    "primary_metric",
    "baseline",
    "treatment",
    "acceptance_criterion",
)


def _finite_number(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be numeric")
    result = float(value)
    if pd.isna(result) or result in (float("inf"), float("-inf")):
        raise ValueError(f"{name} must be finite")
    return result


def _canonical_hash(value: dict) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _validate_spec(raw: Any) -> dict:
    if not isinstance(raw, dict):
        raise ValueError("experiment_spec must be an object")
    missing = [field for field in _REQUIRED_SPEC_FIELDS if field not in raw]
    if missing:
        raise ValueError("experiment_spec missing fields: " + ", ".join(missing))

    spec = {
        "experiment_id": str(raw["experiment_id"]).strip(),
        "hypothesis": str(raw["hypothesis"]).strip(),
        "primary_metric": str(raw["primary_metric"]).strip(),
        "baseline": str(raw["baseline"]).strip(),
        "treatment": str(raw["treatment"]).strip(),
        "baseline_checkpoint_id": str(raw.get("baseline_checkpoint_id", "")).strip(),
        "trained_checkpoint_id": str(raw.get("trained_checkpoint_id", "")).strip(),
        "expected_treatment_share": _finite_number(raw.get("expected_treatment_share", 0.5), "expected_treatment_share"),
        "srm_alpha": _finite_number(raw.get("srm_alpha", 0.01), "srm_alpha"),
        "guardrails": raw.get("guardrails", []),
        "acceptance_criterion": raw["acceptance_criterion"],
    }
    for field in ("experiment_id", "hypothesis", "primary_metric", "baseline", "treatment", "baseline_checkpoint_id", "trained_checkpoint_id"):
        if not spec[field]:
            raise ValueError(f"{field} must be non-empty")
    if spec["baseline"] == spec["treatment"]:
        raise ValueError("baseline and treatment labels must differ")
    if not 0.0 < spec["expected_treatment_share"] < 1.0:
        raise ValueError("expected_treatment_share must be between 0 and 1")
    if not 0.0 < spec["srm_alpha"] < 1.0:
        raise ValueError("srm_alpha must be between 0 and 1")
    if not isinstance(spec["guardrails"], list):
        raise ValueError("guardrails must be a list")

    criterion = spec["acceptance_criterion"]
    if not isinstance(criterion, dict):
        raise ValueError("acceptance_criterion must be an object")
    allowed = {"alpha", "min_absolute_uplift", "require_ci_above_zero"}
    if set(criterion) - allowed:
        raise ValueError("unsupported acceptance_criterion fields")
    normalized_criterion = {
        "alpha": _finite_number(criterion.get("alpha", 0.05), "acceptance_criterion.alpha"),
        "min_absolute_uplift": _finite_number(criterion.get("min_absolute_uplift", 0.0), "acceptance_criterion.min_absolute_uplift"),
        "require_ci_above_zero": bool(criterion.get("require_ci_above_zero", True)),
    }
    if not 0.0 < normalized_criterion["alpha"] < 1.0:
        raise ValueError("acceptance_criterion.alpha must be between 0 and 1")
    spec["acceptance_criterion"] = normalized_criterion

    normalized_guardrails = []
    for index, guardrail in enumerate(spec["guardrails"]):
        if not isinstance(guardrail, dict):
            raise ValueError(f"guardrails[{index}] must be an object")
        metric = str(guardrail.get("metric", "")).strip()
        direction = str(guardrail.get("direction", "")).strip()
        if not metric:
            raise ValueError(f"guardrails[{index}].metric must be non-empty")
        if direction not in {"max_increase", "max_decrease"}:
            raise ValueError(f"guardrails[{index}].direction is invalid")
        normalized_guardrails.append({
            "metric": metric,
            "direction": direction,
            "limit": _finite_number(guardrail.get("limit"), f"guardrails[{index}].limit"),
        })
    spec["guardrails"] = normalized_guardrails
    return spec


def _normal_two_sided_p(z: float) -> float:
    return erfc(abs(z) / sqrt(2.0))


def _binary_comparison(control: pd.Series, treatment: pd.Series) -> dict:
    if control.empty or treatment.empty:
        raise ValueError("both experiment groups must contain observations")
    valid_values = {0, 1, 0.0, 1.0, False, True}
    if not set(control.dropna().tolist()).issubset(valid_values) or not set(treatment.dropna().tolist()).issubset(valid_values):
        raise ValueError("primary metric must be binary 0/1")
    if control.isna().any() or treatment.isna().any():
        raise ValueError("primary metric contains null values")

    n_control = int(control.size)
    n_treatment = int(treatment.size)
    success_control = int(control.astype(int).sum())
    success_treatment = int(treatment.astype(int).sum())
    rate_control = success_control / n_control
    rate_treatment = success_treatment / n_treatment
    diff = rate_treatment - rate_control

    pooled = (success_control + success_treatment) / (n_control + n_treatment)
    pooled_se = sqrt(max(pooled * (1.0 - pooled) * (1.0 / n_control + 1.0 / n_treatment), 0.0))
    if pooled_se == 0.0:
        z_score = 0.0 if diff == 0.0 else (float("inf") if diff > 0 else float("-inf"))
        p_value = 1.0 if diff == 0.0 else 0.0
    else:
        z_score = diff / pooled_se
        p_value = _normal_two_sided_p(z_score)

    unpooled_se = sqrt(
        rate_control * (1.0 - rate_control) / n_control
        + rate_treatment * (1.0 - rate_treatment) / n_treatment
    )
    ci_low = diff - 1.96 * unpooled_se
    ci_high = diff + 1.96 * unpooled_se

    return {
        "baseline_n": n_control,
        "treatment_n": n_treatment,
        "baseline_successes": success_control,
        "treatment_successes": success_treatment,
        "baseline_rate": round(rate_control, 8),
        "treatment_rate": round(rate_treatment, 8),
        "absolute_uplift": round(diff, 8),
        "relative_uplift": None if rate_control == 0.0 else round(diff / rate_control, 8),
        "z_score": None if z_score in (float("inf"), float("-inf")) else round(z_score, 8),
        "p_value": round(p_value, 10),
        "confidence_interval_95": [round(ci_low, 8), round(ci_high, 8)],
    }


def _validate_srm(n_baseline: int, n_treatment: int, expected_treatment_share: float, alpha: float) -> dict:
    total = n_baseline + n_treatment
    if total <= 0:
        raise ValueError("experiment contains no observations")
    expected_treatment = total * expected_treatment_share
    expected_baseline = total - expected_treatment
    if expected_baseline <= 0.0 or expected_treatment <= 0.0:
        raise ValueError("invalid expected allocation")
    chi_square = (
        ((n_baseline - expected_baseline) ** 2) / expected_baseline
        + ((n_treatment - expected_treatment) ** 2) / expected_treatment
    )
    p_value = erfc(sqrt(chi_square / 2.0))
    result = {
        "observed": {"baseline": n_baseline, "treatment": n_treatment},
        "expected_treatment_share": round(expected_treatment_share, 8),
        "chi_square": round(chi_square, 8),
        "p_value": round(p_value, 10),
        "alpha": round(alpha, 8),
        "valid": bool(p_value >= alpha),
    }
    if not result["valid"]:
        raise ValueError(
            "sample ratio mismatch: experimental allocation is invalid "
            f"(p_value={result['p_value']}, alpha={result['alpha']})"
        )
    return result


def _evaluate_guardrails(df: pd.DataFrame, spec: dict) -> list[dict]:
    results = []
    for guardrail in spec["guardrails"]:
        metric = guardrail["metric"]
        if metric not in df.columns:
            raise ValueError(f"guardrail metric column is missing: {metric}")
        values = pd.to_numeric(df[metric], errors="coerce")
        if values.isna().any():
            raise ValueError(f"guardrail metric contains non-numeric/null values: {metric}")
        base_values = values[df["variant"] == spec["baseline"]]
        treatment_values = values[df["variant"] == spec["treatment"]]
        if base_values.empty or treatment_values.empty:
            raise ValueError(f"guardrail metric lacks observations: {metric}")
        baseline_mean = float(base_values.mean())
        treatment_mean = float(treatment_values.mean())
        delta = treatment_mean - baseline_mean
        if guardrail["direction"] == "max_increase":
            passed = delta <= guardrail["limit"]
        else:
            passed = (-delta) <= guardrail["limit"]
        results.append({
            "metric": metric,
            "direction": guardrail["direction"],
            "limit": round(guardrail["limit"], 8),
            "baseline_mean": round(baseline_mean, 8),
            "treatment_mean": round(treatment_mean, 8),
            "delta": round(delta, 8),
            "passed": bool(passed),
        })
    return results


def execute(payload):
    if not isinstance(payload, dict):
        raise ValueError("payload must be an object")
    spec = _validate_spec(payload.get("experiment_spec"))
    raw_records = payload.get("records")
    if not isinstance(raw_records, list) or not raw_records:
        raise ValueError("records must be a non-empty list")

    preregistered_spec = json.loads(json.dumps(spec, sort_keys=True))
    spec_hash = _canonical_hash(preregistered_spec)

    df = pd.DataFrame(raw_records)
    required_columns = {"variant", spec["primary_metric"]}
    missing_columns = sorted(required_columns - set(df.columns))
    if missing_columns:
        raise ValueError("records missing columns: " + ", ".join(missing_columns))
    if df["variant"].isna().any():
        raise ValueError("variant contains null values")
    unexpected = sorted(set(df["variant"].astype(str)) - {spec["baseline"], spec["treatment"]})
    if unexpected:
        raise ValueError("unexpected experiment variants: " + ", ".join(unexpected))

    baseline_rows = df.loc[df["variant"].astype(str) == spec["baseline"]]
    treatment_rows = df.loc[df["variant"].astype(str) == spec["treatment"]]
    srm = _validate_srm(
        int(len(baseline_rows)),
        int(len(treatment_rows)),
        spec["expected_treatment_share"],
        spec["srm_alpha"],
    )

    comparison = _binary_comparison(
        baseline_rows[spec["primary_metric"]],
        treatment_rows[spec["primary_metric"]],
    )
    guardrails = _evaluate_guardrails(df, spec)
    criterion = spec["acceptance_criterion"]

    statistical_significance = comparison["p_value"] <= criterion["alpha"]
    uplift_ok = comparison["absolute_uplift"] >= criterion["min_absolute_uplift"]
    ci_ok = (
        comparison["confidence_interval_95"][0] > 0.0
        if criterion["require_ci_above_zero"]
        else True
    )
    guardrails_ok = all(item["passed"] for item in guardrails)
    accepted = bool(statistical_significance and uplift_ok and ci_ok and guardrails_ok)

    if accepted:
        verdict = "ACCEPT_TREATMENT"
    elif not guardrails_ok:
        verdict = "REJECT_GUARDRAIL"
    elif comparison["absolute_uplift"] < 0.0 and statistical_significance:
        verdict = "REJECT_REGRESSION"
    else:
        verdict = "REJECT_INSUFFICIENT_EVIDENCE"

    dataset_fingerprint_material = df.sort_index(axis=1).to_json(orient="records", double_precision=15)
    dataset_hash = hashlib.sha256(dataset_fingerprint_material.encode("utf-8")).hexdigest()

    return {
        "experiment_id": spec["experiment_id"],
        "protocol": "pre_registered_baseline_vs_treatment_v1",
        "experiment_spec": preregistered_spec,
        "experiment_spec_sha256": spec_hash,
        "dataset_sha256": dataset_hash,
        "checkpoint_links": {
            "baseline_checkpoint_id": spec["baseline_checkpoint_id"],
            "trained_checkpoint_id": spec["trained_checkpoint_id"],
        },
        "design_validation": {
            "srm": srm,
            "valid": True,
        },
        "primary_metric": spec["primary_metric"],
        "comparison": comparison,
        "guardrail_results": guardrails,
        "acceptance_evidence": {
            "alpha": criterion["alpha"],
            "min_absolute_uplift": criterion["min_absolute_uplift"],
            "require_ci_above_zero": criterion["require_ci_above_zero"],
            "statistical_significance_met": bool(statistical_significance),
            "uplift_threshold_met": bool(uplift_ok),
            "confidence_interval_requirement_met": bool(ci_ok),
            "guardrails_met": bool(guardrails_ok),
        },
        "verdict": verdict,
        "accepted": accepted,
    }
