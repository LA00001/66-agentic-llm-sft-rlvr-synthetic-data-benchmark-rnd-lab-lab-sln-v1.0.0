import importlib.util
import json
from pathlib import Path

TARGET = "domain-llm-fine-tuning-05d1e392"
path = Path("src") / "bricks" / TARGET / "core.py"
spec = importlib.util.spec_from_file_location("brick_core_contract", path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

payload = {
    "seed": 23,
    "steps": 6,
    "learning_rate": 0.08,
    "trajectories": [
        {"turns": [
            {"role": "user", "content": "find account balance"},
            {"role": "assistant", "content": "i will query account"},
            {"role": "tool_call", "content": "sql_balance account 7"},
            {"role": "tool_result", "content": "balance 900"},
            {"role": "assistant", "content": "account balance is 900"}
        ]},
        {"turns": [
            {"role": "user", "content": "calculate tax"},
            {"role": "assistant", "content": "i will calculate tax"},
            {"role": "tool_call", "content": "calculator_tax 100"},
            {"role": "tool_result", "content": "tax 20"},
            {"role": "assistant", "content": "tax is 20"}
        ]}
    ]
}
result = module.execute(payload)
required = {"scope", "technology", "configuration", "training", "metrics", "before_after_artifact", "label_masking", "trainable_parameters", "serialization", "dataset"}
assert set(result) == required
assert result["configuration"]["seed"] == 23
assert result["configuration"]["architecture"] == "GPT2LMHeadModel"
assert result["configuration"]["supervised_roles"] == ["assistant", "tool_call"]
artifact = json.loads(result["before_after_artifact"])
assert artifact["metric"] == "supervised_token_cross_entropy"
assert artifact["baseline"] == result["metrics"]["baseline"]
assert artifact["post_sft"] == result["metrics"]["post_sft"]
assert artifact["improved"] is True
assert result["serialization"]["model_state_bytes"] > 0
assert result["serialization"]["tokenizer_json_bytes"] > 0
assert result["serialization"]["adapter_state_bytes"] > 0
assert len(result["serialization"]["adapter_artifact_b64"]) > 20
assert result["serialization"]["tokenization_equal_after_reload"] is True
assert result["serialization"]["adapter_inference_equivalent"] is True
assert result["serialization"]["adapter_inference_max_abs_diff"] <= 1e-6
assert result["dataset"]["contains_tool_calls"] is True
assert result["dataset"]["contains_tool_results"] is True
assert result["dataset"]["final_answers_present"] is True
