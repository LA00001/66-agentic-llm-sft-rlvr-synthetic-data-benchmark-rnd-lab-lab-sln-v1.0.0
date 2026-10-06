# ADAPT · project-owned-end-to-en-f490927d

BASE: `project-owned-docker-pa-ffcf750f@1.0.1` · origin project `65`

The `base/` directory is immutable source material. Do not edit it. Implement the derivative only in `work/`.

## Adaptation intent

Existing project-owned packaging/integration infrastructure is a useful donor, but this vacancy-specific project must integrate its own agent runtime, synthetic-data generator, SFT/RLVR training, benchmark runner, checkpoints, metrics and reproducible experiment outputs rather than merely reuse another candidate runtime. BUILD29_STAGE3A=ADAPT_REQUIRED. ACTUAL_EVIDENCE: core.py содержит реальный FastAPI app, typed Pydantic request, /health и /infer, sqlite3, настоящий SparkSession local[1], logging и Dockerfile generation; requirements включают fastapi, uvicorn и pyspark. Но это другой candidate runtime и не интегрирует текущие SFT/RLVR/synthetic-data/benchmark components.. REQUIRED_PROOF: Запустить проект через Python entrypoint и выполнить end-to-end путь synthetic data → SFT/RLVR artifact → benchmark evaluation без ручного вмешательства.; Запустить реальный FastAPI app локально и проверить /health HTTP 200 и типизированный inference/experiment endpoint.; Проверить Python dependency preflight и импорт ключевых runtime modules перед стартом pipeline.; Сохранить run_id, config, seeds, input fingerprints, checkpoint identifiers и итоговые metrics в experiment artifact.; Повторить один фиксированный run и проверить воспроизводимость ключевых output metrics/artifact hashes в допустимых пределах.; Проверить pytest integration test, который поднимает или вызывает локальный service path и валидирует end-to-end response contract.. Runtime и service patterns полезны, однако vacancy-specific end-to-end graph должен быть заново собран и доказан без переноса чужого project behavior как готового результата.

## Required preservation

- source provenance and version
- declared runtime contract unless ProjectSpec explicitly changes it
- existing behavioral tests as regression inputs