# ADAPT · sql-agent-tasks-and-exe-31fdd585

BASE: `complex-sql-analysis-an-0e9c0c3c@1.0.1` · origin project `65`

The `base/` directory is immutable source material. Do not edit it. Implement the derivative only in `work/`.

## Adaptation intent

Directly covers complex SQL analysis and data preparation. It can supply executable SQL scenarios and expected-result fixtures for SQL-oriented agent trajectories and benchmark verification. BUILD29_STAGE3A=ADAPT_REQUIRED. ACTUAL_EVIDENCE: core.py использует настоящий sqlite3, создает SQL с CTE, JOIN, window functions, GROUP BY и исполняет запросы над таблицами; pandas используется для подготовки/валидации входов. Но agent-generated SQL tasks и benchmark oracle contract не показаны.. REQUIRED_PROOF: Создать локальную SQL fixture database и выполнить реальные CREATE/INSERT/SELECT операции через sqlite3.; Выполнить benchmark query с JOIN, aggregation и/или window function и проверить exact expected rows.; Передать SQL как результат agent task и выполнить его через тот же реальный database engine.; Сравнить agent query result с canonical oracle result независимо от текстового совпадения SQL.; Проверить syntax/runtime/wrong-result failure cases и классифицировать их отдельно.; Сохранить query, parameters, expected result и actual result в reproducible benchmark artifact.. SQL execution доказан непосредственно, однако vacancy capability требует превратить его в agent task/oracle framework с эталонными результатами и проверкой сгенерированных запросов.

## Required preservation

- source provenance and version
- declared runtime contract unless ProjectSpec explicitly changes it
- existing behavioral tests as regression inputs