"""Tradução de `IntegrityError` → erros de aplicação de scheduling — CA07, metade unit.

O mapa do `add` traduz **as duas** constraints e só elas (concept §6). A outra metade importa
tanto quanto a primeira: as filhas, as `CHECK`, a âncora `uq_schedules_tenant_unit_id`, a
trilha e qualquer constraint desconhecida sobem **intactas** — vesti-las de erro de negócio
esconderia um defeito de mapper atrás de um 4xx plausível.
"""

from types import SimpleNamespace

import pytest
from sqlalchemy.exc import IntegrityError

from restaurant_hub.features.scheduling.adapters.out.postgres.integrity_errors import (
    ON_ADD_SCHEDULE,
    constraint_name,
    translate,
)
from restaurant_hub.features.scheduling.adapters.out.postgres.tables import (
    EX_SCHEDULES_UNIT_DAYS_DISJOINT,
    PK_SCHEDULES,
    scheduling_metadata,
)
from restaurant_hub.features.scheduling.application.errors import (
    IdentifierInUseError,
    SchedulePeriodTakenError,
)

pytestmark = pytest.mark.unit


def _erro(constraint: str | None) -> IntegrityError:
    """`IntegrityError` com o `diag.constraint_name` que o psycopg 3 expõe."""
    original = SimpleNamespace(diag=SimpleNamespace(constraint_name=constraint))
    return IntegrityError("INSERT ...", {}, original)  # type: ignore[arg-type]


def test_o_mapa_do_add_tem_exatamente_as_duas_constraints() -> None:
    assert set(ON_ADD_SCHEDULE) == {PK_SCHEDULES, EX_SCHEDULES_UNIT_DAYS_DISJOINT}


def test_pk_schedules_vira_id_de_escala_em_uso_com_o_id_de_quem_gravava() -> None:
    traduzido = translate(_erro(PK_SCHEDULES), ON_ADD_SCHEDULE, "s1")
    assert type(traduzido) is IdentifierInUseError
    assert (traduzido.id_type, traduzido.value) == ("ScheduleId", "s1")


def test_a_exclusion_constraint_vira_periodo_tomado() -> None:
    traduzido = translate(_erro(EX_SCHEDULES_UNIT_DAYS_DISJOINT), ON_ADD_SCHEDULE, "s1")
    assert type(traduzido) is SchedulePeriodTakenError


_TODAS = sorted(
    str(constraint.name)
    for tabela in scheduling_metadata.tables.values()
    for constraint in tabela.constraints
)


@pytest.mark.parametrize(
    "constraint",
    [c for c in _TODAS if c not in {PK_SCHEDULES, EX_SCHEDULES_UNIT_DAYS_DISJOINT}]
    + ["ck_alguma_coisa_nova"],
)
def test_o_resto_sobe_intacto(constraint: str) -> None:
    """Toda outra constraint do schema — e uma desconhecida — devolve o próprio erro."""
    erro = _erro(constraint)
    assert translate(erro, ON_ADD_SCHEDULE, "s1") is erro


def test_erro_sem_nome_de_constraint_sobe_intacto() -> None:
    sem_nome = _erro(None)
    assert constraint_name(sem_nome) is None
    assert translate(sem_nome, ON_ADD_SCHEDULE, "s1") is sem_nome
    sem_diag = IntegrityError("INSERT ...", {}, Exception("driver sem diag"))
    assert constraint_name(sem_diag) is None
    assert translate(sem_diag, ON_ADD_SCHEDULE, "s1") is sem_diag


def test_constraint_name_le_o_diag_estruturado() -> None:
    assert constraint_name(_erro(PK_SCHEDULES)) == PK_SCHEDULES
