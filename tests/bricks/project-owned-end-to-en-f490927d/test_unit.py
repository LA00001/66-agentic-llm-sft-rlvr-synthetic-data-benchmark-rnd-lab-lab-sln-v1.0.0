import importlib.util
import pathlib


BRICK = "project-owned-end-to-en-f490927d"
CORE = pathlib.Path("src/bricks") / BRICK / "core.py"
spec = importlib.util.spec_from_file_location("candidate_core", CORE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_execute_real_pipeline_and_artifact():
    result = module.execute({"seed": 41, "samples": 32, "sft_epochs": 5, "rlvr_steps": 10})
    assert result["status"] == "completed"
    assert result["pipeline"] == ["dependency_preflight", "synthetic_data", "sft", "rlvr", "benchmark_evaluation"]
    artifact = result["experiment_artifact"]
    assert artifact["preflight"]["status"] == "ready"
    assert {"python", "fastapi", "pydantic", "uvicorn"} <= set(artifact["preflight"]["modules"])
    assert artifact["dataset"]["samples"] == 32
    assert artifact["sft"]["method"] == "supervised_fine_tuning"
    assert len(artifact["sft"]["losses"]) == 5
    assert artifact["rlvr"]["method"] == "reinforcement_learning_with_verifiable_rewards"
    assert artifact["rlvr"]["verifier"] == "exact_binary_outcome"
    assert len(artifact["rlvr"]["mean_rewards"]) == 10
    assert artifact["checkpoints"]["sft"].startswith("sft-")
    assert artifact["checkpoints"]["rlvr"].startswith("rlvr-")
    assert len(artifact["input_fingerprints"]["synthetic_dataset"]) == 64
    assert 0.0 <= result["metrics"]["final_accuracy"] <= 1.0
    assert 0.0 <= result["metrics"]["final_mean_confidence"] <= 1.0


def test_reproducibility_and_seed_sensitivity():
    payload = {"seed": 9001, "samples": 40, "sft_epochs": 6, "rlvr_steps": 12}
    first = module.execute(payload)
    second = module.execute(payload)
    assert first["run_id"] == second["run_id"]
    assert first["artifact_hash"] == second["artifact_hash"]
    assert first["metrics"] == second["metrics"]
    assert first["experiment_artifact"] == second["experiment_artifact"]
    changed = module.execute({**payload, "seed": 9002})
    assert changed["experiment_artifact"]["input_fingerprints"]["synthetic_dataset"] != first["experiment_artifact"]["input_fingerprints"]["synthetic_dataset"]
    assert changed["run_id"] != first["run_id"]


def test_validation_rejects_bad_contract():
    try:
        module.execute({"seed": 1, "samples": 3})
    except Exception as exc:
        assert "samples" in str(exc)
    else:
        raise AssertionError("invalid sample count was accepted")
    try:
        module.execute({"seed": 1, "samples": 16, "unexpected": 1})
    except ValueError as exc:
        assert "unknown payload keys" in str(exc)
    else:
        raise AssertionError("unknown input key was accepted")
