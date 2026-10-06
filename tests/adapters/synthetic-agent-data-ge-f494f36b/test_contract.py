from pathlib import Path
import importlib.util

p = Path.cwd() / "src" / "adapters" / "synthetic-agent-data-ge-f494f36b" / "core.py"
spec = importlib.util.spec_from_file_location("adapter", p)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
assert m.SOURCE_CONTRACT == "foundry.candidate.synthetic-agent-data-ge-5456d7a2.v1"
assert m.TARGET_CONTRACT == "foundry.platform.evidence_registry.v1"
assert m.ADAPTER_ID == "synthetic-agent-data-ge-f494f36b"
print("PASS contract")