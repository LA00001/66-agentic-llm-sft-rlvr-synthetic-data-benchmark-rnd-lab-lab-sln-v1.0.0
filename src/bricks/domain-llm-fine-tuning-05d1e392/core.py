import base64
import io
import json
import math
import random
from typing import Any, Dict, List, Tuple

import torch
from peft import LoraConfig, TaskType, get_peft_model, get_peft_model_state_dict, set_peft_model_state_dict
from tokenizers import Tokenizer
from tokenizers.models import WordLevel
from tokenizers.pre_tokenizers import Whitespace
from transformers import GPT2Config, GPT2LMHeadModel, PreTrainedTokenizerFast

SPECIAL = ["<pad>", "<bos>", "<eos>", "<unk>", "<user>", "<assistant>", "<tool_call>", "<tool_result>"]
DEFAULT_TRAJECTORIES = [
    {
        "turns": [
            {"role": "user", "content": "find orders for customer alice"},
            {"role": "assistant", "content": "i will query orders"},
            {"role": "tool_call", "content": "sql_select customer alice"},
            {"role": "tool_result", "content": "orders 17 23"},
            {"role": "assistant", "content": "alice has orders 17 23"}
        ]
    },
    {
        "turns": [
            {"role": "user", "content": "check invoice total"},
            {"role": "assistant", "content": "i will calculate invoice"},
            {"role": "tool_call", "content": "calculator_sum 40 2"},
            {"role": "tool_result", "content": "42"},
            {"role": "assistant", "content": "invoice total is 42"}
        ]
    },
    {
        "turns": [
            {"role": "user", "content": "inspect server status"},
            {"role": "assistant", "content": "i will inspect status"},
            {"role": "tool_call", "content": "status_check api"},
            {"role": "tool_result", "content": "api healthy"},
            {"role": "assistant", "content": "api is healthy"}
        ]
    }
]


def _seed(seed: int) -> None:
    random.seed(seed)
    torch.manual_seed(seed)
    torch.use_deterministic_algorithms(True)


def _validate_trajectories(value: Any) -> List[Dict[str, Any]]:
    if not isinstance(value, list) or not value:
        raise ValueError("trajectories must be a non-empty list")
    if len(value) > 16:
        raise ValueError("trajectories limited to 16")
    required_roles = {"user", "assistant", "tool_call", "tool_result"}
    result = []
    for trajectory in value:
        if not isinstance(trajectory, dict) or not isinstance(trajectory.get("turns"), list):
            raise ValueError("each trajectory must contain turns")
        turns = trajectory["turns"]
        if len(turns) < 5 or len(turns) > 16:
            raise ValueError("each trajectory must contain 5..16 turns")
        roles = []
        clean = []
        for turn in turns:
            if not isinstance(turn, dict):
                raise ValueError("turn must be an object")
            role = turn.get("role")
            content = turn.get("content")
            if role not in required_roles or not isinstance(content, str) or not content.strip():
                raise ValueError("turn requires supported role and non-empty content")
            if len(content) > 300:
                raise ValueError("turn content too long")
            roles.append(role)
            clean.append({"role": role, "content": content.strip().lower()})
        if not required_roles.issubset(set(roles)) or roles[-1] != "assistant":
            raise ValueError("trajectory must include user/assistant/tool_call/tool_result and end with assistant")
        result.append({"turns": clean})
    return result


def _words(text: str) -> List[str]:
    return [part for part in text.replace("\n", " ").split(" ") if part]


def _build_tokenizer(trajectories: List[Dict[str, Any]]) -> PreTrainedTokenizerFast:
    observed = set()
    for trajectory in trajectories:
        for turn in trajectory["turns"]:
            observed.update(_words(turn["content"]))
    vocab_tokens = SPECIAL + sorted(token for token in observed if token not in SPECIAL)
    vocab = {token: index for index, token in enumerate(vocab_tokens)}
    backend = Tokenizer(WordLevel(vocab=vocab, unk_token="<unk>"))
    backend.pre_tokenizer = Whitespace()
    return PreTrainedTokenizerFast(
        tokenizer_object=backend,
        pad_token="<pad>",
        bos_token="<bos>",
        eos_token="<eos>",
        unk_token="<unk>"
    )


def _encode(trajectory: Dict[str, Any], tokenizer: PreTrainedTokenizerFast, max_length: int) -> Tuple[List[int], List[int], List[str]]:
    ids = [tokenizer.convert_tokens_to_ids("<bos>")]
    labels = [-100]
    supervised_roles = []
    for turn in trajectory["turns"]:
        marker = "<" + turn["role"] + ">"
        marker_id = tokenizer.convert_tokens_to_ids(marker)
        content_ids = tokenizer.encode(turn["content"], add_special_tokens=False)
        ids.append(marker_id)
        labels.append(-100)
        ids.extend(content_ids)
        if turn["role"] in {"assistant", "tool_call"}:
            labels.extend(content_ids)
            supervised_roles.extend([turn["role"]] * len(content_ids))
        else:
            labels.extend([-100] * len(content_ids))
    eos_id = tokenizer.convert_tokens_to_ids("<eos>")
    ids.append(eos_id)
    labels.append(eos_id)
    supervised_roles.append("assistant")
    if len(ids) > max_length:
        raise ValueError("max_length too small for trajectory")
    return ids, labels, supervised_roles


def _batch(trajectories: List[Dict[str, Any]], tokenizer: PreTrainedTokenizerFast, max_length: int):
    encoded = [_encode(item, tokenizer, max_length) for item in trajectories]
    width = max(len(item[0]) for item in encoded)
    pad = tokenizer.pad_token_id
    input_rows, label_rows, mask_rows = [], [], []
    for ids, labels, _ in encoded:
        extra = width - len(ids)
        input_rows.append(ids + [pad] * extra)
        label_rows.append(labels + [-100] * extra)
        mask_rows.append([1] * len(ids) + [0] * extra)
    return (
        torch.tensor(input_rows, dtype=torch.long),
        torch.tensor(mask_rows, dtype=torch.long),
        torch.tensor(label_rows, dtype=torch.long),
        encoded
    )


def _config(vocab_size: int, max_length: int) -> GPT2Config:
    return GPT2Config(
        vocab_size=vocab_size,
        n_positions=max_length + 8,
        n_ctx=max_length + 8,
        n_embd=32,
        n_layer=1,
        n_head=2,
        bos_token_id=1,
        eos_token_id=2,
        pad_token_id=0,
        embd_pdrop=0.0,
        resid_pdrop=0.0,
        attn_pdrop=0.0,
        use_cache=False
    )


def _lora_config() -> LoraConfig:
    return LoraConfig(
        task_type=TaskType.CAUSAL_LM,
        r=4,
        lora_alpha=8,
        lora_dropout=0.0,
        bias="none",
        target_modules=["c_attn"]
    )


def _loss(model, input_ids, attention_mask, labels) -> float:
    model.eval()
    with torch.no_grad():
        value = model(input_ids=input_ids, attention_mask=attention_mask, labels=labels).loss
    return float(value.detach().cpu())


def _logits(model, input_ids, attention_mask) -> torch.Tensor:
    model.eval()
    with torch.no_grad():
        return model(input_ids=input_ids, attention_mask=attention_mask).logits.detach().cpu()


def execute(payload):
    if payload is None:
        payload = {}
    if not isinstance(payload, dict):
        raise ValueError("payload must be an object")
    seed = payload.get("seed", 17)
    steps = payload.get("steps", 12)
    learning_rate = payload.get("learning_rate", 0.08)
    max_length = payload.get("max_length", 96)
    if not isinstance(seed, int) or seed < 0 or seed > 1000000:
        raise ValueError("seed must be an integer in 0..1000000")
    if not isinstance(steps, int) or steps < 1 or steps > 30:
        raise ValueError("steps must be in 1..30")
    if not isinstance(learning_rate, (int, float)) or not 0 < float(learning_rate) <= 0.2:
        raise ValueError("learning_rate must be in (0, 0.2]")
    if not isinstance(max_length, int) or max_length < 32 or max_length > 256:
        raise ValueError("max_length must be in 32..256")
    trajectories = _validate_trajectories(payload.get("trajectories", DEFAULT_TRAJECTORIES))
    _seed(seed)
    tokenizer = _build_tokenizer(trajectories)
    input_ids, attention_mask, labels, encoded = _batch(trajectories, tokenizer, max_length)
    config = _config(len(tokenizer), max_length)
    base_model = GPT2LMHeadModel(config)

    base_buffer = io.BytesIO()
    torch.save(base_model.state_dict(), base_buffer)
    base_bytes = base_buffer.getvalue()
    tokenizer_json = tokenizer.backend_tokenizer.to_str()

    model = get_peft_model(base_model, _lora_config())
    trainable = [(name, parameter) for name, parameter in model.named_parameters() if parameter.requires_grad]
    frozen = [name for name, parameter in model.named_parameters() if not parameter.requires_grad]
    if not trainable or not all("lora_" in name for name, _ in trainable):
        raise RuntimeError("unexpected PEFT trainable parameter set")

    baseline_loss = _loss(model, input_ids, attention_mask, labels)
    before_params = {name: parameter.detach().clone() for name, parameter in trainable}
    optimizer = torch.optim.AdamW([parameter for _, parameter in trainable], lr=float(learning_rate))
    training_losses = []
    gradient_seen = False
    model.train()
    for _ in range(steps):
        optimizer.zero_grad(set_to_none=True)
        output = model(input_ids=input_ids, attention_mask=attention_mask, labels=labels)
        loss = output.loss
        if not torch.isfinite(loss):
            raise RuntimeError("non-finite training loss")
        loss.backward()
        if any(parameter.grad is not None and torch.isfinite(parameter.grad).all() and float(parameter.grad.abs().sum()) > 0 for _, parameter in trainable):
            gradient_seen = True
        optimizer.step()
        training_losses.append(float(loss.detach().cpu()))
    post_loss = _loss(model, input_ids, attention_mask, labels)
    changed = [name for name, parameter in trainable if not torch.equal(before_params[name], parameter.detach())]
    if not gradient_seen or not changed:
        raise RuntimeError("training did not update LoRA parameters")

    adapter_state = {key: value.detach().cpu() for key, value in get_peft_model_state_dict(model).items()}
    adapter_buffer = io.BytesIO()
    torch.save(adapter_state, adapter_buffer)
    adapter_bytes = adapter_buffer.getvalue()

    fixed_ids = input_ids[:1]
    fixed_mask = attention_mask[:1]
    trained_logits = _logits(model, fixed_ids, fixed_mask)

    restored_base_state = torch.load(io.BytesIO(base_bytes), map_location="cpu", weights_only=True)
    restored_base = GPT2LMHeadModel(config)
    restored_base.load_state_dict(restored_base_state)
    restored = get_peft_model(restored_base, _lora_config())
    restored_adapter_state = torch.load(io.BytesIO(adapter_bytes), map_location="cpu", weights_only=True)
    set_peft_model_state_dict(restored, restored_adapter_state)
    restored_logits = _logits(restored, fixed_ids, fixed_mask)
    reload_max_abs_diff = float((trained_logits - restored_logits).abs().max())

    restored_backend = Tokenizer.from_str(tokenizer_json)
    restored_tokenizer = PreTrainedTokenizerFast(
        tokenizer_object=restored_backend,
        pad_token="<pad>",
        bos_token="<bos>",
        eos_token="<eos>",
        unk_token="<unk>"
    )
    tokenization_equal = restored_tokenizer.encode("find orders for customer alice", add_special_tokens=False) == tokenizer.encode("find orders for customer alice", add_special_tokens=False)

    supervised_count = int((labels != -100).sum().item())
    masked_count = int((labels == -100).sum().item())
    tool_call_supervised = 0
    assistant_supervised = 0
    for _, _, roles in encoded:
        tool_call_supervised += sum(1 for role in roles if role == "tool_call")
        assistant_supervised += sum(1 for role in roles if role == "assistant")

    trainable_count = sum(parameter.numel() for _, parameter in trainable)
    total_count = sum(parameter.numel() for parameter in model.parameters())
    before_after = {
        "metric": "supervised_token_cross_entropy",
        "baseline": baseline_loss,
        "post_sft": post_loss,
        "delta": post_loss - baseline_loss,
        "improved": post_loss < baseline_loss
    }
    artifact_json = json.dumps(before_after, sort_keys=True, separators=(",", ":"))

    return {
        "scope": "LOCAL",
        "technology": {
            "framework": "PyTorch",
            "model_library": "Transformers",
            "adapter_library": "PEFT",
            "adapter": "LoRA",
            "training": "SFT"
        },
        "configuration": {
            "seed": seed,
            "steps": steps,
            "learning_rate": float(learning_rate),
            "max_length": max_length,
            "architecture": "GPT2LMHeadModel",
            "n_layer": config.n_layer,
            "n_head": config.n_head,
            "n_embd": config.n_embd,
            "vocab_size": config.vocab_size,
            "lora_r": 4,
            "lora_alpha": 8,
            "lora_target_modules": ["c_attn"],
            "supervised_roles": ["assistant", "tool_call"]
        },
        "training": {
            "finite_losses": all(math.isfinite(value) for value in training_losses),
            "losses": training_losses,
            "gradient_seen": gradient_seen,
            "updated_trainable_parameters": sorted(changed)
        },
        "metrics": before_after,
        "before_after_artifact": artifact_json,
        "label_masking": {
            "supervised_tokens": supervised_count,
            "masked_tokens": masked_count,
            "assistant_supervised_tokens": assistant_supervised,
            "tool_call_supervised_tokens": tool_call_supervised,
            "user_and_tool_result_masked": True
        },
        "trainable_parameters": {
            "names": sorted(name for name, _ in trainable),
            "trainable_count": trainable_count,
            "total_count": total_count,
            "fraction": trainable_count / total_count,
            "all_trainable_are_lora": all("lora_" in name for name, _ in trainable),
            "frozen_parameter_count": len(frozen)
        },
        "serialization": {
            "model_state_bytes": len(base_bytes),
            "tokenizer_json_bytes": len(tokenizer_json.encode("utf-8")),
            "adapter_state_bytes": len(adapter_bytes),
            "tokenization_equal_after_reload": tokenization_equal,
            "adapter_inference_max_abs_diff": reload_max_abs_diff,
            "adapter_inference_equivalent": reload_max_abs_diff <= 1e-6,
            "adapter_artifact_b64": base64.b64encode(adapter_bytes).decode("ascii")
        },
        "dataset": {
            "trajectory_count": len(trajectories),
            "roles_present": sorted({turn["role"] for trajectory in trajectories for turn in trajectory["turns"]}),
            "contains_tool_calls": True,
            "contains_tool_results": True,
            "final_answers_present": all(trajectory["turns"][-1]["role"] == "assistant" for trajectory in trajectories)
        }
    }
