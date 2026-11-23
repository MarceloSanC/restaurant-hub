"""Adapter HTTP de entrada do BC scheduling — a superfície de runtime da escala (Stage 4.5).

Espelha em forma o pacote homônimo de staff (Stage 3.6), e o espelho é deliberado:

- `schemas.py` — Pydantic de request/response e os conversores da borda. **É o único lugar
  do BC onde Pydantic aparece**; nada daqui atravessa para `application` ou `domain`.
- `error_handlers.py` — o mapa exceção → status HTTP de scheduling (ADR 4.5.0002).
- `dependencies.py` — os validadores de identificador, dia e instante, o requisito de acesso
  por rota e o provedor de ator.
- `router.py` — as sete rotas (concept 4.5 §4.1).

**Este pacote não decide autorização.** Ele declara qual permissão cada rota exige e qual é
a unidade alvo, e delega ao port `AccessGuard` (ADR 4.3.0002, ADR 4.5.0003); o use case
autoriza de novo. Nenhum módulo do BC nomeia `Role` ou `Permission` de identity.

**O tenant não chega pela requisição.** Ele vem do token, resolvido pelo guard (L-SG5), e o
`tenant_id` de todo command/query sai de `AuthorizedScope.tenant_id` (ADR 0.0.0005).
"""
