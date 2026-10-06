# ADAPT · scientifically-rigorous-2d3b54ba

BASE: `ab-testing@1.0.0` · origin project `64`

The `base/` directory is immutable source material. Do not edit it. Implement the derivative only in `work/`.

## Adaptation intent

Directly provides experimentation and statistics and can serve as the controlled comparison layer for baseline-versus-SFT/RLVR experiments, confidence estimates and predefined acceptance criteria. BUILD29_STAGE3A=ADAPT_REQUIRED. ACTUAL_EVIDENCE: core.py реально выполняет pandas-фильтрацию, расчет control/treatment rates, pooled z-test, p-value, confidence interval и SRM-проверку. Но сам протокол формулирования гипотез, фиксированные метрики и экспериментальная дисциплина для LLM не представлены.. REQUIRED_PROOF: Сохранить experiment spec с гипотезой, primary metric, guardrails, baseline, treatment и заранее заданным acceptance criterion до запуска сравнения.; На реальном pandas DataFrame выполнить baseline-versus-treatment statistical comparison с p-value и confidence interval.; Проверить SRM/валидность разбиения и явно завершать эксперимент ошибкой при некорректном дизайне.; Повторить анализ на фиксированном dataset и подтвердить детерминированный machine-readable verdict.; Связать experiment artifact с конкретными baseline и trained checkpoint identifiers.. Статистический механизм доказан, но vacancy capability включает научную постановку эксперимента и выводы по LLM/SFT/RLVR; требуется адаптация протокола и доменных метрик.

## Required preservation

- source provenance and version
- declared runtime contract unless ProjectSpec explicitly changes it
- existing behavioral tests as regression inputs