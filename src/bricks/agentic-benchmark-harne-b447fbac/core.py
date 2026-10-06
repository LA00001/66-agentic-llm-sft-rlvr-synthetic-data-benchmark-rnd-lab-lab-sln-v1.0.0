from __future__ import annotations

import hashlib
import json
import sqlite3
from collections import Counter, defaultdict
from typing import Any


FAILURE_TYPES = (
    "execution_failure",
    "oracle_failure",
    "wrong_answer",
)


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _checksum(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _candidate_sum_even(values: list[int]) -> int:
    return sum(v for v in values if v % 2 == 0)


def _candidate_sum_all(values: list[int]) -> int:
    return sum(values)


def _candidate_max_or_none(values: list[int]) -> int | None:
    return max(values) if values else None


def _candidate_raise(values: list[int]) -> int:
    raise RuntimeError("intentional candidate execution failure")


_CODE_CANDIDATES = {
    "sum_even": _candidate_sum_even,
    "sum_all": _candidate_sum_all,
    "max_or_none": _candidate_max_or_none,
    "raise_error": _candidate_raise,
}


def _validate_task(task: dict[str, Any]) -> None:
    if not isinstance(task, dict):
        raise ValueError("task must be an object")
    if not isinstance(task.get("id"), str) or not task["id"].strip():
        raise ValueError("task.id must be a non-empty string")
    if task.get("domain") not in {"code", "sql", "tool_use"}:
        raise ValueError("task.domain must be code, sql, or tool_use")


def _result(task: dict[str, Any], passed: bool, failure_type: str | None, reason: str, evidence: dict[str, Any]) -> dict[str, Any]:
    verdict = {
        "task_id": task["id"],
        "domain": task["domain"],
        "passed": passed,
        "failure_type": failure_type,
        "failure_reason": reason,
        "evidence": evidence,
    }
    artifact = {
        "task": task,
        "verdict": verdict,
    }
    verdict["artifact_sha256"] = _checksum(artifact)
    return verdict


def _run_code(task: dict[str, Any]) -> dict[str, Any]:
    oracle = task.get("oracle")
    if not isinstance(oracle, dict) or "expected" not in oracle:
        return _result(task, False, "oracle_failure", "code oracle requires expected", {"oracle_valid": False})

    candidate_name = task.get("candidate")
    candidate = _CODE_CANDIDATES.get(candidate_name)
    if candidate is None:
        return _result(task, False, "execution_failure", "unknown code candidate", {"candidate": candidate_name})

    cases = task.get("cases")
    if not isinstance(cases, list) or not cases:
        return _result(task, False, "oracle_failure", "code task requires non-empty cases", {"oracle_valid": False})
    expected = oracle["expected"]
    if not isinstance(expected, list) or len(expected) != len(cases):
        return _result(task, False, "oracle_failure", "expected results must align with cases", {"oracle_valid": False})

    actual = []
    try:
        for case in cases:
            if not isinstance(case, list) or any(not isinstance(v, int) or isinstance(v, bool) for v in case):
                return _result(task, False, "oracle_failure", "each code case must be a list of integers", {"oracle_valid": False})
            actual.append(candidate(case))
    except Exception as exc:
        return _result(
            task,
            False,
            "execution_failure",
            f"candidate raised {type(exc).__name__}: {exc}",
            {"candidate": candidate_name, "completed_cases": len(actual)},
        )

    passed = actual == expected
    return _result(
        task,
        passed,
        None if passed else "wrong_answer",
        "" if passed else "candidate outputs differ from deterministic oracle",
        {
            "candidate": candidate_name,
            "actual": actual,
            "expected": expected,
            "executable_tests": len(cases),
        },
    )


def _normalize_rows(rows: list[tuple[Any, ...]]) -> list[list[Any]]:
    return [list(row) for row in rows]


def _run_sql(task: dict[str, Any]) -> dict[str, Any]:
    oracle = task.get("oracle")
    if not isinstance(oracle, dict) or not isinstance(oracle.get("expected_rows"), list):
        return _result(task, False, "oracle_failure", "SQL oracle requires expected_rows", {"oracle_valid": False})

    setup = task.get("setup_sql")
    query = task.get("query")
    if not isinstance(setup, list) or not all(isinstance(s, str) and s.strip() for s in setup):
        return _result(task, False, "oracle_failure", "setup_sql must be a list of SQL statements", {"oracle_valid": False})
    if not isinstance(query, str) or not query.strip():
        return _result(task, False, "execution_failure", "SQL query is missing", {"query_executed": False})

    con = sqlite3.connect(":memory:")
    try:
        for statement in setup:
            con.execute(statement)
        rows = _normalize_rows(con.execute(query).fetchall())
    except sqlite3.Error as exc:
        return _result(
            task,
            False,
            "execution_failure",
            f"sqlite execution failed: {exc}",
            {"engine": "sqlite3", "query_executed": True},
        )
    finally:
        con.close()

    expected = oracle["expected_rows"]
    passed = rows == expected
    return _result(
        task,
        passed,
        None if passed else "wrong_answer",
        "" if passed else "SQL result set differs from expected oracle",
        {
            "engine": "sqlite3",
            "query_executed": True,
            "actual_rows": rows,
            "expected_rows": expected,
        },
    )


def _run_tool_use(task: dict[str, Any]) -> dict[str, Any]:
    oracle = task.get("oracle")
    if not isinstance(oracle, dict):
        return _result(task, False, "oracle_failure", "tool-use oracle must be an object", {"oracle_valid": False})
    expected_steps = oracle.get("expected_steps")
    if not isinstance(expected_steps, list) or "expected_final_answer" not in oracle:
        return _result(task, False, "oracle_failure", "tool-use oracle requires expected_steps and expected_final_answer", {"oracle_valid": False})

    trajectory = task.get("trajectory")
    if not isinstance(trajectory, dict):
        return _result(task, False, "execution_failure", "trajectory must be an object", {"trajectory_valid": False})
    steps = trajectory.get("steps")
    if not isinstance(steps, list):
        return _result(task, False, "execution_failure", "trajectory.steps must be a list", {"trajectory_valid": False})

    normalized = []
    for index, step in enumerate(steps):
        if not isinstance(step, dict):
            return _result(task, False, "execution_failure", f"trajectory step {index} is invalid", {"trajectory_valid": False})
        if not isinstance(step.get("tool"), str) or not isinstance(step.get("arguments"), dict) or "observation" not in step:
            return _result(task, False, "execution_failure", f"trajectory step {index} lacks tool/arguments/observation", {"trajectory_valid": False})
        normalized.append({
            "tool": step["tool"],
            "arguments": step["arguments"],
            "observation": step["observation"],
        })

    actual_answer = trajectory.get("final_answer")
    steps_match = normalized == expected_steps
    answer_match = actual_answer == oracle["expected_final_answer"]
    passed = steps_match and answer_match
    return _result(
        task,
        passed,
        None if passed else "wrong_answer",
        "" if passed else "tool calls, arguments, observations, or final answer differ from oracle",
        {
            "steps_match": steps_match,
            "answer_match": answer_match,
            "actual_steps": normalized,
            "expected_steps": expected_steps,
            "actual_final_answer": actual_answer,
            "expected_final_answer": oracle["expected_final_answer"],
        },
    )


def _run_task(task: dict[str, Any]) -> dict[str, Any]:
    _validate_task(task)
    if task["domain"] == "code":
        return _run_code(task)
    if task["domain"] == "sql":
        return _run_sql(task)
    return _run_tool_use(task)


def _score(verdicts: list[dict[str, Any]]) -> dict[str, Any]:
    by_domain: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for verdict in verdicts:
        by_domain[verdict["domain"]].append(verdict)

    domains = {}
    for domain in sorted(by_domain):
        items = by_domain[domain]
        passed = sum(1 for item in items if item["passed"])
        domains[domain] = {
            "passed": passed,
            "total": len(items),
            "score": passed / len(items),
        }

    total = len(verdicts)
    passed_total = sum(1 for item in verdicts if item["passed"])
    return {
        "domains": domains,
        "aggregate": {
            "passed": passed_total,
            "total": total,
            "score": passed_total / total if total else 0.0,
        },
    }


def _failure_distribution(verdicts: list[dict[str, Any]]) -> dict[str, int]:
    counts = Counter(v["failure_type"] for v in verdicts if v["failure_type"] is not None)
    return {name: counts.get(name, 0) for name in FAILURE_TYPES}


def _suite(tasks: list[dict[str, Any]]) -> dict[str, Any]:
    verdicts = [_run_task(task) for task in tasks]
    manifest = [
        {
            "task_id": verdict["task_id"],
            "domain": verdict["domain"],
            "sha256": verdict["artifact_sha256"],
        }
        for verdict in verdicts
    ]
    return {
        "verdicts": verdicts,
        "scores": _score(verdicts),
        "failure_taxonomy": _failure_distribution(verdicts),
        "evidence_manifest": manifest,
    }


def execute(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("payload must be an object")
    tasks = payload.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        raise ValueError("payload.tasks must be a non-empty list")

    suite = _suite(tasks)
    result = {
        "schema": "foundry.agentic_benchmark_harness.v1",
        "task_schema": {
            "required": ["id", "domain", "oracle"],
            "domains": ["code", "sql", "tool_use"],
        },
        "scoring_contract": "per-domain and aggregate exact-pass fraction",
        "failure_types": list(FAILURE_TYPES),
        **suite,
    }

    baseline = payload.get("baseline_tasks")
    trained = payload.get("trained_tasks")
    if baseline is not None or trained is not None:
        if not isinstance(baseline, list) or not baseline or not isinstance(trained, list) or not trained:
            raise ValueError("baseline_tasks and trained_tasks must both be non-empty lists")
        baseline_suite = _suite(baseline)
        trained_suite = _suite(trained)
        before = baseline_suite["failure_taxonomy"]
        after = trained_suite["failure_taxonomy"]
        changed = {
            name: after[name] - before[name]
            for name in FAILURE_TYPES
            if after[name] != before[name]
        }
        result["before_after"] = {
            "baseline_scores": baseline_suite["scores"],
            "trained_scores": trained_suite["scores"],
            "baseline_failure_distribution": before,
            "trained_failure_distribution": after,
            "changed_failure_categories": changed,
        }

    result["result_sha256"] = _checksum({k: v for k, v in result.items() if k != "result_sha256"})
    return result
