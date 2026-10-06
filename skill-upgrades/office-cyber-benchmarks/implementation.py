from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import zipfile


def _office_task() -> dict:
    source = """owner,priority,status
alice,high,open
bob,low,open
alice,high,closed
carol,high,open
"""
    reader = csv.DictReader(io.StringIO(source))
    rows = list(reader)
    actual = sorted(
        row["owner"]
        for row in rows
        if row["priority"] == "high" and row["status"] == "open"
    )
    expected = ["alice", "carol"]

    # Package a real office-style artifact and verify its content.
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("report/summary.json", json.dumps({"owners": actual}, sort_keys=True))
        zf.writestr("report/source.csv", source)
    package_bytes = buffer.getvalue()

    with zipfile.ZipFile(io.BytesIO(package_bytes), "r") as zf:
        names = sorted(zf.namelist())
        summary = json.loads(zf.read("report/summary.json").decode("utf-8"))

    passed = (
        actual == expected
        and summary["owners"] == expected
        and names == ["report/source.csv", "report/summary.json"]
    )
    return {
        "domain": "office",
        "passed": passed,
        "oracle": expected,
        "actual": actual,
        "artifact_sha256": hashlib.sha256(package_bytes).hexdigest(),
        "artifact_members": names,
    }


def _cyber_task() -> dict:
    log = [
        "2026-10-04T10:00:00Z user=alice ip=10.0.0.5 action=login result=ok",
        "2026-10-04T10:01:00Z user=admin ip=203.0.113.9 action=login result=fail",
        "2026-10-04T10:01:20Z user=admin ip=203.0.113.9 action=login result=fail",
        "2026-10-04T10:01:40Z user=admin ip=203.0.113.9 action=login result=fail",
        "2026-10-04T10:02:00Z user=admin ip=203.0.113.9 action=login result=fail",
        "2026-10-04T10:03:00Z user=bob ip=10.0.0.8 action=login result=fail",
    ]
    pattern = re.compile(
        r"user=(?P<user>\S+) ip=(?P<ip>\S+) action=(?P<action>\S+) result=(?P<result>\S+)"
    )
    failures = {}
    for line in log:
        match = pattern.search(line)
        if not match:
            raise ValueError("malformed log line")
        event = match.groupdict()
        if event["action"] == "login" and event["result"] == "fail":
            key = (event["user"], event["ip"])
            failures[key] = failures.get(key, 0) + 1

    alerts = sorted(
        {"user": user, "ip": ip, "failed_logins": count}
        for (user, ip), count in failures.items()
        if count >= 4
    )
    expected = [{"user": "admin", "ip": "203.0.113.9", "failed_logins": 4}]
    passed = alerts == expected
    return {
        "domain": "cyber",
        "passed": passed,
        "oracle": expected,
        "actual": alerts,
        "rule": ">=4 failed logins for same user and IP",
    }


def run_demo() -> dict:
    office = _office_task()
    cyber = _cyber_task()
    passed = office["passed"] and cyber["passed"]
    return {
        "status": "PASS" if passed else "FAIL",
        "domains": {"office": office, "cyber": cyber},
        "aggregate_score": 1.0 if passed else 0.0,
        "failure_taxonomy": [] if passed else [
            item["domain"] for item in (office, cyber) if not item["passed"]
        ],
    }


if __name__ == "__main__":
    print(json.dumps(run_demo(), sort_keys=True))
