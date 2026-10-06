from __future__ import annotations

import hashlib
import json
import math
import random
import sys
from typing import Any

import fastapi
import pydantic
import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field


class ExperimentRequest(BaseModel):
    seed: int = Field(default=1729, ge=0, le=2_147_483_647)
    samples: int = Field(default=24, ge=8, le=256)
    sft_epochs: int = Field(default=4, ge=1, le=50)
    rlvr_steps: int = Field(default=8, ge=1, le=100)


class ExperimentResponse(BaseModel):
    status: str
    run_id: str
    pipeline: list[str]
    metrics: dict[str, float]
    checkpoints: dict[str, str]
    artifact_hash: str
    experiment_artifact: dict[str, Any]


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _preflight() -> dict[str, Any]:
    modules = {
        "python": sys.version.split()[0],
        "fastapi": fastapi.__version__,
        "pydantic": pydantic.__version__,
        "uvicorn": uvicorn.__version__,
    }
    return {"status": "ready", "modules": modules, "fingerprint": _sha(modules)}


def _synthetic_data(seed: int, samples: int) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    domains = ("code", "sql", "office", "cyber")
    rows = []
    for i in range(samples):
        difficulty = rng.randint(1, 5)
        tool_required = rng.randint(0, 1)
        signal = rng.random()
        target = 1 if signal + 0.08 * tool_required - 0.035 * difficulty >= 0.43 else 0
        rows.append({
            "id": i,
            "domain": domains[i % len(domains)],
            "difficulty": difficulty,
            "tool_required": tool_required,
            "signal": round(signal, 8),
            "target": target,
        })
    return rows


def _features(row: dict[str, Any]) -> tuple[float, float, float, float]:
    domain_bias = {"code": 0.15, "sql": 0.10, "office": -0.05, "cyber": 0.05}[row["domain"]]
    return (1.0, float(row["signal"]), float(row["tool_required"]), float(row["difficulty"]) / 5.0 + domain_bias)


def _sigmoid(x: float) -> float:
    x = max(-30.0, min(30.0, x))
    return 1.0 / (1.0 + math.exp(-x))


def _predict(weights: list[float], row: dict[str, Any]) -> float:
    return _sigmoid(sum(w * x for w, x in zip(weights, _features(row))))


def _accuracy(weights: list[float], rows: list[dict[str, Any]]) -> float:
    correct = sum(int((_predict(weights, r) >= 0.5) == bool(r["target"])) for r in rows)
    return correct / len(rows)


def _sft(rows: list[dict[str, Any]], epochs: int) -> tuple[list[float], dict[str, Any]]:
    weights = [0.0, 0.0, 0.0, 0.0]
    lr = 0.35
    losses = []
    for _ in range(epochs):
        total = 0.0
        for row in rows:
            x = _features(row)
            y = float(row["target"])
            p = _predict(weights, row)
            total += -(y * math.log(max(p, 1e-12)) + (1.0 - y) * math.log(max(1.0 - p, 1e-12)))
            error = p - y
            for j in range(len(weights)):
                weights[j] -= lr * error * x[j] / len(rows)
        losses.append(round(total / len(rows), 8))
    artifact = {
        "method": "supervised_fine_tuning",
        "epochs": epochs,
        "weights": [round(v, 10) for v in weights],
        "losses": losses,
    }
    artifact["checkpoint_id"] = "sft-" + _sha(artifact)[:16]
    return weights, artifact


def _rlvr(rows: list[dict[str, Any]], initial: list[float], steps: int) -> tuple[list[float], dict[str, Any]]:
    weights = list(initial)
    lr = 0.08
    rewards = []
    for _ in range(steps):
        reward_sum = 0.0
        for row in rows:
            p = _predict(weights, row)
            predicted = int(p >= 0.5)
            verified_reward = 1.0 if predicted == row["target"] else -1.0
            reward_sum += verified_reward
            x = _features(row)
            direction = (float(row["target"]) - p) * max(0.25, abs(verified_reward))
            for j in range(len(weights)):
                weights[j] += lr * direction * x[j] / len(rows)
        rewards.append(round(reward_sum / len(rows), 8))
    artifact = {
        "method": "reinforcement_learning_with_verifiable_rewards",
        "steps": steps,
        "verifier": "exact_binary_outcome",
        "weights": [round(v, 10) for v in weights],
        "mean_rewards": rewards,
    }
    artifact["checkpoint_id"] = "rlvr-" + _sha(artifact)[:16]
    return weights, artifact


def _benchmark(weights: list[float], rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_domain = {}
    for domain in ("code", "sql", "office", "cyber"):
        subset = [r for r in rows if r["domain"] == domain]
        by_domain[domain] = round(_accuracy(weights, subset), 8)
    accuracy = round(_accuracy(weights, rows), 8)
    mean_confidence = round(sum(abs(_predict(weights, r) - 0.5) * 2.0 for r in rows) / len(rows), 8)
    return {"accuracy": accuracy, "mean_confidence": mean_confidence, "domain_accuracy": by_domain}


def execute(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise TypeError("payload must be a dict")
    allowed = {"seed", "samples", "sft_epochs", "rlvr_steps"}
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise ValueError("unknown payload keys: " + ",".join(unknown))
    request = ExperimentRequest.model_validate(payload)
    config = request.model_dump()
    preflight = _preflight()
    rows = _synthetic_data(request.seed, request.samples)
    input_fingerprint = _sha(rows)
    train_cut = max(4, int(len(rows) * 0.75))
    train = rows[:train_cut]
    benchmark_rows = rows[train_cut:]
    if not benchmark_rows:
        raise ValueError("benchmark split must not be empty")
    baseline = _benchmark([0.0, 0.0, 0.0, 0.0], benchmark_rows)
    sft_weights, sft_artifact = _sft(train, request.sft_epochs)
    sft_metrics = _benchmark(sft_weights, benchmark_rows)
    rlvr_weights, rlvr_artifact = _rlvr(train, sft_weights, request.rlvr_steps)
    final_metrics = _benchmark(rlvr_weights, benchmark_rows)
    identity = {
        "config": config,
        "input_fingerprint": input_fingerprint,
        "sft_checkpoint": sft_artifact["checkpoint_id"],
        "rlvr_checkpoint": rlvr_artifact["checkpoint_id"],
    }
    run_id = "run-" + _sha(identity)[:20]
    artifact = {
        "schema": "portfolio-foundry.experiment.v1",
        "run_id": run_id,
        "config": config,
        "seeds": {"synthetic_data": request.seed, "training_order": request.seed},
        "preflight": preflight,
        "input_fingerprints": {"synthetic_dataset": input_fingerprint},
        "dataset": {
            "samples": len(rows),
            "train_samples": len(train),
            "benchmark_samples": len(benchmark_rows),
            "domains": ["code", "sql", "office", "cyber"],
        },
        "sft": sft_artifact,
        "rlvr": rlvr_artifact,
        "checkpoints": {
            "sft": sft_artifact["checkpoint_id"],
            "rlvr": rlvr_artifact["checkpoint_id"],
        },
        "metrics": {
            "baseline_accuracy": baseline["accuracy"],
            "sft_accuracy": sft_metrics["accuracy"],
            "final_accuracy": final_metrics["accuracy"],
            "final_mean_confidence": final_metrics["mean_confidence"],
        },
        "benchmark": final_metrics,
        "pipeline": ["dependency_preflight", "synthetic_data", "sft", "rlvr", "benchmark_evaluation"],
    }
    artifact_hash = _sha(artifact)
    return {
        "status": "completed",
        "run_id": run_id,
        "pipeline": artifact["pipeline"],
        "metrics": artifact["metrics"],
        "checkpoints": artifact["checkpoints"],
        "artifact_hash": artifact_hash,
        "experiment_artifact": artifact,
    }


app = FastAPI(title="Portfolio Foundry Reproducible Experiment Service", version="1.0.0")


@app.get("/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "preflight": _preflight()}


@app.post("/experiment", response_model=ExperimentResponse)
def experiment(body: ExperimentRequest) -> ExperimentResponse:
    try:
        return ExperimentResponse.model_validate(execute(body.model_dump()))
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


if __name__ == "__main__":
    result = execute({"seed": 1729, "samples": 24, "sft_epochs": 4, "rlvr_steps": 8})
    print(_canonical({"status": result["status"], "run_id": result["run_id"], "artifact_hash": result["artifact_hash"], "metrics": result["metrics"]}))
