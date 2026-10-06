from pathlib import Path
import importlib.util

p = Path.cwd() / "src" / "adapters" / "scientifically-rigorous-83d835d4" / "core.py"
spec = importlib.util.spec_from_file_location("adapter", p)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
sample = {"contract": "foundry.analytics.ab_testing.v1", "payload": {"sample": 1, "rows": [1, 2, 3]}}
out = m.adapt(sample)
assert out["contract"] == "foundry.candidate.synthetic-agent-data-ge-5456d7a2.v1"
assert out["payload"] == sample["payload"]
assert out["source_contract"] == "foundry.analytics.ab_testing.v1"
print("PASS integration")