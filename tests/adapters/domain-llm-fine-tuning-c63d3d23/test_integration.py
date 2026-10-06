from pathlib import Path
import importlib.util

p = Path.cwd() / "src" / "adapters" / "domain-llm-fine-tuning-c63d3d23" / "core.py"
spec = importlib.util.spec_from_file_location("adapter", p)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
sample = {"contract": "foundry.project.enterprise-operational-risk-agentic-21313c83.v1", "payload": {"sample": 1, "rows": [1, 2, 3]}}
out = m.adapt(sample)
assert out["contract"] == "foundry.analytics.ab_testing.v1"
assert out["payload"] == sample["payload"]
assert out["source_contract"] == "foundry.project.enterprise-operational-risk-agentic-21313c83.v1"
print("PASS integration")