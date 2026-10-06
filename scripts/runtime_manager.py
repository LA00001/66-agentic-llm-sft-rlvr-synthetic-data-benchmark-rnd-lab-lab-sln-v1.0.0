# FEATURE: Portfolio_Foundry_v0.38.0.20.16309_BUILD49_TEST62
"""Foundry shared runtime manager. Stdlib + pip's bundled packaging; no provider calls.

Existing environments are inspected in place. Only newly created v048 environments
are modified. A compatible environment must pass identity, requirements and pip check.
The same file is embedded in Core and shipped with portable applications.
"""
import contextlib
import hashlib
import importlib.metadata as metadata
import json
import os
from pathlib import Path
import platform
import queue
import shutil
import signal
import subprocess
import sys
import sysconfig
import threading
import time
import uuid

try:
    from pip._vendor.packaging.requirements import Requirement
    from pip._vendor.packaging.utils import canonicalize_name
except ImportError:
    from packaging.requirements import Requirement
    from packaging.utils import canonicalize_name

SCHEMA = "foundry.runtime-library.v1"
GROUPS = ("v03b", "v031", "v038", "v048")


FEATURE_TOKEN = "Portfolio_Foundry_v0.38.0.20.16309_BUILD49_TEST62"
FEATURE_REVISION = "PATCH_READY1"
PATCH_TOKEN = os.environ.get("PORTFOLIO_FOUNDRY_PATCH_TOKEN", "PATCH_STAGE10_FORENSIC_PORTABLE_PATH100")


def with_provenance(value):
    return dict(value, featureToken=FEATURE_TOKEN, featureRevision=FEATURE_REVISION, patchToken=PATCH_TOKEN)


def stamp():
    import datetime
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]


def atomic(path, value):
    value = with_provenance(value)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def read(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return default


def parse_requirements(values):
    result = []
    for value in values:
        if not isinstance(value, str) or len(value) > 500 or any(c in value for c in "\r\n\x00"):
            raise ValueError("Invalid package requirement")
        value = value.strip()
        if not value or value.startswith("#"):
            continue
        req = Requirement(value)
        if req.url:
            raise ValueError("Direct package URLs are not accepted by the shared runtime manager")
        name = canonicalize_name(req.name)
        extras = "[" + ",".join(sorted(req.extras)) + "]" if req.extras else ""
        result.append(name + extras + str(req.specifier) + ("; " + str(req.marker) if req.marker else ""))
    return sorted(set(result))


def identity():
    return {"version": platform.python_version(), "implementation": sys.implementation.name,
            "platform": sysconfig.get_platform(), "cacheTag": sys.implementation.cache_tag}


def probe(requirements, include_sizes=False):
    installed = {}
    distributions = {}
    for dist in metadata.distributions():
        name = dist.metadata.get("Name")
        if name:
            name = canonicalize_name(name)
            installed[name] = dist.version
            distributions[name] = dist
    missing = []
    visited = set()

    def verify(value, extra=""):
        req = Requirement(value)
        if req.marker and not req.marker.evaluate({"extra": extra}):
            return
        key = (str(req), extra)
        if key in visited:
            return
        visited.add(key)
        name = canonicalize_name(req.name)
        version = installed.get(name)
        if version is None or not req.specifier.contains(version, prereleases=None):
            missing.append(str(req))
            return
        # pip check does not validate optional extras. Check their active dependencies too.
        for requested_extra in req.extras:
            for dependency in distributions[name].requires or []:
                verify(dependency, requested_extra)

    for req in requirements:
        verify(req)
    packages = []
    for name, version in sorted(installed.items()):
        item = {"name": name, "version": version}
        if include_sizes:
            dist = distributions.get(name)
            if dist is not None:
                item["bytes"] = distribution_bytes(dist)
        packages.append(item)
    return {"featureToken": FEATURE_TOKEN, "featureRevision": FEATURE_REVISION, "identity": identity(), "packages": packages,
            "satisfies": not missing, "missing": missing, "requirements": parse_requirements(requirements)}


def snapshot_may_match(record, requirements):
    installed = {p["name"]: p["version"] for p in record.get("packages", [])}
    if not installed:
        return True
    for value in requirements:
        req = Requirement(value)
        if req.marker and not req.marker.evaluate():
            continue
        version = installed.get(canonicalize_name(req.name))
        if version is None or not req.specifier.contains(version, prereleases=None):
            return False
    return True


def python_at(root):
    return Path(root) / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def package_failure_name(output):
    """Best-effort package name extraction for truthful Stage 9 diagnostics."""
    import re
    text = output or ""
    patterns = [
        r"ERROR:\s+Cannot install\s+([A-Za-z0-9_.-]+)(?:[<>=!~]=?[^\s]*)?",
        r"ERROR:\s+Failed building wheel for\s+([A-Za-z0-9_.-]+)",
        r"Failed to build\s+([A-Za-z0-9_.-]+)",
        r"Could not find a version that satisfies the requirement\s+([A-Za-z0-9_.-]+)",
        r"No matching distribution found for\s+([A-Za-z0-9_.-]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return canonicalize_name(match.group(1))
    return "unknown"


def bytes_at(root):
    total = 0
    for directory, subdirs, files in os.walk(root, followlinks=False):
        subdirs[:] = [d for d in subdirs if not (Path(directory) / d).is_symlink()]
        for name in files:
            try:
                p = Path(directory) / name
                if not p.is_symlink():
                    total += p.stat().st_size
            except OSError:
                pass
    return total


def distribution_bytes(dist):
    total = 0
    seen = set()
    for item in dist.files or []:
        try:
            p = Path(dist.locate_file(item))
            key = str(p.resolve())
            if key in seen or p.is_symlink() or not p.is_file():
                continue
            seen.add(key)
            total += p.stat().st_size
        except OSError:
            pass
    return total


def merge_package_sizes(old_packages, new_packages):
    old = {(p.get("name"), p.get("version")): p.get("bytes") for p in old_packages or [] if p.get("bytes") is not None}
    merged = []
    for package in new_packages or []:
        item = dict(package)
        key = (item.get("name"), item.get("version"))
        if item.get("bytes") is None and key in old:
            item["bytes"] = old[key]
        merged.append(item)
    return merged


class Manager:
    def __init__(self, request):
        self.request = request
        self.root = Path(request["cacheRoot"]).resolve() / "runtimes"
        self.control = self.root / "library"
        self.control.mkdir(parents=True, exist_ok=True)
        self.use_id = request.get("useId") or uuid.uuid4().hex
        self.context = request.get("context") or {}
        self.log_path = self.control / "logs" / (digest(self.use_id) + ".jsonl")
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.history_root = self.control / "runtime-history"
        self.history_root.mkdir(parents=True, exist_ok=True)
        self.current = None
        self.phase_serial = 0
        # BUILD143: package-source accounting makes it explicit whether a new env reused local wheels or touched network.
        self.local_wheel_families = []
        self.network_wheel_families = []

    def lifecycle(self, runtime_id, event, **values):
        item = with_provenance(dict(schema="foundry.runtime-lifecycle.v1", runtimeId=runtime_id, event=event, at=stamp(), useId=self.use_id, context=self.context, **values))
        atomic(self.history_root / (digest(runtime_id + ":" + self.use_id + ":" + event + ":" + item["at"]) + ".json"), item)
        return item

    def emit(self, phase, status, **values):
        event = with_provenance(dict(phase=phase, status=status, at=stamp(), context=self.context, useId=self.use_id, **values))
        line = json.dumps(event, ensure_ascii=False)
        with self.log_path.open("a", encoding="utf-8") as stream:
            stream.write(line + "\n")
        print(line, flush=True)

    def run(self, command, phase, timeout, quiet=False):
        started = time.monotonic()
        self.phase_serial += 1
        phase_id = self.use_id + ":" + str(self.phase_serial)
        phase_record = dict(id=phase_id, context=self.context, category="runtime-step", label=phase,
                            startedAt=stamp(), endedAt=None, durationMs=0, status="RUNNING", cacheStatus="UNKNOWN",
                            ownerPid=os.getpid())
        event_path = Path(self.request["cacheRoot"]) / "work-history" / "events" / (digest(phase_id) + ".json")
        atomic(event_path, phase_record)
        self.emit(phase, "RUNNING", command=Path(str(command[0])).name)
        env = dict(os.environ, PYTHONUNBUFFERED="1", PIP_DISABLE_PIP_VERSION_CHECK="1", PIP_NO_INPUT="1")
        options = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {"start_new_session": True}
        process = subprocess.Popen([str(x) for x in command], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   text=True, encoding="utf-8", errors="replace", env=env, **options)
        lines = queue.Queue()

        def drain():
            try:
                for line in process.stdout:
                    lines.put(line.rstrip())
            finally:
                lines.put(None)

        reader = threading.Thread(target=drain, daemon=True)
        reader.start()
        output = []
        done = False
        last_heartbeat = time.monotonic()
        try:
            while not done or process.poll() is None:
                if time.monotonic() - started > timeout:
                    raise TimeoutError(f"{phase}: time limit {timeout}s exceeded")
                try:
                    line = lines.get(timeout=.2)
                    if line is None:
                        done = True
                    else:
                        output.append(line)
                        if len(output) > 10000:
                            output.pop(0)
                        if not quiet:
                            self.emit(phase, "OUTPUT", message=line[-3000:])
                except queue.Empty:
                    pass
                if time.monotonic() - last_heartbeat >= 5:
                    self.emit(phase, "HEARTBEAT", durationMs=(time.monotonic() - started) * 1000)
                    last_heartbeat = time.monotonic()
            code = process.wait(timeout=5)
        except BaseException:
            if process.poll() is None:
                if os.name == "nt":
                    subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True, timeout=15)
                else:
                    os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=15)
            atomic(event_path, dict(phase_record, endedAt=stamp(), status="FAIL", durationMs=(time.monotonic() - started)*1000))
            self.emit(phase, "FAIL", durationMs=(time.monotonic() - started) * 1000)
            raise
        finally:
            process.stdout.close()
        duration = (time.monotonic() - started) * 1000
        atomic(event_path, dict(phase_record, endedAt=stamp(), status="PASS" if code == 0 else "FAIL", durationMs=duration))
        self.emit(phase, "PASS" if code == 0 else "FAIL", durationMs=duration, exitCode=code)
        return code, "\n".join(output)

    @contextlib.contextmanager
    def lock(self):
        # OS lock is automatically released after a crash. A second process waits,
        # then rechecks compatibility before starting any new installation.
        path = self.control / "install.lock"
        started = time.monotonic()
        stream = path.open("a+b")
        stream.seek(0, 2)
        if stream.tell() == 0:
            stream.write(b"0")
            stream.flush()
        try:
            while True:
                try:
                    stream.seek(0)
                    if os.name == "nt":
                        import msvcrt
                        msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except OSError:
                    if time.monotonic() - started > self.limit("lock", 1200):
                        raise TimeoutError("Another runtime installation did not finish in time")
                    self.emit("queue", "HEARTBEAT", message="Waiting for shared runtime installation lock")
                    time.sleep(1)
            yield
        finally:
            stream.close()

    def limit(self, name, default):
        value = (self.request.get("timeouts") or {}).get(name, default)
        return max(5, min(3600, int(value)))

    def folders(self):
        for group in GROUPS:
            parent = self.root / group
            if parent.is_dir() and not parent.is_symlink():
                for folder in sorted(parent.iterdir()):
                    if folder.is_dir() and not folder.is_symlink() and python_at(folder).is_file():
                        yield folder

    def record_path(self, folder):
        return self.control / "environments" / (digest(folder.relative_to(self.root).as_posix()) + ".json")

    def describe(self, folder, details=None, state=None):
        old = read(self.record_path(folder), {})
        relative = folder.relative_to(self.root).as_posix()
        runtime_id = digest(relative)
        record = dict(old, featureToken=FEATURE_TOKEN, featureRevision=FEATURE_REVISION, schema=SCHEMA, runtimeId=runtime_id, relativePath=relative,
                      pythonPath=str(python_at(folder)), state=state or old.get("state", "DISCOVERED"),
                      imported=not relative.startswith("v048/"),
                      generation=max(1, int(old.get("generation") or 1)),
                      rebuildCount=max(0, int(old.get("rebuildCount") or 0)),
                      failureCount=max(0, int(old.get("failureCount") or 0)),
                      firstSeenAt=old.get("firstSeenAt", stamp()))
        if details:
            merged_packages = merge_package_sizes(old.get("packages", []), details["packages"] )
            old_signature = [(p.get("name"), p.get("version")) for p in old.get("packages", [])]
            new_signature = [(p.get("name"), p.get("version")) for p in merged_packages]
            record.update(identity=details["identity"], packages=merged_packages, inspectedAt=stamp(),
                          bytes=old.get("bytes") if old_signature == new_signature and old.get("bytes") is not None else bytes_at(folder))
        atomic(self.record_path(folder), record)
        return record

    def inspect(self, folder, requirements, include_sizes=False):
        mode = "--probe-sizes" if include_sizes else "--probe"
        code, output = self.run([python_at(folder), Path(__file__).resolve(), mode, json.dumps(requirements)],
                                "inspect", self.limit("inspect", 120 if include_sizes else 30), quiet=True)
        if code:
            return None
        try:
            return json.loads(output.splitlines()[-1])
        except (ValueError, IndexError):
            return None

    def inventory(self):
        records = []
        # Inventory imports metadata without pip installs or compatibility claims.
        for folder in self.folders():
            details = None
            if self.request.get("inspectExisting"):
                try:
                    details = self.inspect(folder, [], include_sizes=True)
                except (OSError, TimeoutError):
                    pass
            records.append(self.describe(folder, details))
        return with_provenance(dict(environments=records, inspectedAt=stamp()))

    def use(self, record, cache_status, requirements):
        previous_state = record.get("state")
        created_requirements = sorted(record.get("createdRequirements") or [])
        requested_requirements = sorted(requirements or [])
        if cache_status == "HIT":
            origin = "REUSED_EXISTING"
            reuse_mode = "EXACT_REQUIREMENTS" if created_requirements and created_requirements == requested_requirements else "COMPATIBLE_SUPERSET"
        elif int(record.get("rebuildCount") or 0) > 0:
            origin = "REBUILT_AFTER_FAILED"
            reuse_mode = "REBUILT_RUNTIME"
        else:
            origin = "NEW"
            reuse_mode = "NEW_RUNTIME"
        package_source = {
            "localWheelFamilies": sorted(set(self.local_wheel_families)),
            "networkWheelFamilies": sorted(set(self.network_wheel_families)),
        }
        record = dict(record, state="PASS", lastUsedAt=stamp(), lastCacheStatus=cache_status, lastOrigin=origin,
                      lastReuseMode=reuse_mode, lastPackageSource=package_source)
        atomic(self.control / "environments" / (record["runtimeId"] + ".json"), record)
        usage = dict(schema=SCHEMA, useId=self.use_id, runtimeId=record["runtimeId"], context=self.context,
                     at=stamp(), cacheStatus=cache_status, origin=origin, reuseMode=reuse_mode,
                     reusedBytes=(record.get("bytes") or 0) if cache_status == "HIT" else 0,
                     packageSource=package_source, generation=record.get("generation", 1),
                     rebuildCount=record.get("rebuildCount", 0), requirements=requirements,
                     logRelativePath=self.log_path.relative_to(self.root).as_posix())
        atomic(self.control / "uses" / (digest(self.use_id) + ".json"), usage)
        self.lifecycle(record["runtimeId"], "USE", fromState=previous_state, toState="PASS", cacheStatus=cache_status, origin=origin,
                       reuseMode=reuse_mode, generation=record.get("generation", 1), rebuildCount=record.get("rebuildCount", 0))
        return with_provenance(dict(record, cacheStatus=cache_status, origin=origin, reuseMode=reuse_mode, useId=self.use_id, packageSource=package_source))

    def ensure(self):
        requirements = parse_requirements(self.request.get("requirements") or [])
        expected = identity()
        with self.lock():
            candidates = list(self.folders())
            # BUILD143 reuse planner: exact created-requirement matches first, then the smallest compatible supersets.
            # This keeps heavy torch/PySpark environments reusable while avoiding a larger superset when an exact env exists.
            def candidate_cost(folder):
                old = read(self.record_path(folder), {})
                exact = sorted(old.get("createdRequirements") or []) == sorted(requirements) and bool(old.get("createdRequirements"))
                measured = int(old.get("bytes") or (1 << 62))
                packages = len(old.get("packages", [])) or 100000
                return (0 if exact else 1, measured, packages, folder.as_posix())
            candidates.sort(key=candidate_cost)
            for folder in candidates:
                old = read(self.record_path(folder), {})
                if old.get("identity") and old["identity"] != expected:
                    continue
                if old.get("state") in ("INSTALLING", "FAILED"):
                    continue
                if not snapshot_may_match(old, requirements):
                    continue
                try:
                    details = self.inspect(folder, requirements)
                    if not details:
                        continue
                    record = self.describe(folder, details)
                    if details["identity"] != expected or not details["satisfies"]:
                        continue
                    code, _ = self.run([python_at(folder), "-m", "pip", "check"], "check", self.limit("check", 60))
                    if code == 0:
                        return self.use(record, "HIT", requirements)
                except (OSError, TimeoutError):
                    continue

            key = digest(json.dumps(expected, sort_keys=True) + "\n" + "\n".join(requirements))
            folder = self.root / "v048" / key
            # Never mutate a legacy environment or a previously verified environment.
            # Failed own partial installations can be rebuilt; verified mismatches use a new folder.
            if folder.exists():
                old = read(self.record_path(folder), {})
                if old.get("state") in ("INSTALLING", "FAILED"):
                    runtime_id = digest(folder.relative_to(self.root).as_posix())
                    prior_state = old.get("state") or "UNKNOWN"
                    previous_failure = old.get("lastFailureReason")
                    old = dict(old, generation=max(1, int(old.get("generation") or 1)) + 1,
                               rebuildCount=max(0, int(old.get("rebuildCount") or 0)) + 1,
                               lastRebuildAt=stamp(), lastRebuildFromState=prior_state,
                               previousFailureReason=previous_failure)
                    atomic(self.record_path(folder), old)
                    self.lifecycle(runtime_id, "REBUILD", fromState=prior_state, toState="INSTALLING",
                                   generation=old["generation"], rebuildCount=old["rebuildCount"],
                                   previousFailureReason=previous_failure)
                    shutil.rmtree(folder)
                else:
                    folder = folder.with_name(key + "-" + uuid.uuid4().hex[:8])
            folder.mkdir(parents=True)
            self.current = folder
            initial = self.describe(folder, state="INSTALLING")
            initial = dict(initial, createdRequirements=requirements)
            atomic(self.record_path(folder), initial)
            try:
                code, _ = self.run([sys.executable, "-m", "venv", folder], "venv", self.limit("venv", 180))
                if code:
                    raise RuntimeError("Python environment creation failed; see runtime log")
                wheels = self.root / "wheels"
                wheels.mkdir(exist_ok=True)
                reqfile = folder / "requirements.requested.txt"
                reqfile.write_text("\n".join(requirements) + "\n", encoding="utf-8")
                if requirements:
                    # BUILD83 STRICT CACHE FIRST + observable package families. Each top-level family first
                    # tries the local wheel store with --no-index. Network is allowed only for the family whose
                    # complete dependency wheel closure is missing. Installation is then performed one family
                    # at a time so Stage 9 can expose 1/N .. N/N instead of a silent multi-minute pip command.
                    total_packages = len(requirements)
                    for index, requirement in enumerate(requirements, start=1):
                        family = canonicalize_name(Requirement(requirement).name)
                        self.emit("package", "RUNNING", current=index-1, total=total_packages, package=family,
                                  requirement=requirement, action="CACHE_CHECK")
                        offline_wheel = [python_at(folder), "-m", "pip", "wheel", "--disable-pip-version-check",
                                         "--no-index", "--find-links", wheels, "--wheel-dir", wheels, requirement]
                        try:
                            offline_code, offline_output = self.run(offline_wheel, f"wheel-cache-{index}-{family}", self.limit("packages", 180))
                        except TimeoutError as error:
                            self.emit("package", "FAIL", current=index-1, total=total_packages, package=family,
                                      requirement=requirement, action="CACHE_CHECK", message=str(error))
                            raise RuntimeError(f"Package cache check failed; phase=packages; failedPackage={family}; {error}") from error
                        if offline_code:
                            self.network_wheel_families.append(family)
                            self.emit("package", "RUNNING", current=index-1, total=total_packages, package=family,
                                      requirement=requirement, action="DOWNLOAD")
                            command = [python_at(folder), "-m", "pip", "wheel", "--disable-pip-version-check",
                                       "--prefer-binary", "--find-links", wheels, "--wheel-dir", wheels, requirement]
                            try:
                                code, package_output = self.run(command, f"wheel-network-{index}-{family}", self.limit("packages", 900))
                            except TimeoutError as error:
                                self.emit("package", "FAIL", current=index-1, total=total_packages, package=family,
                                          requirement=requirement, action="DOWNLOAD", message=str(error))
                                raise RuntimeError(f"Package download/build failed; phase=packages; failedPackage={family}; {error}") from error
                            if code:
                                failed_package = package_failure_name(package_output)
                                if failed_package == "unknown":
                                    failed_package = family
                                self.emit("package", "FAIL", current=index-1, total=total_packages, package=failed_package,
                                          requirement=requirement, action="DOWNLOAD")
                                raise RuntimeError(f"Package download/build failed; phase=packages; failedPackage={failed_package}; see runtime log")
                        else:
                            self.local_wheel_families.append(family)
                            self.emit("package", "RUNNING", current=index-1, total=total_packages, package=family,
                                      requirement=requirement, action="CACHE_HIT")

                    for index, requirement in enumerate(requirements, start=1):
                        family = canonicalize_name(Requirement(requirement).name)
                        self.emit("package", "RUNNING", current=index-1, total=total_packages, package=family,
                                  requirement=requirement, action="INSTALL")
                        command = [python_at(folder), "-m", "pip", "install", "--disable-pip-version-check",
                                   "--no-index", "--find-links", wheels, requirement]
                        try:
                            code, install_output = self.run(command, f"install-{index}-{family}", self.limit("install", 900))
                        except TimeoutError as error:
                            self.emit("package", "FAIL", current=index-1, total=total_packages, package=family,
                                      requirement=requirement, action="INSTALL", message=str(error))
                            raise RuntimeError(f"Offline package installation failed; phase=install; failedPackage={family}; {error}") from error
                        if code:
                            failed_package = package_failure_name(install_output)
                            if failed_package == "unknown":
                                failed_package = family
                            self.emit("package", "FAIL", current=index-1, total=total_packages, package=failed_package,
                                      requirement=requirement, action="INSTALL")
                            raise RuntimeError(f"Offline package installation failed; phase=install; failedPackage={failed_package}; see runtime log")
                        self.emit("package", "PASS", current=index, total=total_packages, package=family,
                                  requirement=requirement, action="INSTALL")
                code, _ = self.run([python_at(folder), "-m", "pip", "check"], "check", self.limit("check", 60))
                details = self.inspect(folder, requirements)
                if code or not details or not details["satisfies"] or details["identity"] != expected:
                    raise RuntimeError("Installed environment failed requirements or consistency validation")
                record = self.describe(folder, details, "PASS")
                atomic(folder / "RESTORE_PASS.json", record)
                return self.use(record, "MISS", requirements)
            except BaseException as error:
                record = self.describe(folder, state="FAILED")
                record = dict(record, failureCount=max(0, int(record.get("failureCount") or 0)) + 1,
                              lastFailureAt=stamp(), lastFailureReason=str(error)[:2000], lastOrigin="FAILED_BUILD")
                atomic(self.record_path(folder), record)
                self.lifecycle(record["runtimeId"], "FAIL", fromState="INSTALLING", toState="FAILED",
                               generation=record.get("generation", 1), failureCount=record.get("failureCount", 1),
                               reason=record.get("lastFailureReason"))
                raise


def main():
    if len(sys.argv) > 1 and sys.argv[1] in ("--probe", "--probe-sizes"):
        print(json.dumps(probe(json.loads(sys.argv[2]), include_sizes=sys.argv[1] == "--probe-sizes"), ensure_ascii=False))
        return
    if len(sys.argv) > 2 and sys.argv[1] == "--request":
        request = read(sys.argv[2])
    else:
        request = json.load(sys.stdin)
    manager = Manager(request)
    try:
        result = manager.inventory() if request.get("mode") == "inventory" else manager.ensure()
        manager.emit("result", "PASS", result=result)
    except Exception as error:
        manager.emit("result", "FAIL", message=str(error))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
