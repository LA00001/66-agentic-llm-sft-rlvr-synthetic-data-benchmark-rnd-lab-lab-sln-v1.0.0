import importlib.util
from pathlib import Path

import pandas as pd

TARGET = "synthetic-training-eval-00c1d43f"
path = Path("src") / "bricks" / TARGET / "core.py"
spec = importlib.util.spec_from_file_location("brick_core_integration", path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

source = pd.DataFrame([
    {"record_id": "1", "split": "train", "task_id": "task-1", "trajectory_id": "traj-1", "task": "Write SQL aggregation", "answer": "ok", "oracle_answer": "ok", "verifier_verdict": "pass", "reward": 0.95, "trajectory_steps": [{"role": "assistant", "content": "reason"}, {"role": "tool", "content": "result"}], "error_count": 0},
    {"record_id": "2", "split": "eval", "task_id": "task-2", "trajectory_id": "traj-2", "task": " write   sql aggregation ", "answer": "ok", "oracle_answer": "ok", "verifier_verdict": "pass", "reward": 0.92, "trajectory_steps": [{"role": "assistant", "content": "reason"}], "error_count": 0},
    {"record_id": "3", "split": "train", "task_id": "task-3", "trajectory_id": "traj-3", "task": "Python transformation", "answer": "wrong", "oracle_answer": "right", "verifier_verdict": "pass", "reward": 0.5, "trajectory_steps": [{"role": "assistant", "content": "attempt"}], "error_count": 0},
    {"record_id": "4", "split": "train", "task_id": "task-4", "trajectory_id": "traj-4", "task": "Broken agent run", "answer": "x", "oracle_answer": "y", "verifier_verdict": "fail", "reward": 0.2, "trajectory_steps": [], "error_count": 3},
    {"record_id": "5", "split": "train", "task_id": "task-5", "trajectory_id": "traj-5", "task": "Healthy independent task", "answer": "yes", "oracle_answer": "yes", "verifier_verdict": "pass", "reward": 0.8, "trajectory_steps": [{"role": "assistant", "content": "complete"}], "error_count": 0},
])
assert isinstance(source, pd.DataFrame)
result = mod.execute({"records": source.to_dict(orient="records"), "contamination_policy": "FAIL", "max_steps": 4, "max_errors": 0})
assert result["status"] == "FAIL"
assert result["metrics"]["input_rows"] == 5
assert result["metrics"]["clean_rows"] == 1
assert result["metrics"]["quarantined_rows"] == 4
assert result["metrics"]["partition_lossless"] is True
assert result["metrics"]["record_ids_preserved"] is True
assert [x["record_id"] for x in result["clean"]] == ["5"]
quarantine = {x["record_id"]: x["filter_reasons"] for x in result["quarantined"]}
assert quarantine["1"] == ["train_eval_contamination"]
assert quarantine["2"] == ["train_eval_contamination"]
assert "answer_oracle_verifier_inconsistency" in quarantine["3"]
assert "invalid_trajectory" in quarantine["4"]
assert "error_outlier" in quarantine["4"]
checks = {x["name"]: x["failed_rows"] for x in result["checks"]}
assert checks["train_eval_contamination"] == 2
assert checks["answer_oracle_verifier_inconsistency"] == 1
assert checks["invalid_trajectory"] == 1
assert checks["error_outlier"] == 1
recovered = result["clean"] + result["quarantined"]
assert sorted(x["record_id"] for x in recovered) == sorted(source["record_id"].tolist())
