import importlib.util
from pathlib import Path


TARGET = "agentic-benchmark-harne-b447fbac"
CORE = Path("src") / "bricks" / TARGET / "core.py"
spec = importlib.util.spec_from_file_location("benchmark_core", CORE)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def _code(task_id, candidate, expected):
    return {
        "id": task_id,
        "domain": "code",
        "candidate": candidate,
        "cases": [[1, 2, 3, 4]],
        "oracle": {"expected": [expected]},
    }


def _sql(task_id, query, expected):
    return {
        "id": task_id,
        "domain": "sql",
        "setup_sql": [
            "CREATE TABLE events(kind TEXT, value INTEGER)",
            "INSERT INTO events VALUES ('a', 3), ('a', 4), ('b', 10)"
        ],
        "query": query,
        "oracle": {"expected_rows": expected},
    }


def _tool(task_id, answer):
    expected_steps = [
        {"tool": "search", "arguments": {"q": "alpha"}, "observation": {"value": 5}},
        {"tool": "add", "arguments": {"a": 5, "b": 2}, "observation": 7}
    ]
    return {
        "id": task_id,
        "domain": "tool_use",
        "trajectory": {"steps": expected_steps, "final_answer": answer},
        "oracle": {"expected_steps": expected_steps, "expected_final_answer": 7},
    }


def test_real_code_sql_and_tool_use_benchmark_with_scores_and_failure_taxonomy():
    tasks = [
        _code("code-pass", "sum_even", 6),
        _code("code-wrong", "sum_all", 6),
        _sql(
            "sql-pass",
            "SELECT kind, SUM(value) FROM events GROUP BY kind ORDER BY kind",
            [["a", 7], ["b", 10]],
        ),
        _sql(
            "sql-wrong",
            "SELECT kind, COUNT(*) FROM events GROUP BY kind ORDER BY kind",
            [["a", 7], ["b", 10]],
        ),
        _tool("tool-pass", 7),
        _tool("tool-wrong", 8),
        {
            "id": "execution-failure",
            "domain": "code",
            "candidate": "raise_error",
            "cases": [[1]],
            "oracle": {"expected": [0]},
        },
        {
            "id": "oracle-failure",
            "domain": "sql",
            "setup_sql": ["CREATE TABLE t(x INTEGER)"],
            "query": "SELECT x FROM t",
            "oracle": {},
        },
    ]
    result = mod.execute({"tasks": tasks})
    verdicts = {v["task_id"]: v for v in result["verdicts"]}

    assert verdicts["code-pass"]["passed"] is True
    assert verdicts["sql-pass"]["passed"] is True
    assert verdicts["sql-pass"]["evidence"]["engine"] == "sqlite3"
    assert verdicts["sql-pass"]["evidence"]["actual_rows"] == [["a", 7], ["b", 10]]
    assert verdicts["tool-pass"]["passed"] is True
    assert verdicts["tool-pass"]["evidence"]["steps_match"] is True

    assert verdicts["code-wrong"]["failure_type"] == "wrong_answer"
    assert verdicts["sql-wrong"]["failure_type"] == "wrong_answer"
    assert verdicts["tool-wrong"]["failure_type"] == "wrong_answer"
    assert verdicts["execution-failure"]["failure_type"] == "execution_failure"
    assert verdicts["oracle-failure"]["failure_type"] == "oracle_failure"

    assert result["failure_taxonomy"] == {
        "execution_failure": 1,
        "oracle_failure": 1,
        "wrong_answer": 3,
    }
    assert result["scores"]["domains"]["code"] == {"passed": 1, "total": 3, "score": 1 / 3}
    assert result["scores"]["domains"]["sql"] == {"passed": 1, "total": 3, "score": 1 / 3}
    assert result["scores"]["domains"]["tool_use"] == {"passed": 1, "total": 2, "score": 0.5}
    assert result["scores"]["aggregate"] == {"passed": 3, "total": 8, "score": 3 / 8}
    assert len(result["evidence_manifest"]) == 8
    assert len({item["sha256"] for item in result["evidence_manifest"]}) == 8


def test_before_after_failure_analysis_uses_actual_benchmark_executions():
    baseline = [
        _code("b-code", "sum_all", 6),
        _sql("b-sql", "SELECT kind, COUNT(*) FROM events GROUP BY kind ORDER BY kind", [["a", 7], ["b", 10]]),
        _tool("b-tool", 8),
    ]
    trained = [
        _code("t-code", "sum_even", 6),
        _sql("t-sql", "SELECT kind, SUM(value) FROM events GROUP BY kind ORDER BY kind", [["a", 7], ["b", 10]]),
        _tool("t-tool", 7),
    ]
    result = mod.execute({
        "tasks": trained,
        "baseline_tasks": baseline,
        "trained_tasks": trained,
    })
    comparison = result["before_after"]
    assert comparison["baseline_scores"]["aggregate"]["score"] == 0.0
    assert comparison["trained_scores"]["aggregate"]["score"] == 1.0
    assert comparison["baseline_failure_distribution"]["wrong_answer"] == 3
    assert comparison["trained_failure_distribution"]["wrong_answer"] == 0
    assert comparison["changed_failure_categories"]["wrong_answer"] == -3
