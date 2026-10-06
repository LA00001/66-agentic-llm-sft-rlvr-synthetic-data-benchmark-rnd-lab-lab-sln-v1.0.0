from pathlib import Path
import importlib.util

p = Path.cwd() / "src" / "adapters" / "synthetic-training-eval-ae6d4440" / "core.py"
spec = importlib.util.spec_from_file_location("adapter", p)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
assert m.SOURCE_CONTRACT == "foundry.data.data_quality.v1"
assert m.TARGET_CONTRACT == "foundry.candidate.project-owned-docker-pa-ffcf750f.v1"
assert m.ADAPTER_ID == "synthetic-training-eval-ae6d4440"
print("PASS contract")