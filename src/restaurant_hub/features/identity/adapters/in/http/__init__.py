"""Adapter HTTP de entrada do BC identity — a superfície de runtime do bounded context.

Quatro módulos, com fronteiras deliberadas:

- `schemas.py` — Pydantic de request/response. **É o único lugar do BC onde
  Pydantic aparece**; nada daqui atravessa para `application` ou `domain`.
- `error_handlers.py` — o mapa exceção → status HTTP (ADR 2.4.0001).
- `dependencies.py` — o guard: extrai o Bearer, verifica o token e **delega** a
  decisão de acesso a `AuthorizeActionUseCase`.
- `router.py` — as rotas.

**Este pacote não decide autorização.** Ele declara qual permissão cada ação
exige e qual é o alvo; quem decide é o use case (ADR 2.2.0002, ADR 2.4.0003).
A distinção é o que impede que a política de acesso passe a existir em dois
lugares capazes de divergir.
"""
