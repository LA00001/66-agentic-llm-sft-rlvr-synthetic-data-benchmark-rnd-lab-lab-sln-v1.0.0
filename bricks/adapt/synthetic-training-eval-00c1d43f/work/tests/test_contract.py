import importlib.util
from pathlib import Path

import pandas as pd

TARGET = "synthetic-training-eval-00c1d43f"
path = Path("src") / "bricks" / TARGET / "core.py"
spec = importlib.util.spec_from_file_location("brick_core_contract", path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

records = pd.DataFrame([
    {"record_id": "a", "split": "train", "task_id": "ta", "trajectory_id": "xa", "task": "SELECT count rows", "answer": "3", "oracle_answer": "3", "verifier_verdict": "pass", "reward": 0.9, "trajectory_steps": [{"role": "assistant", "content": "query"}], "error_count": 0},
    {"record_id": "b", "split": "eval", "task_id": "tb", "trajectory_id": "xb", "task": " select   count rows ", "answer": "3", "oracle_answer": "3", "verifier_verdict": "pass", "reward": 0.9, "trajectory_steps": [{"role": "assistant", "content": "query"}], "error_count": 0},
    {"record_id": "c", "split": "train", "task_id": "tc", "trajectory_id": "xc", "task": "independent", "answer": "ok", "oracle_answer": "ok", "verifier_verdict": "pass", "reward": 0.7, "trajectory_steps": [{"role": "assistant", "content": "done"}], "error_count": 0},
])

warn = mod.execute({"records": records.to_dict(orient="records"), "contamination_policy": "WARN"})
fail = mod.execute({"records": records.to_dict(orient="records"), "contamination_policy": "FAIL"})
assert warn["status"] == "WARN"
assert fail["status"] == "FAIL"
assert warn["metrics"]["contaminated_rows"] == 2
assert warn["metrics"]["contaminated_task_count"] == 1
assert warn["metrics"]["clean_rows"] == 1
assert warn["metrics"]["quarantined_rows"] == 2
assert warn["metrics"]["input_rows"] == warn["metrics"]["clean_rows"] + warn["metrics"]["quarantined_rows"]
assert warn["metrics"]["partition_lossless"] is True
assert warn["metrics"]["record_ids_preserved"] is True
assert {r["record_id"] for r in warn["clean"] + warn["quarantined"]} == {"a", "b", "c"}
assert len(warn["contaminated_task_fingerprints"]) == 1

try:
    mod.execute({"records": records.to_dict(orient="records"), "contamination_policy": "IGNORE"})
    raise AssertionError("invalid policy was accepted")
except ValueError:
    pass
