from pathlib import Path
import importlib.util

p = Path.cwd() / "src" / "adapters" / "domain-llm-fine-tuning-c63d3d23" / "core.py"
spec = importlib.util.spec_from_file_location("adapter", p)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
assert m.SOURCE_CONTRACT == "foundry.project.enterprise-operational-risk-agentic-21313c83.v1"
assert m.TARGET_CONTRACT == "foundry.analytics.ab_testing.v1"
assert m.ADAPTER_ID == "domain-llm-fine-tuning-c63d3d23"
print("PASS contract")