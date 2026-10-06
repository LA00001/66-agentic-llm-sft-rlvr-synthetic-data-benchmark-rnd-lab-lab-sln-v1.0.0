import importlib.util
import json
from pathlib import Path

TARGET = "domain-llm-fine-tuning-05d1e392"
path = Path("src") / "bricks" / TARGET / "core.py"
spec = importlib.util.spec_from_file_location("brick_core_integration", path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

payload = {
    "seed": 31,
    "steps": 10,
    "learning_rate": 0.08,
    "max_length": 96,
    "trajectories": [
        {"turns": [
            {"role": "user", "content": "show failed jobs"},
            {"role": "assistant", "content": "i will inspect jobs"},
            {"role": "tool_call", "content": "sql_jobs status failed"},
            {"role": "tool_result", "content": "jobs build7 build9"},
            {"role": "assistant", "content": "failed jobs are build7 build9"}
        ]},
        {"turns": [
            {"role": "user", "content": "compute average latency"},
            {"role": "assistant", "content": "i will calculate latency"},
            {"role": "tool_call", "content": "calculator_average 10 20 30"},
            {"role": "tool_result", "content": "average 20"},
            {"role": "assistant", "content": "average latency is 20"}
        ]},
        {"turns": [
            {"role": "user", "content": "check service health"},
            {"role": "assistant", "content": "i will inspect service"},
            {"role": "tool_call", "content": "health_check worker"},
            {"role": "tool_result", "content": "worker healthy"},
            {"role": "assistant", "content": "worker is healthy"}
        ]}
    ]
}
first = module.execute(payload)
second = module.execute(payload)
assert first["metrics"]["baseline"] == second["metrics"]["baseline"]
assert first["metrics"]["post_sft"] == second["metrics"]["post_sft"]
assert first["training"]["losses"] == second["training"]["losses"]
assert first["training"]["updated_trainable_parameters"] == second["training"]["updated_trainable_parameters"]
assert first["metrics"]["post_sft"] < first["metrics"]["baseline"]
assert first["serialization"]["adapter_inference_equivalent"] is True
assert first["serialization"]["tokenization_equal_after_reload"] is True
assert first["training"]["gradient_seen"] is True
assert first["trainable_parameters"]["all_trainable_are_lora"] is True
assert 0 < first["trainable_parameters"]["fraction"] < 1
assert first["label_masking"]["assistant_supervised_tokens"] > 0
assert first["label_masking"]["tool_call_supervised_tokens"] > 0
artifact = json.loads(first["before_after_artifact"])
assert artifact["delta"] < 0
assert artifact["improved"] is True
