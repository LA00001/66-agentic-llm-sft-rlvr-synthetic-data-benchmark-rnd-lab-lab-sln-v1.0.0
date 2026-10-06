from pathlib import Path
import importlib.util

p = Path.cwd() / "src" / "adapters" / "ingress-domain-llm-fine-4d7e8b27" / "core.py"
spec = importlib.util.spec_from_file_location("adapter", p)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
assert m.SOURCE_CONTRACT == "foundry.requirement.v1"
assert m.TARGET_CONTRACT == "foundry.project.enterprise-operational-risk-agentic-21313c83.v1"
assert m.ADAPTER_ID == "ingress-domain-llm-fine-4d7e8b27"
print("PASS contract")