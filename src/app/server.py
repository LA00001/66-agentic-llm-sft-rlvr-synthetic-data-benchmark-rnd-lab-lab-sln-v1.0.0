# BUILD122_LIVE_EXECUTION_FRESH_CAPTURE: PRO MAX+ can bypass resumable checkpoints for a truthful fresh capture.
from __future__ import annotations

import argparse
import ast
import builtins
import hashlib
import importlib.util
import inspect
import json
import math
import mimetypes
import os
import platform
import re
import signal
import subprocess
import sys
import time
import tokenize
import traceback
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

SERVER_VERSION = "portfolio-foundry-generated-app-v0.37.0.3-proof-receipt-reuse"
FACTORY_VERSION = "v41.3.4167.51"
BUILD_TOKEN = "BUILD249_TEST262"
RUNTIME_SCHEMA = "portfolio-foundry.runtime-invocation.v1"
# BUILD120_VISUAL_GRAPH_PRO_MAX: truthful live input/runtime/output receipts for every demo node.
LEGACY_PROVIDER_SHIMS = {"source-onboarding-v1", "data-contract-adapt-v1", "compliance-workflow-v1", "pyspark-transform-v1", "audience-reach-v1"}
sys.dont_write_bytecode = True
_FIXTURE_UNRESOLVED = object()


def read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return default


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def safe_text(path: Path, limit: int = 180_000) -> str:
    try:
        data = path.read_text(encoding="utf-8-sig")
        return data[:limit]
    except Exception as exc:
        return f"<unavailable: {exc}>"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_json(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _json_contract_schema(value: Any) -> dict[str, Any]:
    """BUILD88: derive a deterministic JSON-shape contract from the proven smoke input."""
    if value is None:
        return {"type": "null"}
    if isinstance(value, bool):
        return {"type": "boolean"}
    if isinstance(value, int) and not isinstance(value, bool):
        return {"type": "integer"}
    if isinstance(value, float):
        return {"type": "number"}
    if isinstance(value, str):
        return {"type": "string"}
    if isinstance(value, dict):
        keys = sorted(str(k) for k in value.keys())
        return {
            "type": "object",
            "required": keys,
            "properties": {key: _json_contract_schema(value[key]) for key in keys},
            "additionalProperties": True,
        }
    if isinstance(value, (list, tuple)):
        if not value:
            return {"type": "array", "items": {"type": "any"}}
        variants: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in value:
            schema = _json_contract_schema(item)
            token = json.dumps(schema, sort_keys=True, separators=(",", ":"))
            if token not in seen:
                seen.add(token); variants.append(schema)
        items = variants[0] if len(variants) == 1 else {"anyOf": variants}
        return {"type": "array", "items": items}
    return {"type": "json-compatible"}


def _validate_json_contract(value: Any, schema: dict[str, Any], path: str = "$") -> list[str]:
    """Return precise shape mismatches; empty means the value satisfies the deterministic contract."""
    if "anyOf" in schema:
        variants = schema.get("anyOf") or []
        if any(not _validate_json_contract(value, item, path) for item in variants if isinstance(item, dict)):
            return []
        return [f"{path}: no anyOf variant matched"]
    kind = str(schema.get("type") or "any")
    if kind == "any": return []
    if kind == "null": return [] if value is None else [f"{path}: expected null, got {type(value).__name__}"]
    if kind == "boolean": return [] if isinstance(value, bool) else [f"{path}: expected boolean, got {type(value).__name__}"]
    if kind == "integer": return [] if isinstance(value, int) and not isinstance(value, bool) else [f"{path}: expected integer, got {type(value).__name__}"]
    if kind == "number": return [] if isinstance(value, (int, float)) and not isinstance(value, bool) else [f"{path}: expected number, got {type(value).__name__}"]
    if kind == "string": return [] if isinstance(value, str) else [f"{path}: expected string, got {type(value).__name__}"]
    if kind == "array":
        if not isinstance(value, (list, tuple)):
            return [f"{path}: expected array, got {type(value).__name__}"]
        item_schema = schema.get("items") if isinstance(schema.get("items"), dict) else {"type": "any"}
        errors: list[str] = []
        for idx, item in enumerate(value):
            errors.extend(_validate_json_contract(item, item_schema, f"{path}[{idx}]")[:4])
            if len(errors) >= 12: break
        return errors
    if kind == "object":
        if not isinstance(value, dict):
            return [f"{path}: expected object, got {type(value).__name__}"]
        errors: list[str] = []
        required = [str(x) for x in schema.get("required", [])]
        for key in required:
            if key not in value:
                errors.append(f"{path}.{key}: required field missing")
        props = schema.get("properties") if isinstance(schema.get("properties"), dict) else {}
        for key, child in props.items():
            if key in value and isinstance(child, dict):
                errors.extend(_validate_json_contract(value[key], child, f"{path}.{key}")[:4])
            if len(errors) >= 12: break
        return errors
    if kind == "json-compatible":
        try: json.dumps(value, ensure_ascii=False); return []
        except Exception as exc: return [f"{path}: not JSON-compatible: {type(exc).__name__}: {exc}"]
    return [f"{path}: unsupported contract type {kind}"]


def read_python_source(path: Path) -> tuple[str, str, bool]:
    bom_detected = path.read_bytes()[:3] == b"\xef\xbb\xbf"
    with tokenize.open(path) as handle:
        source = handle.read()
        encoding = handle.encoding or "unknown"
    return source, encoding, bom_detected


def import_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class RuntimeInvocationError(RuntimeError):
    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.details = details or {}


RUNTIME_DEFAULT_TIMEOUT_SECONDS = 30.0
RUNTIME_SPARK_COLD_START_TIMEOUT_SECONDS = 90.0
RUNTIME_HEAVY_IMPORT_TIMEOUT_SECONDS = 90.0
RUNTIME_SPARK_CALL_TIMEOUT_SECONDS = 90.0
RUNTIME_CLEANUP_GRACE_SECONDS = 5.0
RUNTIME_STDIO_EVIDENCE_LIMIT = 120_000
RUNTIME_HEAVY_IMPORT_ROOTS = {"pandas", "scipy", "pyarrow", "pyspark", "numpy", "sklearn", "torch", "tensorflow"}


def _source_heavy_import_modules(path: Path) -> list[str]:
    """Return directly imported heavy/native module roots for phase-aware import budgets."""
    try:
        source, _, _ = read_python_source(path)
        module = ast.parse(source, filename=str(path))
    except Exception:
        return []
    roots: set[str] = set()
    for stmt in ast.walk(module):
        if isinstance(stmt, ast.Import):
            for alias in stmt.names:
                root = alias.name.split(".", 1)[0].casefold()
                if root in RUNTIME_HEAVY_IMPORT_ROOTS:
                    roots.add(root)
        elif isinstance(stmt, ast.ImportFrom) and stmt.module:
            root = stmt.module.split(".", 1)[0].casefold()
            if root in RUNTIME_HEAVY_IMPORT_ROOTS:
                roots.add(root)
    return sorted(roots)


def _runtime_phase_family(phase: str) -> str:
    marker = (phase or "").upper()
    if marker == "IMPORT_STARTED" or marker == "IMPORT_COMPLETED" or marker.startswith("DEPENDENCY_IMPORT_"):
        return "IMPORT"
    # BUILD100: child processes are created from inside the target callable. They must not
    # reset a healthy Spark/Python call back to WORKER_STARTUP and accidentally arm a 30s budget.
    if marker in {"CALL_STARTED", "CALL_RETURNED", "CHILD_PROCESS_STARTED", "SPARK_CHILD_PROCESS_STARTED"}:
        return "CALL"
    if marker in {"OUTPUT_SERIALIZED", "CHILD_CLEANUP_COMPLETED", "WORKER_SHUTDOWN_READY"}:
        return "FINALIZE"
    return "STARTUP"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _runtime_phase(status_path: Path, phase: str, **extra: Any) -> None:
    """Append a Stage 9 worker phase without ever making telemetry itself fatal.

    BUILD151 rule: diagnostics are *observer infrastructure*. A short Windows file lock,
    malformed prior status file, or antivirus race must not turn a healthy candidate into FAIL.
    Every phase is attempted in the primary JSON status file and also mirrored to an append-only
    NDJSON trace. If the primary write fails, a telemetry-error record is written best-effort.
    """
    event = {"phase": phase, "at": _utc_now(), **extra}
    trace_path = status_path.with_name(status_path.stem + "-events.ndjson")
    try:
        trace_path.parent.mkdir(parents=True, exist_ok=True)
        with trace_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")
    except Exception:
        pass
    try:
        current = read_json(status_path, {}) if status_path.is_file() else {}
        if not isinstance(current, dict):
            current = {}
        events = current.get("events") if isinstance(current.get("events"), list) else []
        events.append(event)
        payload = {"phase": phase, "updated_at": event["at"], "events": events, **extra}
        tmp = status_path.with_name(f".{status_path.name}.{os.getpid()}.{time.time_ns()}.tmp")
        write_json(tmp, payload)
        os.replace(tmp, status_path)
    except Exception as exc:
        try:
            warning = {
                "phase": "TELEMETRY_WRITE_FAILED", "at": _utc_now(), "attempted_phase": phase,
                "error": f"{type(exc).__name__}: {exc}", "status_path": str(status_path),
            }
            with status_path.with_name(status_path.stem + "-telemetry-errors.ndjson").open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(warning, ensure_ascii=False, default=str) + "\n")
        except Exception:
            pass


def _stage9_safe_env() -> dict[str, str]:
    """Return only non-secret process context useful for reproducing a Stage 9 worker failure."""
    allow = {
        "PYTHONHOME", "PYTHONPATH", "VIRTUAL_ENV", "JAVA_HOME", "SPARK_HOME", "HADOOP_HOME",
        "PORTFOLIO_FOUNDRY_RUNTIME_WORKER", "PORTFOLIO_FOUNDRY_PATCH_TOKEN",
    }
    result: dict[str, str] = {}
    for key in sorted(allow):
        value = os.environ.get(key)
        if value:
            result[key] = value[:4000]
    return result


def _stage9_exception_details(exc: BaseException) -> dict[str, Any]:
    """Full exception evidence for forensic bundles. No secrets or arbitrary env values are copied."""
    return {
        "exception_type": type(exc).__name__,
        "exception": str(exc),
        "traceback": traceback.format_exc(),
        "python": sys.version,
        "python_executable": sys.executable,
        "platform": platform.platform(),
        "cwd": os.getcwd(),
        "subprocess_popen_type": f"{type(subprocess.Popen).__module__}.{type(subprocess.Popen).__name__}",
        "subprocess_popen_repr": repr(subprocess.Popen)[:2000],
        "safe_env": _stage9_safe_env(),
    }

def _runtime_source(root: Path, relative: str) -> Path:
    if not relative or Path(relative).is_absolute():
        raise RuntimeInvocationError("RUNTIME_PATH_ESCAPE", f"runtime source path must be candidate-relative: {relative}")
    path = (root / relative).resolve()
    if path != root and root not in path.parents:
        raise RuntimeInvocationError("RUNTIME_PATH_ESCAPE", f"runtime source escapes candidate root: {relative}")
    if not path.is_file():
        raise RuntimeInvocationError("RUNTIME_SOURCE_MISSING", f"runtime source missing: {relative}")
    return path


def _normalize_runtime_value(output: Any) -> Any:
    if isinstance(output, Path):
        return str(output)
    if isinstance(output, tuple):
        return list(output)
    if isinstance(output, set):
        return sorted(output, key=lambda x: str(x))
    return output


def _cleanup_observed_children(children: list[subprocess.Popen[Any]]) -> dict[str, Any]:
    cleaned: list[int] = []
    failed: list[dict[str, Any]] = []
    for child in reversed(children):
        try:
            if child.poll() is not None:
                continue
            if os.name == "nt":
                result = subprocess.run(["taskkill.exe", "/PID", str(child.pid), "/T", "/F"], capture_output=True, text=True, timeout=8)
                if result.returncode not in (0, 128):
                    raise RuntimeError((result.stderr or result.stdout or f"taskkill exit {result.returncode}").strip())
            else:
                child.terminate()
                try:
                    child.wait(timeout=1.5)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait(timeout=2)
            cleaned.append(child.pid)
        except Exception as exc:
            failed.append({"pid": child.pid, "error": f"{type(exc).__name__}: {exc}"})
    return {"cleaned_pids": cleaned, "cleanup_failures": failed}


def _runtime_worker(request_path: Path) -> int:
    """Execute one candidate runtime contract in a fresh process.

    BUILD151 hardening principles:
    1. Candidate imports happen against untouched stdlib/process primitives.
    2. Child-process observation is class-preserving and best-effort, enabled only *after* import.
    3. Observer/telemetry failures are diagnostics warnings, never candidate failures.
    4. Every import/call/cleanup boundary emits enough evidence to reproduce the exact failure.
    """
    request = read_json(request_path, {})
    response_path = Path(str(request.get("response_path") or ""))
    status_path = Path(str(request.get("status_path") or ""))
    root = Path(str(request.get("root") or "")).resolve()
    relative = str(request.get("relative") or "")
    callable_name = str(request.get("callable") or "")
    expected_sha = str(request.get("source_sha256") or "")
    args = request.get("args") if isinstance(request.get("args"), list) else []
    heavy_import_modules = {str(x).casefold() for x in (request.get("heavy_import_modules") or []) if str(x).strip()}
    observe_children = bool(request.get("observe_children", True))
    children: list[subprocess.Popen[Any]] = []
    real_popen = subprocess.Popen
    worker_started = time.perf_counter()
    observer_active = False
    observer_warning: str | None = None
    import_diagnostics: dict[str, Any] = {}

    _runtime_phase(
        status_path, "WORKER_STARTED", worker_pid=os.getpid(), entrypoint=f"{relative}::{callable_name}",
        python=sys.version, python_executable=sys.executable, platform=platform.platform(), cwd=os.getcwd(),
        observe_children_requested=observe_children, popen_is_class=isinstance(real_popen, type),
        popen_repr=repr(real_popen)[:2000], safe_env=_stage9_safe_env(),
    )
    try:
        path = _runtime_source(root, relative)
        actual_sha = sha256_file(path)
        if expected_sha and expected_sha.lower() != actual_sha.lower():
            raise RuntimeInvocationError(
                "RUNTIME_SOURCE_STALE", f"runtime source fingerprint changed: {relative}",
                {"expected": expected_sha, "actual": actual_sha, "source": relative},
            )

        # IMPORTANT: never monkey-patch subprocess.Popen before candidate imports. Heavy libraries
        # (torch/asyncio on Windows in particular) legitimately expect subprocess.Popen to be a class.
        # BUILD150 exposed a false Stage 9 FAIL because a function replacement violated that contract.
        import_started = time.perf_counter()
        _runtime_phase(
            status_path, "IMPORT_STARTED", heavy_import_modules=sorted(heavy_import_modules),
            popen_is_class=isinstance(subprocess.Popen, type), popen_repr=repr(subprocess.Popen)[:2000],
        )
        real_import = builtins.__import__
        traced_imports: set[str] = set()
        current_dependency: str | None = None

        def observed_import(name: str, globals=None, locals=None, fromlist=(), level=0):
            nonlocal current_dependency
            root_name = str(name or "").split(".", 1)[0].casefold()
            trace_this = root_name in heavy_import_modules and root_name not in traced_imports
            dep_started = time.perf_counter()
            if trace_this:
                traced_imports.add(root_name)
                current_dependency = root_name
                _runtime_phase(
                    status_path, "DEPENDENCY_IMPORT_STARTED", dependency=root_name,
                    popen_is_class=isinstance(subprocess.Popen, type), loaded_modules=len(sys.modules),
                )
            try:
                result = real_import(name, globals, locals, fromlist, level)
            except Exception as exc:
                if trace_this:
                    import_diagnostics.update(_stage9_exception_details(exc))
                    import_diagnostics["dependency"] = root_name
                    _runtime_phase(
                        status_path, "DEPENDENCY_IMPORT_FAILED", dependency=root_name,
                        dependency_import_ms=int((time.perf_counter() - dep_started) * 1000),
                        error=f"{type(exc).__name__}: {exc}", traceback=traceback.format_exc(),
                        popen_is_class=isinstance(subprocess.Popen, type), popen_repr=repr(subprocess.Popen)[:2000],
                    )
                raise
            if trace_this:
                current_dependency = None
                _runtime_phase(
                    status_path, "DEPENDENCY_IMPORT_COMPLETED", dependency=root_name,
                    dependency_import_ms=int((time.perf_counter() - dep_started) * 1000),
                    module_file=str(getattr(result, "__file__", "") or "")[:4000],
                )
            return result

        builtins.__import__ = observed_import
        try:
            module = import_module(path, f"portfolio_runtime_worker_{actual_sha[:8]}_{os.getpid()}")
        except Exception as exc:
            details = _stage9_exception_details(exc)
            details.update(import_diagnostics)
            details.update({
                "source": relative, "callable": callable_name, "source_sha256": actual_sha,
                "current_dependency": current_dependency, "heavy_import_modules": sorted(heavy_import_modules),
                "observer_active": False, "observer_note": "candidate import is intentionally executed before process observation",
            })
            raise RuntimeInvocationError(
                "RUNTIME_IMPORT_FAILED",
                f"runtime source import failed: {type(exc).__name__}: {exc}",
                details,
            ) from exc
        finally:
            builtins.__import__ = real_import

        import_ms = int((time.perf_counter() - import_started) * 1000)
        _runtime_phase(
            status_path, "IMPORT_COMPLETED", import_ms=import_ms, heavy_import_modules=sorted(heavy_import_modules),
            imported_module=getattr(module, "__name__", None), popen_is_class=isinstance(subprocess.Popen, type),
        )
        fn = getattr(module, callable_name, None)
        if fn is None or not callable(fn):
            raise RuntimeInvocationError(
                "RUNTIME_CALLABLE_MISSING", f"declared callable missing: {relative}::{callable_name}",
                {"source": relative, "callable": callable_name, "available_callables": sorted([name for name, value in vars(module).items() if callable(value)])[:200]},
            )

        # Process observation must preserve the type contract of subprocess.Popen. A subclass is
        # intentionally used instead of a function wrapper so libraries importing asyncio or other
        # process helpers during the target call continue to see a class and can safely subclass it.
        if observe_children:
            try:
                class ObservedPopen(real_popen):  # type: ignore[misc, valid-type]
                    def __init__(self, *popen_args: Any, **popen_kwargs: Any):
                        super().__init__(*popen_args, **popen_kwargs)
                        children.append(self)
                        try:
                            command_value = popen_args[0] if popen_args else popen_kwargs.get("args")
                            if isinstance(command_value, (list, tuple)):
                                command = " ".join(str(x) for x in command_value)
                            else:
                                command = str(command_value or "")
                            marker = command.casefold()
                            phase = "SPARK_CHILD_PROCESS_STARTED" if any(x in marker for x in ("java", "spark-submit", "pyspark")) else "CHILD_PROCESS_STARTED"
                            _runtime_phase(status_path, phase, child_pid=self.pid, command=command[:2000])
                        except Exception as observe_exc:
                            _runtime_phase(status_path, "PROCESS_OBSERVER_EVENT_WARNING", error=f"{type(observe_exc).__name__}: {observe_exc}")

                subprocess.Popen = ObservedPopen  # type: ignore[assignment]
                observer_active = True
                _runtime_phase(
                    status_path, "PROCESS_OBSERVER_ENABLED", observer_kind="CLASS_PRESERVING_SUBCLASS",
                    observer_class=f"{ObservedPopen.__module__}.{ObservedPopen.__name__}", popen_is_class=isinstance(subprocess.Popen, type),
                )
            except Exception as exc:
                observer_warning = f"{type(exc).__name__}: {exc}"
                subprocess.Popen = real_popen  # type: ignore[assignment]
                _runtime_phase(
                    status_path, "PROCESS_OBSERVER_DEGRADED", error=observer_warning,
                    policy="CONTINUE_WITHOUT_OBSERVER", popen_is_class=isinstance(subprocess.Popen, type),
                )

        call_started = time.perf_counter()
        _runtime_phase(
            status_path, "CALL_STARTED", observer_active=observer_active, observer_warning=observer_warning,
            argument_count=len(args), callable=f"{relative}::{callable_name}",
        )
        try:
            output = fn(*args)
        except RuntimeInvocationError:
            raise
        except Exception as exc:
            details = _stage9_exception_details(exc)
            details.update({
                "source": relative, "callable": callable_name, "observer_active": observer_active,
                "observer_warning": observer_warning, "child_pids": [child.pid for child in children],
            })
            raise RuntimeInvocationError("RUNTIME_EXCEPTION", f"{type(exc).__name__}: {exc}", details) from exc

        call_ms = int((time.perf_counter() - call_started) * 1000)
        _runtime_phase(status_path, "CALL_RETURNED", call_ms=call_ms, child_count=len(children), observer_active=observer_active)
        output = _normalize_runtime_value(output)
        serialize_started = time.perf_counter()
        try:
            json.dumps(output, ensure_ascii=False)
        except Exception as exc:
            raise RuntimeInvocationError(
                "RUNTIME_OUTPUT_INVALID", f"runtime output is not JSON serializable: {type(exc).__name__}: {exc}",
                {**_stage9_exception_details(exc), "output_type": type(output).__name__},
            ) from exc
        serialize_ms = int((time.perf_counter() - serialize_started) * 1000)
        _runtime_phase(status_path, "OUTPUT_SERIALIZED", serialize_ms=serialize_ms, output_type=type(output).__name__)

        # Always restore stdlib before cleanup; cleanup itself may call subprocess.run/taskkill.
        subprocess.Popen = real_popen  # type: ignore[assignment]
        cleanup = _cleanup_observed_children(children)
        _runtime_phase(status_path, "CHILD_CLEANUP_COMPLETED", **cleanup)
        response = {
            "status": "PASS", "output": output, "worker_pid": os.getpid(), "source_sha256": actual_sha,
            "observer": {"requested": observe_children, "active": observer_active, "warning": observer_warning, "mode": "CLASS_PRESERVING_SUBCLASS" if observer_active else "NONE"},
            "timings": {"import_ms": import_ms, "call_ms": call_ms, "serialize_ms": serialize_ms, "worker_total_ms": int((time.perf_counter() - worker_started) * 1000)},
            "cleanup": cleanup,
        }
        write_json(response_path, response)
        _runtime_phase(status_path, "WORKER_SHUTDOWN_READY", worker_total_ms=response["timings"]["worker_total_ms"], observer_active=observer_active)
        return 0
    except RuntimeInvocationError as exc:
        subprocess.Popen = real_popen  # type: ignore[assignment]
        cleanup = _cleanup_observed_children(children)
        details = dict(exc.details or {})
        details.setdefault("worker", {})
        if isinstance(details["worker"], dict):
            details["worker"].update({
                "python": sys.version, "python_executable": sys.executable, "platform": platform.platform(),
                "cwd": os.getcwd(), "observe_children_requested": observe_children, "observer_active": observer_active,
                "observer_warning": observer_warning, "child_pids": [child.pid for child in children],
                "safe_env": _stage9_safe_env(),
            })
        write_json(response_path, {
            "status": "FAIL", "error_code": exc.code, "error": str(exc), "details": details,
            "worker_pid": os.getpid(), "cleanup": cleanup,
            "observer": {"requested": observe_children, "active": observer_active, "warning": observer_warning},
            "worker_total_ms": int((time.perf_counter() - worker_started) * 1000),
        })
        _runtime_phase(status_path, "WORKER_FAILED", error_code=exc.code, error=str(exc), details=details, **cleanup)
        return 20
    except Exception as exc:
        subprocess.Popen = real_popen  # type: ignore[assignment]
        cleanup = _cleanup_observed_children(children)
        details = _stage9_exception_details(exc)
        details.update({"observer_active": observer_active, "observer_warning": observer_warning, "child_pids": [child.pid for child in children]})
        write_json(response_path, {
            "status": "FAIL", "error_code": "RUNTIME_WORKER_EXCEPTION", "error": f"{type(exc).__name__}: {exc}",
            "details": details, "worker_pid": os.getpid(), "cleanup": cleanup,
            "worker_total_ms": int((time.perf_counter() - worker_started) * 1000),
        })
        _runtime_phase(status_path, "WORKER_FAILED", error_code="RUNTIME_WORKER_EXCEPTION", error=f"{type(exc).__name__}: {exc}", details=details, **cleanup)
        return 21
    finally:
        subprocess.Popen = real_popen  # type: ignore[assignment]

def _terminate_process_tree(proc: subprocess.Popen[str], grace_seconds: float = RUNTIME_CLEANUP_GRACE_SECONDS) -> dict[str, Any]:
    started = time.perf_counter()
    method = "NONE"
    detail = "already-exited"
    if proc.poll() is None:
        if os.name == "nt":
            method = "TASKKILL_TREE"
            try:
                result = subprocess.run(["taskkill.exe", "/PID", str(proc.pid), "/T", "/F"], capture_output=True, text=True, timeout=max(2.0, grace_seconds + 3.0))
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
                    proc.wait(timeout=max(0.5, grace_seconds / 2.0))
                except subprocess.TimeoutExpired:
                    os.killpg(pgid, signal.SIGKILL)
                detail = f"process-group={pgid}"
            except Exception as exc:
                detail = f"killpg failed: {type(exc).__name__}: {exc}"
                try: proc.kill()
                except Exception: pass
        try: proc.wait(timeout=max(1.0, grace_seconds))
        except Exception: pass
    return {
        "method": method,
        "detail": detail,
        "exit_code": proc.poll(),
        "cleanup_ms": int((time.perf_counter() - started) * 1000),
        "tree_terminated": proc.poll() is not None,
    }


def stage9_evidence_reference(root: Path, evidence: Path, path: Path) -> str:
    """Portable reference, even when Stage 9 evidence belongs to the vacancy workspace."""
    path = path.resolve()
    try:
        return path.relative_to(root.resolve()).as_posix()
    except ValueError:
        return "evidence/v031/" + path.relative_to(evidence.resolve()).as_posix()


def resolve_stage9_evidence(root: Path, evidence: Path, reference: str) -> Path:
    relative = Path(reference.replace("\\", "/"))
    if relative.is_absolute() or re.match(r"^[a-zA-Z]:", reference) or ".." in relative.parts:
        raise ValueError("Evidence reference must be a bounded relative path")
    prefix = ("evidence", "v031")
    base = evidence.resolve() if relative.parts[:2] == prefix else root.resolve()
    suffix = Path(*relative.parts[2:]) if relative.parts[:2] == prefix else relative
    result = (base / suffix).resolve()
    if result != base and base not in result.parents:
        raise ValueError("Evidence reference escapes its owner")
    return result


class GenericRuntimeInvoker:
    """BUILD87: execute current physical bytes in an isolated process with bounded, observable cleanup."""

    def __init__(self, root: Path, evidence_dir: Path):
        self.root = root.resolve()
        self.evidence_dir = evidence_dir.resolve()
        self.stage9_context = read_json(self.root / "foundry" / "stage9-run-context.json", {})
        self.stage9_run_id = str(self.stage9_context.get("runId") or "") if isinstance(self.stage9_context, dict) else ""

    def _resolve_file(self, relative: str) -> Path:
        return _runtime_source(self.root, relative)

    def _write_execution_evidence(self, run_dir: Path, payload: dict[str, Any]) -> None:
        write_json(run_dir / "runtime-execution.json", payload)

    def invoke(self, descriptor: dict[str, Any], value: Any = None) -> tuple[str, Any, dict[str, Any]]:
        started = time.perf_counter()
        started_at = _utc_now()
        if descriptor.get("schema") != RUNTIME_SCHEMA:
            raise RuntimeInvocationError("RUNTIME_CONTRACT_INVALID", "runtime-invocation.json schema mismatch")
        entry = descriptor.get("entrypoint") or {}
        if entry.get("kind") != "python-function":
            raise RuntimeInvocationError("RUNTIME_PROFILE_UNSUPPORTED", f"unsupported entrypoint kind: {entry.get('kind')}")
        relative = str(entry.get("file") or "")
        callable_name = str(entry.get("callable") or "")
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", callable_name):
            raise RuntimeInvocationError("RUNTIME_CONTRACT_INVALID", f"invalid callable identifier: {callable_name}")
        path = self._resolve_file(relative)
        actual_sha = sha256_file(path)
        expected_sha = str((descriptor.get("integrity") or {}).get("source_sha256") or "")
        if expected_sha and expected_sha.lower() != actual_sha.lower():
            raise RuntimeInvocationError("RUNTIME_SOURCE_STALE", f"runtime source fingerprint changed: {relative}", {"expected": expected_sha, "actual": actual_sha})

        argument_mode = str((descriptor.get("arguments") or {}).get("mode") or "payload")
        if argument_mode not in {"payload", "value", "none"}:
            raise RuntimeInvocationError("RUNTIME_CONTRACT_INVALID", f"invalid argument mode: {argument_mode}")
        if argument_mode == "none":
            args: list[Any] = []
            input_value: Any = None
        else:
            input_value = value
            input_spec = descriptor.get("input") or {}
            fixture_rel = str(input_spec.get("smoke_fixture") or "")
            if input_value is None:
                if not fixture_rel:
                    raise RuntimeInvocationError("FIXTURE_MISSING", f"runtime fixture missing for {descriptor.get('target_brick_id')}")
                try:
                    fixture = self._resolve_file(fixture_rel)
                except RuntimeInvocationError as exc:
                    if exc.code == "RUNTIME_SOURCE_MISSING":
                        raise RuntimeInvocationError("FIXTURE_MISSING", f"runtime fixture missing: {fixture_rel}", {"fixture": fixture_rel}) from exc
                    raise
                expected_fixture_sha = str(input_spec.get("fixture_sha256") or "")
                actual_fixture_sha = sha256_file(fixture)
                if expected_fixture_sha and actual_fixture_sha.lower() != expected_fixture_sha.lower():
                    raise RuntimeInvocationError("CONTRACT_MISMATCH", f"fixture fingerprint changed after deterministic resolution: {fixture_rel}", {"expected": expected_fixture_sha, "actual": actual_fixture_sha})
                try:
                    input_value = json.loads(fixture.read_text(encoding="utf-8-sig"))
                except Exception as exc:
                    raise RuntimeInvocationError("CONTRACT_MISMATCH", f"runtime fixture is invalid JSON: {fixture_rel}: {exc}", {"fixture": fixture_rel}) from exc
            schema_rel = str(input_spec.get("schema") or "")
            if schema_rel:
                try:
                    schema_path = self._resolve_file(schema_rel)
                    schema = json.loads(schema_path.read_text(encoding="utf-8-sig"))
                except Exception as exc:
                    raise RuntimeInvocationError("CONTRACT_MISMATCH", f"input schema unavailable or invalid: {schema_rel}: {exc}", {"schema": schema_rel}) from exc
                findings = _validate_json_contract(input_value, schema)
                if findings:
                    raise RuntimeInvocationError("CONTRACT_MISMATCH", f"input does not satisfy deterministic contract for {descriptor.get('target_brick_id')}: {findings[0]}", {"schema": schema_rel, "findings": findings[:12], "input_contract": input_spec.get("contract")})
            args = [input_value]

        execution = descriptor.get("execution") or {}
        base_timeout = max(0.1, float(execution.get("timeout_seconds") or RUNTIME_DEFAULT_TIMEOUT_SECONDS))
        call_timeout = max(0.1, float(execution.get("call_timeout_seconds") or base_timeout))
        runtime_profile = str(descriptor.get("runtime_profile") or "python")
        spark_like = "spark" in runtime_profile.casefold() or "pyspark" in relative.casefold()
        spark_call_timeout = max(call_timeout, float(execution.get("spark_call_timeout_seconds") or (RUNTIME_SPARK_CALL_TIMEOUT_SECONDS if spark_like else call_timeout)))
        heavy_import_modules = sorted({str(x).casefold() for x in (execution.get("heavy_import_modules") or []) if str(x).strip()})
        heavy_import = bool(heavy_import_modules) or spark_like
        configured_import_timeout = execution.get("import_timeout_seconds")
        if configured_import_timeout is None:
            configured_import_timeout = execution.get("cold_start_timeout_seconds") if spark_like else (RUNTIME_HEAVY_IMPORT_TIMEOUT_SECONDS if heavy_import else call_timeout)
        import_timeout = max(call_timeout, float(configured_import_timeout or call_timeout))
        timeout_seconds = max(import_timeout, spark_call_timeout if spark_like else call_timeout)
        cleanup_grace = max(1.0, float(execution.get("cleanup_grace_seconds") or RUNTIME_CLEANUP_GRACE_SECONDS))
        budget_kind = "PHASE_AWARE"

        run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + "-" + uuid.uuid4().hex[:8]
        run_dir = self.evidence_dir / "runtime-execution" / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        request_path = run_dir / "worker-request.json"
        response_path = run_dir / "worker-response.json"
        status_path = run_dir / "worker-status.json"
        observe_children = not bool(execution.get("_disable_process_observer", False))
        request = {
            "schema": "portfolio-foundry.runtime-worker-request.v1",
            "run_id": run_id,
            "stage9_run_id": self.stage9_run_id or None,
            "root": str(self.root),
            "relative": relative,
            "callable": callable_name,
            "args": args,
            "heavy_import_modules": heavy_import_modules,
            "observe_children": observe_children,
            "source_sha256": actual_sha,
            "response_path": str(response_path),
            "status_path": str(status_path),
        }
        write_json(request_path, request)
        worker_command = [sys.executable, str(Path(__file__).resolve()), "--runtime-worker-request", str(request_path)]
        popen_kwargs: dict[str, Any] = {
            "cwd": str(self.root), "stdout": subprocess.PIPE, "stderr": subprocess.PIPE, "text": True,
            "encoding": "utf-8", "errors": "replace", "env": {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PORTFOLIO_FOUNDRY_RUNTIME_WORKER": "1"},
        }
        if os.name == "nt":
            popen_kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
        else:
            popen_kwargs["start_new_session"] = True
        proc = subprocess.Popen(worker_command, **popen_kwargs)
        stdout = ""
        stderr = ""
        cleanup: dict[str, Any] | None = None
        phase_family = "STARTUP"
        phase_started = time.perf_counter()
        timed_out = False
        timeout_budget = call_timeout
        timeout_budget_kind = "WORKER_STARTUP"
        while True:
            status_snapshot = read_json(status_path, {}) if status_path.is_file() else {}
            status_phase = str(status_snapshot.get("phase") or "WORKER_STARTED")
            observed_family = _runtime_phase_family(status_phase)
            if observed_family != phase_family:
                phase_family = observed_family
                phase_started = time.perf_counter()
            if phase_family == "IMPORT":
                timeout_budget = import_timeout
                timeout_budget_kind = "HEAVY_IMPORT" if heavy_import else "IMPORT"
            elif phase_family == "CALL":
                timeout_budget = spark_call_timeout if spark_like else call_timeout
                timeout_budget_kind = "SPARK_CALL" if spark_like else "CALLABLE"
            elif phase_family == "FINALIZE":
                timeout_budget = call_timeout
                timeout_budget_kind = "FINALIZE"
            else:
                timeout_budget = call_timeout
                timeout_budget_kind = "WORKER_STARTUP"
            remaining = timeout_budget - (time.perf_counter() - phase_started)
            if remaining <= 0:
                timed_out = True
                break
            try:
                stdout, stderr = proc.communicate(timeout=min(0.5, max(0.05, remaining)))
                break
            except subprocess.TimeoutExpired:
                continue

        if timed_out:
            cleanup = _terminate_process_tree(proc, cleanup_grace)
            try:
                stdout, stderr = proc.communicate(timeout=2)
            except Exception:
                pass
            status = read_json(status_path, {})
            last_phase = str(status.get("phase") or "WORKER_STARTED")
            payload = {
                "schema": "portfolio-foundry.runtime-execution.v1", "status": "TIMEOUT", "run_id": run_id, "stage9_run_id": self.stage9_run_id or None,
                "target_brick_id": descriptor.get("target_brick_id"), "entrypoint": f"{relative}::{callable_name}",
                "runtime_profile": runtime_profile, "budget_kind": timeout_budget_kind, "timeout_seconds": timeout_budget,
                "base_timeout_seconds": base_timeout, "call_timeout_seconds": call_timeout, "spark_call_timeout_seconds": spark_call_timeout, "import_timeout_seconds": import_timeout,
                "heavy_import_modules": heavy_import_modules, "cleanup_grace_seconds": cleanup_grace, "worker_pid": proc.pid,
                "last_phase": last_phase, "phase_status": status, "cleanup": cleanup,
                "stdout": stdout[-RUNTIME_STDIO_EVIDENCE_LIMIT:], "stderr": stderr[-RUNTIME_STDIO_EVIDENCE_LIMIT:],
                "started_at": started_at, "completed_at": _utc_now(), "duration_ms": int((time.perf_counter() - started) * 1000),
                "source_sha256": actual_sha, "input_sha256": sha256_json(input_value) if argument_mode != "none" else None,
                "input": input_value if argument_mode != "none" else None,
            }
            self._write_execution_evidence(run_dir, payload)
            raise RuntimeInvocationError("RUNTIME_TIMEOUT", f"runtime phase exceeded {timeout_budget:g}s ({timeout_budget_kind}); last phase={last_phase}: {relative}::{callable_name}", {
                "run_id": run_id, "evidence": stage9_evidence_reference(self.root, self.evidence_dir, run_dir / "runtime-execution.json"), "last_phase": last_phase,
                "budget_kind": timeout_budget_kind, "timeout_seconds": timeout_budget, "call_timeout_seconds": call_timeout,
                "spark_call_timeout_seconds": spark_call_timeout, "import_timeout_seconds": import_timeout, "heavy_import_modules": heavy_import_modules, "cleanup": cleanup,
            })

        response = read_json(response_path, {}) if response_path.is_file() else {}
        status = read_json(status_path, {}) if status_path.is_file() else {}
        result_status = str(response.get("status") or "FAIL")
        payload = {
            "schema": "portfolio-foundry.runtime-execution.v1", "status": result_status, "run_id": run_id, "stage9_run_id": self.stage9_run_id or None,
            "target_brick_id": descriptor.get("target_brick_id"), "entrypoint": f"{relative}::{callable_name}",
            "runtime_profile": runtime_profile, "budget_kind": budget_kind, "timeout_seconds": timeout_seconds,
            "base_timeout_seconds": base_timeout, "call_timeout_seconds": call_timeout, "spark_call_timeout_seconds": spark_call_timeout, "import_timeout_seconds": import_timeout,
            "heavy_import_modules": heavy_import_modules, "cleanup_grace_seconds": cleanup_grace, "worker_pid": proc.pid,
            "worker_exit_code": proc.returncode, "last_phase": status.get("phase"), "phase_status": status,
            "worker_cleanup": response.get("cleanup"), "worker_timings": response.get("timings"),
            "stdout": stdout[-RUNTIME_STDIO_EVIDENCE_LIMIT:], "stderr": stderr[-RUNTIME_STDIO_EVIDENCE_LIMIT:],
            "started_at": started_at, "completed_at": _utc_now(), "duration_ms": int((time.perf_counter() - started) * 1000),
            "source_sha256": actual_sha, "input_sha256": sha256_json(input_value) if argument_mode != "none" else None,
            "input": input_value if argument_mode != "none" else None,
        }
        self._write_execution_evidence(run_dir, payload)
        if result_status != "PASS":
            code = str(response.get("error_code") or ("RUNTIME_WORKER_CRASH" if not response else "RUNTIME_EXCEPTION"))
            message = str(response.get("error") or f"runtime worker exited {proc.returncode} without a PASS response")
            details = response.get("details") if isinstance(response.get("details"), dict) else {}
            details = {**details, "run_id": run_id, "evidence": stage9_evidence_reference(self.root, self.evidence_dir, run_dir / "runtime-execution.json"), "last_phase": status.get("phase"), "worker_exit_code": proc.returncode, "observer": response.get("observer")}

            # BUILD151: infrastructure faults get one bounded clean-worker retry. This is not a
            # PASS shortcut: source/fixtures/contracts/output validation stay identical. The retry
            # only removes Stage 9 observer plumbing so instrumentation cannot become the reason a
            # healthy candidate is marked red. Deterministic candidate/contract failures never retry.
            retryable_infrastructure = {"RUNTIME_WORKER_EXCEPTION", "RUNTIME_INSTRUMENTATION_ERROR", "RUNTIME_TIMEOUT"}
            already_retried = bool(execution.get("_infra_retry", False))
            if code in retryable_infrastructure and not already_retried:
                retry_log = self.evidence_dir / "stage9-infrastructure-retries.ndjson"
                try:
                    retry_log.parent.mkdir(parents=True, exist_ok=True)
                    with retry_log.open("a", encoding="utf-8") as stream:
                        stream.write(json.dumps({
                            "schema": "portfolio-foundry.stage9-infrastructure-retry.v1",
                            "stage9RunId": self.stage9_run_id or None, "brick": descriptor.get("target_brick_id"),
                            "errorCode": code, "error": message, "firstRunId": run_id,
                            "policy": "ONE_CLEAN_WORKER_RETRY_NO_PROCESS_OBSERVER", "at": _utc_now(),
                        }, ensure_ascii=False, default=str) + "\n")
                except Exception:
                    pass
                retry_descriptor = json.loads(json.dumps(descriptor, ensure_ascii=False))
                retry_execution = retry_descriptor.setdefault("execution", {})
                retry_execution["_infra_retry"] = True
                retry_execution["_disable_process_observer"] = True
                action, retry_output, retry_evidence = self.invoke(retry_descriptor, value)
                retry_evidence["infrastructure_retry"] = {
                    "status": "RECOVERED", "reason": code, "first_run_id": run_id,
                    "policy": "ONE_CLEAN_WORKER_RETRY_NO_PROCESS_OBSERVER",
                }
                return action, retry_output, retry_evidence

            raise RuntimeInvocationError(code, message, details)

        raw_output = response.get("output")
        try:
            json.dumps(raw_output, ensure_ascii=False)
        except Exception as exc:
            raise RuntimeInvocationError("RUNTIME_OUTPUT_INVALID", f"runtime raw output is not JSON serializable: {type(exc).__name__}: {exc}") from exc

        output_spec = descriptor.get("output") or {}
        graph_output_contract = str(output_spec.get("graph_contract") or output_spec.get("contract") or "")
        runtime_output_contract = str(output_spec.get("runtime_contract") or "")
        actual_runtime_contract = str(raw_output.get("contract") or "") if isinstance(raw_output, dict) else ""
        contract_bridge = output_spec.get("bridge") if isinstance(output_spec.get("bridge"), dict) else None

        # BUILD97: validate the brick's intrinsic runtime contract before any semantic graph wrapping.
        if runtime_output_contract and actual_runtime_contract and actual_runtime_contract != runtime_output_contract:
            raise RuntimeInvocationError(
                "CONTRACT_MISMATCH",
                f"runtime intrinsic output contract mismatch for {descriptor.get('target_brick_id')}: expected {runtime_output_contract}, got {actual_runtime_contract}",
                {
                    "direction": "output",
                    "contract_layer": "runtime-intrinsic",
                    "expected_contract": runtime_output_contract,
                    "actual_contract": actual_runtime_contract,
                },
            )

        output = raw_output
        bridge_applied = False
        bridge_kind = None
        if contract_bridge:
            source_contract = str(contract_bridge.get("source_contract") or "")
            target_contract = str(contract_bridge.get("target_contract") or "")
            if contract_bridge.get("payload_from") != "return_value" or not source_contract or not target_contract:
                raise RuntimeInvocationError("RUNTIME_CONTRACT_INVALID", "invalid semantic output contract bridge")
            if source_contract != runtime_output_contract or target_contract != graph_output_contract:
                raise RuntimeInvocationError("RUNTIME_CONTRACT_INVALID", "semantic output contract bridge does not match descriptor contracts")
            if not isinstance(raw_output, dict) or str(raw_output.get("contract") or "") != source_contract:
                raise RuntimeInvocationError(
                    "CONTRACT_MISMATCH",
                    f"semantic output bridge source contract mismatch for {descriptor.get('target_brick_id')}: expected {source_contract}, got {raw_output.get('contract') if isinstance(raw_output, dict) else type(raw_output).__name__}",
                    {
                        "direction": "output",
                        "contract_layer": "bridge-source",
                        "expected_contract": source_contract,
                        "actual_contract": raw_output.get("contract") if isinstance(raw_output, dict) else None,
                        "target_contract": target_contract,
                    },
                )
            output = {
                "contract": target_contract,
                "payload": raw_output,
                "source_contract": source_contract,
                "runtime_wrapper": True,
                "wrapper_kind": "SEMANTIC_OUTPUT_CONTRACT_BRIDGE",
            }
            bridge_applied = True
            bridge_kind = "SEMANTIC_OUTPUT_CONTRACT_BRIDGE"

        wrapper = descriptor.get("result_wrapper") or {}
        if wrapper:
            if bridge_applied:
                raise RuntimeInvocationError("RUNTIME_CONTRACT_INVALID", "result_wrapper conflicts with semantic output contract bridge")
            contract = str(wrapper.get("contract") or "")
            if not contract or wrapper.get("payload_from") != "return_value":
                raise RuntimeInvocationError("RUNTIME_CONTRACT_INVALID", "invalid declarative result_wrapper")
            output = {"contract": contract, "payload": output, "runtime_wrapper": True}

        try:
            json.dumps(output, ensure_ascii=False)
        except Exception as exc:
            raise RuntimeInvocationError("RUNTIME_OUTPUT_INVALID", f"runtime output is not JSON serializable: {type(exc).__name__}: {exc}") from exc
        validation = str((descriptor.get("output") or {}).get("validation") or "json-compatible")
        if validation == "mapping" and not isinstance(output, dict):
            raise RuntimeInvocationError("CONTRACT_MISMATCH", f"runtime output must be mapping, got {type(output).__name__}", {"direction": "output", "expected": "mapping", "actual": type(output).__name__})
        if validation not in {"json-compatible", "mapping", "any"}:
            raise RuntimeInvocationError("RUNTIME_CONTRACT_INVALID", f"unsupported output validation: {validation}")
        expected_output_contract = str((descriptor.get("output") or {}).get("contract") or "")
        if expected_output_contract and isinstance(output, dict) and output.get("contract") is not None and str(output.get("contract")) != expected_output_contract:
            raise RuntimeInvocationError("CONTRACT_MISMATCH", f"runtime output contract mismatch for {descriptor.get('target_brick_id')}: expected {expected_output_contract}, got {output.get('contract')}", {"direction": "output", "expected_contract": expected_output_contract, "actual_contract": output.get("contract")})

        evidence = {
            "resolution": descriptor.get("resolution"),
            "provider": (descriptor.get("provenance") or {}).get("implementation_provider"),
            "provider_used_for_dispatch": False,
            "entrypoint": f"{relative}::{callable_name}",
            "argument_mode": argument_mode,
            "source_sha256": actual_sha,
            "input_sha256": sha256_json(input_value) if argument_mode != "none" else None,
            "input_value": input_value if argument_mode != "none" else None,
            "input_contract": str((descriptor.get("input") or {}).get("contract") or ""),
            "input_schema": (descriptor.get("input") or {}).get("schema"),
            "fixture_sha256": (descriptor.get("input") or {}).get("fixture_sha256"),
            "runtime_output_contract": runtime_output_contract,
            "graph_output_contract": graph_output_contract,
            "output_contract": graph_output_contract,
            "raw_output_contract": actual_runtime_contract or None,
            "raw_output_sha256": sha256_json(raw_output),
            "contract_bridge_applied": bridge_applied,
            "contract_bridge_kind": bridge_kind,
            "output_sha256": sha256_json(output),
            "duration_ms": int((time.perf_counter() - started) * 1000),
            "stage9_run_id": self.stage9_run_id or None,
            "runtime_execution_run_id": run_id,
            "runtime_execution_evidence": stage9_evidence_reference(self.root, self.evidence_dir, run_dir / "runtime-execution.json"),
            "runtime_budget_kind": budget_kind,
            "runtime_timeout_seconds": timeout_seconds,
            "runtime_import_timeout_seconds": import_timeout,
            "runtime_call_timeout_seconds": call_timeout,
            "runtime_spark_call_timeout_seconds": spark_call_timeout,
            "heavy_import_modules": heavy_import_modules,
            "worker_timings": response.get("timings"),
        }
        # BUILD97: enrich the per-call BLACKBOX/runtime receipt after semantic contract validation.
        execution_receipt_path = run_dir / "runtime-execution.json"
        execution_receipt = read_json(execution_receipt_path, {}) if execution_receipt_path.is_file() else {}
        if isinstance(execution_receipt, dict):
            execution_receipt.update({
                "runtime_output_contract": runtime_output_contract or None,
                "graph_output_contract": graph_output_contract or None,
                "raw_output_contract": actual_runtime_contract or None,
                "raw_output_sha256": sha256_json(raw_output),
                "contract_bridge_applied": bridge_applied,
                "contract_bridge_kind": bridge_kind,
                "output_sha256": sha256_json(output),
                "raw_output": raw_output,
                "output": output,
            })
            write_json(execution_receipt_path, execution_receipt)
        return callable_name, output, evidence

class ProjectRuntime:
    def __init__(self, root: Path, *, allow_unresolved_inventory: bool = False):
        self.root = root.resolve()
        self.web = self.root / "web"
        self.foundry = self.root / "foundry"
        evidence_scope = os.environ.get("PORTFOLIO_FOUNDRY_RUNTIME_EVIDENCE_DIR", "evidence/v031")
        evidence_path = Path(evidence_scope)
        self.evidence_v031 = evidence_path if evidence_path.is_absolute() else self.root / evidence_path
        self.invocation_dir = self.foundry / "runtime-invocations"
        self.fixture_dir = self.foundry / "runtime-fixtures"
        self.contract_dir = self.foundry / "runtime-contracts"
        self.fixture_resolution_dir = self.foundry / "fixture-resolutions"
        self.stage9_context = read_json(self.foundry / "stage9-run-context.json", {})
        self.stage9_run_id = str(self.stage9_context.get("runId") or "") if isinstance(self.stage9_context, dict) else ""
        self.stage9_started = time.perf_counter()
        self.graph = read_json(self.foundry / "executable-capability-graph.json", {"nodes": [], "edges": []})
        self.foundation = read_json(self.foundry / "project-foundation.json", {})
        self.implementation = read_json(self.foundry / "capability-implementation-proof.json", {"capabilities": []})
        self.contract_closure = read_json(self.foundry / "contract-closure-proof.json", {"adapters": []})
        self.routes = read_json(self.foundry / "application-routes.json", [])
        self.runtime_profile = read_json(self.foundry / "runtime-profile.json", {})
        self.demo_spec = read_json(self.foundry / "demo-scenario.json", {})
        self.case_portfolio = read_json(self.foundry / "case-portfolio.json", {})
        self.life_scenario = read_json(self.foundry / "life-scenario.json", {})
        self.economic_effect = read_json(self.foundry / "economic-effect.json", {})
        self.project_spec = read_json(self.foundry / "project-spec.json", {})
        self.gap_plan = read_json(self.foundry / "brick-gap-reconciled-plan.json", {"composition": []})
        self.supplemental_proof_capabilities = {
            str(x.get("capability") or "").strip().casefold()
            for x in self.gap_plan.get("composition", [])
            if "BUILD37_VACANCY_PROOF_TARGET" in str(x.get("rationale") or "")
        }
        self.implementation_by_id = {str(x.get("fileSystemId", "")): x for x in self.implementation.get("capabilities", [])}
        self.adapter_by_id = {str(x.get("adapterId", "")): x for x in self.contract_closure.get("adapters", [])}
        self.invoker = GenericRuntimeInvoker(self.root, self.evidence_v031)
        self.runtime_invocations: dict[str, dict[str, Any]] = {}
        self.fixture_resolutions: dict[str, dict[str, Any]] = {}
        self.discovery_diagnostics: list[dict[str, Any]] = []
        self.proof_reuse_errors: dict[str, str] = {}
        self._discovery_inventory: list[dict[str, Any]] = []
        # BUILD99: durable Stage 9 node-result checkpoints. These are candidate-scoped and
        # deliberately survive Factory/build iterations; reuse is allowed only when the
        # node/dependency/runtime fingerprints below still match.
        self.stage9_checkpoint_dir = self.foundry / "stage9-checkpoints"
        self.stage9_checkpoint_dir.mkdir(parents=True, exist_ok=True)
        self.stage9_checkpoint_decisions: list[dict[str, Any]] = []
        self.stage9_checkpoint_invalidations: list[dict[str, Any]] = []
        self.stage9_checkpoint_reused = 0
        self.stage9_checkpoint_written = 0
        self.stage9_checkpoint_bootstrapped = 0
        self.stage9_checkpoint_invalidated = 0
        self.stage9_resume_start_node: str | None = None
        self.stage9_checkpoint_fingerprints: dict[str, str] = {}
        self.stage9_force_fresh = False
        try:
            self._build_runtime_invocation_inventory()
        except RuntimeInvocationError as exc:
            if not allow_unresolved_inventory:
                raise
            self._persist_runtime_discovery_failure(exc)
        except Exception as exc:
            if not allow_unresolved_inventory:
                raise
            self._persist_runtime_discovery_failure(RuntimeInvocationError(
                "RUNTIME_DISCOVERY_EXCEPTION",
                f"{type(exc).__name__}: {exc}",
                {"exception_type": type(exc).__name__},
            ))
        inventory = read_json(self.foundry / "runtime-invocation-inventory.json", {})
        if inventory.get("status") != "PASS" and not allow_unresolved_inventory:
            missing = [str(x.get("node_id")) for x in inventory.get("nodes", []) if x.get("status") != "READY"]
            raise RuntimeInvocationError("RUNTIME_INVENTORY_UNRESOLVED", "runtime invocation inventory contains unresolved required nodes", {"nodes": missing})

    @property
    def project_id(self) -> str:
        return str(self.foundation.get("projectId") or self.project_spec.get("projectId") or self.root.name)

    @property
    def vacancy_id(self) -> str:
        return str(self.foundation.get("vacancyId") or self.project_spec.get("vacancyId") or self.stage9_context.get("vacancyId") or "")

    @property
    def candidate_id(self) -> str:
        return str(self.implementation.get("candidateId") or self.foundation.get("candidateId") or self.stage9_context.get("candidateId") or self.root.name)

    def _stage9_graph_event(self, event_type: str, status: str, detail: str, *, node: str | None = None, current: int | None = None, total: int | None = None, extra: dict[str, Any] | None = None) -> None:
        row = {
            "schema": "portfolio-foundry.stage9-event.v1", "eventType": event_type, "runId": self.stage9_run_id or None,
            "candidateId": self.candidate_id, "vacancyId": self.vacancy_id, "phase": "SMOKE_BRICK_EXECUTES",
            "status": status, "detail": detail, "node": node, "current": current, "total": total,
            "durationMs": int((time.perf_counter()-self.stage9_started)*1000), "at": _utc_now(),
        }
        if extra:
            row.update(extra)
        try:
            path = self.evidence_v031 / "stage9-graph-events.ndjson"
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(row, ensure_ascii=False) + "\n")
        except Exception:
            pass

    def _stage9_live(self, status: str, detail: str, *, node: str | None = None, current: int | None = None, total: int | None = None, wait_reason: str | None = None) -> None:
        runtime_env = read_json(self.foundry / "runtime-environment.json", {})
        payload = {
            "schema": "portfolio-foundry.stage9-live-status.v3", "runId": self.stage9_run_id or None,
            "candidateId": self.candidate_id, "vacancyId": self.vacancy_id, "phase": "SMOKE_BRICK_EXECUTES", "status": status,
            "detail": detail, "current": current, "total": total, "currentNode": node, "waitReason": wait_reason,
            "runtimeId": runtime_env.get("runtimeId") or runtime_env.get("cache_key"), "runtimeCacheStatus": runtime_env.get("cacheStatus"),
            "durationMs": int((time.perf_counter()-self.stage9_started)*1000),
            "checkpointMode": "FRESH_CAPTURE" if self.stage9_force_fresh else "RESUMABLE", "checkpointsReused": self.stage9_checkpoint_reused,
            "checkpointsWritten": self.stage9_checkpoint_written, "checkpointsBootstrapped": self.stage9_checkpoint_bootstrapped, "checkpointsInvalidated": self.stage9_checkpoint_invalidated,
            "resumeStartNode": self.stage9_resume_start_node,
            "previousRunId": self.stage9_context.get("previousRunId"), "previousStatus": self.stage9_context.get("previousStatus"), "previousPhase": self.stage9_context.get("previousPhase"), "previousUpdatedAt": self.stage9_context.get("previousUpdatedAt"),
            "updatedAt": _utc_now(),
        }
        try:
            write_json(self.foundry / "stage9-live-status.json", payload)
        except Exception:
            pass

    def _node_id(self, node: dict[str, Any]) -> str:
        return str(node.get("fileSystemId") or node.get("id") or "")

    def _checkpoint_safe_name(self, node_id: str) -> str:
        return re.sub(r"[^A-Za-z0-9._-]+", "_", node_id).strip("._") or "node"

    def _checkpoint_path(self, node_id: str) -> Path:
        return self.stage9_checkpoint_dir / f"{self._checkpoint_safe_name(node_id)}.json"

    def _checkpoint_append(self, path: Path, row: dict[str, Any]) -> None:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
        except Exception:
            pass

    def _checkpoint_dependency_map(self) -> dict[str, dict[str, list[str]]]:
        node_ids = [self._node_id(x) for x in self.graph.get("nodes", []) if self._node_id(x)]
        incoming = {node_id: [] for node_id in node_ids}
        outgoing = {node_id: [] for node_id in node_ids}
        for edge in self.graph.get("edges", []):
            source = str(edge.get("from") or "")
            target = str(edge.get("to") or "")
            if target in incoming and source in outgoing:
                incoming[target].append(source)
                outgoing[source].append(target)
        return {
            node_id: {
                "incoming": sorted(set(incoming.get(node_id, []))),
                "outgoing": sorted(set(outgoing.get(node_id, []))),
            }
            for node_id in node_ids
        }

    def _checkpoint_source_path(self, brick_id: str, descriptor: dict[str, Any] | None, node: dict[str, Any]) -> Path | None:
        if descriptor:
            entrypoint = str(descriptor.get("entrypoint") or "")
            if "::" in entrypoint:
                path = (self.root / entrypoint.split("::", 1)[0]).resolve()
                if path.is_file():
                    return path
        candidate_relative = str(node.get("candidateRelativePath") or "").strip("/")
        for rel in [
            f"src/bricks/{brick_id}/core.py",
            f"src/adapters/{brick_id}/core.py",
            f"{candidate_relative}/core.py" if candidate_relative else "",
        ]:
            if not rel:
                continue
            path = (self.root / rel).resolve()
            if path.is_file():
                return path
        return None

    def _checkpoint_import_roots(self, source_path: Path | None) -> list[str]:
        if source_path is None or not source_path.is_file():
            return []
        try:
            source, _, _ = read_python_source(source_path)
            tree = ast.parse(source, filename=str(source_path))
            roots: set[str] = set()
            for item in ast.walk(tree):
                if isinstance(item, ast.Import):
                    roots.update(str(alias.name).split(".", 1)[0] for alias in item.names)
                elif isinstance(item, ast.ImportFrom) and item.module:
                    roots.add(str(item.module).split(".", 1)[0])
            return sorted(x for x in roots if x)
        except Exception:
            return []

    def _checkpoint_runtime_dependency_fingerprint(self, source_path: Path | None) -> tuple[str, dict[str, Any]]:
        runtime_env = read_json(self.foundry / "runtime-environment.json", {})
        dependency = read_json(self.evidence_v031 / "dependency-resolution.json", {})
        installed = {
            re.sub(r"[-_.]+", "-", str(row.get("name") or "")).casefold(): str(row.get("version") or "")
            for row in dependency.get("installedPackages", []) if isinstance(row, dict)
        }
        aliases = {"sklearn": "scikit-learn", "cv2": "opencv-python", "yaml": "pyyaml", "PIL": "pillow"}
        imports = self._checkpoint_import_roots(source_path)
        package_versions: dict[str, str | None] = {}
        for root in imports:
            package = aliases.get(root, root)
            normalized = re.sub(r"[-_.]+", "-", package).casefold()
            package_versions[root] = installed.get(normalized)
        env_snapshot = read_json(self.evidence_v031 / "environment.json", {})
        payload = {
            "pythonVersion": runtime_env.get("pythonVersion") or env_snapshot.get("pythonVersion"),
            "imports": imports,
            "packageVersions": package_versions,
            "javaVersion": env_snapshot.get("javaVersion") if "pyspark" in imports else None,
            "sparkVersion": env_snapshot.get("sparkVersion") if "pyspark" in imports else None,
        }
        return sha256_json(payload), payload

    def _checkpoint_local_context(self, node: dict[str, Any], index: int, descriptor: dict[str, Any] | None, impl: dict[str, Any] | None, adapter: dict[str, Any] | None) -> dict[str, Any]:
        brick_id = self._node_id(node)
        source_path = self._checkpoint_source_path(brick_id, descriptor, node)
        source_sha = sha256_file(source_path) if source_path is not None and source_path.is_file() else None
        input_spec = (descriptor or {}).get("input") if isinstance((descriptor or {}).get("input"), dict) else {}
        output_spec = (descriptor or {}).get("output") if isinstance((descriptor or {}).get("output"), dict) else {}
        fixture_rel = str(input_spec.get("smoke_fixture") or "")
        fixture_path = self.root / fixture_rel if fixture_rel else None
        fixture_sha = sha256_file(fixture_path) if fixture_path is not None and fixture_path.is_file() else input_spec.get("fixture_sha256")
        runtime_dependency_sha, runtime_dependency_detail = self._checkpoint_runtime_dependency_fingerprint(source_path)
        dependency_map = self._checkpoint_dependency_map()
        incoming_ids = dependency_map.get(brick_id, {}).get("incoming", [])
        incoming_edges = [
            edge for edge in self.graph.get("edges", [])
            if str(edge.get("to") or "") == brick_id and str(edge.get("from") or "") in incoming_ids
        ]
        upstream = {node_id: self.stage9_checkpoint_fingerprints.get(node_id) for node_id in incoming_ids}
        contracts = {
            "nodeInput": node.get("inputContract"), "nodeOutput": node.get("outputContract"),
            "descriptorInput": input_spec.get("contract"), "descriptorOutput": output_spec.get("contract"),
            "runtimeOutput": output_spec.get("runtime_contract") or (descriptor or {}).get("runtime_output_contract"),
            "contractBridge": (descriptor or {}).get("contract_bridge"),
        }
        return {
            "policy": "portfolio-foundry.stage9-checkpoint-policy.v1",
            "candidateId": self.candidate_id,
            "projectId": self.project_id,
            "vacancyId": self.vacancy_id,
            "nodeId": brick_id,
            "nodeIndex": index,
            "nodeDefinitionSha256": sha256_json(node),
            "incomingEdgesSha256": sha256_json(incoming_edges),
            "descriptorSha256": sha256_json(descriptor) if descriptor is not None else None,
            "implementationSha256": sha256_json(impl) if impl is not None else None,
            "adapterSha256": sha256_json(adapter) if adapter is not None else None,
            "sourcePath": source_path.relative_to(self.root).as_posix() if source_path is not None and self.root in source_path.parents else None,
            "sourceSha256": source_sha,
            "fixturePath": fixture_rel or None,
            "fixtureSha256": fixture_sha,
            "contractsSha256": sha256_json(contracts),
            "runtimeDependencySha256": runtime_dependency_sha,
            "runtimeDependencyDetail": runtime_dependency_detail,
            "upstreamReceiptFingerprints": upstream,
        }

    def _checkpoint_invalidation_reason(self, previous: dict[str, Any], current: dict[str, Any]) -> str:
        if previous.get("candidateId") != current.get("candidateId") or previous.get("projectId") != current.get("projectId"):
            return "INVALIDATED_CANDIDATE_CHANGED"
        if previous.get("nodeDefinitionSha256") != current.get("nodeDefinitionSha256") or previous.get("incomingEdgesSha256") != current.get("incomingEdgesSha256"):
            return "INVALIDATED_GRAPH_CHANGED"
        if previous.get("sourceSha256") != current.get("sourceSha256") or previous.get("descriptorSha256") != current.get("descriptorSha256"):
            return "INVALIDATED_BRICK_SOURCE_CHANGED"
        if previous.get("fixtureSha256") != current.get("fixtureSha256"):
            return "INVALIDATED_FIXTURE_CHANGED"
        if previous.get("contractsSha256") != current.get("contractsSha256"):
            return "INVALIDATED_CONTRACT_CHANGED"
        if previous.get("runtimeDependencySha256") != current.get("runtimeDependencySha256"):
            return "INVALIDATED_RUNTIME_CHANGED"
        if previous.get("upstreamReceiptFingerprints") != current.get("upstreamReceiptFingerprints"):
            return "INVALIDATED_UPSTREAM_CHANGED"
        return "INVALIDATED_FINGERPRINT_CHANGED"

    def _checkpoint_try_reuse(self, node: dict[str, Any], index: int, descriptor: dict[str, Any] | None, impl: dict[str, Any] | None, adapter: dict[str, Any] | None) -> tuple[dict[str, Any] | None, dict[str, Any], str]:
        brick_id = self._node_id(node)
        context = self._checkpoint_local_context(node, index, descriptor, impl, adapter)
        checkpoint_key = sha256_json(context)
        path = self._checkpoint_path(brick_id)
        receipt = read_json(path, {}) if path.is_file() else {}
        if not isinstance(receipt, dict) or receipt.get("status") != "PASS":
            reason = "MISS_NO_PASS_CHECKPOINT"
            return None, context, reason
        previous_context = receipt.get("fingerprintContext") if isinstance(receipt.get("fingerprintContext"), dict) else {}
        if str(receipt.get("checkpointKey") or "") != checkpoint_key:
            reason = self._checkpoint_invalidation_reason(previous_context, context)
            self.stage9_checkpoint_invalidated += 1
            invalidation = {
                "schema": "portfolio-foundry.stage9-checkpoint-invalidation.v1",
                "stage9RunId": self.stage9_run_id or None,
                "node": brick_id,
                "reason": reason,
                "sourceRunId": receipt.get("sourceRunId"),
                "previousCheckpointKey": receipt.get("checkpointKey"),
                "currentCheckpointKey": checkpoint_key,
                "at": _utc_now(),
            }
            self.stage9_checkpoint_invalidations.append(invalidation)
            self._checkpoint_append(self.evidence_v031 / "stage9-checkpoint-invalidations.ndjson", invalidation)
            return None, context, reason
        output = receipt.get("output")
        if str(receipt.get("outputSha256") or "") != sha256_json(output):
            reason = "INVALIDATED_OUTPUT_HASH_MISMATCH"
            self.stage9_checkpoint_invalidated += 1
            invalidation = {
                "schema": "portfolio-foundry.stage9-checkpoint-invalidation.v1",
                "stage9RunId": self.stage9_run_id or None,
                "node": brick_id,
                "reason": reason,
                "sourceRunId": receipt.get("sourceRunId"),
                "at": _utc_now(),
            }
            self.stage9_checkpoint_invalidations.append(invalidation)
            self._checkpoint_append(self.evidence_v031 / "stage9-checkpoint-invalidations.ndjson", invalidation)
            return None, context, reason
        return receipt, context, "CACHE_HIT"

    def _checkpoint_write_pass(self, node: dict[str, Any], index: int, context: dict[str, Any], action: str, mode: str, output: Any, runtime_evidence: dict[str, Any], *, input_value: Any = None, input_source: str | None = None, source_run_id: str | None = None, origin: str = "CURRENT_EXECUTION") -> dict[str, Any]:
        brick_id = self._node_id(node)
        checkpoint_key = sha256_json(context)
        output_sha = sha256_json(output)
        receipt_fingerprint = sha256_json({
            "checkpointKey": checkpoint_key,
            "outputSha256": output_sha,
            "node": brick_id,
            "status": "PASS",
        })
        receipt = {
            "schema": "portfolio-foundry.stage9-node-checkpoint.v1",
            "status": "PASS",
            "node": brick_id,
            "order": index,
            "candidateId": self.candidate_id,
            "vacancyId": self.vacancy_id,
            "checkpointKey": checkpoint_key,
            "receiptFingerprint": receipt_fingerprint,
            "fingerprintContext": context,
            "action": action,
            "mode": mode,
            "input": input_value,
            "inputSource": input_source,
            "inputSha256": sha256_json(input_value) if input_value is not None else runtime_evidence.get("input_sha256"),
            "output": output,
            "outputSha256": output_sha,
            "runtimeExecutionRunId": runtime_evidence.get("runtime_execution_run_id"),
            "runtimeEvidence": runtime_evidence,
            "sourceRunId": source_run_id or self.stage9_run_id or None,
            "origin": origin,
            "completedAt": _utc_now(),
        }
        write_json(self._checkpoint_path(brick_id), receipt)
        self.stage9_checkpoint_written += 1
        self.stage9_checkpoint_fingerprints[brick_id] = receipt_fingerprint
        return receipt

    def _checkpoint_bootstrap_previous_demo(self, nodes: list[dict[str, Any]]) -> None:
        """Seed an empty BUILD99 cache from the immediately previous compatible Stage 9 demo evidence.
        This avoids one unnecessary full replay after upgrading from BUILD98 while remaining fail-closed:
        every imported PASS is rebound to the current source/fixture/contract/runtime/upstream fingerprints.
        """
        if any(self.stage9_checkpoint_dir.glob("*.json")):
            return
        previous = read_json(self.evidence_v031 / "runtime-demo-run.json", {})
        if not isinstance(previous, dict):
            return
        previous_run_id = str(previous.get("stage9RunId") or "")
        if not previous_run_id or previous_run_id == self.stage9_run_id:
            return
        if str(previous.get("candidateId") or "") not in {"", self.candidate_id}:
            return
        steps = previous.get("steps") if isinstance(previous.get("steps"), list) else []
        by_order = {int(row.get("order")): row for row in steps if isinstance(row, dict) and str(row.get("order") or "").isdigit()}
        for index, node in enumerate(nodes, start=1):
            row = by_order.get(index)
            brick_id = self._node_id(node)
            if not row or str(row.get("node") or "") != brick_id or str(row.get("status") or "").upper() != "PASS":
                break
            output = row.get("output")
            try:
                json.dumps(output, ensure_ascii=False)
            except Exception:
                break
            descriptor = self.runtime_invocations.get(brick_id)
            impl = self.implementation_by_id.get(brick_id)
            adapter = self.adapter_by_id.get(brick_id)
            context = self._checkpoint_local_context(node, index, descriptor, impl, adapter)
            runtime_evidence = row.get("runtime") if isinstance(row.get("runtime"), dict) else {}
            receipt = self._checkpoint_write_pass(
                node, index, context,
                str(row.get("action") or "execute"),
                str(row.get("mode") or "GENERIC_RUNTIME_CONTRACT"),
                output,
                {**runtime_evidence, "checkpoint_bootstrap": True, "checkpoint_bootstrap_source_run_id": previous_run_id},
                input_value=row.get("input"), input_source=str(row.get("inputSource") or "PREVIOUS_DEMO"),
                source_run_id=previous_run_id,
                origin="PREVIOUS_DEMO_BOOTSTRAP",
            )
            self.stage9_checkpoint_bootstrapped += 1
            self._checkpoint_record_decision(brick_id, index, "BOOTSTRAP", "PREVIOUS_COMPATIBLE_DEMO_PASS", source_run_id=previous_run_id)
            self.stage9_checkpoint_fingerprints[brick_id] = str(receipt.get("receiptFingerprint") or "")

    def _checkpoint_record_decision(self, node_id: str, index: int, decision: str, reason: str, *, source_run_id: str | None = None) -> None:
        row = {
            "schema": "portfolio-foundry.stage9-checkpoint-decision.v1",
            "stage9RunId": self.stage9_run_id or None,
            "node": node_id,
            "order": index,
            "decision": decision,
            "reason": reason,
            "sourceRunId": source_run_id,
            "at": _utc_now(),
        }
        self.stage9_checkpoint_decisions.append(row)
        self._checkpoint_append(self.evidence_v031 / "stage9-checkpoint-decisions.ndjson", row)

    def _checkpoint_persist_summary(self, nodes: list[dict[str, Any]], status: str) -> None:
        dependency_map = self._checkpoint_dependency_map()
        receipts: list[dict[str, Any]] = []
        for index, node in enumerate(nodes, start=1):
            node_id = self._node_id(node)
            receipt = read_json(self._checkpoint_path(node_id), {})
            receipts.append({
                "order": index,
                "node": node_id,
                "status": receipt.get("status") if isinstance(receipt, dict) else None,
                "sourceRunId": receipt.get("sourceRunId") if isinstance(receipt, dict) else None,
                "receiptFingerprint": receipt.get("receiptFingerprint") if isinstance(receipt, dict) else None,
                "checkpointKey": receipt.get("checkpointKey") if isinstance(receipt, dict) else None,
            })
        summary = {
            "schema": "portfolio-foundry.stage9-resume-summary.v1",
            "stage9RunId": self.stage9_run_id or None,
            "status": status,
            "checkpointMode": "RESUMABLE",
            "reused": self.stage9_checkpoint_reused,
            "written": self.stage9_checkpoint_written,
            "bootstrapped": self.stage9_checkpoint_bootstrapped,
            "invalidated": self.stage9_checkpoint_invalidated,
            "resumeStartNode": self.stage9_resume_start_node,
            "totalNodes": len(nodes),
            "receipts": receipts,
            "createdAt": _utc_now(),
        }
        index_payload = {
            "schema": "portfolio-foundry.stage9-checkpoint-index.v1",
            "stage9RunId": self.stage9_run_id or None,
            "candidateId": self.candidate_id,
            "status": status,
            "checkpointMode": "RESUMABLE",
            "reused": self.stage9_checkpoint_reused,
            "written": self.stage9_checkpoint_written,
            "bootstrapped": self.stage9_checkpoint_bootstrapped,
            "invalidated": self.stage9_checkpoint_invalidated,
            "resumeStartNode": self.stage9_resume_start_node,
            "nodes": receipts,
            "createdAt": _utc_now(),
        }
        write_json(self.evidence_v031 / "stage9-resume-summary.json", summary)
        write_json(self.evidence_v031 / "stage9-checkpoint-index.json", index_payload)
        write_json(self.evidence_v031 / "stage9-checkpoint-dependency-map.json", {
            "schema": "portfolio-foundry.stage9-checkpoint-dependency-map.v1",
            "stage9RunId": self.stage9_run_id or None,
            "candidateId": self.candidate_id,
            "nodes": dependency_map,
            "createdAt": _utc_now(),
        })
        write_json(self.foundry / "stage9-checkpoint-index.json", index_payload)

    def _python_ast(self, path: Path, brick_id: str, purpose: str) -> tuple[ast.AST | None, dict[str, Any]]:
        row: dict[str, Any] = {
            "brick_id": brick_id,
            "physical_path": path.relative_to(self.root).as_posix() if path.is_absolute() and self.root in path.parents else str(path),
            "purpose": purpose,
            "encoding": None,
            "bom_detected": False,
            "parse_status": "FAIL",
            "public_callables": [],
            "error_code": None,
            "error": None,
        }
        if not path.is_file():
            row["error_code"] = "PYTHON_SOURCE_MISSING"
            row["error"] = "source file does not exist"
            self.discovery_diagnostics.append(row)
            return None, row
        try:
            source, encoding, bom = read_python_source(path)
            row["encoding"] = encoding
            row["bom_detected"] = bom
        except Exception as exc:
            row["error_code"] = "PYTHON_DISCOVERY_READ_FAILED"
            row["error"] = f"{type(exc).__name__}: {exc}"
            self.discovery_diagnostics.append(row)
            return None, row
        try:
            tree = ast.parse(source, filename=str(path))
            row["parse_status"] = "PASS"
            self.discovery_diagnostics.append(row)
            return tree, row
        except Exception as exc:
            row["error_code"] = "PYTHON_DISCOVERY_PARSE_FAILED"
            row["error"] = f"{type(exc).__name__}: {exc}"
            self.discovery_diagnostics.append(row)
            return None, row

    def _public_functions(self, path: Path, brick_id: str, purpose: str = "callable-discovery") -> list[tuple[str, int]]:
        tree, diagnostic = self._python_ast(path, brick_id, purpose)
        if tree is None:
            return []
        rows: list[tuple[str, int]] = []
        for stmt in tree.body:
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)) and not stmt.name.startswith("_"):
                positional = len(stmt.args.posonlyargs) + len(stmt.args.args)
                required = max(0, positional - len(stmt.args.defaults))
                rows.append((stmt.name, required))
        diagnostic["public_callables"] = [{"name": name, "required_args": required} for name, required in rows]
        return rows

    def _manifest_expected_hash(self, relative: str, brick_id: str) -> str | None:
        candidates = [
            self.root / "evidence" / "v030" / brick_id / "IMPLEMENTATION_MANIFEST.sha256",
            self.root / "evidence" / "v030" / "contract-closure" / brick_id / "ADAPTER_MANIFEST.sha256",
            self.root / relative.rsplit("/", 1)[0] / "SOURCE_MANIFEST.sha256",
        ]
        for manifest in candidates:
            if not manifest.is_file():
                continue
            try:
                for line in manifest.read_text(encoding="utf-8").splitlines():
                    parts = line.strip().split(None, 1)
                    if len(parts) != 2:
                        continue
                    manifest_path = parts[1].strip().replace("\\", "/")
                    if manifest_path == relative or manifest_path.endswith("/" + Path(relative).name):
                        return parts[0].lower()
            except Exception:
                continue
        return None

    def _literal_assignments(self, tree: ast.AST) -> dict[str, Any]:
        values: dict[str, Any] = {}
        for stmt in ast.walk(tree):
            if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1 and isinstance(stmt.targets[0], ast.Name):
                try:
                    values[stmt.targets[0].id] = ast.literal_eval(stmt.value)
                except Exception:
                    pass
            elif isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name) and stmt.value is not None:
                try:
                    values[stmt.target.id] = ast.literal_eval(stmt.value)
                except Exception:
                    pass
        return values

    def _fixture_exec_block(self, statements: list[ast.stmt], assignments: dict[str, ast.AST], helpers: dict[str, ast.FunctionDef], local: dict[str, Any]) -> tuple[bool, Any]:
        """BUILD149: bounded static interpreter for deterministic test-fixture helpers.

        This is intentionally small: it supports the pure Python constructs emitted by Stage 3/8
        fixture helpers (assignments, range loops, append/extend, if/return and scalar arithmetic).
        It never imports or executes candidate code.
        """
        for stmt in statements:
            budget = local.setdefault("__PF_STATIC_BUDGET__", [50_000])
            budget[0] -= 1
            if budget[0] < 0:
                raise ValueError("fixture static evaluation budget exceeded")
            if isinstance(stmt, ast.Assign):
                value = self._fixture_eval(stmt.value, assignments, helpers, local)
                for target in stmt.targets:
                    if isinstance(target, ast.Name):
                        local[target.id] = value
                    elif isinstance(target, ast.Subscript):
                        container = self._fixture_eval(target.value, assignments, helpers, local)
                        key = self._fixture_eval(target.slice, assignments, helpers, local)
                        container[key] = value
                    else:
                        raise ValueError(f"fixture assignment unsupported: {type(target).__name__}")
                continue
            if isinstance(stmt, ast.AnnAssign) and stmt.value is not None:
                value = self._fixture_eval(stmt.value, assignments, helpers, local)
                if isinstance(stmt.target, ast.Name):
                    local[stmt.target.id] = value
                elif isinstance(stmt.target, ast.Subscript):
                    container = self._fixture_eval(stmt.target.value, assignments, helpers, local)
                    key = self._fixture_eval(stmt.target.slice, assignments, helpers, local)
                    container[key] = value
                else:
                    raise ValueError(f"fixture annotated assignment unsupported: {type(stmt.target).__name__}")
                continue
            if isinstance(stmt, ast.AugAssign):
                if not isinstance(stmt.target, ast.Name):
                    raise ValueError("fixture augmented assignment target unsupported")
                left = local.get(stmt.target.id)
                right = self._fixture_eval(stmt.value, assignments, helpers, local)
                if isinstance(stmt.op, ast.Add): local[stmt.target.id] = left + right
                elif isinstance(stmt.op, ast.Sub): local[stmt.target.id] = left - right
                elif isinstance(stmt.op, ast.Mult): local[stmt.target.id] = left * right
                elif isinstance(stmt.op, ast.Div): local[stmt.target.id] = left / right
                else: raise ValueError(f"fixture augmented operator unsupported: {type(stmt.op).__name__}")
                continue
            if isinstance(stmt, ast.For) and isinstance(stmt.target, ast.Name):
                values = self._fixture_eval(stmt.iter, assignments, helpers, local)
                if len(values) > 10_000:
                    raise ValueError("fixture loop limit exceeded")
                for item in values:
                    local[stmt.target.id] = item
                    returned, result = self._fixture_exec_block(stmt.body, assignments, helpers, local)
                    if returned:
                        return True, result
                returned, result = self._fixture_exec_block(stmt.orelse, assignments, helpers, local)
                if returned:
                    return True, result
                continue
            if isinstance(stmt, ast.If):
                branch = stmt.body if self._fixture_eval(stmt.test, assignments, helpers, local) else stmt.orelse
                returned, result = self._fixture_exec_block(branch, assignments, helpers, local)
                if returned:
                    return True, result
                continue
            if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call) and isinstance(stmt.value.func, ast.Attribute):
                owner = self._fixture_eval(stmt.value.func.value, assignments, helpers, local)
                args = [self._fixture_eval(x, assignments, helpers, local) for x in stmt.value.args]
                if stmt.value.func.attr == "append" and isinstance(owner, list) and len(args) == 1:
                    owner.append(args[0]); continue
                if stmt.value.func.attr == "extend" and isinstance(owner, list) and len(args) == 1:
                    owner.extend(args[0]); continue
                raise ValueError(f"fixture method unsupported: {stmt.value.func.attr}")
            if isinstance(stmt, ast.Return):
                return True, self._fixture_eval(stmt.value, assignments, helpers, local) if stmt.value is not None else None
            if isinstance(stmt, ast.Pass):
                continue
            raise ValueError(f"fixture helper statement unsupported: {type(stmt).__name__}")
        return False, None

    def _fixture_eval(self, node: ast.AST, assignments: dict[str, ast.AST], helpers: dict[str, ast.FunctionDef], local: dict[str, Any] | None = None) -> Any:
        local = {} if local is None else local
        budget = local.setdefault("__PF_STATIC_BUDGET__", [50_000])
        budget[0] -= 1
        if budget[0] < 0:
            raise ValueError("fixture static evaluation budget exceeded")
        if isinstance(node, ast.Constant): return node.value
        if isinstance(node, ast.Name):
            if node.id in local:
                if local[node.id] is _FIXTURE_UNRESOLVED:
                    raise ValueError(f"fixture preparation unresolved: {node.id}")
                return local[node.id]
            if node.id in assignments: return self._fixture_eval(assignments[node.id], assignments, helpers, local)
            raise ValueError(f"fixture name unresolved: {node.id}")
        if isinstance(node, ast.Dict): return {self._fixture_eval(k, assignments, helpers, local): self._fixture_eval(v, assignments, helpers, local) for k, v in zip(node.keys, node.values)}
        if isinstance(node, ast.List): return [self._fixture_eval(x, assignments, helpers, local) for x in node.elts]
        if isinstance(node, ast.Tuple): return tuple(self._fixture_eval(x, assignments, helpers, local) for x in node.elts)
        if isinstance(node, ast.Set): return {self._fixture_eval(x, assignments, helpers, local) for x in node.elts}
        if isinstance(node, ast.UnaryOp):
            value = self._fixture_eval(node.operand, assignments, helpers, local)
            if isinstance(node.op, ast.USub): return -value
            if isinstance(node.op, ast.UAdd): return +value
            if isinstance(node.op, ast.Not): return not value
            raise ValueError(f"fixture unary operator unsupported: {type(node.op).__name__}")
        if isinstance(node, ast.BinOp):
            left = self._fixture_eval(node.left, assignments, helpers, local)
            right = self._fixture_eval(node.right, assignments, helpers, local)
            if isinstance(node.op, ast.Add): return left + right
            if isinstance(node.op, ast.Sub): return left - right
            if isinstance(node.op, ast.Mult): return left * right
            if isinstance(node.op, ast.Div): return left / right
            if isinstance(node.op, ast.FloorDiv): return left // right
            if isinstance(node.op, ast.Mod): return left % right
            if isinstance(node.op, ast.Pow): return left ** right
            raise ValueError(f"fixture binary operator unsupported: {type(node.op).__name__}")
        if isinstance(node, ast.BoolOp):
            values = [self._fixture_eval(x, assignments, helpers, local) for x in node.values]
            if isinstance(node.op, ast.And): return all(values)
            if isinstance(node.op, ast.Or): return any(values)
            raise ValueError(f"fixture bool operator unsupported: {type(node.op).__name__}")
        if isinstance(node, ast.Subscript):
            container = self._fixture_eval(node.value, assignments, helpers, local)
            key = self._fixture_eval(node.slice, assignments, helpers, local)
            return container[key]
        if isinstance(node, ast.IfExp): return self._fixture_eval(node.body if self._fixture_eval(node.test, assignments, helpers, local) else node.orelse, assignments, helpers, local)
        if isinstance(node, ast.Compare) and len(node.ops) == 1 and len(node.comparators) == 1:
            left = self._fixture_eval(node.left, assignments, helpers, local); right = self._fixture_eval(node.comparators[0], assignments, helpers, local); op = node.ops[0]
            if isinstance(op, ast.Eq): return left == right
            if isinstance(op, ast.NotEq): return left != right
            if isinstance(op, ast.Lt): return left < right
            if isinstance(op, ast.LtE): return left <= right
            if isinstance(op, ast.Gt): return left > right
            if isinstance(op, ast.GtE): return left >= right
            if isinstance(op, ast.In): return left in right
            if isinstance(op, ast.NotIn): return left not in right
            raise ValueError("fixture comparison unsupported")
        if isinstance(node, ast.ListComp) and len(node.generators) == 1:
            gen = node.generators[0]
            if gen.ifs or not isinstance(gen.target, ast.Name): raise ValueError("fixture comprehension unsupported")
            values = self._fixture_eval(gen.iter, assignments, helpers, local)
            if len(values) > 10_000: raise ValueError("fixture comprehension limit exceeded")
            return [self._fixture_eval(node.elt, assignments, helpers, {**local, gen.target.id: item}) for item in values]
        # BUILD225: Stage-8 data-quality tests commonly build deterministic literal rows through
        # pandas.DataFrame(...).to_dict(orient="records").  Runtime discovery must reconstruct
        # that JSON payload statically without importing/executing pandas or candidate code.
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            attr = node.func.attr
            if isinstance(node.func.value, ast.Name) and node.func.value.id == "pd" and attr == "DataFrame":
                if not node.args: raise ValueError("fixture DataFrame requires records")
                rows = self._fixture_eval(node.args[0], assignments, helpers, local)
                if not isinstance(rows, (list, tuple)): raise ValueError("fixture DataFrame records must be a sequence")
                return ("__PF_STATIC_DATAFRAME__", [dict(x) if isinstance(x, dict) else x for x in rows])
            owner = self._fixture_eval(node.func.value, assignments, helpers, local)
            args = [self._fixture_eval(x, assignments, helpers, local) for x in node.args]
            kwargs = {kw.arg: self._fixture_eval(kw.value, assignments, helpers, local) for kw in node.keywords if kw.arg is not None}
            if attr == "to_dict" and isinstance(owner, tuple) and len(owner) == 2 and owner[0] == "__PF_STATIC_DATAFRAME__":
                orient = kwargs.get("orient", args[0] if args else "dict")
                if orient != "records": raise ValueError(f"fixture DataFrame.to_dict orient unsupported: {orient}")
                return owner[1]
            raise ValueError(f"fixture method expression unsupported: {attr}")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            name = node.func.id
            args = [self._fixture_eval(x, assignments, helpers, local) for x in node.args]
            if name == "dict" and len(args) <= 1: return dict(args[0]) if args else {}
            if name == "list" and len(args) <= 1: return list(args[0]) if args else []
            if name == "tuple" and len(args) <= 1: return tuple(args[0]) if args else ()
            if name == "set" and len(args) <= 1: return set(args[0]) if args else set()
            if name == "range": return range(*[int(x) for x in args])
            if name == "len" and len(args) == 1: return len(args[0])
            if name == "int" and len(args) == 1: return int(args[0])
            if name == "float" and len(args) == 1: return float(args[0])
            if name == "str" and len(args) == 1: return str(args[0])
            if name == "bool" and len(args) == 1: return bool(args[0])
            if name == "min" and args: return min(args)
            if name == "max" and args: return max(args)
            if name == "sum" and len(args) == 1: return sum(args[0])
            if name == "abs" and len(args) == 1: return abs(args[0])
            if name == "round" and args: return round(*args)
            helper = helpers.get(name)
            if helper is not None:
                params = [x.arg for x in helper.args.args]
                if len(args) != len(params): raise ValueError("fixture helper arity mismatch")
                helper_local = {**local, **dict(zip(params, args))}
                returned, result = self._fixture_exec_block(helper.body, assignments, helpers, helper_local)
                if not returned: raise ValueError("fixture helper has no return")
                return result
        raise ValueError(f"fixture expression unsupported: {type(node).__name__}")

    def _fixture_value_at_call(self, tree: ast.Module, call: ast.Call, helpers: dict[str, ast.FunctionDef], parent_map: dict[ast.AST, ast.AST]) -> Any:
        """BUILD235: replay pure preparation in order, never execute imports or target code."""
        local: dict[str, Any] = {}
        ancestors: set[ast.AST] = {call}
        current: ast.AST = call
        while current in parent_map:
            current = parent_map[current]
            ancestors.add(current)

        def invalidate(stmt: ast.stmt) -> None:
            names = {x.id for x in ast.walk(stmt) if isinstance(x, ast.Name) and isinstance(x.ctx, (ast.Store, ast.Del))}
            for node in ast.walk(stmt):
                if isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Attribute):
                        names.update(x.id for x in ast.walk(node.func.value) if isinstance(x, ast.Name))
                    for arg in node.args:
                        names.update(x.id for x in ast.walk(arg) if isinstance(x, ast.Name))
                if isinstance(node, ast.Subscript) and isinstance(node.ctx, (ast.Store, ast.Del)):
                    names.update(x.id for x in ast.walk(node.value) if isinstance(x, ast.Name))
            objects = {id(local[name]) for name in names if name in local and isinstance(local[name], (list, dict, set))}
            def contains(value: Any, seen: set[int]) -> bool:
                if id(value) in objects: return True
                if id(value) in seen: return False
                seen.add(id(value))
                children = value.values() if isinstance(value, dict) else value if isinstance(value, (list, tuple)) else ()
                return any(contains(child, seen) for child in children)
            for name, value in list(local.items()):
                if name != "__PF_STATIC_BUDGET__" and (name in names or contains(value, set())):
                    local[name] = _FIXTURE_UNRESOLVED

        def prepare(stmt: ast.stmt) -> None:
            if isinstance(stmt, (ast.Import, ast.ImportFrom, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Assert, ast.Pass)):
                return
            if isinstance(stmt, (ast.Assign, ast.AnnAssign, ast.Expr)) and any(
                isinstance(node, ast.Call) and ast.dump(node.func) == ast.dump(call.func)
                for node in ast.walk(stmt)
            ):
                for node in ast.walk(stmt):
                    if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
                        local[node.id] = _FIXTURE_UNRESOLVED
                return
            # Result variables cannot be reconstructed by static discovery. Target calls are
            # observed below; candidate/test code is never imported or invoked here.
            try:
                self._fixture_exec_block([stmt], {}, helpers, local)
            except Exception:
                invalidate(stmt)

        def descend(statements: list[ast.stmt]) -> Any:
            for stmt in statements:
                if stmt not in ancestors:
                    prepare(stmt)
                    continue
                if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    # Python locals shadow globals even before their first assignment.
                    for node in ast.walk(stmt):
                        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
                            local[node.id] = _FIXTURE_UNRESOLVED
                    for arg in (*stmt.args.posonlyargs, *stmt.args.args, *stmt.args.kwonlyargs):
                        local[arg.arg] = _FIXTURE_UNRESOLVED
                    return descend(stmt.body)
                if isinstance(stmt, ast.If):
                    branch = stmt.body if self._fixture_eval(stmt.test, {}, helpers, local) else stmt.orelse
                    if not any(child in ancestors for child in branch):
                        raise ValueError("fixture target is in an inactive branch")
                    return descend(branch)
                if isinstance(stmt, (ast.With, ast.AsyncWith, ast.Try)):
                    blocks = [stmt.body]
                    if isinstance(stmt, ast.Try):
                        blocks += [stmt.orelse, stmt.finalbody] + [handler.body for handler in stmt.handlers]
                    for block in blocks:
                        if any(child in ancestors for child in block): return descend(block)
                if isinstance(stmt, (ast.For, ast.AsyncFor, ast.While)):
                    raise ValueError("fixture target inside a loop requires explicit fixture evidence")
                # Freeze this call's input before any later alias mutation or reassignment.
                return json.loads(json.dumps(self._fixture_eval(call.args[0], {}, helpers, local), allow_nan=False))
            raise ValueError("fixture target preparation path not found")

        function_scope = any(isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) for node in ancestors)
        if function_scope:
            for stmt in tree.body:
                if stmt not in ancestors: prepare(stmt)
            # Global preparation already ran; only enter the containing function now.
            return descend([stmt for stmt in tree.body if stmt in ancestors])
        return descend(tree.body)

    def _persist_fixture_binding(self, brick_id: str, callable_name: str, fixture_rel: str, source_rel: str, source_kind: str, selection: dict[str, Any] | None = None) -> str:
        fixture = self.root / fixture_rel
        if not fixture.is_file():
            raise RuntimeInvocationError("FIXTURE_MISSING", f"fixture missing for {brick_id}: {fixture_rel}")
        try:
            value = json.loads(fixture.read_text(encoding="utf-8-sig"))
        except Exception as exc:
            raise RuntimeInvocationError("CONTRACT_MISMATCH", f"fixture is not valid JSON for {brick_id}: {fixture_rel}: {exc}") from exc
        schema = _json_contract_schema(value)
        schema_rel = f"foundry/runtime-contracts/{brick_id}.input-schema.json"
        write_json(self.root / schema_rel, schema)
        binding = {
            "schema": "portfolio-foundry.fixture-resolution.v1",
            "brick": brick_id,
            "consumer_brick": brick_id,
            "callable": callable_name,
            "fixture": fixture_rel,
            "fixture_source": source_rel,
            "source_kind": source_kind,
            "input_schema": schema_rel,
            "fixture_sha256": sha256_file(fixture),
            "fixture_value_sha256": sha256_json(value),
            "input_schema_sha256": sha256_json(schema),
            "stage9RunId": self.stage9_run_id or None,
        }
        if selection:
            binding["selection"] = selection
        self.fixture_resolutions[brick_id] = binding
        write_json(self.fixture_resolution_dir / f"{brick_id}.json", binding)
        return fixture_rel

    def _derive_fixture(self, brick_id: str, callable_name: str, tests_relative: str | None) -> str | None:
        fixture_rel = f"foundry/runtime-fixtures/{brick_id}.json"
        fixture = self.root / fixture_rel
        existing = fixture_rel if fixture.is_file() else None
        existing_value: Any = None
        existing_hash: str | None = None
        if existing:
            try:
                existing_value = json.loads(fixture.read_text(encoding="utf-8-sig"))
                existing_hash = sha256_json(existing_value)
            except Exception:
                # Do not let an invalid/stale fixture silently become runtime input. If current
                # test evidence can reconstruct a fixture we will replace it below; otherwise the
                # normal binding validation will fail closed.
                existing_hash = None

        if not tests_relative:
            return self._persist_fixture_binding(brick_id, callable_name, existing, fixture_rel, "existing-runtime-fixture") if existing else None
        tests = self.root / tests_relative
        if not tests.is_dir():
            return self._persist_fixture_binding(brick_id, callable_name, existing, fixture_rel, "existing-runtime-fixture") if existing else None

        # BUILD96: collect target-call evidence across contract/unit/integration tests before
        # selecting a fixture. Multi-mode bricks can legitimately call the same execute() with
        # different payload shapes; an existing runtime fixture is accepted only when current
        # target-call evidence confirms its exact value.
        preferred_names = ("payload", "base_payload", "sample", "input_data", "request", "data", "fixture")
        all_candidates: list[dict[str, Any]] = []
        parsed_tests: list[dict[str, Any]] = []
        target_calls_seen = 0

        for test_path in [tests / "test_contract.py", tests / "test_unit.py", tests / "test_integration.py"]:
            if not test_path.is_file():
                continue
            try:
                tree, _ = self._python_ast(test_path, brick_id, "fixture-discovery")
                if tree is None:
                    continue
                assignment_nodes: dict[str, ast.AST] = {}
                helpers = {x.name: x for x in tree.body if isinstance(x, ast.FunctionDef)}
                module_aliases: set[str] = set()
                module_factory_helpers = {
                    name for name, helper in helpers.items()
                    if any(isinstance(x, ast.Call) and isinstance(x.func, ast.Attribute) and x.func.attr == "module_from_spec" for x in ast.walk(helper))
                }
                for stmt in tree.body:
                    if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1 and isinstance(stmt.targets[0], ast.Name):
                        assignment_nodes[stmt.targets[0].id] = stmt.value
                        value = stmt.value
                        if isinstance(value, ast.Call) and isinstance(value.func, ast.Attribute) and value.func.attr == "module_from_spec":
                            module_aliases.add(stmt.targets[0].id)
                    elif isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name) and stmt.value is not None:
                        assignment_nodes[stmt.target.id] = stmt.value
                # BUILD149: Stage-8 pytest modules often load the candidate inside a test helper:
                #     core = load_core(); core.execute({...})
                # Discover those aliases statically instead of requiring a module_from_spec assignment
                # at module scope. No candidate code is executed during discovery.
                for stmt in ast.walk(tree):
                    if not isinstance(stmt, ast.Assign) or len(stmt.targets) != 1 or not isinstance(stmt.targets[0], ast.Name):
                        continue
                    value = stmt.value
                    if isinstance(value, ast.Call) and isinstance(value.func, ast.Name) and value.func.id in module_factory_helpers:
                        module_aliases.add(stmt.targets[0].id)

                parent_map: dict[ast.AST, ast.AST] = {}
                for parent in ast.walk(tree):
                    for child in ast.iter_child_nodes(parent):
                        parent_map[child] = parent

                def guarded_target_call(call_node: ast.Call) -> bool:
                    current: ast.AST | None = call_node
                    while current is not None and current in parent_map:
                        parent = parent_map[current]
                        if isinstance(parent, (ast.With, ast.AsyncWith)):
                            for item in parent.items:
                                expr = item.context_expr
                                if isinstance(expr, ast.Call):
                                    func = expr.func
                                    name = func.id if isinstance(func, ast.Name) else (func.attr if isinstance(func, ast.Attribute) else "")
                                    if name == "raises":
                                        return True
                        # Generated negative-contract probes use try/except. Keep them as diagnostics
                        # but do not allow them to become the Stage-9 smoke input.
                        if isinstance(parent, ast.Try):
                            return True
                        current = parent
                    return False

                parsed_tests.append({"path": test_path, "assignments": assignment_nodes, "helpers": helpers})
                test_rel = test_path.relative_to(self.root).as_posix()
                test_kind = test_path.stem.removeprefix("test_")
                for call in [x for x in ast.walk(tree) if isinstance(x, ast.Call)]:
                    direct = isinstance(call.func, ast.Name) and call.func.id == callable_name
                    module_call = (isinstance(call.func, ast.Attribute) and call.func.attr == callable_name
                                   and isinstance(call.func.value, ast.Name) and call.func.value.id in module_aliases)
                    if not (direct or module_call) or not call.args:
                        continue
                    target_calls_seen += 1
                    arg = call.args[0]
                    try:
                        value = self._fixture_value_at_call(tree, call, helpers, parent_map)
                    except Exception:
                        continue
                    arg_name = arg.id if isinstance(arg, ast.Name) else None
                    all_candidates.append({
                        "value": value,
                        "hash": sha256_json(value),
                        "argument_name": arg_name,
                        "line": getattr(call, "lineno", None),
                        "expression": type(arg).__name__,
                        "test_path": test_rel,
                        "test_kind": test_kind,
                        "guarded": guarded_target_call(call),
                    })
            except RuntimeInvocationError:
                raise
            except Exception:
                continue

        def candidate_evidence(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
            keys = ("hash", "argument_name", "line", "expression", "test_path", "test_kind", "guarded")
            return [{k: row.get(k) for k in keys} for row in rows]

        # Highest-confidence BUILD96 path: a previously materialized runtime fixture may
        # disambiguate a genuinely multi-mode callable, but only when the *current* tests prove
        # that exact JSON value is still passed to the target callable. To avoid blessing an old
        # negative fixture, confirmation must be strong: integration evidence, a canonical named
        # target argument, or the fixture being the only distinct current target-call value.
        if existing and existing_hash:
            matching = [row for row in all_candidates if not row.get("guarded") and row.get("hash") == existing_hash]
            unique_hashes = {str(row.get("hash")) for row in all_candidates}
            strong_matching = [
                row for row in matching
                if row.get("test_kind") == "integration" or row.get("argument_name") in preferred_names
            ]
            matching_test_kinds = {str(row.get("test_kind") or "") for row in matching if row.get("test_kind")}
            # BUILD96 contract: an existing runtime fixture is not trusted just because the file
            # exists; it must exactly match at least one *current* target-call argument. Once that
            # equality is proven, the existing fixture is a deterministic mode selector for a
            # multi-mode callable. Input-contract validation still runs afterwards and remains
            # fail-closed if the confirmed fixture is no longer valid for the brick.
            existing_confirmed = bool(matching)
            if existing_confirmed:
                selection = {
                    "reason": "EXISTING_FIXTURE_CONFIRMED_BY_TARGET_CALL",
                    "selected_hash": existing_hash,
                    "selected_argument_name": next((row.get("argument_name") for row in strong_matching if row.get("argument_name")), None),
                    "selected_source_line": next((row.get("line") for row in strong_matching), matching[0].get("line")),
                    "selected_test_path": next((row.get("test_path") for row in strong_matching), matching[0].get("test_path")),
                    "confirmation_kinds": sorted({str(row.get("test_kind") or "") for row in matching}),
                    "matching_candidate_count": len(matching),
                    "candidate_count": len(all_candidates),
                    "candidate_hashes": sorted(unique_hashes),
                    "candidates": candidate_evidence(all_candidates),
                }
                source_rel = str(selection.get("selected_test_path") or fixture_rel)
                return self._persist_fixture_binding(
                    brick_id, callable_name, fixture_rel, source_rel,
                    "existing-runtime-fixture-confirmed-by-target-call", selection,
                )

        # BUILD95 rule retained: a canonical named fixture actually passed to the target
        # callable outranks deliberate negative/mutated calls. BUILD96 applies it across all
        # available test files rather than failing inside the first multi-mode test file.
        canonical = [row for row in all_candidates if not row.get("guarded") and row.get("argument_name") in preferred_names]
        canonical_unique = {str(row["hash"]): row for row in canonical}
        # BUILD225: a generated brick may legitimately use the same canonical variable name
        # (usually `payload`) for different PASS CONTRACT/INTEGRATION scenarios.  Multiple
        # canonical hashes across files are therefore not an immediate contract failure.  Keep
        # the single-canonical fast path, but defer multi-canonical resolution to the sealed
        # Stage-8 PASS-test selector below.  If no proven PASS call can resolve it, we still
        # fail closed with the original CONTRACT_MISMATCH after that selector.
        if len(canonical_unique) == 1:
            selected = next(iter(canonical_unique.values()))
            value = selected["value"]
            write_json(fixture, value)
            selection = {
                "reason": "CANONICAL_NAMED_TARGET_ARGUMENT",
                "selected_argument_name": selected.get("argument_name"),
                "selected_source_line": selected.get("line"),
                "selected_test_path": selected.get("test_path"),
                "selected_hash": selected.get("hash"),
                "candidate_count": len(all_candidates),
                "candidate_hashes": sorted({str(row["hash"]) for row in all_candidates}),
                "candidates": candidate_evidence(all_candidates),
            }
            return self._persist_fixture_binding(
                brick_id, callable_name, fixture_rel, str(selected.get("test_path") or tests_relative),
                "canonical-target-call-argument", selection,
            )

        # BUILD149: a sealed PASS Stage-8 test is direct proof that an unguarded target-call
        # payload in that exact test file is executable. Use the smallest deterministic smoke
        # payload from the strongest available PASS test kind before treating legitimate
        # multi-mode execute() calls as ambiguous. This keeps negative probes (try/pytest.raises)
        # out of the runtime fixture and still fails closed when no proven positive call exists.
        impl = self.implementation_by_id.get(brick_id) or {}
        test_receipts = {
            str(row.get("kind") or "").upper(): str(row.get("status") or "").upper()
            for row in impl.get("tests", []) if isinstance(row, dict)
        }
        for test_kind, receipt_kind in (("contract", "CONTRACT"), ("unit", "UNIT"), ("integration", "INTEGRATION")):
            if test_receipts.get(receipt_kind) != "PASS":
                continue
            proven_rows = [row for row in all_candidates if row.get("test_kind") == test_kind and not row.get("guarded")]
            if not proven_rows:
                continue
            by_hash: dict[str, dict[str, Any]] = {}
            for row in proven_rows:
                token = str(row.get("hash") or "")
                current = by_hash.get(token)
                if current is None or int(row.get("line") or 10**9) < int(current.get("line") or 10**9):
                    by_hash[token] = row
            def smoke_rank(row: dict[str, Any]) -> tuple[int, int, str]:
                try:
                    compact = json.dumps(row.get("value"), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                except Exception:
                    compact = repr(row.get("value"))
                return (len(compact), int(row.get("line") or 10**9), str(row.get("hash") or ""))
            selected = min(by_hash.values(), key=smoke_rank)
            value = selected["value"]
            write_json(fixture, value)
            selection = {
                "reason": "V030_PASS_TEST_SMOKE_ARGUMENT",
                "proof_test_kind": receipt_kind,
                "selected_argument_name": selected.get("argument_name"),
                "selected_source_line": selected.get("line"),
                "selected_test_path": selected.get("test_path"),
                "selected_hash": selected.get("hash"),
                "candidate_count": len(all_candidates),
                "eligible_candidate_count": len(proven_rows),
                "candidate_hashes": sorted({str(row.get("hash")) for row in all_candidates}),
                "candidates": candidate_evidence(all_candidates),
            }
            return self._persist_fixture_binding(
                brick_id, callable_name, fixture_rel, str(selected.get("test_path") or tests_relative),
                f"v030-pass-{test_kind}-smoke-argument", selection,
            )

        # BUILD225: only after sealed PASS evidence had a chance to select a deterministic
        # smoke payload does a multi-canonical set remain a real unresolved ambiguity.
        if len(canonical_unique) > 1:
            raise RuntimeInvocationError(
                "CONTRACT_MISMATCH",
                f"ambiguous canonical fixture candidates for {brick_id}::{callable_name} in {tests_relative}",
                {
                    "brick_id": brick_id, "callable": callable_name,
                    "tests_relative": tests_relative,
                    "candidate_hashes": sorted(canonical_unique),
                    "existing_fixture_hash": existing_hash,
                    "candidates": candidate_evidence(all_candidates),
                },
            )

        unique = {str(row["hash"]): row for row in all_candidates if not row.get("guarded")}
        if len(unique) > 1:
            raise RuntimeInvocationError(
                "CONTRACT_MISMATCH",
                f"ambiguous fixture candidates for {brick_id}::{callable_name} in {tests_relative}",
                {
                    "brick_id": brick_id, "callable": callable_name,
                    "tests_relative": tests_relative,
                    "candidate_hashes": sorted(unique),
                    "existing_fixture_hash": existing_hash,
                    "existing_fixture_confirmed": False,
                    "target_calls_seen": target_calls_seen,
                    "candidates": candidate_evidence(all_candidates),
                },
            )
        if len(unique) == 1:
            selected = next(iter(unique.values()))
            value = selected["value"]
            write_json(fixture, value)
            selection = {
                "reason": "UNIQUE_TARGET_ARGUMENT",
                "selected_argument_name": selected.get("argument_name"),
                "selected_source_line": selected.get("line"),
                "selected_test_path": selected.get("test_path"),
                "selected_hash": selected.get("hash"),
                "candidate_count": len(all_candidates),
                "candidates": candidate_evidence(all_candidates),
            }
            return self._persist_fixture_binding(
                brick_id, callable_name, fixture_rel, str(selected.get("test_path") or tests_relative),
                "unique-target-call-argument", selection,
            )

        if target_calls_seen:
            raise RuntimeInvocationError(
                "CONTRACT_MISMATCH",
                f"current target-call fixture could not be safely reconstructed for {brick_id}::{callable_name}",
                {"target_calls_seen": target_calls_seen, "existing_fixture_confirmed": False},
            )

        # Compatibility fallback applies only when no target-call argument could be evaluated.
        # Prefer named assignments from parsed tests. Existing fixtures remain a last-resort
        # compatibility path only when there is no evaluable current target-call evidence.
        for parsed in parsed_tests:
            assignment_nodes = parsed["assignments"]
            helpers = parsed["helpers"]
            test_path = parsed["path"]
            for preferred in preferred_names:
                if preferred in assignment_nodes:
                    try:
                        value = self._fixture_eval(assignment_nodes[preferred], assignment_nodes, helpers)
                    except Exception:
                        continue
                    write_json(fixture, value)
                    return self._persist_fixture_binding(
                        brick_id, callable_name, fixture_rel, test_path.relative_to(self.root).as_posix(),
                        f"named-assignment:{preferred}",
                        {
                            "reason": "NAMED_ASSIGNMENT_FALLBACK",
                            "selected_argument_name": preferred,
                            "candidate_count": 0,
                            "target_calls_seen": target_calls_seen,
                        },
                    )
        if existing:
            return self._persist_fixture_binding(
                brick_id, callable_name, existing, fixture_rel,
                "existing-runtime-fixture-no-evaluable-target-evidence",
                {
                    "reason": "EXISTING_FIXTURE_NO_EVALUABLE_TARGET_EVIDENCE",
                    "selected_hash": existing_hash,
                    "candidate_count": 0,
                    "target_calls_seen": target_calls_seen,
                },
            )
        return None


    def _is_supplemental_vacancy_proof_target(self, node: dict[str, Any], impl: dict[str, Any]) -> bool:
        capability = str(impl.get("capability") or node.get("displayName") or node.get("capability") or "").strip().casefold()
        return bool(capability and capability in self.supplemental_proof_capabilities)

    def _v030_proof_receipt_descriptor(self, node: dict[str, Any], brick_id: str, impl: dict[str, Any]) -> dict[str, Any] | None:
        """Reuse a sealed v0.30 proof for supplemental vacancy-proof nodes instead of rerunning the proof runtime in v0.31."""
        if str(impl.get("status") or "").upper() != "PASS":
            self.proof_reuse_errors[brick_id] = "v0.30 capability status is not PASS"
            return None
        fingerprint = str(impl.get("implementationFingerprint") or "")
        if not fingerprint:
            self.proof_reuse_errors[brick_id] = "v0.30 implementation fingerprint is missing"
            return None
        tests = {str(x.get("kind") or "").upper(): str(x.get("status") or "").upper() for x in impl.get("tests", []) if isinstance(x, dict)}
        required = ("UNIT", "CONTRACT", "INTEGRATION")
        if any(tests.get(kind) != "PASS" for kind in required):
            self.proof_reuse_errors[brick_id] = "v0.30 UNIT/CONTRACT/INTEGRATION receipt is incomplete"
            return None
        evidence_relative = str(impl.get("evidenceRelativePath") or f"evidence/v030/{brick_id}").strip("/")
        if not (self.root / evidence_relative).is_dir():
            self.proof_reuse_errors[brick_id] = f"v0.30 evidence directory is missing: {evidence_relative}"
            return None
        source_relative = str(impl.get("sourceRelativePath") or f"src/bricks/{brick_id}").strip("/")
        relative = f"{source_relative}/core.py"
        path = self.root / relative
        if not path.is_file():
            self.proof_reuse_errors[brick_id] = f"proven v0.30 source is missing: {relative}"
            return None
        actual_sha = sha256_file(path)
        expected_sha = self._manifest_expected_hash(relative, brick_id) or actual_sha
        if expected_sha.lower() != actual_sha.lower():
            self.proof_reuse_errors[brick_id] = f"proven v0.30 source changed after proof: {relative}"
            return None
        saved_ms = sum(int(x.get("durationMs") or 0) for x in impl.get("tests", []) if isinstance(x, dict) and str(x.get("status") or "").upper() == "PASS")
        output_contract = str(impl.get("outputContract") or node.get("outputContract") or node.get("declaredContract") or "")
        return {
            "schema": RUNTIME_SCHEMA,
            "target_brick_id": brick_id,
            "strategy": str(node.get("strategy") or "UNKNOWN"),
            "runtime_profile": "v030-proof-receipt",
            "resolution": "V030_PROOF_RECEIPT_REUSE",
            "entrypoint": {"kind": "v030-proof-receipt", "file": relative, "callable": "reuse_v030_proof_receipt"},
            "arguments": {"mode": "none"},
            "input": {"contract": str(impl.get("inputContract") or node.get("inputContract") or ""), "smoke_fixture": None},
            "output": {"validation": "mapping", "contract": output_contract},
            "execution": {"working_directory": "candidate-root", "timeout_seconds": 0, "network": False, "shell": False, "execute_capability": False},
            "integrity": {"source_sha256": expected_sha},
            "provenance": {
                "implementation_provider": str(impl.get("provider") or ""),
                "v030_capability_fingerprint": fingerprint,
                "provider_used_for_dispatch": False,
                "proof_source": "capability-implementation-proof.json",
            },
            "proof": {
                "status": "PASS",
                "stage": "v0.30",
                "capability": str(impl.get("capability") or ""),
                "implementation_fingerprint": fingerprint,
                "evidence_relative_path": evidence_relative,
                "tests": list(required),
                "saved_execution_ms": saved_ms,
            },
        }

    def _reuse_v030_proof_receipt(self, descriptor: dict[str, Any]) -> tuple[str, Any, dict[str, Any]]:
        started = time.perf_counter()
        brick_id = str(descriptor.get("target_brick_id") or "")
        entry = descriptor.get("entrypoint") or {}
        relative = str(entry.get("file") or "")
        path = self.invoker._resolve_file(relative)
        actual_sha = sha256_file(path)
        expected_sha = str((descriptor.get("integrity") or {}).get("source_sha256") or "")
        if not expected_sha or actual_sha.lower() != expected_sha.lower():
            raise RuntimeInvocationError("RUNTIME_SOURCE_STALE", f"v0.30 proven source fingerprint changed: {relative}", {"expected": expected_sha, "actual": actual_sha})
        proof = descriptor.get("proof") or {}
        evidence_relative = str(proof.get("evidence_relative_path") or "")
        if str(proof.get("status") or "").upper() != "PASS" or not evidence_relative or not (self.root / evidence_relative).is_dir():
            raise RuntimeInvocationError("V030_PROOF_RECEIPT_INVALID", f"v0.30 proof receipt is no longer reusable for {brick_id}")
        output_contract = str((descriptor.get("output") or {}).get("contract") or "")
        if not output_contract:
            raise RuntimeInvocationError("V030_PROOF_RECEIPT_INVALID", f"v0.30 proof receipt output contract is missing for {brick_id}")
        output = {
            "contract": output_contract,
            "payload": {
                "proof_status": "PASS",
                "brick_id": brick_id,
                "capability": proof.get("capability"),
                "implementation_fingerprint": proof.get("implementation_fingerprint"),
                "evidence_relative_path": evidence_relative,
                "reused_from_stage": "v0.30",
            },
            "runtime_reuse": True,
        }
        evidence = {
            "resolution": "V030_PROOF_RECEIPT_REUSE",
            "provider": (descriptor.get("provenance") or {}).get("implementation_provider"),
            "provider_used_for_dispatch": False,
            "entrypoint": "proof:v0.30",
            "executed": False,
            "reused_receipt": True,
            "source_sha256": actual_sha,
            "v030_capability_fingerprint": proof.get("implementation_fingerprint"),
            "saved_execution_ms": int(proof.get("saved_execution_ms") or 0),
            "duration_ms": int((time.perf_counter() - started) * 1000),
            "output_sha256": sha256_json(output),
        }
        return "reuse_v030_proof_receipt", output, evidence

    def _write_descriptor(self, brick_id: str, descriptor: dict[str, Any]) -> None:
        self.runtime_invocations[brick_id] = descriptor
        write_json(self.invocation_dir / f"{brick_id}.json", descriptor)

    def _persist_runtime_discovery_failure(self, exc: RuntimeInvocationError) -> None:
        self.foundry.mkdir(parents=True, exist_ok=True)
        self.evidence_v031.mkdir(parents=True, exist_ok=True)
        details = dict(exc.details or {})
        brick_id = str(details.get("brick_id") or details.get("node_id") or "runtime-discovery")
        nodes = list(getattr(self, "_discovery_inventory", []) or [])
        if brick_id and not any(str(row.get("node_id") or row.get("target_brick_id") or "") == brick_id for row in nodes):
            nodes.append({
                "node_id": brick_id,
                "target_brick_id": brick_id,
                "resolution": "DISCOVERY_FAILED",
                "entrypoint": None,
                "provider": None,
                "provider_used_for_dispatch": False,
                "status": exc.code,
                "reason": str(exc),
                "failure_details": details,
            })
        failure = {"code": exc.code, "message": str(exc), "node": brick_id, "details": details}
        payload = {
            "schema": "portfolio-foundry.runtime-invocation-inventory.v2",
            "stage9RunId": self.stage9_run_id or None,
            "status": "FAIL",
            "nodes": nodes,
            "failure": failure,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        diagnostics = {
            "schema": "portfolio-foundry.runtime-discovery-diagnostics.v2",
            "stage9RunId": self.stage9_run_id or None,
            "status": "FAIL",
            "attempts": self.discovery_diagnostics,
            "failure": failure,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        for base in (self.foundry, self.evidence_v031):
            write_json(base / "runtime-invocation-inventory.json", payload)
            write_json(base / "runtime-discovery-diagnostics.json", diagnostics)
        fixture_resolution = {
            "schema": "portfolio-foundry.fixture-resolution-set.v1",
            "stage9RunId": self.stage9_run_id or None,
            "status": "FAIL",
            "bindings": [self.fixture_resolutions[key] for key in sorted(self.fixture_resolutions)],
            "failure": failure,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        contract_resolution = {
            "schema": "portfolio-foundry.runtime-contract-resolution.v1",
            "stage9RunId": self.stage9_run_id or None,
            "status": "FAIL",
            "nodes": [{
                "brick": key,
                "callable": str((value.get("entrypoint") or {}).get("callable") or ""),
                "input_contract": str((value.get("input") or {}).get("contract") or ""),
                "output_contract": str((value.get("output") or {}).get("contract") or ""),
                "runtime_output_contract": str((value.get("output") or {}).get("runtime_contract") or ""),
                "graph_output_contract": str((value.get("output") or {}).get("graph_contract") or (value.get("output") or {}).get("contract") or ""),
                "contract_bridge": (value.get("output") or {}).get("bridge"),
                "input_schema": (value.get("input") or {}).get("schema"),
                "fixture_sha256": (value.get("input") or {}).get("fixture_sha256"),
            } for key, value in sorted(self.runtime_invocations.items())],
            "failure": failure,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        for base in (self.foundry, self.evidence_v031):
            write_json(base / "fixture-resolution.json", fixture_resolution)
            write_json(base / "contract-resolution.json", contract_resolution)

    def _build_runtime_invocation_inventory(self) -> None:
        self.invocation_dir.mkdir(parents=True, exist_ok=True)
        self.fixture_dir.mkdir(parents=True, exist_ok=True)
        self.contract_dir.mkdir(parents=True, exist_ok=True)
        self.fixture_resolution_dir.mkdir(parents=True, exist_ok=True)
        self.evidence_v031.mkdir(parents=True, exist_ok=True)
        inventory: list[dict[str, Any]] = []
        self._discovery_inventory = inventory
        for node in self.graph.get("nodes", []):
            brick_id = self._node_id(node)
            if not brick_id:
                continue
            impl = self.implementation_by_id.get(brick_id)
            adapter = self.adapter_by_id.get(brick_id)
            descriptor: dict[str, Any] | None = None
            resolution = "REUSE_BINDING_VERIFICATION"
            if adapter:
                relative = f"src/adapters/{brick_id}/core.py"
                path = self.root / relative
                functions = self._public_functions(path, brick_id, "adapter-discovery") if path.is_file() else []
                if any(name == "adapt" for name, _ in functions):
                    descriptor = self._descriptor(node, brick_id, relative, "adapt", "value", "EXPLICIT_GRAPH_ADAPTER", "contract-closure-adapter-v1", None, "mapping")
                else:
                    resolution = "UNRESOLVED"
            elif impl:
                if self._is_supplemental_vacancy_proof_target(node, impl):
                    # BUILD74: Stage 9 consumes the sealed v0.30 proof as a trusted graph input. These
                    # supplemental vacancy-proof targets are evidence producers, not app-time business
                    # transformations; rerunning HDFS/Hive/Excel here duplicates Stage 8 and can cost minutes.
                    descriptor = self._v030_proof_receipt_descriptor(node, brick_id, impl)
                    if descriptor is None:
                        resolution = "V030_PROOF_RECEIPT_INVALID"
                else:
                    source_relative = str(impl.get("sourceRelativePath") or f"src/bricks/{brick_id}").strip("/")
                    relative = f"{source_relative}/core.py"
                    path = self.root / relative
                    functions = self._public_functions(path, brick_id) if path.is_file() else []
                    if any(name == "execute" for name, _ in functions):
                        fixture = self._derive_fixture(brick_id, "execute", str(impl.get("testsRelativePath") or ""))
                        descriptor = self._descriptor(node, brick_id, relative, "execute", "payload", "GENERIC_RUNTIME_CONTRACT", str(impl.get("provider") or ""), fixture, "json-compatible")
                    else:
                        provider = str(impl.get("provider") or "")
                        # Legacy deterministic implementations are READY only when a real compatibility shim exists.
                        resolution = "LEGACY_PROVIDER_SHIM" if provider in LEGACY_PROVIDER_SHIMS else "UNRESOLVED"
            else:
                candidate_relative = str(node.get("candidateRelativePath") or "").strip("/")
                relative = f"{candidate_relative}/core.py" if candidate_relative else ""
                path = self.root / relative if relative else self.root / "__missing__"
                functions = self._public_functions(path, brick_id) if path.is_file() else []
                # Safe legacy REUSE backfill: execute only an explicitly discoverable zero-argument callable.
                zero_arg = next(((name, required) for name, required in functions if name == "execute" and required == 0), None)
                if zero_arg is None:
                    zero_arg = next(((name, required) for name, required in functions if required == 0), None)
                if zero_arg is not None:
                    callable_name = zero_arg[0]
                    output_contract = str(node.get("outputContract") or node.get("declaredContract") or "")
                    descriptor = self._descriptor(node, brick_id, relative, callable_name, "none", "REUSE_RUNTIME_CONTRACT", "REUSE", None, "json-compatible")
                    if callable_name != "execute" and output_contract:
                        descriptor["result_wrapper"] = {"contract": output_contract, "payload_from": "return_value"}
            if descriptor is not None:
                self._write_descriptor(brick_id, descriptor)
                resolution = str(descriptor.get("resolution"))
                status = "READY" if resolution == "V030_PROOF_RECEIPT_REUSE" or descriptor.get("arguments", {}).get("mode") == "none" or descriptor.get("input", {}).get("smoke_fixture") or descriptor.get("arguments", {}).get("mode") == "value" else "RUNTIME_FIXTURE_UNAVAILABLE"
                entrypoint = "proof:v0.30" if resolution == "V030_PROOF_RECEIPT_REUSE" else f"{descriptor['entrypoint']['file']}::{descriptor['entrypoint']['callable']}"
                inventory.append({
                    "node_id": brick_id,
                    "target_brick_id": descriptor.get("target_brick_id"),
                    "resolution": resolution,
                    "entrypoint": entrypoint,
                    "provider": (descriptor.get("provenance") or {}).get("implementation_provider"),
                    "provider_used_for_dispatch": False,
                    "status": status,
                    "input_contract": str((descriptor.get("input") or {}).get("contract") or ""),
                    "output_contract": str((descriptor.get("output") or {}).get("contract") or ""),
                    "runtime_output_contract": str((descriptor.get("output") or {}).get("runtime_contract") or ""),
                    "graph_output_contract": str((descriptor.get("output") or {}).get("graph_contract") or (descriptor.get("output") or {}).get("contract") or ""),
                    "contract_bridge": (descriptor.get("output") or {}).get("bridge"),
                    "fixture_resolution": self.fixture_resolutions.get(brick_id),
                    "executed_capability": False if resolution == "V030_PROOF_RECEIPT_REUSE" else None,
                    "saved_execution_ms": (descriptor.get("proof") or {}).get("saved_execution_ms") if resolution == "V030_PROOF_RECEIPT_REUSE" else None,
                })
            else:
                provider = str((impl or {}).get("provider") or "")
                if resolution == "LEGACY_PROVIDER_SHIM" and provider in LEGACY_PROVIDER_SHIMS:
                    inventory.append({"node_id": brick_id, "target_brick_id": brick_id, "resolution": resolution, "entrypoint": None, "provider": provider, "provider_used_for_dispatch": True, "status": "READY"})
                elif resolution == "REUSE_BINDING_VERIFICATION" and str(node.get("candidateRelativePath") or "") and (self.root / str(node.get("candidateRelativePath"))).exists():
                    inventory.append({"node_id": brick_id, "target_brick_id": brick_id, "resolution": resolution, "entrypoint": None, "provider": "REUSE", "provider_used_for_dispatch": False, "status": "READY"})
                else:
                    unresolved_resolution = resolution if resolution == "V030_PROOF_RECEIPT_INVALID" else "UNRESOLVED"
                    unresolved_status = "V030_PROOF_RECEIPT_INVALID" if resolution == "V030_PROOF_RECEIPT_INVALID" else "RUNTIME_CONTRACT_MISSING"
                    inventory.append({"node_id": brick_id, "target_brick_id": brick_id, "resolution": unresolved_resolution, "entrypoint": None, "provider": provider or None, "provider_used_for_dispatch": False, "status": unresolved_status, "reason": self.proof_reuse_errors.get(brick_id)})
        payload = {"schema": "portfolio-foundry.runtime-invocation-inventory.v2", "stage9RunId": self.stage9_run_id or None, "status": "PASS" if all(x["status"] == "READY" for x in inventory) else "FAIL", "nodes": inventory, "created_at": datetime.now(timezone.utc).isoformat()}
        diagnostics = {"schema": "portfolio-foundry.runtime-discovery-diagnostics.v2", "stage9RunId": self.stage9_run_id or None, "status": "PASS" if all(x.get("parse_status") == "PASS" for x in self.discovery_diagnostics if x.get("error_code") != "PYTHON_SOURCE_MISSING") else "FAIL", "attempts": self.discovery_diagnostics, "created_at": datetime.now(timezone.utc).isoformat()}
        write_json(self.foundry / "runtime-invocation-inventory.json", payload)
        write_json(self.evidence_v031 / "runtime-invocation-inventory.json", payload)
        write_json(self.foundry / "runtime-discovery-diagnostics.json", diagnostics)
        write_json(self.evidence_v031 / "runtime-discovery-diagnostics.json", diagnostics)
        fixture_resolution = {
            "schema": "portfolio-foundry.fixture-resolution-set.v1",
            "stage9RunId": self.stage9_run_id or None,
            "status": "PASS" if all((x.get("arguments") or {}).get("mode") != "payload" or x.get("target_brick_id") in self.fixture_resolutions for x in self.runtime_invocations.values()) else "FAIL",
            "bindings": [self.fixture_resolutions[key] for key in sorted(self.fixture_resolutions)],
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        contract_resolution = {
            "schema": "portfolio-foundry.runtime-contract-resolution.v1",
            "stage9RunId": self.stage9_run_id or None,
            "status": "PASS",
            "nodes": [{
                "brick": key,
                "callable": str((value.get("entrypoint") or {}).get("callable") or ""),
                "input_contract": str((value.get("input") or {}).get("contract") or ""),
                "output_contract": str((value.get("output") or {}).get("contract") or ""),
                "runtime_output_contract": str((value.get("output") or {}).get("runtime_contract") or ""),
                "graph_output_contract": str((value.get("output") or {}).get("graph_contract") or (value.get("output") or {}).get("contract") or ""),
                "contract_bridge": (value.get("output") or {}).get("bridge"),
                "input_schema": (value.get("input") or {}).get("schema"),
                "fixture_sha256": (value.get("input") or {}).get("fixture_sha256"),
            } for key, value in sorted(self.runtime_invocations.items())],
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        write_json(self.foundry / "fixture-resolution.json", fixture_resolution)
        write_json(self.evidence_v031 / "fixture-resolution.json", fixture_resolution)
        write_json(self.foundry / "contract-resolution.json", contract_resolution)
        write_json(self.evidence_v031 / "contract-resolution.json", contract_resolution)

    def _source_intrinsic_output_contract(self, relative: str) -> str:
        """Resolve the brick's intrinsic runtime result contract without executing candidate code.

        BUILD152: generated/adapted bricks do not always publish OUTPUT_CONTRACT as a
        module constant.  Stage 8 can nevertheless prove a stable intrinsic contract by
        returning a literal ``{"contract": "foundry...."}`` and asserting that value in
        its PASS contract test.  Stage 9 must discover that intrinsic contract and bridge
        it to the graph-level semantic contract instead of misclassifying a valid result
        as CONTRACT_MISMATCH.

        Discovery is deliberately static and fail-closed:
          1. explicit module constants win;
          2. a single literal contract returned by the runtime callable is accepted;
          3. a single contract asserted by a Stage-8 PASS contract test is accepted;
          4. ambiguity returns an empty string so the normal strict checks remain active.
        """
        path = self.root / relative
        if not path.is_file():
            return ""
        try:
            module = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
        except Exception as exc:
            self.discovery_diagnostics.append({
                "phase": "RUNTIME_CONTRACT_DISCOVERY", "source": relative,
                "parse_status": "FAIL", "error_code": "CONTRACT_SOURCE_PARSE_FAILED",
                "detail": f"{type(exc).__name__}: {exc}",
            })
            return ""

        def const_string(node: ast.AST | None) -> str:
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                return node.value.strip()
            return ""

        preferred = {"RUNTIME_OUTPUT_CONTRACT", "OUTPUT_CONTRACT", "CONTRACT"}
        module_constants: dict[str, str] = {}
        for stmt in module.body:
            name = None
            value = None
            if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1 and isinstance(stmt.targets[0], ast.Name):
                name = stmt.targets[0].id
                value = stmt.value
            elif isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                name = stmt.target.id
                value = stmt.value
            literal = const_string(value)
            if name and literal:
                module_constants[name] = literal
            if name in preferred and literal:
                self.discovery_diagnostics.append({
                    "phase": "RUNTIME_CONTRACT_DISCOVERY", "source": relative,
                    "parse_status": "PASS", "mode": "MODULE_CONSTANT", "contract": literal,
                })
                return literal

        def resolve_string(node: ast.AST | None) -> str:
            literal = const_string(node)
            if literal:
                return literal
            if isinstance(node, ast.Name):
                return module_constants.get(node.id, "")
            return ""

        def dict_contract(node: ast.AST | None) -> str:
            if isinstance(node, ast.Dict):
                for key, value in zip(node.keys, node.values):
                    if const_string(key) == "contract":
                        return resolve_string(value)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "dict":
                for kw in node.keywords:
                    if kw.arg == "contract":
                        return resolve_string(kw.value)
            return ""

        # Prefer the conventional runtime callable.  If it is absent, scan all functions;
        # this also supports generated adapters whose public callable name differs.
        functions = [x for x in module.body if isinstance(x, (ast.FunctionDef, ast.AsyncFunctionDef))]
        execute_functions = [x for x in functions if x.name == "execute"] or functions
        returned_contracts: set[str] = set()
        for fn in execute_functions:
            for node in ast.walk(fn):
                if isinstance(node, ast.Return):
                    contract = dict_contract(node.value)
                    if contract.startswith("foundry."):
                        returned_contracts.add(contract)
        if len(returned_contracts) == 1:
            contract = next(iter(returned_contracts))
            self.discovery_diagnostics.append({
                "phase": "RUNTIME_CONTRACT_DISCOVERY", "source": relative,
                "parse_status": "PASS", "mode": "RETURN_LITERAL", "contract": contract,
            })
            return contract

        # PASS contract tests are executable proof from Stage 8.  Use only an unambiguous
        # literal equality assertion such as result["contract"] == "foundry....".
        parts = Path(relative).as_posix().split("/")
        brick_id = ""
        if "bricks" in parts:
            idx = parts.index("bricks")
            if idx + 1 < len(parts):
                brick_id = parts[idx + 1]
        elif "adapters" in parts:
            idx = parts.index("adapters")
            if idx + 1 < len(parts):
                brick_id = parts[idx + 1]
        proven_contract_test = False
        implementation = self.implementation_by_id.get(brick_id, {}) if brick_id else {}
        for receipt in implementation.get("tests", []) if isinstance(implementation, dict) else []:
            if str(receipt.get("kind") or "").upper() == "CONTRACT" and str(receipt.get("status") or "").upper() == "PASS":
                proven_contract_test = True
                break
        asserted_contracts: set[str] = set()
        tests_relative = str(implementation.get("testsRelativePath") or (f"tests/bricks/{brick_id}" if brick_id else ""))
        tests_dir = self.root / tests_relative if tests_relative else None
        if proven_contract_test and tests_dir and tests_dir.is_dir():
            for test_path in sorted(tests_dir.glob("*contract*.py")):
                try:
                    test_ast = ast.parse(test_path.read_text(encoding="utf-8-sig"), filename=str(test_path))
                except Exception:
                    continue
                for assertion in (n for n in ast.walk(test_ast) if isinstance(n, ast.Assert)):
                    compare = assertion.test
                    if not isinstance(compare, ast.Compare) or len(compare.ops) != 1 or not isinstance(compare.ops[0], ast.Eq) or len(compare.comparators) != 1:
                        continue
                    candidates = (compare.left, compare.comparators[0])
                    literal_values = [const_string(x) for x in candidates]
                    for literal in literal_values:
                        if literal.startswith("foundry."):
                            other = candidates[1] if literal == literal_values[0] else candidates[0]
                            is_contract_lookup = (
                                isinstance(other, ast.Subscript) and const_string(other.slice) == "contract"
                            ) or (
                                isinstance(other, ast.Call) and isinstance(other.func, ast.Attribute)
                                and other.func.attr == "get" and other.args and const_string(other.args[0]) == "contract"
                            )
                            if is_contract_lookup:
                                asserted_contracts.add(literal)
        if len(asserted_contracts) == 1:
            contract = next(iter(asserted_contracts))
            self.discovery_diagnostics.append({
                "phase": "RUNTIME_CONTRACT_DISCOVERY", "source": relative,
                "parse_status": "PASS", "mode": "STAGE8_PASS_CONTRACT_ASSERTION",
                "contract": contract, "brick": brick_id,
            })
            return contract

        if returned_contracts or asserted_contracts:
            self.discovery_diagnostics.append({
                "phase": "RUNTIME_CONTRACT_DISCOVERY", "source": relative,
                "parse_status": "PASS", "mode": "AMBIGUOUS_FAIL_CLOSED",
                "return_contracts": sorted(returned_contracts),
                "asserted_contracts": sorted(asserted_contracts),
                "brick": brick_id or None,
            })
        return ""

    def _descriptor(self, node: dict[str, Any], brick_id: str, relative: str, callable_name: str, argument_mode: str, resolution: str, provider: str, fixture: str | None, validation: str) -> dict[str, Any]:
        path = self.root / relative
        runtime_profile = str(node.get("runtimeProfile") or "python")
        spark_like = "spark" in runtime_profile.casefold() or "pyspark" in relative.casefold()
        heavy_import_modules = _source_heavy_import_modules(path) if path.is_file() else []
        heavy_import = bool(heavy_import_modules) or spark_like
        source_sha = sha256_file(path) if path.is_file() else ""
        expected = self._manifest_expected_hash(relative, brick_id)
        if expected and source_sha and expected != source_sha:
            # Keep the proven expected hash so invocation fails closed with RUNTIME_SOURCE_STALE.
            integrity_sha = expected
        else:
            integrity_sha = source_sha
        graph_output_contract = str(node.get("outputContract") or node.get("declaredContract") or "")
        runtime_output_contract = self._source_intrinsic_output_contract(relative)
        contract_bridge = None
        if graph_output_contract and runtime_output_contract and graph_output_contract != runtime_output_contract:
            contract_bridge = {
                "kind": "SEMANTIC_OUTPUT_CONTRACT_BRIDGE",
                "source_contract": runtime_output_contract,
                "target_contract": graph_output_contract,
                "payload_from": "return_value",
                "mode": "semantic-envelope",
            }
        return {
            "schema": RUNTIME_SCHEMA,
            "target_brick_id": brick_id,
            "strategy": str(node.get("strategy") or "UNKNOWN"),
            "runtime_profile": runtime_profile,
            "resolution": resolution,
            "entrypoint": {"kind": "python-function", "file": relative, "callable": callable_name},
            "arguments": {"mode": argument_mode},
            "input": {
                "contract": str(node.get("inputContract") or ""),
                "smoke_fixture": fixture,
                "schema": (self.fixture_resolutions.get(brick_id) or {}).get("input_schema"),
                "fixture_sha256": (self.fixture_resolutions.get(brick_id) or {}).get("fixture_sha256"),
                "fixture_source": (self.fixture_resolutions.get(brick_id) or {}).get("fixture_source"),
                "consumer_brick": brick_id,
            },
            "output": {
                "validation": validation,
                "contract": graph_output_contract,
                "graph_contract": graph_output_contract,
                "runtime_contract": runtime_output_contract,
                "bridge": contract_bridge,
            },
            "execution": {
                "working_directory": "candidate-root",
                "timeout_seconds": 30,
                "call_timeout_seconds": 30,
                "spark_call_timeout_seconds": 90 if spark_like else 30,
                "import_timeout_seconds": 90 if heavy_import else 30,
                "cold_start_timeout_seconds": 90 if spark_like else 30,
                "heavy_import_modules": heavy_import_modules,
                "cleanup_grace_seconds": 5,
                "network": False,
                "shell": False,
                "execution_model": "isolated-process-tree",
                "timeout_policy": "phase-aware-import-call",
            },
            "integrity": {"source_sha256": integrity_sha},
            "provenance": {"implementation_provider": provider, "v030_proof_fingerprint": self.implementation.get("implementationFingerprint", ""), "provider_used_for_dispatch": False},
        }

    def api_project(self) -> dict[str, Any]:
        nodes = self.graph.get("nodes", [])
        edges = self.graph.get("edges", [])
        return {"projectId": self.project_id, "vacancyId": self.foundation.get("vacancyId") or self.project_spec.get("vacancyId"), "vacancyTitle": self.project_spec.get("vacancyTitle"), "generatedBy": f"Portfolio Foundry {FACTORY_VERSION} {BUILD_TOKEN}", "factoryBuildToken": BUILD_TOKEN, "capabilities": len(nodes), "edges": len(edges), "routes": self.routes, "runtimeProfiles": self.runtime_profile.get("profiles", [])}

    def api_overview(self) -> dict[str, Any]:
        nodes = self.graph.get("nodes", [])
        strategies: dict[str, int] = {}
        for node in nodes:
            strategy = str(node.get("strategy", "UNKNOWN"))
            strategies[strategy] = strategies.get(strategy, 0) + 1
        return {"project": self.api_project(), "strategies": strategies, "implementationStatus": self.implementation.get("status", "UNKNOWN"), "implementationFingerprint": self.implementation.get("implementationFingerprint", ""), "demoScenario": self.demo_spec.get("id", "portfolio-demo"), "runtimeInvocationInventory": read_json(self.foundry / "runtime-invocation-inventory.json", {}), "generatedAt": datetime.now(timezone.utc).isoformat()}

    def api_capabilities(self) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for node in self.graph.get("nodes", []):
            fsid = self._node_id(node)
            impl = self.implementation_by_id.get(fsid)
            adapter = self.adapter_by_id.get(fsid)
            reuse_core = self.root / str(node.get("candidateRelativePath") or "") / "core.py"
            result.append({**node, "implementation": impl, "contractAdapter": adapter, "runtimeInvocation": self.runtime_invocations.get(fsid), "sourceInspectable": ((self.root / "src" / "bricks" / fsid / "core.py").is_file() or (self.root / "src" / "adapters" / fsid / "core.py").is_file() or reuse_core.is_file())})
        return result


    def api_graph(self) -> dict[str, Any]:
        inventory = read_json(self.foundry / "runtime-invocation-inventory.json", {"nodes": []})
        runtime_by_id = {str(x.get("node_id") or x.get("target_brick_id") or ""): x for x in inventory.get("nodes", []) if isinstance(x, dict)}
        promotion = read_json(self.foundry / "v033-promotion-link.json", {})
        promoted_versions = {str(x.get("id") or ""): str(x.get("version") or "") for x in promotion.get("promoted", []) if isinstance(x, dict)}
        demo_candidates = [self.root / "evidence" / "v032" / "runtime" / "runtime-demo-run.json", self.evidence_v031 / "runtime-demo-run.json"]
        existing_demo_paths = [x for x in demo_candidates if x.is_file()]
        demo_path = max(existing_demo_paths, key=lambda x: x.stat().st_mtime_ns) if existing_demo_paths else demo_candidates[-1]
        demo = read_json(demo_path, {})
        last_status = {str(x.get("node") or ""): str(x.get("status") or "") for x in demo.get("steps", []) if isinstance(x, dict)}
        nodes = []
        for index, node in enumerate(self.graph.get("nodes", []), start=1):
            brick_id = self._node_id(node)
            runtime = runtime_by_id.get(brick_id, {})
            path = str(node.get("candidateRelativePath") or "")
            resolution = str(runtime.get("resolution") or "")
            if resolution == "EXPLICIT_GRAPH_ADAPTER" or "/adapters/" in "/" + path.replace("\\", "/"):
                visual_kind = "ADAPTER"
            elif resolution.startswith("REUSE_") or str(node.get("strategy")) == "0":
                visual_kind = "REUSE"
            elif resolution == "GENERIC_RUNTIME_CONTRACT":
                visual_kind = "ADAPTER"
            else:
                visual_kind = "ADAPT"
            enriched = dict(node)
            enriched.update({
                "order": index,
                "runtime": runtime,
                "runtimeResolution": resolution or "UNRESOLVED",
                "runtimeProfile": runtime.get("runtime_profile") or runtime.get("profile") or "UNRESOLVED",
                "visualKind": visual_kind,
                "lastDemoStatus": last_status.get(brick_id, "NOT_RUN"),
                "promotedVersion": promoted_versions.get(brick_id),
                "closedLoopReuse": brick_id == str(promotion.get("closedLoopBrickId") or "") and str(promotion.get("closedLoopStatus") or "").upper() == "PASS",
            })
            nodes.append(enriched)
        return {
            "schema": "portfolio-foundry.visual-live-graph.v1",
            "status": "PASS",
            "projectId": self.project_id,
            "nodes": nodes,
            "edges": self.graph.get("edges", []),
            "runtimeInventoryStatus": inventory.get("status", "UNKNOWN"),
            "demo": demo,
            "promotion": promotion,
            "generatedAt": datetime.now(timezone.utc).isoformat(),
        }

    def api_live_execution(self) -> dict[str, Any]:
        """BUILD120: project a truthful PRO-MAX view from the last real RUN DEMO.

        Graph edges describe architecture. step.inputSource describes what was *actually* supplied
        to the callable (UPSTREAM_OUTPUT, SMOKE_FIXTURE, checkpoint/proof reuse, etc.). The UI must
        never imply an upstream payload transfer when the demo executed the node against its own fixture.
        """
        demo_candidates = [
            self.root / "evidence" / "v032" / "runtime" / "runtime-demo-run.json",
            self.evidence_v031 / "runtime-demo-run.json",
        ]
        existing_demo_paths = [path for path in demo_candidates if path.is_file()]
        demo_path = max(existing_demo_paths, key=lambda path: path.stat().st_mtime_ns) if existing_demo_paths else demo_candidates[-1]
        demo = read_json(demo_path, {})
        edges = list(self.graph.get("edges", []))
        node_by_id = {self._node_id(node): node for node in self.graph.get("nodes", [])}
        rows: list[dict[str, Any]] = []
        for step in demo.get("steps", []) if isinstance(demo.get("steps"), list) else []:
            if not isinstance(step, dict):
                continue
            node_id = str(step.get("node") or "")
            runtime = step.get("runtime") if isinstance(step.get("runtime"), dict) else {}
            receipt: dict[str, Any] = {}
            receipt_rel = str(runtime.get("runtime_execution_evidence") or "")
            if receipt_rel:
                try:
                    receipt_path = resolve_stage9_evidence(self.root, self.evidence_v031, receipt_rel)
                    if receipt_path.is_file():
                        receipt = read_json(receipt_path, {})
                except ValueError:
                    pass
            incoming = [edge for edge in edges if isinstance(edge, dict) and str(edge.get("to") or "") == node_id]
            outgoing = [edge for edge in edges if isinstance(edge, dict) and str(edge.get("from") or "") == node_id]
            rows.append({
                **step,
                "nodeMeta": node_by_id.get(node_id, {}),
                "incomingEdges": incoming,
                "outgoingEdges": outgoing,
                "executionReceipt": receipt,
            })
        executed = [row for row in rows if str(row.get("status") or "").upper() == "PASS"]
        actual_upstream = [row for row in rows if str(row.get("inputSource") or "").upper() == "UPSTREAM_OUTPUT"]
        fixtures = [row for row in rows if "FIXTURE" in str(row.get("inputSource") or "").upper()]
        checkpoint_reuse = [row for row in rows if str(row.get("mode") or "").upper() == "CHECKPOINT_REUSE" or str(row.get("checkpoint") or "").upper() == "HIT"]
        fresh_executions = [row for row in rows if str(row.get("status") or "").upper() == "PASS" and "REUSE" not in str(row.get("mode") or "").upper() and str(row.get("checkpoint") or "").upper() != "HIT"]
        actual_inputs = [row for row in rows if row.get("input") is not None]
        no_inputs = [row for row in rows if str(row.get("inputSource") or "").upper() == "NONE"]
        total_duration = sum(int(row.get("durationMs") or (row.get("runtime") or {}).get("duration_ms") or 0) for row in rows if isinstance(row, dict))
        return {
            "schema": "portfolio-foundry.live-execution-view.v1",
            "status": "READY" if demo else "NOT_RUN",
            "projectId": self.project_id,
            "candidateId": self.candidate_id,
            "run": demo,
            "steps": rows,
            "summary": {
                "graphNodes": len(self.graph.get("nodes", [])),
                "graphEdges": len(edges),
                "passed": len(executed),
                "total": len(rows),
                "actualUpstreamTransfers": len(actual_upstream),
                "fixtureInputs": len(fixtures),
                "checkpointReuse": len(checkpoint_reuse),
                "freshExecutions": len(fresh_executions),
                "actualInputPayloads": len(actual_inputs),
                "noInputNodes": len(no_inputs),
                "captureMode": "FRESH_CAPTURE" if bool(demo.get("freshCapture")) else str(demo.get("checkpointMode") or "RESUMABLE"),
                "totalDurationMs": total_duration,
            },
            "truthNote": "Graph edges are architectural bindings; inputSource identifies the actual data source used by this RUN DEMO node.",
            "generatedAt": datetime.now(timezone.utc).isoformat(),
        }

    def api_life_scenario(self) -> dict[str, Any]:
        if self.life_scenario.get("schemaVersion") != "portfolio-foundry.life-scenario.v1":
            return {"status": "NOT_CONFIGURED", "error": "Life Scenario has not been materialized by Factory stage 14."}
        return {"status": "READY", "scenario": self.life_scenario, "projectId": self.project_id, "execution": "real-candidate-run-demo"}

    def api_case_portfolio(self) -> dict[str, Any]:
        if self.case_portfolio.get("schemaVersion") != "portfolio-foundry.case-portfolio.v1":
            return {"status": "NOT_CONFIGURED", "error": "Practical Case Portfolio has not been materialized by Factory stage 14."}
        cases = self.case_portfolio.get("cases", [])
        if len(cases) != 3:
            return {"status": "NOT_CONFIGURED", "error": "Practical Case Portfolio must contain exactly three cases."}
        return {"status": "READY", "portfolio": self.case_portfolio, "projectId": self.project_id, "execution": "real-candidate-run-demo"}

    def api_economic_effect(self) -> dict[str, Any]:
        if self.economic_effect.get("schemaVersion") != "portfolio-foundry.economic-effect.v1":
            return {"status": "NOT_CONFIGURED", "error": "Economic Effect has not been materialized by Factory stage 15."}
        assumptions = self.economic_effect.get("assumptions", [])
        brick_effects = self.economic_effect.get("brickEffects", [])
        if len(assumptions) != 9 or len(brick_effects) != len(self.graph.get("nodes", [])):
            return {"status": "NOT_CONFIGURED", "error": "Economic Effect model does not match the candidate graph."}
        return {
            "status": "READY",
            "model": self.economic_effect,
            "projectId": self.project_id,
            "calculation": "deterministic-candidate-runtime",
            "brandPolicy": "BRANDLESS",
            "doubleCountPolicy": "normalized-brick-attribution",
        }

    def api_evidence(self) -> dict[str, Any]:
        evidence = self.root / "evidence"
        files: list[dict[str, Any]] = []
        seen: set[Path] = set()
        for owner in (evidence, self.evidence_v031):
            if not owner.is_dir():
                continue
            for path in sorted(owner.rglob("*")):
                if not path.is_file():
                    continue
                if path.resolve() in seen:
                    continue
                seen.add(path.resolve())
                try:
                    rel = stage9_evidence_reference(self.root, self.evidence_v031, path)
                except ValueError:
                    continue
                if any(part.lower() in {".venv", ".runtime", ".vs"} for part in path.parts):
                    continue
                files.append({"path": rel, "bytes": path.stat().st_size})
                if len(files) >= 250:
                    break
            if len(files) >= 250:
                break
        return {"count": len(files), "files": files}

    def api_diagnostics(self) -> dict[str, Any]:
        # BUILD101: diagnostics is an HTTP health/readiness surface, not a dependency execution probe.
        # Cold-importing pandas/scipy/pyspark here made the default 4s smoke request time out before
        # /api/demo/run, so resumable checkpoints never had a chance to bootstrap/reuse.  PREFLIGHT
        # already proves the actual dependency closure.  Diagnostics therefore performs a side-effect-
        # free module availability lookup and reports whether a module is already loaded.
        optional: dict[str, str] = {}
        for module_name in self.runtime_profile.get("optionalModules", []):
            name = str(module_name).strip()
            if not name:
                continue
            try:
                if name in sys.modules:
                    optional[name] = "LOADED"
                else:
                    optional[name] = "AVAILABLE" if importlib.util.find_spec(name) is not None else "MISSING"
            except Exception as exc:
                optional[name] = f"UNKNOWN: {type(exc).__name__}"
        return {"status": "READY", "server": SERVER_VERSION, "python": sys.version.split()[0], "platform": platform.platform(), "executable": sys.executable, "projectRoot": str(self.root), "runtimeProfiles": self.runtime_profile.get("profiles", []), "optionalModules": optional, "dependencyProbe": "NON_BLOCKING_FIND_SPEC", "runtimeInvocationInventory": str(self.foundry / "runtime-invocation-inventory.json")}

    def brick(self, brick_id: str) -> dict[str, Any] | None:
        for capability in self.api_capabilities():
            if str(capability.get("fileSystemId") or capability.get("id")) == brick_id:
                return capability
        return None

    def source(self, brick_id: str) -> dict[str, Any]:
        node = self.brick(brick_id)
        if node is None:
            raise KeyError("brick not found")
        candidates = [self.root / "src" / "bricks" / brick_id / "core.py", self.root / "src" / "adapters" / brick_id / "core.py"]
        candidate_relative = str(node.get("candidateRelativePath") or "").strip("/")
        if candidate_relative:
            candidates.append(self.root / candidate_relative / "core.py")
        allowed_roots = [(self.root / "src" / "bricks").resolve(), (self.root / "src" / "adapters").resolve(), (self.root / "bricks").resolve()]
        for raw in candidates:
            path = raw.resolve()
            if path.is_file() and any(path == allowed or allowed in path.parents for allowed in allowed_roots):
                return {"brickId": brick_id, "path": path.relative_to(self.root).as_posix(), "source": safe_text(path), "status": "READY", "strategy": node.get("strategy"), "runtimeInvocation": self.runtime_invocations.get(brick_id)}
        return {"brickId": brick_id, "path": None, "source": "", "status": "NOT_AVAILABLE"}

    def demo_data(self) -> dict[str, Any]:
        return {"events": [{"session_id": "s1", "date": "2026-08-20T10:00:00+00:00", "user_id": "u1", "segment": "sports", "eligible": True, "delivered": True}, {"session_id": "s2", "date": "2026-08-20T10:02:00+00:00", "user_id": "u2", "segment": "sports", "eligible": True, "delivered": False}, {"session_id": "s3", "date": "2026-08-20T10:03:00+00:00", "user_id": "u3", "segment": "finance", "eligible": True, "delivered": True}], "sourceRequest": {"source": "ads-events", "owner": "data-platform", "consumer": "bi", "purpose": "portfolio demo", "dataset": "clickstream", "sla_minutes": 30, "freshness_minutes": 10}, "contract": {"producer": "ads-events", "consumer": "bi", "dataset_owner": "data-platform", "purpose": "portfolio demo", "entity_fields": ["session_id", "user_id"], "attribute_fields": ["segment", "date"], "pii_classification": "PERSONAL_DATA", "retention_days": 30, "legal_basis": "demo-consent", "dpo_approved": True, "security_approved": True, "sla_minutes": 30, "freshness_minutes": 10, "quality_gates": ["session_id_not_null", "freshness_lt_30m"]}, "transfer": {"producer": "ads-events", "consumer": "bi", "purpose": "portfolio demo", "legal_basis": "demo-consent", "fields": ["session_id", "user_id", "device_id", "segment"], "dpo_approved": True, "security_approved": True, "retention_days": 30}}

    def _execute_provider(self, provider: str, brick_id: str, data: dict[str, Any]) -> tuple[str, Any]:
        core = self.root / "src" / "bricks" / brick_id / "core.py"
        if not core.is_file():
            raise FileNotFoundError(f"implementation core missing: {core.relative_to(self.root).as_posix()}")
        module = import_module(core, f"portfolio_capability_{brick_id.replace('-', '_')}")
        if provider == "source-onboarding-v1": return "assess_source", module.assess_source(data["sourceRequest"])
        if provider == "data-contract-adapt-v1": return "validate_delivery_contract", module.validate_delivery_contract(data["contract"])
        if provider == "compliance-workflow-v1": return "evaluate_transfer_request", module.evaluate_transfer_request(data["transfer"])
        if provider == "pyspark-transform-v1": return "transform_records", {"rows": module.transform_records(data["events"]), "backend": module.runtime_backend()}
        if provider == "audience-reach-v1": return "analyze_segment_reach", module.analyze_segment_reach(data["events"])
        raise RuntimeInvocationError("RUNTIME_CONTRACT_MISSING", f"no runtime-invocation contract and no legacy v0.31 shim for provider {provider}")

    def run_demo(self, force_fresh: bool = False) -> dict[str, Any]:
        data = self.demo_data()
        steps: list[dict[str, Any]] = []
        nodes = list(self.graph.get("nodes", []))
        status = "PASS"
        last_output: Any = None
        graph_edges = [edge for edge in self.graph.get("edges", []) if isinstance(edge, dict)]
        incoming_by: dict[str, list[dict[str, Any]]] = {}
        outgoing_by: dict[str, list[dict[str, Any]]] = {}
        for edge in graph_edges:
            incoming_by.setdefault(str(edge.get("to") or ""), []).append(edge)
            outgoing_by.setdefault(str(edge.get("from") or ""), []).append(edge)
        # BUILD122: counters describe this exact RUN DEMO, not the lifetime of the server process.
        self.stage9_force_fresh = bool(force_fresh)
        self.stage9_checkpoint_decisions = []
        self.stage9_checkpoint_invalidations = []
        self.stage9_checkpoint_reused = 0
        self.stage9_checkpoint_written = 0
        self.stage9_checkpoint_bootstrapped = 0
        self.stage9_checkpoint_invalidated = 0
        self.stage9_resume_start_node = None
        self.stage9_checkpoint_fingerprints = {}
        if not force_fresh:
            self._checkpoint_bootstrap_previous_demo(nodes)
        for index, node in enumerate(nodes, start=1):
            brick_id = self._node_id(node)
            capability = str(node.get("displayName") or node.get("capability") or brick_id)
            self._stage9_live("RUNNING", f"Executing graph node {index}/{len(nodes)} · {capability}", node=brick_id, current=index-1, total=len(nodes), wait_reason="waiting for current brick / Python / Spark / JVM runtime")
            self._stage9_graph_event("EXECUTE_BRICK", "RUNNING", capability, node=brick_id, current=index-1, total=len(nodes))
            impl = self.implementation_by_id.get(brick_id)
            adapter = self.adapter_by_id.get(brick_id)
            descriptor = self.runtime_invocations.get(brick_id)
            node_started = time.perf_counter()
            actual_input: Any = None
            input_source = "NONE"
            try:
                provider_used_for_dispatch = False
                runtime_evidence: dict[str, Any] = {}
                if force_fresh:
                    cached_receipt = None
                    checkpoint_context = self._checkpoint_local_context(node, index, descriptor, impl, adapter)
                    checkpoint_reason = "FORCE_FRESH_CAPTURE"
                else:
                    cached_receipt, checkpoint_context, checkpoint_reason = self._checkpoint_try_reuse(node, index, descriptor, impl, adapter)
                if cached_receipt is not None:
                    self.stage9_checkpoint_reused += 1
                    output = cached_receipt.get("output")
                    last_output = output
                    self.stage9_checkpoint_fingerprints[brick_id] = str(cached_receipt.get("receiptFingerprint") or "")
                    mode = str(cached_receipt.get("mode") or "CHECKPOINT_REUSE")
                    action = str(cached_receipt.get("action") or "reuse_checkpoint")
                    runtime_evidence = {
                        "checkpoint_cache": "HIT",
                        "checkpoint_source_run_id": cached_receipt.get("sourceRunId"),
                        "checkpoint_receipt_fingerprint": cached_receipt.get("receiptFingerprint"),
                        "output_sha256": cached_receipt.get("outputSha256"),
                        "reused": True,
                    }
                    self._checkpoint_record_decision(brick_id, index, "REUSE", "CACHE_HIT", source_run_id=str(cached_receipt.get("sourceRunId") or "") or None)
                    actual_input = cached_receipt.get("input")
                    input_source = str(cached_receipt.get("inputSource") or "CHECKPOINT_HIT")
                    steps.append({"order": index, "node": brick_id, "capability": node.get("displayName") or node.get("capability"), "mode": "CHECKPOINT_REUSE", "action": action, "status": "PASS", "input": actual_input, "inputSource": input_source, "inputSha256": cached_receipt.get("inputSha256"), "output": output, "outputSha256": cached_receipt.get("outputSha256"), "runtime": runtime_evidence, "durationMs": int((time.perf_counter()-node_started)*1000), "incoming": incoming_by.get(brick_id, []), "outgoing": outgoing_by.get(brick_id, []), "providerUsedForDispatch": False, "checkpoint": "HIT"})
                    self._stage9_graph_event("CHECKPOINT_HIT", "PASS", f"{capability} reused verified checkpoint", node=brick_id, current=index, total=len(nodes), extra={"sourceRunId": cached_receipt.get("sourceRunId"), "receiptFingerprint": cached_receipt.get("receiptFingerprint")})
                    self._stage9_live("RUNNING", f"Checkpoint CACHE HIT · {capability}", node=brick_id, current=index, total=len(nodes), wait_reason=None)
                    continue
                if self.stage9_resume_start_node is None:
                    self.stage9_resume_start_node = brick_id
                self._checkpoint_record_decision(brick_id, index, "EXECUTE", checkpoint_reason)
                if descriptor is not None:
                    mode = str(descriptor.get("resolution") or "GENERIC_RUNTIME_CONTRACT")
                    if mode == "V030_PROOF_RECEIPT_REUSE":
                        action, output, runtime_evidence = self._reuse_v030_proof_receipt(descriptor)
                        actual_input = None
                        input_source = "V030_PROOF_RECEIPT"
                    else:
                        argument_mode = str((descriptor.get("arguments") or {}).get("mode") or "payload")
                        if argument_mode == "value":
                            source_contract = str((descriptor.get("input") or {}).get("contract") or (adapter or {}).get("sourceContract") or "")
                            if isinstance(last_output, dict) and (not source_contract or last_output.get("contract") in {None, source_contract}):
                                supplied = last_output
                                input_source = "UPSTREAM_OUTPUT"
                            else:
                                # BUILD85: an ingress adapter needs a real downstream smoke payload.
                                # Seed it from the next descriptor whose input contract matches this adapter output.
                                output_contract = str((descriptor.get("output") or {}).get("contract") or "")
                                seed_payload: Any = None
                                seed_fixture: str | None = None
                                for future in nodes[index:]:
                                    future_id = self._node_id(future)
                                    future_descriptor = self.runtime_invocations.get(future_id)
                                    if not future_descriptor:
                                        continue
                                    future_input = future_descriptor.get("input") or {}
                                    if output_contract and str(future_input.get("contract") or "") != output_contract:
                                        continue
                                    fixture_rel = str(future_input.get("smoke_fixture") or "")
                                    if not fixture_rel:
                                        continue
                                    fixture_path = self.root / fixture_rel
                                    if fixture_path.is_file():
                                        seed_payload = read_json(fixture_path, None)
                                        seed_fixture = fixture_rel
                                        if seed_payload is not None:
                                            break
                                if seed_payload is None:
                                    seed_payload = {"demo": True, "adapter": brick_id}
                                supplied = {"contract": source_contract, "payload": seed_payload}
                                input_source = "DOWNSTREAM_SMOKE_FIXTURE" if seed_fixture else "SYNTHETIC_ADAPTER_SEED"
                        elif argument_mode == "payload":
                            # Exact graph contracts are semantic/proof contracts; generated bricks can have
                            # different Python payload shapes. Execute each proven runtime contract with its
                            # own Stage-8-derived smoke fixture instead of blindly feeding the prior return value.
                            supplied = None
                            input_source = "SMOKE_FIXTURE"
                        else:
                            supplied = None
                            input_source = "NONE"
                        action, output, runtime_evidence = self.invoker.invoke(descriptor, supplied)
                        actual_input = runtime_evidence.pop("input_value", supplied)
                        runtime_evidence["input_source"] = input_source
                    last_output = output
                elif impl:
                    provider = str(impl.get("provider", ""))
                    if provider not in LEGACY_PROVIDER_SHIMS:
                        raise RuntimeInvocationError("RUNTIME_CONTRACT_MISSING", f"no resolved runtime contract for {brick_id}; provider {provider} is provenance only")
                    legacy_inputs = {
                        "source-onboarding-v1": data.get("sourceRequest"),
                        "data-contract-adapt-v1": data.get("contract"),
                        "compliance-workflow-v1": data.get("transfer"),
                        "pyspark-transform-v1": data.get("events"),
                        "audience-reach-v1": data.get("events"),
                    }
                    actual_input = legacy_inputs.get(provider)
                    input_source = "LEGACY_DEMO_DATA"
                    action, output = self._execute_provider(provider, brick_id, data)
                    provider_used_for_dispatch = True
                    mode = "LEGACY_PROVIDER_SHIM"
                    last_output = output
                    runtime_evidence = {"provider": provider, "provider_used_for_dispatch": True}
                else:
                    source_path = self.root / str(node.get("candidateRelativePath", ""))
                    if not source_path.exists():
                        raise RuntimeInvocationError("RUNTIME_SOURCE_MISSING", f"REUSE binding missing: {source_path}")
                    action = "verify_reuse_binding"
                    actual_input = {"candidateRelativePath": source_path.relative_to(self.root).as_posix()}
                    input_source = "REUSE_BINDING"
                    output = {"path": source_path.relative_to(self.root).as_posix(), "exists": True}
                    mode = "REUSE_BINDING_VERIFICATION"
                    runtime_evidence = {"provider": "REUSE", "provider_used_for_dispatch": False}
                checkpoint_receipt = self._checkpoint_write_pass(node, index, checkpoint_context, action, mode, output, runtime_evidence, input_value=actual_input, input_source=input_source)
                steps.append({"order": index, "node": brick_id, "capability": node.get("displayName") or node.get("capability"), "mode": mode, "action": action, "status": "PASS", "input": actual_input, "inputSource": input_source, "inputSha256": checkpoint_receipt.get("inputSha256") or runtime_evidence.get("input_sha256"), "output": output, "outputSha256": checkpoint_receipt.get("outputSha256") or runtime_evidence.get("output_sha256"), "runtime": runtime_evidence, "durationMs": int((time.perf_counter()-node_started)*1000), "incoming": incoming_by.get(brick_id, []), "outgoing": outgoing_by.get(brick_id, []), "providerUsedForDispatch": provider_used_for_dispatch, "checkpoint": "WRITTEN", "checkpointReceiptFingerprint": checkpoint_receipt.get("receiptFingerprint")})
                self._stage9_graph_event("RETURN_RESULT", "PASS", f"{capability} returned PASS", node=brick_id, current=index, total=len(nodes), extra={"runtimeExecutionRunId": runtime_evidence.get("runtime_execution_run_id"), "inputSha256": runtime_evidence.get("input_sha256"), "checkpointReceiptFingerprint": checkpoint_receipt.get("receiptFingerprint")})
                self._stage9_live("RUNNING", f"Graph node PASS · {capability}", node=brick_id, current=index, total=len(nodes), wait_reason=None)
            except RuntimeInvocationError as exc:
                status = "FAIL"
                steps.append({"order": index, "node": brick_id, "capability": node.get("displayName") or node.get("capability"), "mode": "FAILED", "action": "execute", "status": "FAIL", "input": actual_input, "inputSource": input_source, "durationMs": int((time.perf_counter()-node_started)*1000), "incoming": incoming_by.get(brick_id, []), "outgoing": outgoing_by.get(brick_id, []), "error_code": exc.code, "error": str(exc), "details": exc.details})
                self._stage9_graph_event("BRICK_FAIL", "FAIL", f"{exc.code}: {exc}", node=brick_id, current=index-1, total=len(nodes), extra={"errorCode": exc.code, "details": exc.details})
                self._stage9_live("FAIL", f"{exc.code}: {exc}", node=brick_id, current=index-1, total=len(nodes), wait_reason=None)
                for tail_index, tail in enumerate(nodes[index:], start=index + 1):
                    steps.append({"order": tail_index, "node": self._node_id(tail), "capability": tail.get("displayName") or tail.get("capability"), "mode": "NOT_RUN", "action": "not_run", "status": "NOT_RUN"})
                break
            except Exception as exc:
                status = "FAIL"
                steps.append({"order": index, "node": brick_id, "capability": node.get("displayName") or node.get("capability"), "mode": "FAILED", "action": "execute", "status": "FAIL", "input": actual_input, "inputSource": input_source, "durationMs": int((time.perf_counter()-node_started)*1000), "incoming": incoming_by.get(brick_id, []), "outgoing": outgoing_by.get(brick_id, []), "error_code": "RUNTIME_EXCEPTION", "error": str(exc), "trace": traceback.format_exc(limit=5)})
                self._stage9_graph_event("BRICK_FAIL", "FAIL", f"RUNTIME_EXCEPTION: {exc}", node=brick_id, current=index-1, total=len(nodes), extra={"errorCode": "RUNTIME_EXCEPTION"})
                self._stage9_live("FAIL", f"RUNTIME_EXCEPTION: {exc}", node=brick_id, current=index-1, total=len(nodes), wait_reason=None)
                for tail_index, tail in enumerate(nodes[index:], start=index + 1):
                    steps.append({"order": tail_index, "node": self._node_id(tail), "capability": tail.get("displayName") or tail.get("capability"), "mode": "NOT_RUN", "action": "not_run", "status": "NOT_RUN"})
                break
        self._checkpoint_persist_summary(nodes, status)
        result = {"schema": "portfolio-foundry.runtime-demo-run.v1", "run_id": f"demo-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}", "stage9RunId": self.stage9_run_id or None, "candidateId": self.candidate_id, "vacancyId": self.vacancy_id, "status": status, "scenarioId": self.demo_spec.get("id", "portfolio-demo-v031"), "projectId": self.project_id, "graphNodes": len(nodes), "graphEdges": len(self.graph.get("edges", [])), "checkpointMode": "FRESH_CAPTURE" if force_fresh else "RESUMABLE", "freshCapture": bool(force_fresh), "checkpointsReused": self.stage9_checkpoint_reused, "checkpointsWritten": self.stage9_checkpoint_written, "checkpointsBootstrapped": self.stage9_checkpoint_bootstrapped, "checkpointsInvalidated": self.stage9_checkpoint_invalidated, "resumeStartNode": self.stage9_resume_start_node, "steps": steps, "completedAt": datetime.now(timezone.utc).isoformat()}
        write_json(self.evidence_v031 / "runtime-demo-run.json", result)
        return result

    def run_life_scenario(self) -> dict[str, Any]:
        if self.life_scenario.get("schemaVersion") != "portfolio-foundry.life-scenario.v1":
            raise RuntimeError("Life Scenario has not been materialized by Factory stage 14")
        demo = self.run_demo()
        by_node = {str(step.get("node") or ""): step for step in demo.get("steps", [])}
        stage_results: list[dict[str, Any]] = []
        for stage in self.life_scenario.get("stages", []):
            node_ids = [str(value) for value in stage.get("nodeIds", [])]
            node_steps = [by_node.get(node_id, {"node": node_id, "status": "MISSING"}) for node_id in node_ids]
            stage_status = "PASS" if node_steps and all(str(step.get("status")).upper() == "PASS" for step in node_steps) else "FAIL"
            stage_results.append({
                "order": stage.get("order"),
                "title": stage.get("title"),
                "status": stage_status,
                "nodeIds": node_ids,
                "steps": node_steps,
            })
        status = "PASS" if demo.get("status") == "PASS" and stage_results and all(x["status"] == "PASS" for x in stage_results) else "FAIL"
        result = {
            "schema": "portfolio-foundry.life-scenario-run.v1",
            "status": status,
            "scenarioId": self.life_scenario.get("targetBrickId"),
            "projectId": self.project_id,
            "candidateGraphRunId": demo.get("run_id"),
            "stages": stage_results,
            "demo": demo,
            "proof": "Every visual stage is computed from real /api/demo/run node results.",
            "completedAt": datetime.now(timezone.utc).isoformat(),
        }
        write_json(self.root / "evidence" / "v035" / "life-scenario-run.json", result)
        return result

    def run_practical_case(self, case_id: str) -> dict[str, Any]:
        if self.case_portfolio.get("schemaVersion") != "portfolio-foundry.case-portfolio.v1":
            raise RuntimeError("Practical Case Portfolio has not been materialized by Factory stage 14")
        practical_case = next((x for x in self.case_portfolio.get("cases", []) if str(x.get("caseId")) == case_id), None)
        if practical_case is None:
            raise KeyError(f"practical case not found: {case_id}")
        demo = self.run_demo()
        by_node = {str(step.get("node") or ""): step for step in demo.get("steps", [])}
        stage_results: list[dict[str, Any]] = []
        for stage in practical_case.get("stages", []):
            node_ids = [str(value) for value in stage.get("nodeIds", [])]
            node_steps = [by_node.get(node_id, {"node": node_id, "status": "MISSING"}) for node_id in node_ids]
            stage_status = "PASS" if node_steps and all(str(step.get("status")).upper() == "PASS" for step in node_steps) else "FAIL"
            stage_results.append({"order": stage.get("order"), "title": stage.get("title"), "status": stage_status, "nodeIds": node_ids, "steps": node_steps})
        status = "PASS" if demo.get("status") == "PASS" and stage_results and all(x["status"] == "PASS" for x in stage_results) else "FAIL"
        result = {
            "schema": "portfolio-foundry.practical-case-run.v1",
            "status": status,
            "caseId": case_id,
            "caseTitle": practical_case.get("title"),
            "portfolioId": self.case_portfolio.get("targetBrickId"),
            "projectId": self.project_id,
            "candidateGraphRunId": demo.get("run_id"),
            "stages": stage_results,
            "demo": demo,
            "proof": "Every visual stage is computed from the selected case and real /api/demo/run node results.",
            "completedAt": datetime.now(timezone.utc).isoformat(),
        }
        write_json(self.root / "evidence" / "v035" / "case-portfolio-run.json", result)
        return result

    def calculate_economic_effect(self, scenario: str, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
        if self.economic_effect.get("schemaVersion") != "portfolio-foundry.economic-effect.v1":
            raise RuntimeError("Economic Effect has not been materialized by Factory stage 15")
        if scenario not in {"conservative", "base", "potential"}:
            raise ValueError("scenario must be conservative, base, or potential")
        assumptions = self.economic_effect.get("assumptions", [])
        expected_ids = [
            "monthly_volume", "before_minutes", "after_minutes", "hourly_cost",
            "before_defect_rate_pct", "after_defect_rate_pct", "defect_unit_cost",
            "implementation_cost", "monthly_run_cost",
        ]
        if [str(x.get("id")) for x in assumptions] != expected_ids:
            raise RuntimeError("Economic Effect assumptions contract mismatch")
        supplied = overrides if isinstance(overrides, dict) else {}
        values: dict[str, float] = {}
        for item in assumptions:
            key = str(item.get("id"))
            raw = supplied.get(key, item.get(scenario))
            try: value = float(raw)
            except (TypeError, ValueError): raise ValueError(f"invalid numeric assumption: {key}")
            if not math.isfinite(value) or value < 0: raise ValueError(f"assumption must be finite and non-negative: {key}")
            values[key] = value
        if values["monthly_volume"] <= 0 or values["before_minutes"] <= 0:
            raise ValueError("monthly_volume and before_minutes must be greater than zero")
        if values["after_minutes"] > values["before_minutes"] or values["after_defect_rate_pct"] > values["before_defect_rate_pct"]:
            raise ValueError("AFTER assumptions cannot be worse than BEFORE assumptions")

        demo = self.run_demo()
        status_by_node = {str(x.get("node") or ""): str(x.get("status") or "NOT_RUN").upper() for x in demo.get("steps", [])}
        brick_effects = self.economic_effect.get("brickEffects", [])
        total_weight = sum(max(1, int(x.get("contributionWeight", 1))) for x in brick_effects)
        active_weight = sum(max(1, int(x.get("contributionWeight", 1))) for x in brick_effects if status_by_node.get(str(x.get("nodeId"))) == "PASS")
        active_ratio = active_weight / total_weight if total_weight else 0.0
        horizon = int(self.economic_effect.get("horizonMonths") or 12)

        before_labor = values["monthly_volume"] * values["before_minutes"] / 60.0 * values["hourly_cost"]
        before_quality = values["monthly_volume"] * values["before_defect_rate_pct"] / 100.0 * values["defect_unit_cost"]
        theoretical_labor_saving = values["monthly_volume"] * (values["before_minutes"] - values["after_minutes"]) / 60.0 * values["hourly_cost"]
        theoretical_quality_saving = values["monthly_volume"] * (values["before_defect_rate_pct"] - values["after_defect_rate_pct"]) / 100.0 * values["defect_unit_cost"]
        theoretical_gross_annual = (theoretical_labor_saving + theoretical_quality_saving) * horizon
        gross_annual = theoretical_gross_annual * active_ratio
        annual_run_cost = values["monthly_run_cost"] * horizon
        net_annual = gross_annual - annual_run_cost
        first_year_net = net_annual - values["implementation_cost"]
        roi = first_year_net / values["implementation_cost"] * 100.0 if values["implementation_cost"] > 0 else None
        monthly_net = gross_annual / horizon - values["monthly_run_cost"] if horizon > 0 else 0.0
        payback = values["implementation_cost"] / monthly_net if values["implementation_cost"] > 0 and monthly_net > 0 else None
        before_annual = (before_labor + before_quality) * horizon
        after_annual = before_annual - gross_annual + annual_run_cost

        brick_results = []
        for index, item in enumerate(brick_effects, start=1):
            node_id = str(item.get("nodeId") or "")
            proof_status = status_by_node.get(node_id, "MISSING")
            weight = max(1, int(item.get("contributionWeight", 1)))
            share = weight / active_weight if active_weight and proof_status == "PASS" else 0.0
            brick_results.append({
                **item,
                "order": index,
                "proofStatus": proof_status,
                "normalizedSharePct": round(share * 100.0, 4),
                "attributedGrossAnnual": round(gross_annual * share, 2),
                "attributionPolicy": "share of one aggregate benefit pool; not an independently additive claim",
            })

        result = {
            "schema": "portfolio-foundry.economic-effect-run.v1",
            "status": "PASS" if demo.get("status") == "PASS" and active_weight == total_weight else "FAIL",
            "scenario": scenario,
            "currency": "RUB",
            "horizonMonths": horizon,
            "assumptions": values,
            "before": {"annualOperatingCost": round(before_annual, 2), "monthlyLaborCost": round(before_labor, 2), "monthlyQualityLoss": round(before_quality, 2)},
            "after": {"annualOperatingCost": round(after_annual, 2), "monthlyRunCost": round(values["monthly_run_cost"], 2)},
            "effect": {
                "laborSavingAnnual": round(theoretical_labor_saving * horizon * active_ratio, 2),
                "qualityRiskSavingAnnual": round(theoretical_quality_saving * horizon * active_ratio, 2),
                "grossAnnualBenefit": round(gross_annual, 2),
                "annualRunCost": round(annual_run_cost, 2),
                "netAnnualBenefit": round(net_annual, 2),
                "implementationCost": round(values["implementation_cost"], 2),
                "firstYearNetValue": round(first_year_net, 2),
                "firstYearRoiPct": round(roi, 2) if roi is not None else None,
                "paybackMonths": round(payback, 2) if payback is not None else None,
            },
            "graphProof": {"runId": demo.get("run_id"), "status": demo.get("status"), "passedBricks": sum(1 for x in brick_results if x["proofStatus"] == "PASS"), "totalBricks": len(brick_results), "activeWeightRatio": round(active_ratio, 6)},
            "brickResults": brick_results,
            "doubleCountCheck": {"policy": "NORMALIZED_ATTRIBUTION", "attributedGrossTotal": round(sum(x["attributedGrossAnnual"] for x in brick_results), 2), "aggregateGrossAnnual": round(gross_annual, 2)},
            "positioning": "HYPOTHESIS_FOR_PILOT",
            "completedAt": datetime.now(timezone.utc).isoformat(),
        }
        write_json(self.root / "evidence" / "v036" / "economic-effect-run.json", result)
        return result


class Handler(BaseHTTPRequestHandler):
    runtime: ProjectRuntime
    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stdout.write(f"[{BUILD_TOKEN}][HTTP] " + (fmt % args) + "\n"); sys.stdout.flush()
    def _json(self, value: Any, status: int = 200) -> None:
        data = json.dumps(value, ensure_ascii=False, indent=2, default=str).encode("utf-8")
        self.send_response(status); self.send_header("Content-Type", "application/json; charset=utf-8"); self.send_header("Content-Length", str(len(data))); self.send_header("Cache-Control", "no-store"); self.end_headers(); self.wfile.write(data)
    def _bytes(self, data: bytes, content_type: str, status: int = 200) -> None:
        self.send_response(status); self.send_header("Content-Type", content_type); self.send_header("Content-Length", str(len(data))); self.send_header("Cache-Control", "no-store"); self.end_headers(); self.wfile.write(data)
    def _static(self, path: Path) -> None:
        if not path.is_file(): self.send_error(404); return
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        if content_type.startswith("text/") or path.suffix in {".js", ".json", ".svg"}: content_type += "; charset=utf-8"
        self._bytes(path.read_bytes(), content_type)
    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path); path = parsed.path
        try:
            if path == "/health": self._json({"status": "READY", "projectId": self.runtime.project_id, "server": SERVER_VERSION}); return
            if path == "/api/project": self._json(self.runtime.api_project()); return
            if path == "/api/overview": self._json(self.runtime.api_overview()); return
            if path == "/api/routes": self._json(self.runtime.routes); return
            if path == "/api/capabilities": self._json(self.runtime.api_capabilities()); return
            if path == "/api/graph": self._json(self.runtime.api_graph()); return
            if path == "/api/live-execution": self._json(self.runtime.api_live_execution()); return
            if path == "/api/case-portfolio": self._json(self.runtime.api_case_portfolio()); return
            if path == "/api/economic-effect": self._json(self.runtime.api_economic_effect()); return
            if path == "/api/life-scenario": self._json(self.runtime.api_life_scenario()); return
            if path == "/api/evidence": self._json(self.runtime.api_evidence()); return
            if path == "/api/diagnostics": self._json(self.runtime.api_diagnostics()); return
            if path == "/api/demo/data": self._json(self.runtime.demo_data()); return
            if path == "/api/runtime-invocations": self._json(read_json(self.runtime.foundry / "runtime-invocation-inventory.json", {})); return
            if path.startswith("/api/brick/"):
                brick_id = path.split("/", 3)[3]; brick = self.runtime.brick(brick_id); self._json(brick if brick is not None else {"error": "brick not found"}, 200 if brick else 404); return
            if path == "/api/source":
                brick_id = parse_qs(parsed.query).get("brick", [""])[0]; self._json(self.runtime.source(brick_id)); return
            if path == "/app.js": self._static(self.runtime.web / "app.js"); return
            if path == "/styles.css": self._static(self.runtime.web / "styles.css"); return
            if path == "/" or path.startswith("/app/"): self._static(self.runtime.web / "index.html"); return
            self.send_error(404)
        except KeyError as exc: self._json({"error": str(exc)}, 404)
        except Exception as exc: self._json({"error": str(exc), "trace": traceback.format_exc(limit=4)}, 500)
    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/api/demo/run":
                demo_mode = str(parse_qs(parsed.query).get("mode", ["resumable"])[0] or "resumable").strip().lower()
                force_fresh = demo_mode in {"fresh", "force-fresh", "fresh-capture", "pro-max"}
                result = self.runtime.run_demo(force_fresh=force_fresh); self._json(result, 200 if result.get("status") == "PASS" else 500); return
            if parsed.path == "/api/life-scenario/run":
                result = self.runtime.run_life_scenario(); self._json(result, 200 if result.get("status") == "PASS" else 500); return
            if parsed.path == "/api/case-portfolio/run":
                case_id = parse_qs(parsed.query).get("case", ["primary"])[0]
                result = self.runtime.run_practical_case(case_id); self._json(result, 200 if result.get("status") == "PASS" else 500); return
            if parsed.path == "/api/economic-effect/calculate":
                scenario = parse_qs(parsed.query).get("scenario", ["base"])[0]
                length = int(self.headers.get("Content-Length", "0") or 0)
                body = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
                overrides = body.get("assumptions") if isinstance(body, dict) else {}
                result = self.runtime.calculate_economic_effect(scenario, overrides)
                self._json(result); return
            self.send_error(404)
        except Exception as exc: self._json({"error": str(exc), "trace": traceback.format_exc(limit=4)}, 500)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", default=str(Path(__file__).resolve().parents[2]))
    parser.add_argument("--host", default=os.environ.get("PORTFOLIO_APP_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORTFOLIO_APP_PORT", "8071")))
    parser.add_argument("--runtime-discovery-only", action="store_true", help="Build and validate the runtime invocation inventory, then exit.")
    parser.add_argument("--runtime-demo-only", action="store_true", help="BUILD99 regression hook: run the Stage 9 graph demo once and print JSON.")
    parser.add_argument("--runtime-worker-request", help="Internal BUILD87 isolated runtime worker request JSON.")
    args = parser.parse_args()
    if args.runtime_worker_request:
        return _runtime_worker(Path(args.runtime_worker_request).resolve())
    runtime = ProjectRuntime(Path(args.project_root), allow_unresolved_inventory=args.runtime_discovery_only)
    if args.runtime_discovery_only:
        inventory = read_json(runtime.foundry / "runtime-invocation-inventory.json", {})
        nodes = inventory.get("nodes", []) if isinstance(inventory.get("nodes"), list) else []
        non_ready = [
            {
                "node": str(row.get("node_id") or row.get("target_brick_id") or ""),
                "status": str(row.get("status") or "UNKNOWN"),
                "resolution": str(row.get("resolution") or ""),
                "reason": row.get("reason"),
            }
            for row in nodes if isinstance(row, dict) and str(row.get("status") or "").upper() != "READY"
        ]
        status = "PASS" if inventory.get("status") == "PASS" and not non_ready else "FAIL"
        print(json.dumps({
            "status": status,
            "code": None if status == "PASS" else "RUNTIME_INVENTORY_UNRESOLVED",
            "projectId": runtime.project_id,
            "runId": runtime.stage9_run_id or None,
            "inventoryRunId": inventory.get("stage9RunId"),
            "nodes": len(nodes),
            "nonReady": non_ready,
            "failure": inventory.get("failure"),
            "inventory": str(runtime.foundry / "runtime-invocation-inventory.json"),
            "diagnostics": str(runtime.foundry / "runtime-discovery-diagnostics.json"),
            "mode": "runtime-discovery-only",
            "buildToken": BUILD_TOKEN,
        }, ensure_ascii=False), flush=True)
        return 0 if status == "PASS" else 2
    if args.runtime_demo_only:
        result = runtime.run_demo()
        print(json.dumps(result, ensure_ascii=False, default=str), flush=True)
        return 0 if result.get("status") == "PASS" else 3
    Handler.runtime = runtime; server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"[{BUILD_TOKEN}] READY http://{args.host}:{server.server_address[1]} project={runtime.project_id} factory={FACTORY_VERSION}", flush=True)
    try: server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt: pass
    finally: server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
