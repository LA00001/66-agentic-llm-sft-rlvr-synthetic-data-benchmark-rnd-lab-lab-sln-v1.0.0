# ADAPT · agentic-benchmark-harne-b447fbac

BASE: `evidence-registry@1.0.0` · origin project `64`

The `base/` directory is immutable source material. Do not edit it. Implement the derivative only in `work/`.

## Adaptation intent

The existing evidence/integrity/testing brick provides a suitable verification substrate, but vacancy-specific benchmark tasks, executable oracles, trajectory scoring and failure taxonomy require substantial project-owned adaptation. BUILD29_STAGE3A=ADAPT_REQUIRED. ACTUAL_EVIDENCE: evidence-registry реально проверяет наличие файлов и SHA-256 integrity manifest, но не реализует agent benchmarks, executable code/SQL oracles, trajectory scoring или failure taxonomy.. REQUIRED_PROOF: Через pytest выполнить benchmark suite минимум для code, SQL и tool-use задач с реальными pass/fail assertions.; Для code-задачи запустить candidate solution против детерминированных executable tests и записать oracle verdict.; Для SQL-задачи исполнить query в реальном SQL engine и сравнить фактический result set с expected oracle.; Для tool-use trajectory проверить последовательность tool calls, arguments, observations и финальный answer программными assertions.; Рассчитать per-domain и aggregate benchmark scores из фактических test outcomes.; Сохранить failure taxonomy и evidence manifest с checksum каждого benchmark artifact.. Integrity registry годится как substrate для evidence, но benchmark semantics необходимо построить поверх него; простой REUSE исказил бы фактическое содержание brick.

## Required preservation

- source provenance and version
- declared runtime contract unless ProjectSpec explicitly changes it
- existing behavioral tests as regression inputs