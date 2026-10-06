from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import signal
import socket
import subprocess
import sys
import time
import traceback
import zipfile
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


DEMO_REQUEST_TIMEOUT_SECONDS = float(os.environ.get("PORTFOLIO_FOUNDRY_DEMO_REQUEST_TIMEOUT_SECONDS", "120"))
SCENARIO_REQUEST_TIMEOUT_SECONDS = float(os.environ.get("PORTFOLIO_FOUNDRY_SCENARIO_REQUEST_TIMEOUT_SECONDS", str(DEMO_REQUEST_TIMEOUT_SECONDS)))
SMOKE_PROCESS_TIMEOUT_SECONDS = 180.0
DIAGNOSTICS_REQUEST_TIMEOUT_SECONDS = 15.0
SERVER_CLEANUP_GRACE_SECONDS = 5.0


def _evidence_reference(root: Path, evidence: Path, path: Path) -> str:
    path = path.resolve()
    try:
        return path.relative_to(root.resolve()).as_posix()
    except ValueError:
        return "evidence/v031/" + path.relative_to(evidence.resolve()).as_posix()


def _read_json(path: Path, fallback: object) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig")) if path.is_file() else fallback
    except Exception:
        return fallback


def _append_ndjson(path: Path, row: dict[str, object]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _write_json_resilient(path: Path, payload: object, *, retries: int = 40, delay: float = 0.025) -> bool:
    """BUILD100: telemetry/evidence writes must never abort Stage 9 because Windows briefly
    holds stage9-live-status.json while another writer/reader is active.
    Uses a unique sibling temp + atomic replace with bounded retry; falls back to direct write.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(payload, ensure_ascii=False, indent=2)
    last_error: Exception | None = None
    for attempt in range(max(1, retries)):
        tmp = path.with_name(f".{path.name}.{os.getpid()}.{time.time_ns()}.tmp")
        try:
            tmp.write_text(data, encoding="utf-8")
            os.replace(tmp, path)
            return True
        except (PermissionError, OSError) as exc:
            last_error = exc
            try:
                if tmp.exists():
                    tmp.unlink()
            except Exception:
                pass
            time.sleep(delay * min(8, attempt + 1))
        except Exception as exc:
            last_error = exc
            try:
                if tmp.exists():
                    tmp.unlink()
            except Exception:
                pass
            break
    try:
        path.write_text(data, encoding="utf-8")
        return True
    except Exception as exc:
        last_error = exc
    _append_ndjson(path.parent / "stage9-telemetry-write-warnings.ndjson", {
        "schema": "portfolio-foundry.stage9-telemetry-write-warning.v1",
        "path": str(path),
        "error": f"{type(last_error).__name__}: {last_error}" if last_error else "unknown",
        "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    })
    return False


def _delete_transient(path: Path, *, retries: int = 20, delay: float = 0.025) -> bool:
    """Best-effort removal of current-run transient proof so stale prior-run PASS/FAIL cannot be accepted."""
    if not path.exists():
        return True
    for attempt in range(max(1, retries)):
        try:
            path.unlink(missing_ok=True)
            return True
        except (PermissionError, OSError):
            time.sleep(delay * min(8, attempt + 1))
        except Exception:
            return False
    return not path.exists()


def _tail_text(path: Path, limit: int = 160_000) -> str:
    try:
        data = path.read_text(encoding="utf-8-sig", errors="replace")
        return data[-limit:]
    except Exception as exc:
        return f"<unavailable {type(exc).__name__}: {exc}>"


def _run_probe(command: list[str], cwd: Path, timeout: float = 15.0) -> dict[str, object]:
    """Best-effort diagnostic command. Probe failure is evidence, never Stage 9 failure."""
    try:
        result = subprocess.run(command, cwd=str(cwd), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
        return {"command": command, "exitCode": result.returncode, "stdout": (result.stdout or "")[-80_000:], "stderr": (result.stderr or "")[-80_000:]}
    except Exception as exc:
        return {"command": command, "error": f"{type(exc).__name__}: {exc}"}


def _collect_stage9_forensics(root: Path, evidence: Path, run_id: str, error: BaseException, problem_node: str | None, log_path: Path, python_executable: str) -> str | None:
    """BUILD151: create one self-contained forensic ZIP for any Stage 9 smoke failure.

    The bundle intentionally favors exhaustive local evidence over terse messages: current run
    context, runtime closure, inventory, checkpoints, smoke/graph events, worker request/response/
    status files, generated server log and bounded host probes. Environment secrets are not copied.
    """
    try:
        forensic_dir = evidence / "forensics" / run_id
        forensic_dir.mkdir(parents=True, exist_ok=True)
        summary = {
            "schema": "portfolio-foundry.stage9-forensics.v1",
            "runId": run_id,
            "problemNode": problem_node,
            "errorType": type(error).__name__,
            "error": str(error),
            "traceback": traceback.format_exc(),
            "python": sys.version,
            "pythonExecutable": python_executable,
            "platform": platform.platform(),
            "cwd": str(root),
            "serverLogTail": _tail_text(log_path),
            "probes": {
                "pipCheck": _run_probe([python_executable, "-m", "pip", "check"], root),
                "pipList": _run_probe([python_executable, "-m", "pip", "list", "--format=json"], root),
                "java": _run_probe(["java", "-version"], root, 8.0),
                "docker": _run_probe(["docker", "version", "--format", "{{json .}}"], root, 8.0),
                "processes": _run_probe(["tasklist.exe"] if os.name == "nt" else ["ps", "-ef"], root, 8.0),
            },
            "createdAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        _write_json_resilient(forensic_dir / "forensics-summary.json", summary)

        candidates = [
            root / "foundry" / "stage9-run-context.json",
            root / "foundry" / "stage9-live-status.json",
            root / "foundry" / "runtime-environment.json",
            root / "foundry" / "runtime-profile.json",
            root / "foundry" / "application-routes.json",
            root / "foundry" / "executable-capability-graph.json",
            evidence / "preflight.json",
            evidence / "runtime-invocation-inventory.json",
            evidence / "fixture-resolution.json",
            evidence / "dependency-resolution.json",
            evidence / "runtime-import-matrix.log",
            evidence / "contract-resolution.json",
            evidence / "stage9-checkpoint-index.json",
            evidence / "stage9-checkpoint-dependency-map.json",
            evidence / "stage9-checkpoint-decisions.ndjson",
            evidence / "stage9-control-events.ndjson",
            evidence / "stage9-smoke-events.ndjson",
            evidence / "stage9-graph-events.ndjson",
            evidence / "runtime-demo-run.json",
            evidence / "runtime-demo-http-response.json",
            evidence / "smoke-isolation.json",
            evidence / "runtime-smoke-cleanup.json",
            log_path,
        ]
        for source in candidates:
            if not source.is_file():
                continue
            destination = forensic_dir / "snapshot" / _evidence_reference(root, evidence, source)
            destination.parent.mkdir(parents=True, exist_ok=True)
            try:
                shutil.copy2(source, destination)
            except Exception:
                pass

        runtime_exec = evidence / "runtime-execution"
        if runtime_exec.is_dir():
            # Copy all current runtime worker receipts; they are small JSON/NDJSON files and are
            # the fastest route from a red Stage 9 card to the exact import/call/cleanup boundary.
            for source in runtime_exec.rglob("*"):
                if not source.is_file():
                    continue
                try:
                    destination = forensic_dir / "snapshot" / _evidence_reference(root, evidence, source)
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, destination)
                except Exception:
                    pass

        zip_path = evidence / f"stage9-forensics-{run_id}.zip"
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            for source in forensic_dir.rglob("*"):
                if source.is_file():
                    archive.write(source, source.relative_to(forensic_dir).as_posix())
        _write_json_resilient(evidence / "stage9-forensics-latest.json", {
            "schema": "portfolio-foundry.stage9-forensics-pointer.v1", "runId": run_id,
            "bundle": _evidence_reference(root, evidence, zip_path), "problemNode": problem_node,
            "error": str(error), "createdAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        })
        return _evidence_reference(root, evidence, zip_path)
    except Exception as bundle_exc:
        _append_ndjson(evidence / "stage9-forensics-errors.ndjson", {
            "schema": "portfolio-foundry.stage9-forensics-error.v1", "runId": run_id,
            "error": f"{type(bundle_exc).__name__}: {bundle_exc}",
            "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        })
        return None


def terminate_process_tree(proc: subprocess.Popen[object]) -> dict[str, object]:
    started = time.perf_counter()
    method = "NONE"
    detail = "already-exited"
    if proc.poll() is None:
        if os.name == "nt":
            method = "TASKKILL_TREE"
            try:
                result = subprocess.run(["taskkill.exe", "/PID", str(proc.pid), "/T", "/F"], capture_output=True, text=True, timeout=8)
                detail = (result.stdout or result.stderr or f"taskkill exit {result.returncode}").strip()[:4000]
            except Exception as exc:
                detail = f"taskkill failed: {type(exc).__name__}: {exc}"
                try: proc.kill()
                except Exception: pass
        else:
            method = "POSIX_PROCESS_GROUP"
            try:
                pgid = os.getpgid(proc.pid)
                os.killpg(pgid, signal.SIGTERM)
                try:
                    proc.wait(timeout=2.0)
                except subprocess.TimeoutExpired:
                    os.killpg(pgid, signal.SIGKILL)
                detail = f"process-group={pgid}"
            except Exception as exc:
                detail = f"killpg failed: {type(exc).__name__}: {exc}"
                try: proc.kill()
                except Exception: pass
        try: proc.wait(timeout=SERVER_CLEANUP_GRACE_SECONDS)
        except Exception: pass
    return {"method": method, "detail": detail, "exitCode": proc.poll(), "cleanupMs": int((time.perf_counter()-started)*1000)}


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def request(url: str, method: str = "GET", payload: dict[str, object] | None = None, timeout: float = 4.0) -> tuple[int, bytes]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    headers = {"Content-Type": "application/json; charset=utf-8"} if body is not None else {}
    req = Request(url, data=body, headers=headers, method=method)
    try:
        with urlopen(req, timeout=timeout) as response:
            return int(response.status), response.read()
    except HTTPError as exc:
        # v0.33.11.9: preserve structured server diagnostics instead of collapsing every demo failure to "HTTP 500".
        return int(exc.code), exc.read()


def _validate_route_contract(route_spec: object, api_route_spec: object, *, cases_materialized: bool, life_materialized: bool, effect_materialized: bool) -> dict[str, object]:
    """BUILD150: schema-driven route validation.

    Stage 9 must verify the route contract actually exposed by the candidate, but it must not
    freeze an old positional prefix. New product surfaces (for example Live Execution) may be
    inserted between long-lived routes without making an otherwise runnable candidate fail.
    """
    if not isinstance(route_spec, list) or not route_spec:
        raise RuntimeError("application-routes.json contains no UI routes")
    if not isinstance(api_route_spec, list):
        raise RuntimeError("/api/routes did not return a route list")

    def normalize(rows: list[object], source: str) -> list[tuple[str, str]]:
        normalized: list[tuple[str, str]] = []
        seen_ids: set[str] = set()
        seen_paths: set[str] = set()
        for index, raw in enumerate(rows):
            if not isinstance(raw, dict):
                raise RuntimeError(f"{source}[{index}] is not an object")
            route_id = str(raw.get("id") or "").strip()
            path = str(raw.get("path") or "").strip()
            if not route_id or not path:
                raise RuntimeError(f"{source}[{index}] is missing id/path")
            if route_id in seen_ids:
                raise RuntimeError(f"{source} contains duplicate route id: {route_id}")
            if path in seen_paths:
                raise RuntimeError(f"{source} contains duplicate route path: {path}")
            if not path.startswith("/app/"):
                raise RuntimeError(f"{source} route {route_id} has non-application path: {path}")
            seen_ids.add(route_id); seen_paths.add(path); normalized.append((route_id, path))
        return normalized

    declared = normalize(route_spec, "application-routes.json")
    served = normalize(api_route_spec, "/api/routes")
    if declared != served:
        raise RuntimeError(f"Candidate route contract drift: declared={declared}, served={served}")

    route_ids = [route_id for route_id, _ in declared]
    route_index = {route_id: index for index, route_id in enumerate(route_ids)}
    required = ["overview", "graph", "source", "evidence", "diagnostics"]
    missing = [route_id for route_id in required if route_id not in route_index]
    if missing:
        raise RuntimeError(f"Candidate route contract missing required routes: {missing}")
    if not (route_index["overview"] < route_index["graph"] < route_index["source"]):
        raise RuntimeError("Candidate route semantic order invalid: expected overview before graph before source")

    expected_default: str | None = None
    if cases_materialized:
        expected_default = "cases"
    elif life_materialized:
        expected_default = "story"
    elif effect_materialized:
        expected_default = "effect"
    if cases_materialized and "cases" not in route_index:
        raise RuntimeError("case-portfolio.json is materialized but route 'cases' is missing")
    if life_materialized and not cases_materialized and "story" not in route_index:
        raise RuntimeError("life-scenario.json is materialized but route 'story' is missing")
    if effect_materialized and "effect" not in route_index:
        raise RuntimeError("economic-effect.json is materialized but route 'effect' is missing")
    if expected_default and route_ids[0] != expected_default:
        raise RuntimeError(f"Candidate default route mismatch: expected {expected_default}, got {route_ids[0]}")

    # Optional/new surfaces may be inserted anywhere that preserves the semantic baseline order.
    # This is intentional: route presence/reachability/API parity are proof; adjacency is not.
    return {"route_ids": route_ids, "route_paths": [path for _, path in declared], "default_route": route_ids[0]}


def wait_ready(url: str, seconds: float = 12.0) -> None:
    deadline = time.time() + seconds
    last = "not started"
    while time.time() < deadline:
        try:
            status, body = request(url + "/health")
            data = json.loads(body)
            if status == 200 and data.get("status") == "READY":
                return
            last = f"HTTP {status}: {data}"
        except Exception as exc:
            last = str(exc)
        time.sleep(0.2)
    raise RuntimeError("server did not become READY: " + last)


def spark_smoke_if_required(root: Path) -> dict[str, object]:
    """Validate the host Spark dependency without Python-row serialization.

    BUILD153: Stage 9 already proves candidate graph execution separately. This final
    dependency probe exists only to prove that the prepared host runtime can start a JVM
    SparkSession. Using createDataFrame([...]) here needlessly exercises PySpark's
    Python-object serializer/cloudpickle path and can fail on a newly released Python
    runtime even when the candidate's sealed Spark/Docker execution is healthy.

    Run a JVM-native ``range(1).count()`` in an isolated child process instead. It proves
    Python -> Py4J -> JVM -> SparkSession end-to-end, avoids contaminating the smoke
    controller process, and preserves the complete traceback on a genuine dependency
    failure. This is vacancy-independent and applies to every Stage 9 closure containing
    PySpark.
    """
    profile_path = root / "foundry" / "runtime-profile.json"
    profile = json.loads(profile_path.read_text(encoding="utf-8")) if profile_path.is_file() else {}
    modules = {str(x).lower() for x in profile.get("optionalModules", [])}
    if "pyspark" not in modules:
        return {"pyspark": "NOT_REQUIRED", "mode": "DECLARATION_AWARE"}

    probe = r"""
import json, os, traceback
from pyspark.sql import SparkSession

spark = None
try:
    spark = (SparkSession.builder
             .master("local[1]")
             .appName("portfolio-foundry-v031-runtime-proof")
             .config("spark.ui.enabled", "false")
             .config("spark.ui.showConsoleProgress", "false")
             .getOrCreate())
    spark.sparkContext.setLogLevel("ERROR")
    rows = int(spark.range(1).count())
    if rows != 1:
        raise RuntimeError(f"unexpected Spark range count: {rows}")
    print(json.dumps({"status":"PASS","sparkVersion":str(spark.version),"rows":rows,"probe":"JVM_NATIVE_RANGE"}))
except Exception as exc:
    print(json.dumps({"status":"FAIL","error":f"{type(exc).__name__}: {exc}","traceback":traceback.format_exc(),"probe":"JVM_NATIVE_RANGE"}))
    raise SystemExit(43)
finally:
    if spark is not None:
        try: spark.stop()
        except Exception: pass
"""
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env.setdefault("SPARK_LOCAL_IP", "127.0.0.1")
    try:
        completed = subprocess.run(
            [sys.executable, "-c", probe],
            cwd=str(root),
            env=env,
            capture_output=True,
            text=True,
            timeout=75,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"PYSPARK_RUNTIME_PROBE_TIMEOUT: {exc}") from exc
    lines = [line.strip() for line in (completed.stdout or "").splitlines() if line.strip()]
    payload: dict[str, object] = {}
    for line in reversed(lines):
        try:
            candidate = json.loads(line)
            if isinstance(candidate, dict) and candidate.get("status") in {"PASS", "FAIL"}:
                payload = candidate
                break
        except Exception:
            continue
    if completed.returncode != 0 or payload.get("status") != "PASS":
        diagnostic = payload.get("traceback") or payload.get("error") or completed.stderr or completed.stdout or f"exit={completed.returncode}"
        raise RuntimeError(f"PYSPARK_RUNTIME_PROBE_FAILED: {diagnostic}")
    return {
        "pyspark": "PASS",
        "sparkVersion": str(payload.get("sparkVersion") or "unknown"),
        "probe": "JVM_NATIVE_RANGE",
        "processIsolation": "PASS",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--evidence-dir", default=os.environ.get("PORTFOLIO_FOUNDRY_RUNTIME_EVIDENCE_DIR", "evidence/v031"))
    args = parser.parse_args()
    root = Path(args.project_root).resolve()
    evidence = Path(args.evidence_dir)
    if not evidence.is_absolute():
        evidence = root / evidence
    evidence.mkdir(parents=True, exist_ok=True)
    port = free_port()
    server = root / "src" / "app" / "server.py"
    log_path = evidence / "runtime-smoke-server.log"
    checks: list[dict[str, object]] = []
    started = time.perf_counter()

    # BUILD90 / Stage 9.4: isolated smoke phases share the Factory run identity.
    context = _read_json(root / "foundry" / "stage9-run-context.json", {})
    if not isinstance(context, dict):
        context = {}
    run_id = str(context.get("runId") or f"stage9-smoke-{int(time.time()*1000)}")
    candidate_id = context.get("candidateId")
    vacancy_id = context.get("vacancyId")
    runtime_env = _read_json(root / "foundry" / "runtime-environment.json", {})
    if not isinstance(runtime_env, dict):
        runtime_env = {}
    cache_status = runtime_env.get("cacheStatus")
    runtime_id = runtime_env.get("runtimeId") or runtime_env.get("cache_key")
    event_path = evidence / "stage9-smoke-events.ndjson"
    isolation_path = evidence / "smoke-isolation.json"
    isolation_order = ["HTTP_ALIVE", "ROUTE_EXISTS", "GRAPH_LOADS", "BRICK_EXECUTES", "RESULT_RETURNED"]
    isolation: dict[str, dict[str, object]] = {key: {"id": key, "status": "NOT_RUN"} for key in isolation_order}
    current_isolation: str | None = None
    problem_node: str | None = None

    # BUILD100: runtime-smoke.json is a current-run receipt. Never let a prior run survive
    # into C# smoke evaluation. Keep runtime-demo-run.json because BUILD99 checkpoint bootstrap
    # intentionally consumes the immediately previous compatible demo.
    _delete_transient(evidence / "runtime-smoke.json")
    _delete_transient(evidence / "runtime-demo-http-response.json")
    _delete_transient(evidence / "smoke-isolation.json")

    def persist_isolation(primary_error: str | None = None) -> None:
        payload = {
            "schema": "portfolio-foundry.stage9-isolated-smoke.v1", "runId": run_id,
            "candidateId": candidate_id, "vacancyId": vacancy_id, "runtimeId": runtime_id, "cacheStatus": cache_status,
            "status": "PASS" if all(isolation[x].get("status") == "PASS" for x in isolation_order) else ("FAIL" if any(isolation[x].get("status") == "FAIL" for x in isolation_order) else "RUNNING"),
            "phases": [isolation[x] for x in isolation_order], "problemNode": problem_node, "primaryError": primary_error,
            "updatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        _write_json_resilient(isolation_path, payload)

    def live(phase: str, status: str, detail: str, *, node: str | None = None, current: int | None = None, total: int | None = None, wait_reason: str | None = None) -> None:
        payload = {
            "schema": "portfolio-foundry.stage9-live-status.v3", "runId": run_id, "candidateId": candidate_id, "vacancyId": vacancy_id,
            "phase": phase, "status": status, "detail": detail, "current": current, "total": total, "currentNode": node,
            "runtimeId": runtime_id, "runtimeCacheStatus": cache_status, "waitReason": wait_reason,
            "durationMs": int((time.perf_counter()-started)*1000),
            "previousRunId": context.get("previousRunId"), "previousStatus": context.get("previousStatus"), "previousPhase": context.get("previousPhase"), "previousUpdatedAt": context.get("previousUpdatedAt"),
            "updatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        # BUILD100: live telemetry is non-fatal. A transient Windows file lock must never
        # prevent /api/demo/run from starting or destroy resumable checkpoint semantics.
        _write_json_resilient(root / "foundry" / "stage9-live-status.json", payload)

    def isolated(phase: str, status: str, detail: str, *, node: str | None = None, wait_reason: str | None = None) -> None:
        nonlocal current_isolation
        current_isolation = phase
        row = isolation[phase]
        row.update({"status": status, "detail": detail, "node": node, "durationMs": int((time.perf_counter()-started)*1000), "updatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
        _append_ndjson(event_path, {"schema": "portfolio-foundry.stage9-event.v1", "eventType": "ISOLATED_SMOKE", "runId": run_id, "candidateId": candidate_id, "vacancyId": vacancy_id, "phase": phase, "status": status, "detail": detail, "node": node, "runtimeId": runtime_id, "cacheStatus": cache_status, "durationMs": row["durationMs"], "at": row["updatedAt"]})
        live("SMOKE_" + phase, status, detail, node=node, current=isolation_order.index(phase)+(1 if status == "PASS" else 0), total=len(isolation_order), wait_reason=wait_reason)
        persist_isolation()

    with log_path.open("w", encoding="utf-8") as log:
        child_env = dict(os.environ)
        child_env["PYTHONDONTWRITEBYTECODE"] = "1"
        child_env["PORTFOLIO_FOUNDRY_RUNTIME_EVIDENCE_DIR"] = str(evidence)
        server_popen: dict[str, object] = {"stdout": log, "stderr": subprocess.STDOUT, "text": True, "env": child_env}
        if os.name == "nt":
            server_popen["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
        else:
            server_popen["start_new_session"] = True
        proc = subprocess.Popen([args.python, str(server), "--project-root", str(root), "--port", str(port)], **server_popen)
        try:
            base = f"http://127.0.0.1:{port}"
            isolated("HTTP_ALIVE", "RUNNING", "Starting generated server and waiting for /health READY.", wait_reason="waiting for generated HTTP server")
            wait_ready(base)
            checks.append({"id": "server-starts", "status": "PASS"})
            status, _ = request(base + "/health")
            if status != 200:
                raise RuntimeError(f"health returned HTTP {status}")
            checks.append({"id": "health", "status": "PASS"})
            isolated("HTTP_ALIVE", "PASS", "Generated server is READY and /health returned HTTP 200.")

            isolated("ROUTE_EXISTS", "RUNNING", "Validating generated application route table and first UI route.")
            early_routes = _read_json(root / "foundry" / "application-routes.json", [])
            if not isinstance(early_routes, list) or not early_routes:
                raise RuntimeError("application-routes.json contains no route entries")
            first_route = str((early_routes[0] or {}).get("path") or "") if isinstance(early_routes[0], dict) else ""
            if not first_route:
                raise RuntimeError("first generated application route has no path")
            route_status, _ = request(base + first_route)
            if route_status != 200:
                raise RuntimeError(f"generated route {first_route} returned HTTP {route_status}")
            isolated("ROUTE_EXISTS", "PASS", f"Generated route exists and responds: {first_route}.")

            isolated("GRAPH_LOADS", "RUNNING", "Loading executable graph through the generated application API.")
            graph_status, graph_body = request(base + "/api/graph")
            graph_payload = json.loads(graph_body) if graph_body else {}
            graph_nodes = graph_payload.get("nodes", []) if isinstance(graph_payload, dict) else []
            if graph_status != 200 or not isinstance(graph_nodes, list) or not graph_nodes:
                raise RuntimeError(f"graph API did not load executable nodes: HTTP {graph_status}")
            isolated("GRAPH_LOADS", "PASS", f"Executable graph loaded: {len(graph_nodes)} nodes.")

            status, _ = request(base + "/")
            if status != 200:
                raise RuntimeError(f"main-page returned HTTP {status}")
            checks.append({"id": "main-page-http-200", "status": "PASS"})

            effect_materialized = (root / "foundry" / "economic-effect.json").is_file()
            api_paths = ["/api/project", "/api/overview", "/api/graph", "/api/live-execution", "/api/case-portfolio", "/api/life-scenario", "/api/routes", "/api/evidence", "/api/diagnostics", "/api/demo/data"]
            if effect_materialized:
                api_paths.append("/api/economic-effect")
            for path in api_paths:
                endpoint_timeout = DIAGNOSTICS_REQUEST_TIMEOUT_SECONDS if path == "/api/diagnostics" else 4.0
                try:
                    status, _ = request(base + path, timeout=endpoint_timeout)
                except Exception as exc:
                    raise RuntimeError(f"API {path} request failed after {endpoint_timeout:g}s: {type(exc).__name__}: {exc}") from exc
                if status != 200:
                    raise RuntimeError(f"API {path} returned HTTP {status}")
            status, capability_body = request(base + "/api/capabilities")
            if status != 200:
                raise RuntimeError(f"API /api/capabilities returned HTTP {status}")
            capability_rows = json.loads(capability_body)
            inspected = 0
            if capability_rows:
                brick_id = str(capability_rows[0].get("fileSystemId") or capability_rows[0].get("id") or "")
                if brick_id:
                    for path in [f"/api/brick/{brick_id}", f"/api/source?brick={brick_id}"]:
                        status, _ = request(base + path)
                        if status != 200:
                            raise RuntimeError(f"API {path} returned HTTP {status}")
                        inspected += 1
            checks.append({"id": "apis", "status": "PASS", "count": len(api_paths) + 1 + inspected})
            checks.append({"id": "demo-data", "status": "PASS"})

            route_spec = json.loads((root / "foundry" / "application-routes.json").read_text(encoding="utf-8"))
            cases_materialized = (root / "foundry" / "case-portfolio.json").is_file()
            life_materialized = (root / "foundry" / "life-scenario.json").is_file()
            status, route_api_body = request(base + "/api/routes")
            if status != 200:
                raise RuntimeError(f"API /api/routes returned HTTP {status}")
            api_route_spec = json.loads(route_api_body)
            route_contract = _validate_route_contract(
                route_spec, api_route_spec,
                cases_materialized=cases_materialized,
                life_materialized=life_materialized,
                effect_materialized=effect_materialized)
            route_ids = list(route_contract["route_ids"])
            route_paths = list(route_contract["route_paths"])
            checks.append({"id": "route-contract", "status": "PASS", "count": len(route_ids), "defaultRoute": route_contract["default_route"], "mode": "SCHEMA_DRIVEN"})
            for path in route_paths:
                status, _ = request(base + path)
                if status != 200:
                    raise RuntimeError(f"critical UI route {path} returned HTTP {status}")
            checks.append({"id": "critical-ui-routes", "status": "PASS", "count": len(route_paths)})

            app_js = (root / "web" / "app.js").read_text(encoding="utf-8-sig")
            for marker in ["['ALL','REUSE','ADAPTER','PROMOTED']", "'NODE ID'", "'TYPE'", "'RUNTIME ENTRYPOINT'", "'PROFILE'", "'CONTRACT'", "'PROMOTION STATE'", "'PROVEN DEMO'"]:
                if marker not in app_js:
                    raise RuntimeError(f"Visual Graph UI marker missing: {marker}")
            checks.append({"id": "v034-visual-graph-ui", "status": "PASS", "filters": 4, "inspectorFields": 7})

            if cases_materialized:
                for marker in ["CASE PORTFOLIO", "runPracticalCase", "/api/case-portfolio/run", "life-stage"]:
                    if marker not in app_js:
                        raise RuntimeError(f"Practical Case Portfolio UI marker missing: {marker}")
                status, cases_body = request(base + "/api/case-portfolio")
                case_data = json.loads(cases_body)
                case_rows = (case_data.get("portfolio") or {}).get("cases", [])
                if status != 200 or case_data.get("status") != "READY" or len(case_rows) != 3:
                    raise RuntimeError(f"Practical Case Portfolio API is not READY: HTTP {status} cases={len(case_rows)}")
                checks.append({"id": "v0351-case-portfolio-ui", "status": "PASS", "defaultRoute": route_ids[0], "cases": len(case_rows)})
            elif life_materialized:
                for marker in ["runPracticalCase", "/api/life-scenario/run", "life-stage"]:
                    if marker not in app_js:
                        raise RuntimeError(f"Life Scenario UI marker missing: {marker}")
                status, life_body = request(base + "/api/life-scenario")
                life = json.loads(life_body)
                if status != 200 or life.get("status") != "READY":
                    raise RuntimeError(f"Life Scenario API is not READY: HTTP {status} {life}")
                checks.append({"id": "v035-life-scenario-ui", "status": "PASS", "defaultRoute": route_ids[0], "stages": len((life.get("scenario") or {}).get("stages", []))})

            if effect_materialized:
                for marker in ["ECONOMIC EFFECT", "runEconomicEffect", "/api/economic-effect/calculate", "BRICK VALUE MAP", "ДО КАНДИДАТА", "ПОСЛЕ КАНДИДАТА"]:
                    if marker not in app_js:
                        raise RuntimeError(f"Economic Effect UI marker missing: {marker}")
                status, effect_body = request(base + "/api/economic-effect")
                effect_api = json.loads(effect_body)
                model = effect_api.get("model") or {}
                graph_model = json.loads((root / "foundry" / "executable-capability-graph.json").read_text(encoding="utf-8"))
                graph_ids = [str(x.get("fileSystemId") or x.get("id") or "") for x in graph_model.get("nodes", [])]
                effect_ids = [str(x.get("nodeId") or "") for x in model.get("brickEffects", [])]
                if status != 200 or effect_api.get("status") != "READY" or model.get("schemaVersion") != "portfolio-foundry.economic-effect.v1":
                    raise RuntimeError(f"Economic Effect API is not READY: HTTP {status}")
                if len(model.get("assumptions", [])) != 9 or effect_ids != graph_ids:
                    raise RuntimeError(f"Economic Effect model coverage mismatch: assumptions={len(model.get('assumptions', []))} bricks={len(effect_ids)} graph={len(graph_ids)}")
                visible_model = {
                    "title": model.get("title"),
                    "modelScope": model.get("modelScope"),
                    "assumptions": [{"label": x.get("label"), "unit": x.get("unit"), "rationale": x.get("rationale")} for x in model.get("assumptions", [])],
                    "bricks": [{"businessCapability": x.get("businessCapability"), "effectCategory": x.get("effectCategory"), "effectMechanism": x.get("effectMechanism"), "successSignal": x.get("successSignal"), "kpi": x.get("kpi")} for x in model.get("brickEffects", [])],
                    "interpretation": model.get("interpretation"),
                }
                model_text = json.dumps(visible_model, ensure_ascii=False).lower()
                vacancy_context_path = root / "foundry" / "vacancy-context.json"
                vacancy_context = json.loads(vacancy_context_path.read_text(encoding="utf-8")) if vacancy_context_path.is_file() else {}
                employer = str(vacancy_context.get("employer") or "").strip().lower()
                forbidden = ["x5", "яндекс", "yandex", "сбер", "sber", "тинькофф", "tinkoff", "ozon", "wildberries", "vk.com", "http://", "https://"]
                if employer and len(employer) >= 3:
                    forbidden.append(employer)
                found_brand = next((token for token in forbidden if token in model_text), None)
                if found_brand:
                    raise RuntimeError(f"Economic Effect is not brandless: found {found_brand!r}")
                checks.append({"id": "v036-economic-effect-model", "status": "PASS", "route": "/app/effect", "assumptions": 9, "bricks": len(effect_ids), "brandPolicy": "BRANDLESS"})

            isolated("BRICK_EXECUTES", "RUNNING", "Executing real candidate graph bricks through /api/demo/run.", wait_reason="waiting for current brick / Python / Spark / JVM runtime")
            status, body = request(base + "/api/demo/run", method="POST", timeout=DEMO_REQUEST_TIMEOUT_SECONDS)
            try:
                demo = json.loads(body)
            except Exception:
                demo = {"status": "FAIL", "raw": body.decode("utf-8", errors="replace")}
            _write_json_resilient(evidence / "runtime-demo-http-response.json", {"httpStatus": status, "body": demo})
            if status != 200 or demo.get("status") != "PASS":
                failed = next((x for x in demo.get("steps", []) if x.get("status") == "FAIL"), {})
                problem_node = str(failed.get("node") or "") or None
                detail = failed.get("error") or demo.get("error") or "demo flow did not PASS"
                code = failed.get("error_code") or demo.get("error_code") or "DEMO_RUN_FAILED"
                isolated("BRICK_EXECUTES", "FAIL", f"{code}: {detail}", node=problem_node)
                raise RuntimeError(f"{code}: {detail}")
            checks.append({"id": "end-to-end-flow", "status": "PASS", "steps": len([x for x in demo.get("steps", []) if x.get("status") == "PASS"])})
            live_status, live_body = request(base + "/api/live-execution")
            # BUILD155: keep the nested live(...) telemetry function callable. BUILD154 rebound
            # this closure name to the decoded /api/live-execution dict, so the next
            # isolated("RESULT_RETURNED", ...) call failed with TypeError: 'dict' object is not callable
            # after the real graph had already passed 11/11 nodes.
            live_execution = json.loads(live_body) if live_body else {}
            live_steps = live_execution.get("steps", []) if isinstance(live_execution, dict) else []
            if live_status != 200 or live_execution.get("status") != "READY" or len(live_steps) != len(demo.get("steps", [])):
                raise RuntimeError(f"LIVE EXECUTION projection mismatch: HTTP {live_status}, status={live_execution.get('status')}, steps={len(live_steps)}")
            if any("inputSource" not in row or "output" not in row or "durationMs" not in row for row in live_steps if isinstance(row, dict) and row.get("status") == "PASS"):
                raise RuntimeError("LIVE EXECUTION is missing truthful input/output/duration fields on PASS nodes")
            checks.append({"id": "build120-live-execution-pro-max", "status": "PASS", "steps": len(live_steps), "actualUpstreamTransfers": (live_execution.get("summary") or {}).get("actualUpstreamTransfers"), "fixtureInputs": (live_execution.get("summary") or {}).get("fixtureInputs")})
            isolated("BRICK_EXECUTES", "PASS", f"Candidate graph execution PASS: {len([x for x in demo.get('steps', []) if x.get('status') == 'PASS'])} bricks returned PASS; LIVE EXECUTION captured {len(live_steps)} truthful receipts.")
            isolated("RESULT_RETURNED", "RUNNING", "Validating remaining runtime/UI proof before accepting the current-run result.", wait_reason="waiting for final runtime dependency and scenario proof")
            if cases_materialized:
                for case_id in ["primary", "operations", "assurance"]:
                    status, body = request(base + f"/api/case-portfolio/run?case={case_id}", method="POST", timeout=SCENARIO_REQUEST_TIMEOUT_SECONDS)
                    case_run = json.loads(body)
                    (evidence / f"case-portfolio-{case_id}-http-response.json").write_text(json.dumps({"httpStatus": status, "body": case_run}, ensure_ascii=False, indent=2), encoding="utf-8")
                    if status != 200 or case_run.get("status") != "PASS":
                        raise RuntimeError(f"Practical case {case_id} real graph playback failed: HTTP {status} {case_run.get('status')}")
                    checks.append({"id": f"v0351-case-{case_id}-real-playback", "status": "PASS", "stages": len(case_run.get("stages", [])), "graphRunId": case_run.get("candidateGraphRunId")})
            elif life_materialized:
                status, body = request(base + "/api/life-scenario/run", method="POST", timeout=SCENARIO_REQUEST_TIMEOUT_SECONDS)
                life_run = json.loads(body)
                (evidence / "life-scenario-http-response.json").write_text(json.dumps({"httpStatus": status, "body": life_run}, ensure_ascii=False, indent=2), encoding="utf-8")
                if status != 200 or life_run.get("status") != "PASS":
                    raise RuntimeError(f"Life Scenario real graph playback failed: HTTP {status} {life_run.get('status')}")
                checks.append({"id": "v035-life-scenario-real-playback", "status": "PASS", "stages": len(life_run.get("stages", [])), "graphRunId": life_run.get("candidateGraphRunId")})
            if effect_materialized:
                scenario_results: dict[str, dict[str, object]] = {}
                for scenario in ["conservative", "base", "potential"]:
                    status, body = request(base + f"/api/economic-effect/calculate?scenario={scenario}", method="POST", payload={"assumptions": {}})
                    effect_run = json.loads(body)
                    (evidence / f"economic-effect-{scenario}-http-response.json").write_text(json.dumps({"httpStatus": status, "body": effect_run}, ensure_ascii=False, indent=2), encoding="utf-8")
                    proof = effect_run.get("graphProof") or {}
                    brick_rows = effect_run.get("brickResults") or []
                    double_count = effect_run.get("doubleCountCheck") or {}
                    attributed = float(double_count.get("attributedGrossTotal") or 0)
                    aggregate = float(double_count.get("aggregateGrossAnnual") or 0)
                    tolerance = max(0.05, len(brick_rows) * 0.02)
                    if status != 200 or effect_run.get("status") != "PASS":
                        raise RuntimeError(f"Economic Effect {scenario} proof-run failed: HTTP {status} {effect_run.get('status')}")
                    if int(proof.get("passedBricks") or 0) != len(graph_ids) or len(brick_rows) != len(graph_ids):
                        raise RuntimeError(f"Economic Effect {scenario} does not prove every graph brick")
                    if any(str(x.get("proofStatus")).upper() != "PASS" for x in brick_rows):
                        raise RuntimeError(f"Economic Effect {scenario} contains an unproven brick contribution")
                    if abs(attributed - aggregate) > tolerance:
                        raise RuntimeError(f"Economic Effect {scenario} double-count check failed: attributed={attributed} aggregate={aggregate}")
                    if float((effect_run.get("after") or {}).get("annualOperatingCost") or 0) >= float((effect_run.get("before") or {}).get("annualOperatingCost") or 0):
                        raise RuntimeError(f"Economic Effect {scenario} AFTER is not better than BEFORE")
                    scenario_results[scenario] = effect_run
                    checks.append({"id": f"v036-economic-effect-{scenario}-proof", "status": "PASS", "bricks": len(brick_rows), "doubleCountDelta": round(abs(attributed - aggregate), 4)})
                first_year_values = [float(((scenario_results[x].get("effect") or {}).get("firstYearNetValue") or 0)) for x in ["conservative", "base", "potential"]]
                if first_year_values != sorted(first_year_values):
                    raise RuntimeError(f"Economic Effect scenarios are not ordered conservative <= base <= potential: {first_year_values}")
                if not (root / "evidence" / "v036" / "economic-effect-run.json").is_file():
                    raise RuntimeError("Economic Effect runtime evidence was not written")
                checks.append({"id": "v036-economic-effect-before-after", "status": "PASS", "scenarios": 3, "ordered": True, "runtimeEvidence": "evidence/v036/economic-effect-run.json"})
            spark = spark_smoke_if_required(root)
            checks.append({"id": "runtime-dependencies", "status": "PASS", "detail": spark})
            isolated("RESULT_RETURNED", "PASS", "All isolated smoke phases and final runtime dependency proof returned PASS.")
            proof = {"schema": "portfolio-foundry.runtime-smoke.v1", "status": "PASS", "stage9RunId": run_id, "candidateId": candidate_id, "vacancyId": vacancy_id, "durationMs": int((time.perf_counter()-started)*1000), "checks": checks, "isolatedSmoke": _evidence_reference(root, evidence, isolation_path), "port": port, "timeoutPolicy": {"callableSeconds": 30, "sparkColdStartSeconds": 90, "demoHttpSeconds": DEMO_REQUEST_TIMEOUT_SECONDS, "smokeProcessSeconds": SMOKE_PROCESS_TIMEOUT_SECONDS, "diagnosticsHttpSeconds": DIAGNOSTICS_REQUEST_TIMEOUT_SECONDS}}
            _write_json_resilient(evidence / "runtime-smoke.json", proof)
            print(json.dumps(proof, ensure_ascii=False, indent=2))
            return 0
        except Exception as exc:
            if current_isolation and isolation[current_isolation].get("status") == "RUNNING":
                isolation[current_isolation].update({"status": "FAIL", "detail": str(exc), "node": problem_node, "durationMs": int((time.perf_counter()-started)*1000)})
                _append_ndjson(event_path, {"schema": "portfolio-foundry.stage9-event.v1", "eventType": "ISOLATED_SMOKE", "runId": run_id, "candidateId": candidate_id, "vacancyId": vacancy_id, "phase": current_isolation, "status": "FAIL", "detail": str(exc), "node": problem_node, "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
            demo_evidence = _read_json(evidence / "runtime-demo-run.json", {})
            if problem_node is None and isinstance(demo_evidence, dict):
                failed = next((x for x in demo_evidence.get("steps", []) if isinstance(x, dict) and x.get("status") == "FAIL"), {})
                problem_node = str(failed.get("node") or "") or None
            persist_isolation(str(exc))
            live("SMOKE_" + (current_isolation or "UNKNOWN"), "FAIL", str(exc), node=problem_node, wait_reason=None)
            forensic_bundle = _collect_stage9_forensics(root, evidence, run_id, exc, problem_node, log_path, args.python)
            proof = {"schema": "portfolio-foundry.runtime-smoke.v1", "status": "FAIL", "stage9RunId": run_id, "candidateId": candidate_id, "vacancyId": vacancy_id, "problemNode": problem_node, "durationMs": int((time.perf_counter()-started)*1000), "checks": checks, "isolatedSmoke": _evidence_reference(root, evidence, isolation_path), "error": str(exc), "forensicsBundle": forensic_bundle, "forensicsPointer": "evidence/v031/stage9-forensics-latest.json", "traceback": traceback.format_exc(), "port": port, "timeoutPolicy": {"callableSeconds": 30, "sparkColdStartSeconds": 90, "demoHttpSeconds": DEMO_REQUEST_TIMEOUT_SECONDS, "smokeProcessSeconds": SMOKE_PROCESS_TIMEOUT_SECONDS, "diagnosticsHttpSeconds": DIAGNOSTICS_REQUEST_TIMEOUT_SECONDS}}
            _write_json_resilient(evidence / "runtime-smoke.json", proof)
            print(json.dumps(proof, ensure_ascii=False, indent=2), file=sys.stderr)
            return 1
        finally:
            cleanup = terminate_process_tree(proc)
            _append_ndjson(event_path, {"schema": "portfolio-foundry.stage9-event.v1", "eventType": "SERVER_CLEANUP", "runId": run_id, "candidateId": candidate_id, "vacancyId": vacancy_id, "status": "PASS" if cleanup.get("exitCode") is not None else "WARN", "detail": cleanup, "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
            _write_json_resilient(evidence / "runtime-smoke-cleanup.json", {"schema": "portfolio-foundry.runtime-smoke-cleanup.v1", "stage9RunId": run_id, **cleanup})


if __name__ == "__main__":
    raise SystemExit(main())
