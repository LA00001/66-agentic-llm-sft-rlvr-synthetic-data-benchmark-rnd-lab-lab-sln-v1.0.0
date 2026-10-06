import importlib.util
import json
import pathlib
import subprocess
import sys

from fastapi.testclient import TestClient


BRICK = "project-owned-end-to-en-f490927d"
CORE = pathlib.Path("src/bricks") / BRICK / "core.py"
spec = importlib.util.spec_from_file_location("candidate_integration_core", CORE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_end_to_end_service_and_clean_python_entrypoint():
    payload = {"seed": 1729, "samples": 24, "sft_epochs": 4, "rlvr_steps": 8}
    direct = module.execute(payload)
    assert direct["status"] == "completed"
    assert direct["pipeline"][-1] == "benchmark_evaluation"
    assert direct["experiment_artifact"]["sft"]["checkpoint_id"] == direct["checkpoints"]["sft"]
    assert direct["experiment_artifact"]["rlvr"]["checkpoint_id"] == direct["checkpoints"]["rlvr"]

    client = TestClient(module.app)
    health = client.get("/health")
    assert health.status_code == 200
    service = client.post("/experiment", json=payload)
    assert service.status_code == 200
    service_body = service.json()
    module.ExperimentResponse.model_validate(service_body)
    assert service_body["run_id"] == direct["run_id"]
    assert service_body["artifact_hash"] == direct["artifact_hash"]
    assert service_body["metrics"] == direct["metrics"]

    process = subprocess.run(
        [sys.executable, str(CORE)],
        cwd=str(pathlib.Path.cwd()),
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert process.returncode == 0, process.stderr
    entrypoint = json.loads(process.stdout.strip().splitlines()[-1])
    assert entrypoint["status"] == "completed"
    assert entrypoint["run_id"] == direct["run_id"]
    assert entrypoint["artifact_hash"] == direct["artifact_hash"]
    assert entrypoint["metrics"] == direct["metrics"]


def test_fixed_run_is_reproducible_across_service_calls():
    client = TestClient(module.app)
    payload = {"seed": 12345, "samples": 36, "sft_epochs": 5, "rlvr_steps": 9}
    first = client.post("/experiment", json=payload)
    second = client.post("/experiment", json=payload)
    assert first.status_code == 200
    assert second.status_code == 200
    a = first.json()
    b = second.json()
    assert a["run_id"] == b["run_id"]
    assert a["artifact_hash"] == b["artifact_hash"]
    assert a["metrics"] == b["metrics"]
    assert a["experiment_artifact"]["input_fingerprints"] == b["experiment_artifact"]["input_fingerprints"]
