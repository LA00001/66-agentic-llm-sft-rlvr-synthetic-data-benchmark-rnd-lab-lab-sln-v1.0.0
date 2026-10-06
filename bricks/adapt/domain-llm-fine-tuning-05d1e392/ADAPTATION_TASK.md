# ADAPT · domain-llm-fine-tuning-05d1e392

BASE: `nlp-llm-fine-tuning-and-5ad208ff@1.0.1` · origin project `65`

The `base/` directory is immutable source material. Do not edit it. Implement the derivative only in `work/`.

## Adaptation intent

Directly covers NLP/LLM post-training with LoRA and SFT. Project-owned integration will specialize datasets to agent trajectories containing dialogue turns, tool calls, observations and final answers. BUILD29_STAGE3A=ADAPT_REQUIRED. ACTUAL_EVIDENCE: core.py реально импортирует torch, transformers и PEFT, строит GPT2LMHeadModel, tokenizer и LoRA/PromptTuning adapter; есть supervised labels для prompt/response. Но показанные данные не являются agent dialogue/tool-call trajectories и не доказывают vacancy-specific SFT format.. REQUIRED_PROOF: Запустить реальный PyTorch forward/backward training step на Transformers causal LM и подтвердить finite loss и обновление trainable параметров.; Создать PEFT LoraConfig, применить get_peft_model и проверить, что обучаемыми являются LoRA-параметры, а base-параметры ограничены согласно конфигурации.; Выполнить SFT на наборе структурированных dialogue trajectories с user/assistant/tool_call/tool_result turns и проверить корректное masking labels.; Сохранить и повторно загрузить LoRA adapter, затем получить эквивалентный inference result на фиксированном input.; Сравнить baseline и post-SFT метрику на фиксированном eval-наборе и сохранить machine-readable before/after artifact.; Проверить Transformers tokenizer/model serialization и воспроизводимость при фиксированном seed.. Базовый LoRA/SFT механизм реален, но capability шире доказанного донора: нужны доменные agent trajectories, структурированные tool calls и измеримый before/after результат.

## Required preservation

- source provenance and version
- declared runtime contract unless ProjectSpec explicitly changes it
- existing behavioral tests as regression inputs