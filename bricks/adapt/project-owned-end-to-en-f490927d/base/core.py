import re

_ALLOWED_INPUT_KEYS = {"service_name"}
_SERVICE_NAME_RE = re.compile(r"^[a-z][a-z0-9-]{2,40}$")

_APP_SOURCE = r'''import logging
import math
import os
import sqlite3
from typing import Any

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel
from pyspark.sql import SparkSession
from pyspark.sql import functions as F

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
LOG = logging.getLogger("portfolio_service")

app = FastAPI(title="Portfolio Foundry Local Agent Service", version="1.0.0")

DOCS = [
    {"id": "pricing", "text": "portfolio pricing transfer rates margin profitability", "quality": 0.93},
    {"id": "risk", "text": "portfolio risk capital liquidity stress limits", "quality": 0.89},
    {"id": "planning", "text": "business planning forecast budget finance scenario", "quality": 0.87},
]

_SPARK = None


class InferenceRequest(BaseModel):
    query: str


def _split_tokens(text: str) -> list[str]:
    current = []
    out = []
    for ch in text.lower():
        if ch.isalnum():
            current.append(ch)
        elif current:
            out.append("".join(current))
            current = []
    if current:
        out.append("".join(current))
    return out


def _retrieve(query: str) -> list[dict[str, Any]]:
    terms = set(_split_tokens(query))
    ranked = []
    for doc in DOCS:
        overlap = len(terms & set(_split_tokens(doc["text"])))
        ranked.append({
            **doc,
            "overlap": overlap,
            "retrieval_score": round(overlap + doc["quality"], 4),
        })
    ranked.sort(key=lambda item: (-item["retrieval_score"], item["id"]))
    return ranked[:2]


def _sql_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    con = sqlite3.connect(":memory:")
    try:
        con.execute("CREATE TABLE retrieved (doc_id TEXT, overlap INTEGER, quality REAL)")
        con.executemany(
            "INSERT INTO retrieved(doc_id, overlap, quality) VALUES (?, ?, ?)",
            [(row["id"], row["overlap"], row["quality"]) for row in rows],
        )
        count, overlap_sum, avg_quality = con.execute(
            "SELECT COUNT(*), SUM(overlap), AVG(quality) FROM retrieved"
        ).fetchone()
        return {
            "row_count": int(count),
            "overlap_sum": int(overlap_sum or 0),
            "avg_quality": round(float(avg_quality or 0.0), 4),
        }
    finally:
        con.close()


def _spark_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    global _SPARK
    if _SPARK is None:
        _SPARK = (
            SparkSession.builder
            .master("local[1]")
            .appName("portfolio-foundry-local")
            .config("spark.ui.enabled", "false")
            .config("spark.ui.showConsoleProgress", "false")
            .getOrCreate()
        )
        _SPARK.sparkContext.setLogLevel("ERROR")
    frame = _SPARK.createDataFrame(
        [(row["id"], int(row["overlap"]), float(row["quality"])) for row in rows],
        ["doc_id", "overlap", "quality"],
    )
    result = frame.agg(
        F.count("*").alias("row_count"),
        F.max("overlap").alias("max_overlap"),
        F.avg("quality").alias("avg_quality"),
    ).collect()[0]
    return {
        "row_count": int(result["row_count"]),
        "max_overlap": int(result["max_overlap"] or 0),
        "avg_quality": round(float(result["avg_quality"] or 0.0), 4),
    }


def _model_score(sql_metrics: dict[str, Any], spark_metrics: dict[str, Any]) -> float:
    linear = (
        0.55 * sql_metrics["overlap_sum"]
        + 0.35 * spark_metrics["max_overlap"]
        + 0.25 * sql_metrics["avg_quality"]
        - 0.4
    )
    return round(1.0 / (1.0 + math.exp(-linear)), 6)


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": "portfolio-foundry-local-agent",
        "profile": os.environ.get("APP_PROFILE", "local"),
        "secret_configured": bool(os.environ.get("SERVICE_TOKEN")),
    }


@app.post("/infer")
def infer(body: InferenceRequest, x_service_token: str | None = Header(default=None)) -> dict[str, Any]:
    expected = os.environ.get("SERVICE_TOKEN")
    if not expected:
        LOG.error("inference_error reason=service_token_not_configured")
        raise HTTPException(status_code=503, detail="service token is not configured")
    if x_service_token != expected:
        LOG.error("inference_error reason=unauthorized")
        raise HTTPException(status_code=401, detail="unauthorized")

    query = body.query.strip()
    if not query:
        LOG.error("inference_error reason=blank_query")
        raise HTTPException(status_code=400, detail="query must not be blank")

    rows = _retrieve(query)
    sql_metrics = _sql_metrics(rows)
    spark_metrics = _spark_metrics(rows)
    model_score = _model_score(sql_metrics, spark_metrics)
    response = {
        "status": "ok",
        "agent_path": "retrieve->sql->pyspark->local_model",
        "query": query,
        "top_document": rows[0]["id"],
        "retrieved_documents": [row["id"] for row in rows],
        "sql_metrics": sql_metrics,
        "spark_metrics": spark_metrics,
        "model_score": model_score,
        "profile": os.environ.get("APP_PROFILE", "local"),
    }
    LOG.info(
        "inference_success top_document=%s model_score=%s",
        response["top_document"],
        response["model_score"],
    )
    return response
'''

_DOCKERFILE = r'''FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    SPARK_LOCAL_IP=127.0.0.1

RUN apt-get update \
    && apt-get install -y --no-install-recommends openjdk-17-jre-headless \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY app.py /app/app.py

RUN useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
'''

_REQUIREMENTS = '''fastapi>=0.110,<1
uvicorn>=0.29,<1
pyspark>=3.5,<4
'''


def execute(payload):
    if not isinstance(payload, dict):
        raise TypeError("payload must be a dict")
    unknown = sorted(set(payload) - _ALLOWED_INPUT_KEYS)
    if unknown:
        raise ValueError("unsupported payload keys: " + ", ".join(unknown))

    service_name = payload.get("service_name", "portfolio-foundry-agent")
    if not isinstance(service_name, str) or not _SERVICE_NAME_RE.fullmatch(service_name):
        raise ValueError("service_name must match ^[a-z][a-z0-9-]{2,40}$")

    return {
        "kind": "project_owned_docker_bundle",
        "service_name": service_name,
        "files": {
            "Dockerfile": _DOCKERFILE,
            "requirements.txt": _REQUIREMENTS,
            "app.py": _APP_SOURCE,
        },
        "runtime_contract": {
            "required_environment": ["SERVICE_TOKEN"],
            "optional_environment": {"APP_PROFILE": "local"},
            "http": {
                "port": 8000,
                "health": {"method": "GET", "path": "/health"},
                "inference": {
                    "method": "POST",
                    "path": "/infer",
                    "auth_header": "x-service-token",
                    "json_body": {"query": "string"},
                },
            },
        },
        "proof_scope": "LOCAL",
        "technology_evidence": {
            "api": "FastAPI",
            "container": "Docker",
            "sql": "sqlite3 SQL SELECT execution",
            "spark": "PySpark SparkSession/DataFrame aggregation",
            "agent_path": "retrieve->sql->pyspark->local_model",
        },
    }
