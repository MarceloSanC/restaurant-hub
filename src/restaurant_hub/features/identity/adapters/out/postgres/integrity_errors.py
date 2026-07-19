"""Tradução de `IntegrityError` do Postgres para a hierarquia `IdentityError`.

Chama-se `integrity_errors` e não `errors` de propósito: `application/errors.py` é
a **hierarquia** de erros do BC; este módulo é só o **tradutor** que leva uma
violação de constraint até ela. Dois `errors.py` no mesmo BC seriam ambiguidade
gratuita.

**A tradução é por NOME de constraint**, e é por isso que todas são nomeadas
explicitamente em `tables.py` (ADR 2.3.0002). Inspecionar a mensagem do driver
seria frágil de outra forma — o texto muda entre versões e locales do Postgres, e
o gate não pegaria a quebra.

**Só constraint com significado de negócio é traduzida** (concept §7 Decisão 7).
Violação de FK sobe como está, deliberadamente:

- as FKs desta Stage são as de tenancy e de existência de agregado, e o use case
  da 2.2 **já valida** as duas antes de gravar (`RestaurantNotFoundError`,
  `CrossTenantError`);
- logo, uma FK que estoura aqui significa concorrência exótica ou bug — não uma
  regra de negócio que o chamador deva tratar;
- traduzi-la para erro de domínio a transformaria num 4xx plausível, escondendo
  o defeito atrás de uma resposta que parece esperada.

Um `IntegrityError` de constraint desconhecida também sobe intacto, pelo mesmo
motivo: inventar um erro de negócio para o que não se entende é a forma mais rápida
de perder um bug de vista.
"""

from collections.abc import Callable

from sqlalchemy.exc import IntegrityError

from restaurant_hub.features.identity.application.errors import (
    EmailAlreadyRegisteredError,
    RestaurantAlreadyExistsError,
    SessionAlreadyExistsError,
    SessionFingerprintAlreadyExistsError,
    UnitAlreadyExistsError,
    UnitMembershipAlreadyExistsError,
    UserAlreadyExistsError,
)

# nome da constraint -> fábrica da exceção de domínio.
#
# O valor recebe o "detalhe" já extraído pelo chamador (o id ou o e-mail em
# conflito), porque só o repositório sabe o que estava tentando gravar — a
# mensagem do Postgres nem sempre carrega o valor de forma confiável.
_POR_CONSTRAINT: dict[str, Callable[[str], Exception]] = {
    "pk_restaurants": RestaurantAlreadyExistsError,
    "pk_units": UnitAlreadyExistsError,
    "pk_users": UserAlreadyExistsError,
    "uq_users_email": EmailAlreadyRegisteredError,
    "pk_unit_memberships": UnitMembershipAlreadyExistsError,
    "pk_sessions": SessionAlreadyExistsError,
    "uq_sessions_fingerprint": SessionFingerprintAlreadyExistsError,
}


def nome_da_constraint(erro: IntegrityError) -> str | None:
    """Extrai o nome da constraint violada, ou `None` se não der para saber.

    O psycopg 3 expõe isso de forma estruturada em `diag.constraint_name`, sem
    parsing de texto. Quando o atributo não existe (outro driver, erro que não é
    de constraint), devolve `None` e o chamador deixa o erro subir — degradar para
    parsing de mensagem seria trocar uma falha explícita por uma silenciosa.
    """
    original = getattr(erro, "orig", None)
    diag = getattr(original, "diag", None)
    nome = getattr(diag, "constraint_name", None)
    return str(nome) if nome else None


def traduzir(erro: IntegrityError, detalhe: str) -> Exception:
    """Devolve a exceção de domínio correspondente, ou o próprio `erro`.

    Devolver (em vez de levantar) mantém a decisão de `raise` no repositório, onde
    o `from erro` preserva a cadeia de causa — perder o `__cause__` custaria caro
    justamente no diagnóstico de um conflito de integridade.

    `detalhe` é o valor em conflito (id ou e-mail), fornecido por quem tentou
    gravar.
    """
    nome = nome_da_constraint(erro)
    if nome is None:
        return erro
    fabrica = _POR_CONSTRAINT.get(nome)
    if fabrica is None:
        # Constraint conhecida do banco mas sem significado de negócio (as FKs) ou
        # constraint nova que ninguém mapeou: sobe intacta.
        return erro
    return fabrica(detalhe)
