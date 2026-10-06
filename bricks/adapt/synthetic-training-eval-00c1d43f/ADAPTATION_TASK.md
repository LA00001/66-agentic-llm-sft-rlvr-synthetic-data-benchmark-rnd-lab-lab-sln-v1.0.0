# ADAPT · synthetic-training-eval-00c1d43f

BASE: `data-quality@1.0.0` · origin project `64`

The `base/` directory is immutable source material. Do not edit it. Implement the derivative only in `work/`.

## Adaptation intent

The brick directly supplies data-quality and anomaly-oriented primitives, but LLM-specific controls such as trajectory validity, duplicate task detection, answer/oracle consistency, reward outliers and train/eval contamination require adaptation. BUILD29_STAGE3A=ADAPT_REQUIRED. ACTUAL_EVIDENCE: core.py реально применяет pandas DataFrame operations для duplicate/null/anomaly checks и quarantine_invalid. Но текущая схема относится к session/business данным и не содержит trajectory validity, semantic/task deduplication, train/eval contamination или LLM failure-oriented filters.. REQUIRED_PROOF: На реальном pandas DataFrame выполнить schema/null/duplicate/invalid-trajectory checks и проверить ожидаемые failed-row counts.; Выявить exact duplicate task/trajectory IDs и отделить их в quarantine DataFrame.; Проверить train/eval contamination по нормализованным task fingerprints и завершать проверку WARN/FAIL при пересечении.; Проверить answer-oracle consistency и удалить trajectories с противоречащим verifier verdict.; Выявить reward/length/error outliers и сохранить причины фильтрации по каждой записи.; Сформировать clean и quarantined dataset artifacts и проверить, что их объединение восстанавливает исходный набор без потерь IDs.. Pandas-based quality substrate доказан, но требуется существенная LLM/agent-specific адаптация правил и contamination controls.

## Required preservation

- source provenance and version
- declared runtime contract unless ProjectSpec explicitly changes it
- existing behavioral tests as regression inputs