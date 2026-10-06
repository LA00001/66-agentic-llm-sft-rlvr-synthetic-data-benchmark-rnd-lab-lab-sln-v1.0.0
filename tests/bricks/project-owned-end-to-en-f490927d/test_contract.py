import importlib.util
import pathlib

from fastapi.testclient import TestClient


BRICK = "project-owned-end-to-en-f490927d"
CORE = pathlib.Path("src/bricks") / BRICK / "core.py"
spec = importlib.util.spec_from_file_location("candidate_contract_core", CORE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_execute_contract_and_typed_fastapi_contract():
    direct = module.execute({"seed": 77, "samples": 24, "sft_epochs": 3, "rlvr_steps": 6})
    assert set(direct) == {"status", "run_id", "pipeline", "metrics", "checkpoints", "artifact_hash", "experiment_artifact"}
    assert isinstance(direct["run_id"], str) and direct["run_id"].startswith("run-")
    assert isinstance(direct["metrics"], dict)
    assert isinstance(direct["checkpoints"], dict)
    assert len(direct["artifact_hash"]) == 64

    client = TestClient(module.app)
    health = client.get("/health")
    assert health.status_code == 200
    health_body = health.json()
    assert health_body["status"] == "ok"
    assert health_body["preflight"]["status"] == "ready"

    response = client.post("/experiment", json={"seed": 77, "samples": 24, "sft_epochs": 3, "rlvr_steps": 6})
    assert response.status_code == 200
    body = response.json()
    validated = module.ExperimentResponse.model_validate(body)
    assert validated.status == "completed"
    assert validated.run_id == direct["run_id"]
    assert validated.artifact_hash == direct["artifact_hash"]
    assert validated.metrics == direct["metrics"]

    invalid = client.post("/experiment", json={"seed": 77, "samples": 2})
    assert invalid.status_code == 422
