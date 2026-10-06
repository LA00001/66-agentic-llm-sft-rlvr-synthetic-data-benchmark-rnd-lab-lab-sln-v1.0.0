# Agentic LLM Sft Rlvr Synthetic Data Benchmark Rnd Lab

> LLM/DS платформа для NLP/LLM задач: PEFT/LoRA, PyTorch, SQL, FastAPI, Docker, pandas/numpy и Transformers. Live Execution подтверждает реальные запуски узлов, фактические input/output, тесты и воспроизводимый runtime. Архитектура включает agent orchestration, contract adapters, model serving, metrics, E2E integration и adapter reload.

**GitHub showcase:** `66-agentic-llm-sft-rlvr-synthetic-data-benchmark-rnd-lab-lab-sln-v1.0.0` · description `336/350` chars.

## What this repository demonstrates

- PyTorch + Transformers + PEFT/LoRA training loop with evaluation and adapter save/reload verification
- data preparation and analytical processing with pandas/numpy
- FastAPI serving layer and HTTP integration checks
- SQL/data-contract adapters and an executable capability graph
- automated unit/contract/integration tests plus local runtime receipts

## Architecture

The executable graph contains **14 nodes** and **15 edges**. See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the generated Mermaid view and node list.

## Quick start (Windows)

```bat
RUN_DEMO.cmd
```

The runtime manager resolves a project runtime, restores `requirements.txt`, starts the local portfolio application and opens the browser. The **Live Execution PRO** page shows the latest actual input → runtime → output receipts.

## Verified showcase run

After the Factory `BUILD + RUN + CAPTURE` gate passes, the screenshot below is captured from this exact public showcase directory at 67% browser zoom.

![Verified Live Execution](%D0%A3%D0%A1%D0%9F%D0%95%D0%A5/%D0%A3%D0%A1%D0%9F%D0%95%D0%A5.png)

Run smoke/tests with:

```bat
RUN_TESTS.cmd
```

## Repository layout

- `src/` — runnable application, bricks and adapters
- `tests/` — unit/contract/integration tests
- `bricks/` — materialized/reused brick sources required by the executable graph
- `skill-upgrades/` — isolated vacancy-skill proofs (when present)
- `foundry/` — compact execution graph/runtime contracts required by the demo
- `evidence/` — only the minimal proof manifests/materialization receipts needed for truthful runtime reuse
- `docs/PROOF_SUMMARY.md` — concise proof/results summary

## Truth / limitations

- This is a **portfolio prototype**, not production banking infrastructure and it contains no production banking data.
- Graph edges are architectural bindings. A RUN DEMO node can intentionally use an isolated smoke fixture; actual transfer is shown explicitly as `INPUT SOURCE = UPSTREAM_OUTPUT`.
- The PEFT/LoRA proof uses a **small locally initialized causal GPT-style model** to demonstrate the training mechanics; it does not claim production-scale pretrained LLM fine-tuning.
- Internal AI authoring prompts/responses, build caches, nested archives and machine-specific user paths are intentionally excluded from this public projection.

## Proof summary

See [`docs/PROOF_SUMMARY.md`](docs/PROOF_SUMMARY.md). The summary is derived from the candidate's durable receipts at export time; rerun the project to generate fresh local receipts on your machine.

---
Public projection source: `candidate-20261002-165427-agentic-llm-sft-rlvr-synthetic-data-benchmark-rnd-lab` · Factory `v41.3.4167.51 BUILD249_TEST262 PATCH_STAGE17_DURABLE_REQUEST_RESUME185`.

PF_SHOWCASE_NO_LICENSE_V1

PROPRIETARY SOURCE CODE — ALL RIGHTS RESERVED
NO LICENSE GRANTED

Copyright (c) 2026 Андрей / LA00001
All rights reserved.

This repository and all source code, binaries, documentation, data, assets, designs, algorithms, workflows, architecture, configuration, tests, generated artifacts, and other materials contained herein (the “Materials”) are proprietary and protected by applicable copyright and other intellectual property laws.

NO LICENSE OR PERMISSION IS GRANTED TO ANY PERSON OR ENTITY.

Except where such rights cannot lawfully be restricted, you are expressly prohibited from, in whole or in part:

- copying or reproducing the Materials;
- downloading the Materials for reuse;
- modifying, adapting, translating, or creating derivative works;
- redistributing, republishing, transmitting, mirroring, or hosting;
- sublicensing, selling, renting, leasing, assigning, or transferring;
- incorporating the Materials into another product, project, service, dataset, repository, model, system, or work;
- using the Materials for commercial or non-commercial purposes;
- using the Materials in production, research, education, training, benchmarking, or competitive analysis;
- using the Materials to train, fine-tune, evaluate, benchmark, develop, or improve artificial intelligence or machine-learning systems;
- extracting, scraping, indexing, mining, or systematically collecting the Materials;
- reverse engineering, decompiling, disassembling, or otherwise attempting to derive implementation details from compiled artifacts;
- removing or altering copyright, ownership, attribution, or proprietary notices;
- claiming authorship, ownership, or rights in the Materials.

Possession of, access to, or visibility of the Materials does not constitute permission or a license to use them.

Any permission must be granted separately and explicitly in a written agreement signed by the copyright owner.

No implied license, waiver, estoppel, patent license, trademark license, or other intellectual-property right is granted.

Unauthorized use is expressly prohibited.

ALL RIGHTS RESERVED.

---

ПРОПРИЕТАРНЫЙ ИСХОДНЫЙ КОД — ВСЕ ПРАВА ЗАЩИЩЕНЫ
ЛИЦЕНЗИЯ НЕ ПРЕДОСТАВЛЯЕТСЯ

Авторское право (c) 2026 Андрей / LA00001
Все права защищены.

Данный репозиторий, весь исходный код, бинарные файлы, документация, данные, материалы, дизайн, алгоритмы, рабочие процессы, архитектура, конфигурация, тесты, сгенерированные артефакты и иные содержащиеся здесь материалы (далее — «Материалы») являются проприетарными и охраняются применимым законодательством об авторском праве и иной интеллектуальной собственности.

НИКАКАЯ ЛИЦЕНЗИЯ ИЛИ РАЗРЕШЕНИЕ НИ ОДНОМУ ЛИЦУ ИЛИ ОРГАНИЗАЦИИ НЕ ПРЕДОСТАВЛЯЕТСЯ.

За исключением прав, ограничение которых прямо запрещено законом, полностью или частично запрещается:

- копировать или воспроизводить Материалы;
- скачивать Материалы для повторного использования;
- изменять, адаптировать, переводить или создавать производные произведения;
- распространять, повторно публиковать, передавать, зеркалировать или размещать Материалы;
- сублицензировать, продавать, сдавать в аренду, уступать или иным образом передавать права;
- включать Материалы в любой другой продукт, проект, сервис, набор данных, репозиторий, модель, систему или работу;
- использовать Материалы в коммерческих или некоммерческих целях;
- использовать Материалы в производстве, исследованиях, образовании, обучении, бенчмаркинге или конкурентном анализе;
- использовать Материалы для обучения, дообучения, оценки, тестирования, разработки или улучшения систем искусственного интеллекта или машинного обучения;
- извлекать, скрейпить, индексировать, майнить или систематически собирать Материалы;
- выполнять обратную разработку, декомпиляцию, дизассемблирование либо иным способом пытаться получить детали реализации из скомпилированных артефактов;
- удалять или изменять уведомления об авторском праве, праве собственности, авторстве или проприетарном характере;
- заявлять авторство, право собственности или иные права на Материалы.

Сам факт владения копией, доступа к Материалам или возможности их просмотра не означает предоставления разрешения или лицензии на их использование.

Любое разрешение должно быть предоставлено отдельно и явно в письменном соглашении, подписанном правообладателем.

Никакие подразумеваемые лицензии, отказы от прав, права по эстоппелю, патентные, товарные или иные права интеллектуальной собственности не предоставляются.

Несанкционированное использование прямо запрещено.

ВСЕ ПРАВА ЗАЩИЩЕНЫ.
