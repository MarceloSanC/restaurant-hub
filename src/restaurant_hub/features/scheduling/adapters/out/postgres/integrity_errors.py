"""Tradução de `IntegrityError` do Postgres para os erros de aplicação de scheduling.

Forma de staff (ADR 3.3.0004): **por nome de constraint**, lido de `diag.constraint_name`
— nunca por texto de mensagem —, e **por operação**: o mapa é o da operação em curso.

**Por que o mapa é pequeno.** O repositório checa as leis **explicitamente**, na ordem da
lei, sob o lock da unidade (ADR 4.4.0003): as constraints são a garantia do banco, não a
fonte do erro. Sobram duas traduções, e só no `add` (concept §6):

- `pk_schedules` — **alcançável** pelo adapter: dois `add` com o mesmo id de escala em
  unidades diferentes não disputam o mesmo lock, e o segundo cai na unicidade da PK;
- `ex_schedules_unit_days_disjoint` — só responde a escritor que contornou o lock; traduzi-la
  custa uma linha e evita que a garantia do banco saia como erro sem nome.

`uq_schedules_tenant_unit_id` fica fora: a PK responde antes dela pela mesma colisão. O
`save` não escreve período, e a corrida dos ids internos é impossível sob o lock — não tem
mapa. Tudo o mais (PKs e FKs das filhas, `CHECK`, constraint desconhecida) sobe intacto:
vestir de erro de negócio um defeito de mapper esconderia o defeito.

`constraint_name`/`translate` são a terceira cópia das duas funções (identity, staff,
scheduling); a promoção para `shared/infrastructure` é `[finding]` do concept §10.
"""

from collections.abc import Callable, Mapping

from sqlalchemy.exc import IntegrityError

from restaurant_hub.features.scheduling.adapters.out.postgres.tables import (
    EX_SCHEDULES_UNIT_DAYS_DISJOINT,
    PK_SCHEDULES,
)
from restaurant_hub.features.scheduling.application.errors import (
    IdentifierInUseError,
    SchedulePeriodTakenError,
)

# Nome da constraint → fábrica da exceção, que recebe o valor em conflito (o id da escala),
# fornecido por quem tentou gravar — a mensagem do Postgres não é lida.
ConstraintMap = Mapping[str, Callable[[str], Exception]]


def _schedule_id_in_use(schedule_id: str) -> Exception:
    return IdentifierInUseError("ScheduleId", schedule_id)


def _period_taken(_schedule_id: str) -> Exception:
    return SchedulePeriodTakenError()


# `add` de escala (L-SC1, L-SC2).
ON_ADD_SCHEDULE: ConstraintMap = {
    PK_SCHEDULES: _schedule_id_in_use,
    EX_SCHEDULES_UNIT_DAYS_DISJOINT: _period_taken,
}


def constraint_name(error: IntegrityError) -> str | None:
    """O nome da constraint violada, ou `None` quando o driver não o expõe."""
    original = getattr(error, "orig", None)
    diag = getattr(original, "diag", None)
    name = getattr(diag, "constraint_name", None)
    return str(name) if name else None


def translate(error: IntegrityError, constraint_map: ConstraintMap, detail: str) -> Exception:
    """A exceção de aplicação da constraint nesta operação, ou o próprio `error`.

    **Devolve** em vez de levantar: o `raise … from error` fica no repositório, onde
    preserva o `__cause__`.
    """
    name = constraint_name(error)
    factory = constraint_map.get(name) if name is not None else None
    return error if factory is None else factory(detail)
