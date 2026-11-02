"""Raiz das falhas de caso de uso que não são violação de regra de negócio.

O sistema tem duas raízes de erro, uma por significado (ADR 3.9.0001):

- `DomainError` (`shared/domain/exceptions/base.py`) — uma regra que o negócio
  enuncia foi violada.
- `ApplicationError` (aqui) — o caso de uso não pôde ser atendido por um motivo que
  **não** é regra de negócio: o recurso endereçado não existe, a credencial não
  autentica, um identificador técnico colide no armazenamento, o pedido ou um insumo
  de outro bounded context está malformado ou incompleto.

Cada bounded context declara a sua raiz de aplicação em
`features/<bc>/application/errors.py`, subclasse direta desta, e toda classe de erro
do BC descende de exatamente uma das suas duas raízes. O que cada erro vira para
quem chamou é decidido pelo adapter de entrada do BC, num mapa explícito — nunca
pela hierarquia.

Esta classe **não** herda de `DomainError`: a separação é justamente o que permite
distinguir, pelo tipo, uma senha errada de uma invariante quebrada. Ela voltou na
Stage 3.9 depois de ter sido removida na issue #45 por não ter consumidor; agora
nasce com um por BC.
"""


class ApplicationError(Exception):
    """Falha de caso de uso que não é violação de regra de negócio (ADR 3.9.0001 §3)."""
