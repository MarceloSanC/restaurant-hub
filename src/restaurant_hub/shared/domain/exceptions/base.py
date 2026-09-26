"""Hierarquia base de exceções do sistema.

DomainError: raiz de todos os erros de negócio. Capturado pelo error handler HTTP
e convertido em 422 Unprocessable Entity. Subclasse para criar erros específicos
de cada feature (ex: PaymentNotFoundError, InvalidAmountError).

NotFoundError: subclasse de DomainError para entidades inexistentes. Convertido
em 404 Not Found pelo error handler HTTP.

**São duas, e não três.** `ApplicationError` viveu aqui por seis Stages sem uma
única subclasse e sem um único `raise` — sobra do template, não decisão. Pior:
ela **não** herdava de `DomainError`, então nenhum handler a alcançava; se
alguém a tivesse levantado, o resultado seria 500. Os dois BCs escreveram na
docstring dos seus `errors.py` que herdam de `DomainError` *"nunca de
`ApplicationError`"* — a classe existia apenas como o erro que os documentos
mandavam não cometer. Removida na issue #45 (Gate 7), com o gate
`scripts/check_dead_shared.py` no lugar para que a próxima não dure seis Stages.
"""


class DomainError(Exception):
    """Erro de negócio — representa uma violação de regra de domínio."""


class NotFoundError(DomainError):
    """Entidade não encontrada — convertida em HTTP 404."""
