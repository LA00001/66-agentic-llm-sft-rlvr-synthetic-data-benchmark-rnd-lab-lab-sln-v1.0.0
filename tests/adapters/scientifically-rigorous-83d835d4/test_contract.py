from pathlib import Path
import importlib.util

p = Path.cwd() / "src" / "adapters" / "scientifically-rigorous-83d835d4" / "core.py"
spec = importlib.util.spec_from_file_location("adapter", p)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
assert m.SOURCE_CONTRACT == "foundry.analytics.ab_testing.v1"
assert m.TARGET_CONTRACT == "foundry.candidate.synthetic-agent-data-ge-5456d7a2.v1"
assert m.ADAPTER_ID == "scientifically-rigorous-83d835d4"
print("PASS contract")