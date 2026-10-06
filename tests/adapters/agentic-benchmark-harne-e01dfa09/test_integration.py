from pathlib import Path
import importlib.util

p = Path.cwd() / "src" / "adapters" / "agentic-benchmark-harne-e01dfa09" / "core.py"
spec = importlib.util.spec_from_file_location("adapter", p)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
sample = {"contract": "foundry.platform.evidence_registry.v1", "payload": {"sample": 1, "rows": [1, 2, 3]}}
out = m.adapt(sample)
assert out["contract"] == "foundry.project.cybersecurity-data-exchange-route-ri-0fb020cc.v1"
assert out["payload"] == sample["payload"]
assert out["source_contract"] == "foundry.platform.evidence_registry.v1"
print("PASS integration")