import base64
import io
import math
import re
from typing import Any, Dict, List, Tuple

import torch
from peft import (
    LoraConfig,
    PromptTuningConfig,
    PromptTuningInit,
    TaskType,
    get_peft_model,
    get_peft_model_state_dict,
    set_peft_model_state_dict,
)
from tokenizers import Tokenizer
from tokenizers.models import WordLevel
from tokenizers.normalizers import Lowercase
from tokenizers.pre_tokenizers import Whitespace
from transformers import GPT2Config, GPT2LMHeadModel, PreTrainedTokenizerFast


_SPECIAL_TOKENS = ["<pad>", "<bos>", "<sep>", "<eos>", "<unk>"]
_DEFAULT_TRAIN = [
    {"prompt": "Оцени банковский риск рост просрочки", "response": "риск высокий"},
    {"prompt": "Что означает рост ключевой ставки", "response": "стоимость фондирования растет"},
    {"prompt": "План расходов выше факта", "response": "есть экономия бюджета"},
]
_DEFAULT_EVAL = [
    {"prompt": "Оцени банковский риск рост просрочки", "response": "риск высокий"},
    {"prompt": "Что означает рост ключевой ставки", "response": "стоимость фондирования растет"},
]


def _tokens(text: str) -> List[str]:
    return re.findall(r"\w+|[^\w\s]", text.lower(), flags=re.UNICODE)


def _validate_examples(value: Any, name: str) -> List[Dict[str, str]]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{name} must be a non-empty list")
    if len(value) > 32:
        raise ValueError(f"{name} is limited to 32 examples")
    result = []
    for item in value:
        if not isinstance(item, dict):
            raise ValueError(f"{name} items must be objects")
        prompt = item.get("prompt")
        response = item.get("response")
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError(f"{name}.prompt must be a non-empty string")
        if not isinstance(response, str) or not response.strip():
            raise ValueError(f"{name}.response must be a non-empty string")
        if len(prompt) > 500 or len(response) > 500:
            raise ValueError("example text is limited to 500 characters per field")
        result.append({"prompt": prompt.strip(), "response": response.strip()})
    return result


def _build_vocab(train: List[Dict[str, str]], eval_data: List[Dict[str, str]]) -> Tuple[List[str], Dict[str, int]]:
    observed = set()
    for item in train + eval_data:
        observed.update(_tokens(item["prompt"]))
        observed.update(_tokens(item["response"]))
    vocab = _SPECIAL_TOKENS + sorted(token for token in observed if token not in _SPECIAL_TOKENS)
    return vocab, {token: index for index, token in enumerate(vocab)}


def _build_tokenizer(token_to_id: Dict[str, int]) -> PreTrainedTokenizerFast:
    backend = Tokenizer(WordLevel(vocab=token_to_id, unk_token="<unk>"))
    backend.normalizer = Lowercase()
    backend.pre_tokenizer = Whitespace()
    return PreTrainedTokenizerFast(
        tokenizer_object=backend,
        pad_token="<pad>",
        bos_token="<bos>",
        sep_token="<sep>",
        eos_token="<eos>",
        unk_token="<unk>",
    )


def _encode_example(
    item: Dict[str, str], tokenizer: PreTrainedTokenizerFast, max_length: int
) -> Tuple[List[int], List[int]]:
    prompt_ids = tokenizer.encode(item["prompt"], add_special_tokens=False)
    response_ids = tokenizer.encode(item["response"], add_special_tokens=False)
    ids = [tokenizer.bos_token_id] + prompt_ids + [tokenizer.sep_token_id] + response_ids + [tokenizer.eos_token_id]
    labels = [-100] * (2 + len(prompt_ids)) + response_ids + [tokenizer.eos_token_id]
    ids = ids[:max_length]
    labels = labels[:max_length]
    if not any(label != -100 for label in labels[1:]):
        raise ValueError("max_length truncates all supervised response tokens")
    return ids, labels


def _batch(
    examples: List[Dict[str, str]], tokenizer: PreTrainedTokenizerFast, max_length: int
) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
    encoded = [_encode_example(item, tokenizer, max_length) for item in examples]
    width = max(len(ids) for ids, _ in encoded)
    pad_id = tokenizer.pad_token_id
    input_rows = []
    label_rows = []
    mask_rows = []
    for ids, labels in encoded:
        padding = width - len(ids)
        input_rows.append(ids + [pad_id] * padding)
        label_rows.append(labels + [-100] * padding)
        mask_rows.append([1] * len(ids) + [0] * padding)
    return (
        torch.tensor(input_rows, dtype=torch.long),
        torch.tensor(mask_rows, dtype=torch.long),
        torch.tensor(label_rows, dtype=torch.long),
    )


def _base_model(vocab_size: int, max_length: int, seed: int) -> GPT2LMHeadModel:
    torch.manual_seed(seed)
    config = GPT2Config(
        vocab_size=vocab_size,
        n_positions=max_length + 8,
        n_ctx=max_length + 8,
        n_embd=32,
        n_layer=1,
        n_head=2,
        bos_token_id=1,
        eos_token_id=3,
        pad_token_id=0,
        embd_pdrop=0.0,
        resid_pdrop=0.0,
        attn_pdrop=0.0,
        use_cache=False,
    )
    return GPT2LMHeadModel(config)


def _adapter_config(method: str):
    if method == "lora":
        return LoraConfig(
            task_type=TaskType.CAUSAL_LM,
            r=4,
            lora_alpha=8,
            lora_dropout=0.0,
            bias="none",
            target_modules=["c_attn"],
        )
    if method == "prompt_tuning":
        return PromptTuningConfig(
            task_type=TaskType.CAUSAL_LM,
            prompt_tuning_init=PromptTuningInit.RANDOM,
            num_virtual_tokens=4,
        )
    raise ValueError("method must be 'lora' or 'prompt_tuning'")


def _adapter_config_summary(method: str) -> Dict[str, Any]:
    if method == "lora":
        return {
            "peft_type": "LORA",
            "task_type": "CAUSAL_LM",
            "r": 4,
            "lora_alpha": 8,
            "lora_dropout": 0.0,
            "bias": "none",
            "target_modules": ["c_attn"],
        }
    return {
        "peft_type": "PROMPT_TUNING",
        "task_type": "CAUSAL_LM",
        "prompt_tuning_init": "RANDOM",
        "num_virtual_tokens": 4,
    }


def _mean_loss(model, batch: Tuple[torch.Tensor, torch.Tensor, torch.Tensor]) -> float:
    input_ids, attention_mask, labels = batch
    model.train(False)
    with torch.no_grad():
        loss = model(input_ids=input_ids, attention_mask=attention_mask, labels=labels).loss
    return float(loss.detach().cpu())


def _evaluate(model, batch: Tuple[torch.Tensor, torch.Tensor, torch.Tensor]) -> Tuple[float, float]:
    input_ids, attention_mask, labels = batch
    model.train(False)
    with torch.no_grad():
        output = model(input_ids=input_ids, attention_mask=attention_mask, labels=labels)
    predictions = output.logits[:, :-1, :].argmax(dim=-1)
    targets = labels[:, 1:]
    # BUILD142_PEFT_PROMPT_TUNING_ALIGNMENT: PEFT prompt tuning prepends virtual-token logits.
    # Keep only predictions aligned to the original supervised label sequence.
    if predictions.shape[1] != targets.shape[1]:
        if predictions.shape[1] < targets.shape[1]:
            raise RuntimeError(f"prediction/target sequence mismatch: {predictions.shape[1]} < {targets.shape[1]}")
        predictions = predictions[:, -targets.shape[1]:]
    mask = targets.ne(-100)
    correct = predictions.eq(targets) & mask
    denominator = int(mask.sum().item())
    accuracy = float(correct.sum().item() / denominator) if denominator else 0.0
    return float(output.loss.detach().cpu()), accuracy


def _control_inference(
    model, prompt: str, tokenizer: PreTrainedTokenizerFast, max_length: int
) -> Tuple[int, torch.Tensor]:
    prompt_ids = tokenizer.encode(prompt, add_special_tokens=False)[: max_length - 2]
    prefix = [tokenizer.bos_token_id] + prompt_ids + [tokenizer.sep_token_id]
    input_ids = torch.tensor([prefix], dtype=torch.long)
    attention_mask = torch.ones_like(input_ids)
    model.train(False)
    with torch.no_grad():
        logits = model(input_ids=input_ids, attention_mask=attention_mask).logits[0, -1].detach().cpu()
    return int(logits.argmax().item()), logits


def execute(payload):
    if payload is None:
        payload = {}
    if not isinstance(payload, dict):
        raise ValueError("payload must be a dictionary")

    method = payload.get("method", "lora")
    if method not in {"lora", "prompt_tuning"}:
        raise ValueError("method must be 'lora' or 'prompt_tuning'")

    seed = payload.get("seed", 17)
    steps = payload.get("steps", 4)
    learning_rate = payload.get("learning_rate", 0.05)
    max_length = payload.get("max_length", 48)
    if not isinstance(seed, int) or not (0 <= seed <= 2_147_483_647):
        raise ValueError("seed must be a non-negative 32-bit integer")
    if not isinstance(steps, int) or not (1 <= steps <= 32):
        raise ValueError("steps must be an integer from 1 to 32")
    if not isinstance(learning_rate, (int, float)) or not (0.000001 <= float(learning_rate) <= 1.0):
        raise ValueError("learning_rate must be between 1e-6 and 1.0")
    if not isinstance(max_length, int) or not (12 <= max_length <= 64):
        raise ValueError("max_length must be an integer from 12 to 64")

    train_data = _validate_examples(payload.get("train_examples", _DEFAULT_TRAIN), "train_examples")
    eval_data = _validate_examples(payload.get("eval_examples", _DEFAULT_EVAL), "eval_examples")
    vocab, token_to_id = _build_vocab(train_data, eval_data)
    tokenizer = _build_tokenizer(token_to_id)
    train_batch = _batch(train_data, tokenizer, max_length)
    eval_batch = _batch(eval_data, tokenizer, max_length)

    base = _base_model(len(vocab), max_length, seed)
    model = get_peft_model(base, _adapter_config(method))
    trainable = [(name, parameter) for name, parameter in model.named_parameters() if parameter.requires_grad]
    if not trainable:
        raise RuntimeError("PEFT produced no trainable parameters")

    before = {name: parameter.detach().cpu().clone() for name, parameter in trainable}
    initial_train_loss = _mean_loss(model, train_batch)
    optimizer = torch.optim.AdamW([parameter for _, parameter in trainable], lr=float(learning_rate))

    model.train()
    step_losses = []
    for _ in range(steps):
        optimizer.zero_grad(set_to_none=True)
        output = model(
            input_ids=train_batch[0],
            attention_mask=train_batch[1],
            labels=train_batch[2],
        )
        loss = output.loss
        if not torch.isfinite(loss):
            raise RuntimeError("non-finite training loss")
        loss.backward()
        optimizer.step()
        step_losses.append(float(loss.detach().cpu()))

    final_train_loss = _mean_loss(model, train_batch)
    changed = []
    for name, parameter in trainable:
        delta = parameter.detach().cpu() - before[name]
        norm = float(torch.linalg.vector_norm(delta).item())
        if norm > 0.0:
            changed.append((name, norm))
    parameter_changed = bool(changed)
    tracked_name = changed[0][0] if changed else trainable[0][0]
    update_norm = changed[0][1] if changed else 0.0

    eval_loss, token_accuracy = _evaluate(model, eval_batch)
    control_prompt = eval_data[0]["prompt"]
    original_token_id, original_logits = _control_inference(model, control_prompt, tokenizer, max_length)

    adapter_state = {
        name: tensor.detach().cpu().contiguous()
        for name, tensor in get_peft_model_state_dict(model).items()
    }
    buffer = io.BytesIO()
    torch.save(adapter_state, buffer)
    adapter_bytes = buffer.getvalue()
    artifact_b64 = base64.b64encode(adapter_bytes).decode("ascii")

    fresh_base = _base_model(len(vocab), max_length, seed)
    reloaded = get_peft_model(fresh_base, _adapter_config(method))
    loaded_state = torch.load(
        io.BytesIO(base64.b64decode(artifact_b64.encode("ascii"))),
        map_location="cpu",
        weights_only=True,
    )
    set_peft_model_state_dict(reloaded, loaded_state)
    reload_token_id, reload_logits = _control_inference(reloaded, control_prompt, tokenizer, max_length)
    reload_logit_max_abs_diff = float(torch.max(torch.abs(original_logits - reload_logits)).item())
    reload_match = bool(original_token_id == reload_token_id and reload_logit_max_abs_diff <= 1e-6)

    trainable_count = sum(parameter.numel() for _, parameter in trainable)
    total_count = sum(parameter.numel() for parameter in model.parameters())
    supervised_tokens = int(train_batch[2][:, 1:].ne(-100).sum().item())

    if not all(math.isfinite(value) for value in [initial_train_loss, final_train_loss, eval_loss]):
        raise RuntimeError("non-finite loss in result")

    return {
        "method": method,
        "pipeline": ["tokenizer", "dataset", "peft_adapter", "sft_train", "inference", "metric_evaluation", "artifact_reload"],
        "vocab": vocab,
        "dataset": {
            "tokenizer_backend": "tokenizers.WordLevel+transformers.PreTrainedTokenizerFast",
            "train_examples": len(train_data),
            "eval_examples": len(eval_data),
            "supervised_train_tokens": supervised_tokens,
        },
        "training": {
            "initial_train_loss": initial_train_loss,
            "final_train_loss": final_train_loss,
            "tracked_parameter": tracked_name,
            "parameter_changed": parameter_changed,
            "parameter_update_norm": update_norm,
            "changed_parameters": [name for name, _ in changed],
            "step_losses": step_losses,
            "trainable_parameters": trainable_count,
            "total_parameters": total_count,
        },
        "evaluation": {
            "loss": eval_loss,
            "token_accuracy": token_accuracy,
        },
        "inference": {
            "control_prompt": control_prompt,
            "predicted_token_id": original_token_id,
            "predicted_token": vocab[original_token_id],
        },
        "adapter_artifact": {
            "format": "peft_torch_state_dict",
            "file_name": "adapter_model.bin",
            "encoding": "base64",
            "adapter_config": _adapter_config_summary(method),
            "state_keys": sorted(adapter_state.keys()),
            "size_bytes": len(adapter_bytes),
            "data": artifact_b64,
        },
        "reload_verification": {
            "predicted_token_id": reload_token_id,
            "predicted_token": vocab[reload_token_id],
            "max_abs_logit_diff": reload_logit_max_abs_diff,
            "inference_match": reload_match,
        },
    }
