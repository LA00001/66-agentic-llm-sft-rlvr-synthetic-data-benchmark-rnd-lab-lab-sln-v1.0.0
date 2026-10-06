import importlib.util
import math
from pathlib import Path

TARGET = "domain-llm-fine-tuning-05d1e392"
path = Path("src") / "bricks" / TARGET / "core.py"
spec = importlib.util.spec_from_file_location("brick_core", path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

result = module.execute({"seed": 17, "steps": 8, "learning_rate": 0.08})
assert result["scope"] == "LOCAL"
assert result["technology"]["framework"] == "PyTorch"
assert result["technology"]["model_library"] == "Transformers"
assert result["technology"]["adapter_library"] == "PEFT"
assert result["technology"]["adapter"] == "LoRA"
assert result["training"]["finite_losses"] is True
assert result["training"]["gradient_seen"] is True
assert result["training"]["updated_trainable_parameters"]
assert all("lora_" in name for name in result["training"]["updated_trainable_parameters"])
assert math.isfinite(result["metrics"]["baseline"])
assert math.isfinite(result["metrics"]["post_sft"])
assert result["metrics"]["post_sft"] < result["metrics"]["baseline"]
assert result["trainable_parameters"]["all_trainable_are_lora"] is True
assert result["trainable_parameters"]["trainable_count"] < result["trainable_parameters"]["total_count"]
assert result["label_masking"]["supervised_tokens"] > 0
assert result["label_masking"]["masked_tokens"] > 0
assert result["label_masking"]["assistant_supervised_tokens"] > 0
assert result["label_masking"]["tool_call_supervised_tokens"] > 0
assert set(result["dataset"]["roles_present"]) == {"assistant", "tool_call", "tool_result", "user"}

try:
    module.execute({"trajectories": [{"turns": [{"role": "user", "content": "x"}]}]})
except ValueError:
    pass
else:
    raise AssertionError("invalid trajectory must be rejected")
