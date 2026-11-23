# Referência da stage-audit — checklist por camada

Detalhe da [Fase D do SKILL.md](../SKILL.md#fase-d--judgment-a-parte-que-não-se-mecaniza): o
checklist das camadas que saíram do corpo para devolver folga ao teto de 500 linhas. A regra de
aplicação (todas as sub-seções das camadas que a Stage inclui) continua no `SKILL.md`. Os itens
são **piso**, não teto.

## `adapters/inbound/scheduler`

- **Gated por flag** em `Settings` (default `False` — não arranca em
  CI/dev sem opt-in). Composition root constrói sempre; lifespan decide
  se chama `start()`.
- `start()` / `shutdown()` **idempotentes** — segunda chamada não
  duplica jobs nem quebra.
- **Cron string validada cedo** no startup (`CronTrigger.from_crontab(...)`
  levanta `ValueError`) — preferível a job falhar silenciosamente.
- **Warning explícito quando lista de unidades/jobs está vazia** —
  silêncio aqui esconde misconfig (scheduler rodando sem nada
  registrado).
- Erros do use case **capturados dentro do job runner** com log `ERROR`
  — uma exceção não tratada não pode matar o scheduler nem os outros
  jobs.
