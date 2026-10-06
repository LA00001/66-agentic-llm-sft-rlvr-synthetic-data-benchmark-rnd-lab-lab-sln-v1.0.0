from pathlib import Path
import importlib.util

p = Path.cwd() / "src" / "adapters" / "agentic-benchmark-harne-e01dfa09" / "core.py"
spec = importlib.util.spec_from_file_location("adapter", p)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
assert m.SOURCE_CONTRACT == "foundry.platform.evidence_registry.v1"
assert m.TARGET_CONTRACT == "foundry.project.cybersecurity-data-exchange-route-ri-0fb020cc.v1"
assert m.ADAPTER_ID == "agentic-benchmark-harne-e01dfa09"
print("PASS contract")