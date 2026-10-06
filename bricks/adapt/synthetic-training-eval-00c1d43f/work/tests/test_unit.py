import importlib.util
from pathlib import Path

import pandas as pd

TARGET = "synthetic-training-eval-00c1d43f"
path = Path("src") / "bricks" / TARGET / "core.py"
spec = importlib.util.spec_from_file_location("brick_core", path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def row(record_id, split, task_id, trajectory_id, task, answer="4", oracle="4", verdict="pass", reward=0.8, steps=None, errors=0):
    return {
        "record_id": record_id,
        "split": split,
        "task_id": task_id,
        "trajectory_id": trajectory_id,
        "task": task,
        "answer": answer,
        "oracle_answer": oracle,
        "verifier_verdict": verdict,
        "reward": reward,
        "trajectory_steps": steps if steps is not None else [{"role": "assistant", "content": "solve"}],
        "error_count": errors,
    }


records = [
    row("r1", "train", "t1", "tr1", "Add 2 + 2"),
    row("r2", "train", "dup", "tr2", "Unique train task"),
    row("r3", "train", "dup", "tr3", "Another task"),
    row("r4", "eval", "t4", "tr4", "  ADD   2 + 2  "),
    row("r5", "train", "t5", "same-tr", "Bad trajectory", steps=[]),
    row("r6", "train", "t6", "same-tr", "Wrong verifier", answer="5", oracle="4", verdict="pass"),
    row("r7", "train", "t7", "tr7", "Reward bad", reward=1.5),
    row("r8", "train", "t8", "tr8", "Too long", steps=[{"role": "assistant", "content": "x"}, {"role": "tool", "content": "y"}, {"role": "assistant", "content": "z"}]),
    row("r9", "train", "t9", "tr9", "Errors", errors=2),
    row("r10", "train", "t10", "tr10", "Clean task"),
]

frame = pd.DataFrame(records)
assert isinstance(frame, pd.DataFrame)
result = mod.execute({"records": frame.to_dict(orient="records"), "max_steps": 2, "max_errors": 0, "contamination_policy": "WARN"})
checks = {c["name"]: c["failed_rows"] for c in result["checks"]}
assert result["status"] == "WARN"
assert checks["duplicate_task_id"] == 2
assert checks["duplicate_trajectory_id"] == 2
assert checks["invalid_trajectory"] == 1
assert checks["train_eval_contamination"] == 2
assert checks["answer_oracle_verifier_inconsistency"] == 1
assert checks["reward_outlier"] == 1
assert checks["length_outlier"] == 1
assert checks["error_outlier"] == 1
assert result["metrics"]["partition_lossless"] is True
assert result["metrics"]["record_ids_preserved"] is True
assert result["metrics"]["input_rows"] == 10
assert result["metrics"]["clean_rows"] == 1
assert result["metrics"]["quarantined_rows"] == 9
assert result["clean"][0]["record_id"] == "r10"
quarantine = {x["record_id"]: x["filter_reasons"] for x in result["quarantined"]}
assert "train_eval_contamination" in quarantine["r1"]
assert "train_eval_contamination" in quarantine["r4"]
assert "duplicate_task_id" in quarantine["r2"]
assert "duplicate_task_id" in quarantine["r3"]
assert "invalid_trajectory" in quarantine["r5"]
assert "answer_oracle_verifier_inconsistency" in quarantine["r6"]
assert "reward_outlier" in quarantine["r7"]
assert "length_outlier" in quarantine["r8"]
assert "error_outlier" in quarantine["r9"]
