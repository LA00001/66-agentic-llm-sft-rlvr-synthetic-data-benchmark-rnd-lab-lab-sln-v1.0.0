from implementation import run_demo


result = run_demo()

assert result["status"] == "PASS"
assert result["aggregate_score"] == 1.0
assert result["failure_taxonomy"] == []

office = result["domains"]["office"]
assert office["passed"] is True
assert office["actual"] == ["alice", "carol"]
assert office["artifact_members"] == ["report/source.csv", "report/summary.json"]
assert len(office["artifact_sha256"]) == 64

cyber = result["domains"]["cyber"]
assert cyber["passed"] is True
assert cyber["actual"] == [
    {"user": "admin", "ip": "203.0.113.9", "failed_logins": 4}
]
assert cyber["rule"].startswith(">=4 failed logins")
