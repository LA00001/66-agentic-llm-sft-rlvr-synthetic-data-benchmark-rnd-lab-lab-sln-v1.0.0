import hashlib
import importlib.util
import json
from pathlib import Path


TARGET = "agentic-benchmark-harne-b447fbac"
CORE = Path("src") / "bricks" / TARGET / "core.py"
spec = importlib.util.spec_from_file_location("benchmark_core", CORE)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def test_contract_schema_scores_and_manifest_checksums():
    payload = {
        "tasks": [
            {
                "id": "code-1",
                "domain": "code",
                "candidate": "max_or_none",
                "cases": [[1, 9, 3], []],
                "oracle": {"expected": [9, None]},
            },
            {
                "id": "sql-1",
                "domain": "sql",
                "setup_sql": [
                    "CREATE TABLE sales(region TEXT, amount INTEGER)",
                    "INSERT INTO sales VALUES ('a', 10), ('a', 5), ('b', 7)"
                ],
                "query": "SELECT region, SUM(amount) FROM sales GROUP BY region ORDER BY region",
                "oracle": {"expected_rows": [["a", 15], ["b", 7]]},
            },
            {
                "id": "tool-1",
                "domain": "tool_use",
                "trajectory": {
                    "steps": [
                        {"tool": "lookup", "arguments": {"key": "x"}, "observation": 4},
                        {"tool": "multiply", "arguments": {"a": 4, "b": 3}, "observation": 12}
                    ],
                    "final_answer": 12
                },
                "oracle": {
                    "expected_steps": [
                        {"tool": "lookup", "arguments": {"key": "x"}, "observation": 4},
                        {"tool": "multiply", "arguments": {"a": 4, "b": 3}, "observation": 12}
                    ],
                    "expected_final_answer": 12
                },
            },
        ]
    }
    result = mod.execute(payload)
    assert result["schema"] == "foundry.agentic_benchmark_harness.v1"
    assert result["task_schema"]["domains"] == ["code", "sql", "tool_use"]
    assert result["failure_types"] == ["execution_failure", "oracle_failure", "wrong_answer"]
    assert result["scores"]["aggregate"] == {"passed": 3, "total": 3, "score": 1.0}
    assert set(result["scores"]["domains"]) == {"code", "sql", "tool_use"}
    assert len(result["evidence_manifest"]) == 3
    assert all(len(item["sha256"]) == 64 for item in result["evidence_manifest"])
    assert all(int(item["sha256"], 16) >= 0 for item in result["evidence_manifest"])
    without_checksum = {k: v for k, v in result.items() if k != "result_sha256"}
    expected = hashlib.sha256(_canonical(without_checksum)).hexdigest()
    assert result["result_sha256"] == expected


def test_contract_rejects_missing_tasks():
    try:
        mod.execute({})
    except ValueError as exc:
        assert "payload.tasks" in str(exc)
    else:
        raise AssertionError("missing tasks must be rejected")
