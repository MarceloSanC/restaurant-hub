"""Raiz das violações de regra de negócio.

`DomainError` é a raiz de todo erro que nomeia uma regra que o negócio enuncia — num
doc de domínio, numa decisão de produto ou num ADR que registra regra de produto — e
que valeria sob qualquer protocolo, armazenamento ou cliente. Cada bounded context
declara a sua raiz de domínio (`IdentityError`, `StaffError`, `SchedulingError`)
como subclasse direta desta.

A outra raiz do sistema é `ApplicationError` (`shared/application/errors.py`): falha
de caso de uso que **não** é regra de negócio — recurso endereçado inexistente,
credencial que não autentica, identificador técnico que colide. As duas são
disjuntas, e toda classe de erro descende de exatamente uma (ADR 3.9.0001).

O que cada erro vira para quem chamou é decidido pelo adapter de entrada do BC, num
mapa explícito; esta hierarquia não ordena nem carrega nada para isso.

**Uma classe só.** `NotFoundError` viveu aqui até a Stage 3.9 como segunda base dos
erros de "não encontrado", herdada **ao lado** da raiz do BC. Quando esses erros
passaram a ter uma raiz só — a de aplicação do BC —, ela ficou sem subclasse e saiu,
como `ApplicationError` saíra daqui na issue #45 por não ter consumidor
(`scripts/check_dead_shared.py`).
"""


class DomainError(Exception):
    """Violação de uma regra de negócio."""
