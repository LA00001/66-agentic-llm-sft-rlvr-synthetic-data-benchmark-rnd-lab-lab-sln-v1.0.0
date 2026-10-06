from __future__ import annotations

import hashlib
import json
import re
from typing import Any

import pandas as pd

_REQUIRED = [
    "record_id",
    "split",
    "task_id",
    "trajectory_id",
    "task",
    "answer",
    "oracle_answer",
    "verifier_verdict",
    "reward",
    "trajectory_steps",
    "error_count",
]


def _norm(value: Any) -> str:
    if value is None or (not isinstance(value, (list, dict)) and pd.isna(value)):
        return ""
    text = str(value).strip().lower()
    return re.sub(r"\s+", " ", text)


def _fingerprint(task: Any) -> str:
    return hashlib.sha256(_norm(task).encode("utf-8")).hexdigest()


def _trajectory_valid(value: Any) -> bool:
    if not isinstance(value, list) or not value:
        return False
    for step in value:
        if not isinstance(step, dict):
            return False
        if not _norm(step.get("role")) or not _norm(step.get("content")):
            return False
    return True


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    if isinstance(value, tuple):
        return [_json_safe(v) for v in value]
    if pd.isna(value) if not isinstance(value, (dict, list)) else False:
        return None
    if hasattr(value, "item"):
        return value.item()
    return value


def execute(payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise TypeError("payload must be a dict")
    records = payload.get("records")
    if not isinstance(records, list) or not records:
        raise ValueError("records must be a non-empty list")
    if not all(isinstance(row, dict) for row in records):
        raise ValueError("every record must be a dict")

    contamination_policy = str(payload.get("contamination_policy", "WARN")).upper()
    if contamination_policy not in {"WARN", "FAIL"}:
        raise ValueError("contamination_policy must be WARN or FAIL")
    max_steps = payload.get("max_steps", 32)
    max_errors = payload.get("max_errors", 0)
    if not isinstance(max_steps, int) or max_steps < 1:
        raise ValueError("max_steps must be a positive integer")
    if not isinstance(max_errors, int) or max_errors < 0:
        raise ValueError("max_errors must be a non-negative integer")

    df = pd.DataFrame(records).copy()
    original_columns = list(df.columns)
    missing_columns = [name for name in _REQUIRED if name not in df.columns]
    for name in missing_columns:
        df[name] = pd.NA

    df["_source_pos"] = range(len(df))
    df["_fingerprint"] = df["task"].map(_fingerprint)

    required_null = df[_REQUIRED].isna().any(axis=1)
    blank_required = pd.Series(False, index=df.index)
    for column in ["record_id", "split", "task_id", "trajectory_id", "task", "answer", "oracle_answer", "verifier_verdict"]:
        blank_required |= df[column].map(_norm).eq("")
    schema_or_null = required_null | blank_required

    record_id_duplicate = df["record_id"].notna() & df.duplicated("record_id", keep=False)
    task_id_duplicate = df["task_id"].notna() & df.duplicated("task_id", keep=False)
    trajectory_id_duplicate = df["trajectory_id"].notna() & df.duplicated("trajectory_id", keep=False)
    duplicate_any = record_id_duplicate | task_id_duplicate | trajectory_id_duplicate

    invalid_trajectory = ~df["trajectory_steps"].map(_trajectory_valid)
    split_invalid = ~df["split"].map(_norm).isin({"train", "eval"})

    answer_matches_oracle = pd.Series(
        [_norm(a) == _norm(o) and _norm(a) != "" for a, o in zip(df["answer"], df["oracle_answer"])],
        index=df.index,
    )
    verdict = df["verifier_verdict"].map(_norm)
    verdict_invalid = ~verdict.isin({"pass", "fail"})
    verifier_contradiction = ((verdict == "pass") & ~answer_matches_oracle) | ((verdict == "fail") & answer_matches_oracle) | verdict_invalid

    reward_numeric = pd.to_numeric(df["reward"], errors="coerce")
    reward_outlier = reward_numeric.isna() | reward_numeric.lt(0.0) | reward_numeric.gt(1.0)
    trajectory_length = df["trajectory_steps"].map(lambda value: len(value) if isinstance(value, list) else 0)
    length_outlier = trajectory_length.gt(max_steps)
    error_numeric = pd.to_numeric(df["error_count"], errors="coerce")
    error_outlier = error_numeric.isna() | error_numeric.lt(0) | error_numeric.gt(max_errors)

    train_fingerprints = set(df.loc[df["split"].map(_norm).eq("train"), "_fingerprint"])
    eval_fingerprints = set(df.loc[df["split"].map(_norm).eq("eval"), "_fingerprint"])
    contaminated_fingerprints = train_fingerprints.intersection(eval_fingerprints)
    contamination = df["_fingerprint"].isin(contaminated_fingerprints)

    masks = {
        "schema_or_required_null": schema_or_null,
        "duplicate_record_id": record_id_duplicate,
        "duplicate_task_id": task_id_duplicate,
        "duplicate_trajectory_id": trajectory_id_duplicate,
        "invalid_trajectory": invalid_trajectory,
        "invalid_split": split_invalid,
        "answer_oracle_verifier_inconsistency": verifier_contradiction,
        "reward_outlier": reward_outlier,
        "length_outlier": length_outlier,
        "error_outlier": error_outlier,
        "train_eval_contamination": contamination,
    }

    reasons = []
    for idx in df.index:
        row_reasons = [name for name, mask in masks.items() if bool(mask.loc[idx])]
        reasons.append(row_reasons)
    df["filter_reasons"] = reasons

    quarantine_mask = pd.Series([bool(x) for x in reasons], index=df.index)
    clean_df = df.loc[~quarantine_mask].copy()
    quarantine_df = df.loc[quarantine_mask].copy()

    artifact_columns = original_columns + (["filter_reasons"] if "filter_reasons" not in original_columns else [])
    clean_artifact = clean_df[artifact_columns].to_dict(orient="records")
    quarantine_artifact = quarantine_df[artifact_columns].to_dict(orient="records")

    recovered_positions = sorted(clean_df["_source_pos"].tolist() + quarantine_df["_source_pos"].tolist())
    partition_lossless = recovered_positions == list(range(len(df))) and len(clean_df) + len(quarantine_df) == len(df)

    original_ids = [_norm(x) for x in df["record_id"].tolist()]
    partition_ids = [_norm(x) for x in clean_df["record_id"].tolist()] + [_norm(x) for x in quarantine_df["record_id"].tolist()]
    ids_preserved = sorted(original_ids) == sorted(partition_ids)

    checks = [{"name": name, "failed_rows": int(mask.sum())} for name, mask in masks.items()]
    checks.append({"name": "duplicate_any", "failed_rows": int(duplicate_any.sum())})

    contamination_count = int(contamination.sum())
    if contamination_count and contamination_policy == "FAIL":
        status = "FAIL"
    elif bool(quarantine_mask.any()) or contamination_count:
        status = "WARN"
    else:
        status = "PASS"

    result = {
        "status": status,
        "contamination_policy": contamination_policy,
        "checks": checks,
        "metrics": {
            "input_rows": int(len(df)),
            "clean_rows": int(len(clean_df)),
            "quarantined_rows": int(len(quarantine_df)),
            "failed_rows": int(quarantine_mask.sum()),
            "contaminated_rows": contamination_count,
            "contaminated_task_count": int(len(contaminated_fingerprints)),
            "partition_lossless": bool(partition_lossless),
            "record_ids_preserved": bool(ids_preserved),
        },
        "contaminated_task_fingerprints": sorted(contaminated_fingerprints),
        "clean": _json_safe(clean_artifact),
        "quarantined": _json_safe(quarantine_artifact),
    }
    return result
