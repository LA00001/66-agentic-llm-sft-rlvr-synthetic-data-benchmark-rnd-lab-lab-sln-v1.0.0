from pathlib import Path
import importlib.util

p = Path.cwd() / "src" / "adapters" / "sql-agent-tasks-and-exe-e5909590" / "core.py"
spec = importlib.util.spec_from_file_location("adapter", p)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
sample = {"contract": "foundry.project.cybersecurity-data-exchange-route-ri-0fb020cc.v1", "payload": {"sample": 1, "rows": [1, 2, 3]}}
out = m.adapt(sample)
assert out["contract"] == "foundry.data.data_quality.v1"
assert out["payload"] == sample["payload"]
assert out["source_contract"] == "foundry.project.cybersecurity-data-exchange-route-ri-0fb020cc.v1"
print("PASS integration")