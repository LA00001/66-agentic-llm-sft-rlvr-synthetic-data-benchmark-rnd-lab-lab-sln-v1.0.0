import importlib.util
from pathlib import Path


TARGET = "agentic-benchmark-harne-b447fbac"
CORE = Path("src") / "bricks" / TARGET / "core.py"
spec = importlib.util.spec_from_file_location("benchmark_core", CORE)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def test_code_oracle_pass_and_intentional_wrong_answer():
    payload = {
        "tasks": [
            {
                "id": "code-pass",
                "domain": "code",
                "candidate": "sum_even",
                "cases": [[1, 2, 3, 4], [2, 6], []],
                "oracle": {"expected": [6, 8, 0]},
            },
            {
                "id": "code-intentional-fail",
                "domain": "code",
                "candidate": "sum_all",
                "cases": [[1, 2, 3, 4]],
                "oracle": {"expected": [6]},
            },
        ]
    }
    result = mod.execute(payload)
    first, second = result["verdicts"]
    assert first["passed"] is True
    assert first["failure_type"] is None
    assert first["evidence"]["actual"] == [6, 8, 0]
    assert first["evidence"]["executable_tests"] == 3
    assert second["passed"] is False
    assert second["failure_type"] == "wrong_answer"
    assert second["evidence"]["actual"] == [10]
    assert result["scores"]["domains"]["code"]["score"] == 0.5


def test_code_execution_and_oracle_failures_are_distinct():
    result = mod.execute({
        "tasks": [
            {
                "id": "execution-fail",
                "domain": "code",
                "candidate": "raise_error",
                "cases": [[1]],
                "oracle": {"expected": [1]},
            },
            {
                "id": "oracle-fail",
                "domain": "code",
                "candidate": "sum_even",
                "cases": [[2]],
                "oracle": {},
            },
        ]
    })
    assert result["verdicts"][0]["failure_type"] == "execution_failure"
    assert result["verdicts"][1]["failure_type"] == "oracle_failure"
    assert result["failure_taxonomy"] == {
        "execution_failure": 1,
        "oracle_failure": 1,
        "wrong_answer": 0,
    }
