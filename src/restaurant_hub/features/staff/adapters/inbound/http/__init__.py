"""Adapter HTTP de entrada do BC staff — a superfície de runtime do bounded context.

Espelha em forma o pacote homônimo de identity, e o espelho é deliberado: as duas
bordas resolvem o mesmo problema e divergir nelas custaria dois vocabulários para
o mesmo assunto.

- `schemas.py` — Pydantic de request/response e os conversores da borda. **É o
  único lugar do BC onde Pydantic aparece**; nada daqui atravessa para
  `application` ou `domain`.
- `error_handlers.py` — o mapa exceção → status HTTP de staff (ADR 3.4.0002).
- `dependencies.py` — o validador de identificador, o requisito de acesso por
  rota e o provedor de ator (ADR 3.6.0002).
- `router.py` — as rotas.

**Este pacote não decide autorização, e não sabe decidir.** Ele declara qual
permissão cada ação exige e qual é o alvo, e delega ao port `AccessGuard`
(ADR 3.4.0001, ADR 2.4.0003). Não há tabela de papéis nem mapa de permissões
aqui, e nenhum módulo do BC nomeia `Role` ou `Permission` de identity — o
contrato `bc-independence` do `.importlinter` proíbe as duas direções, **sem
nenhum `ignore_imports`**.

**O tenant não chega pela requisição.** Nenhuma das rotas o carrega no path e
nenhum schema o aceita no corpo: ele vem do token e é resolvido no
`composition_root` (ADR 0.0.0005, cláusulas 2 e 3). Consequência viva para quem
escreve rota nova aqui: o `tenant_id` de todo command/query sai de
`AuthorizedScope.tenant_id`, e de nenhuma outra origem.
"""
