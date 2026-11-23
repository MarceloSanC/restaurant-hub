"""`PostgresScheduleRepository` contra o Postgres — CA05, CA06 e CA12 (integração).

As leis L-SC1 a L-SC8 rodam na suíte de contrato, com o mesmo corpo para o fake e o real.
Aqui fica o que só o banco mostra:

- **CA05** — cada escrita aceita deixa **exatamente uma** linha na trilha, com `seq` 1, 2,
  3…, o autor, o instante aware em UTC, as duas versões, as operações e os aceites;
- **CA06** — recusa não grava nada; e uma falha **no banco**, no `INSERT` da trilha, depois
  de a raiz e as filhas terem sido escritas (asserido pelos statements emitidos), desfaz o
  estado inteiro — no `add` e no `save`;
- **CA12** — fidelidade com período ≠ 7 dias e calendário não-default, e linha corrompida
  por fora do adapter que levanta a exceção de domínio ao ser lida.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import Engine, event, func, select, text
from sqlalchemy.exc import DataError

from restaurant_hub.features.scheduling.adapters.out.postgres.schedule_repository import (
    PostgresScheduleRepository,
)
from restaurant_hub.features.scheduling.adapters.out.postgres.tables import (
    schedule_bands,
    schedule_changes,
    schedules,
)
from restaurant_hub.features.scheduling.application.dtos.commands import (
    AssignEmployee,
    DeclareDemand,
    EnableBand,
)
from restaurant_hub.features.scheduling.application.errors import (
    IdentifierInUseError,
    ScheduleNotFoundError,
    SchedulePeriodTakenError,
    ScheduleVersionConflictError,
)
from restaurant_hub.features.scheduling.application.ports.out.schedule_repository import (
    ScheduleChange,
)
from restaurant_hub.features.scheduling.domain.entities.schedule import Schedule
from restaurant_hub.features.scheduling.domain.exceptions.errors import DuplicateShiftBandError
from restaurant_hub.features.scheduling.domain.value_objects.demand_quantity import (
    DemandQuantity,
)
from restaurant_hub.features.scheduling.domain.value_objects.identifiers import (
    AssignmentId,
    EmployeeId,
    JobFunctionId,
    ScheduleId,
    ShiftBandId,
    ShiftDemandId,
    TenantId,
    UnitId,
)
from restaurant_hub.features.scheduling.domain.value_objects.operational_calendar import (
    DayCutoff,
    OperationalCalendar,
    Weekday,
)
from restaurant_hub.features.scheduling.domain.value_objects.schedule_period import (
    SchedulePeriod,
)
from restaurant_hub.features.scheduling.domain.value_objects.time_range import TimeRange
from restaurant_hub.features.scheduling.domain.value_objects.validation_config import (
    EnforcementMode,
    PolicyKind,
)
from restaurant_hub.features.scheduling.domain.value_objects.violation import Violation
from tests.contract.features.scheduling.support import project, read_trail, save_as_read

pytestmark = [pytest.mark.integration]

_T, _U = TenantId("t1"), UnitId("u1")
_SEG = date(2026, 11, 2)
_QUANDO = datetime(2026, 11, 1, 12, 0, tzinfo=UTC)
# Fora do `INTEGER` da coluna: a falha provocada no `INSERT` da trilha (CA06).
_FORA_DO_INTEGER = 2**31


def _faixa(dia: date, hora: int) -> TimeRange:
    inicio = datetime.combine(dia, time(hora))
    return TimeRange(start=inicio, end=inicio + timedelta(hours=4))


def _escala(sid: str = "s1", first_day: date = _SEG) -> Schedule:
    return Schedule(
        id=ScheduleId(sid),
        tenant_id=_T,
        unit_id=_U,
        period=SchedulePeriod(first_day=first_day),
        calendar=OperationalCalendar.default(),
    )


def _mudanca(
    previous: int | None,
    operations: tuple[Any, ...] = (),
    acknowledged: tuple[Violation, ...] = (),
    autor: str = "user-ger",
) -> ScheduleChange:
    return ScheduleChange(
        author_user_id=autor,
        occurred_at=_QUANDO,
        previous_version=previous,
        operations=operations,
        acknowledged=acknowledged,
    )


@pytest.fixture
def repo(banco_limpo: Engine) -> PostgresScheduleRepository:
    return PostgresScheduleRepository(banco_limpo)


def _contagens(engine: Engine) -> dict[str, int]:
    with engine.connect() as conexao:
        return {
            tabela: conexao.execute(text(f"SELECT count(*) FROM {tabela}")).scalar_one()
            for tabela in (
                "schedules",
                "schedule_bands",
                "schedule_demands",
                "schedule_assignments",
                "schedule_changes",
            )
        }


@contextmanager
def _statements(engine: Engine) -> Iterator[list[str]]:
    """Os statements emitidos pelo engine dentro do bloco, em ordem."""
    emitidos: list[str] = []

    def registrar(*args: object) -> None:
        emitidos.append(" ".join(str(args[2]).split()))

    event.listen(engine, "before_cursor_execute", registrar)
    try:
        yield emitidos
    finally:
        event.remove(engine, "before_cursor_execute", registrar)


# ---------------------------------------------------------------------------
# CA05 — uma linha de trilha por escrita
# ---------------------------------------------------------------------------


def test_cada_escrita_aceita_grava_exatamente_uma_linha_com_seq_crescente(
    repo: PostgresScheduleRepository, banco_limpo: Engine
) -> None:
    v1 = _escala()
    repo.add(v1, _mudanca(None))
    habilita = EnableBand(ShiftBandId("f1"), _faixa(_SEG, 10))
    v2 = v1.enable_band(habilita.band_id, habilita.time_range)
    save_as_read(repo, v2, 1, _mudanca(1, (habilita,), autor="user-a"))
    declara = DeclareDemand(
        ShiftDemandId("d1"), ShiftBandId("f1"), JobFunctionId("c"), DemandQuantity(2)
    )
    aloca = AssignEmployee(AssignmentId("a1"), ShiftDemandId("d1"), EmployeeId("ana"))
    v3 = v2.declare_demand(
        declara.demand_id, declara.band_id, declara.job_function_id, declara.quantity
    ).assign(aloca.assignment_id, aloca.demand_id, aloca.employee_id, function_exception=True)
    aceite = Violation(
        policy=PolicyKind.FUNCTION_MISMATCH,
        mode=EnforcementMode.WARN,
        employee_id=EmployeeId("ana"),
        demand_id=None,
        operational_days=(_SEG,),
        assignment_ids=frozenset({AssignmentId("a1")}),
        observed=Decimal("1"),
        limit=Decimal("0"),
    )
    save_as_read(repo, v3, 2, _mudanca(2, (declara, aloca), (aceite,), autor="user-b"))

    with banco_limpo.connect() as conexao:
        linhas = conexao.execute(select(schedule_changes).order_by(schedule_changes.c.seq)).all()
    assert [(linha.schedule_id, linha.seq) for linha in linhas] == [("s1", 1), ("s1", 2), ("s1", 3)]
    assert [(linha.previous_version, linha.resulting_version) for linha in linhas] == [
        (None, 1),
        (1, 2),
        (2, 4),
    ]
    assert [linha.author_user_id for linha in linhas] == ["user-ger", "user-a", "user-b"]
    for linha in linhas:
        assert linha.occurred_at == _QUANDO
        assert linha.occurred_at.utcoffset() == timedelta(0)
    assert linhas[2].operations[1]["function_exception"] is True
    assert linhas[2].acknowledged[0]["observed"] == "1"

    trilha = read_trail(banco_limpo, "s1")
    assert [m.operations for m in trilha] == [(), (habilita,), (declara, aloca)]
    assert trilha[2].acknowledged == (aceite,)
    assert all(m.occurred_at.tzinfo is UTC for m in trilha)


# ---------------------------------------------------------------------------
# CA06 — recusa e falha não gravam nada
# ---------------------------------------------------------------------------


def test_recusas_deixam_estado_e_trilha_como_estavam(
    repo: PostgresScheduleRepository, banco_limpo: Engine
) -> None:
    v1 = _escala().enable_band(ShiftBandId("f1"), _faixa(_SEG, 10))
    repo.add(v1, _mudanca(None))
    outra = _escala("s2", _SEG + timedelta(days=7))
    repo.add(outra, _mudanca(None))
    antes = _contagens(banco_limpo)
    projecao = project(v1)

    recusas: list[tuple[type[Exception], Any]] = [
        (ScheduleVersionConflictError, lambda: save_as_read(repo, v1, 9, _mudanca(9))),
        (
            ScheduleNotFoundError,
            lambda: save_as_read(repo, _escala("s9"), 1, _mudanca(1)),
        ),
        (
            IdentifierInUseError,
            lambda: save_as_read(
                repo,
                outra.enable_band(ShiftBandId("f1"), _faixa(outra.period.first_day, 10)),
                1,
                _mudanca(1),
            ),
        ),
        (
            IdentifierInUseError,
            lambda: repo.add(_escala("s1", _SEG + timedelta(days=21)), _mudanca(None)),
        ),
        (SchedulePeriodTakenError, lambda: repo.add(_escala("s3"), _mudanca(None))),
    ]
    for erro, escrita in recusas:
        with pytest.raises(erro):
            escrita()
        assert _contagens(banco_limpo) == antes, erro
    lida = repo.find_by_id(_T, _U, ScheduleId("s1"))
    assert lida is not None
    assert project(lida) == projecao
    assert len(read_trail(banco_limpo, "s1")) == 1


def test_falha_no_insert_da_trilha_desfaz_o_add(
    repo: PostgresScheduleRepository, banco_limpo: Engine
) -> None:
    escala = (
        _escala()
        .enable_band(ShiftBandId("f1"), _faixa(_SEG, 10))
        .declare_demand(
            ShiftDemandId("d1"), ShiftBandId("f1"), JobFunctionId("c"), DemandQuantity(1)
        )
        .assign(AssignmentId("a1"), ShiftDemandId("d1"), EmployeeId("ana"))
    )
    with _statements(banco_limpo) as emitidos, pytest.raises(DataError):
        repo.add(escala, _mudanca(_FORA_DO_INTEGER))
    escritas = [s.split(" (")[0] for s in emitidos if s.startswith("INSERT")]
    assert escritas == [
        "INSERT INTO schedules",
        "INSERT INTO schedule_bands",
        "INSERT INTO schedule_demands",
        "INSERT INTO schedule_assignments",
        "INSERT INTO schedule_changes",
    ]
    assert repo.find_by_id(_T, _U, ScheduleId("s1")) is None
    assert set(_contagens(banco_limpo).values()) == {0}


def test_falha_no_insert_da_trilha_desfaz_o_save(
    repo: PostgresScheduleRepository, banco_limpo: Engine
) -> None:
    v1 = _escala().enable_band(ShiftBandId("f1"), _faixa(_SEG, 10))
    repo.add(v1, _mudanca(None))
    antes = _contagens(banco_limpo)
    v2 = v1.disable_band(ShiftBandId("f1")).enable_band(ShiftBandId("f2"), _faixa(_SEG, 15))
    with _statements(banco_limpo) as emitidos, pytest.raises(DataError):
        save_as_read(repo, v2, v1.version, _mudanca(_FORA_DO_INTEGER))
    escritas = [s.split(" ")[0] + " " + s.split(" ")[1] + " " + s.split(" ")[2] for s in emitidos]
    assert "UPDATE schedules SET" in escritas
    assert "DELETE FROM schedule_bands" in escritas
    assert escritas.index("INSERT INTO schedule_bands") < escritas.index(
        "INSERT INTO schedule_changes"
    )
    lida = repo.find_by_id(_T, _U, ScheduleId("s1"))
    assert lida is not None
    assert project(lida) == project(v1)
    assert _contagens(banco_limpo) == antes
    assert len(read_trail(banco_limpo, "s1")) == 1


# ---------------------------------------------------------------------------
# CA12 — fidelidade além da lei e linha corrompida
# ---------------------------------------------------------------------------


def test_periodo_de_dez_dias_e_calendario_nao_default_voltam_iguais(
    repo: PostgresScheduleRepository,
) -> None:
    quarta = date(2026, 11, 4)
    escala = Schedule(
        id=ScheduleId("s1"),
        tenant_id=_T,
        unit_id=_U,
        period=SchedulePeriod(first_day=quarta, days=10),
        calendar=OperationalCalendar(
            week_start=Weekday.WEDNESDAY, day_cutoff=DayCutoff(time(3, 45))
        ),
    ).enable_band(ShiftBandId("f1"), _faixa(quarta + timedelta(days=9), 23))
    repo.add(escala, _mudanca(None))
    lida = repo.find_by_id(_T, _U, ScheduleId("s1"))
    assert lida is not None
    assert project(lida) == project(escala)
    (listada,) = repo.list_in_range(_T, _U, quarta + timedelta(days=9), quarta + timedelta(days=9))
    assert project(listada) == project(escala)
    assert (
        repo.list_in_range(_T, _U, quarta + timedelta(days=10), quarta + timedelta(days=30)) == ()
    )


def test_linha_corrompida_por_fora_levanta_a_excecao_de_dominio_ao_ser_lida(
    repo: PostgresScheduleRepository, banco_limpo: Engine
) -> None:
    """Duas faixas com o mesmo `(início, fim)`: o schema aceita, o agregado não."""
    escala = (
        _escala()
        .enable_band(ShiftBandId("f1"), _faixa(_SEG, 10))
        .enable_band(ShiftBandId("f2"), _faixa(_SEG, 15))
    )
    repo.add(escala, _mudanca(None))
    with banco_limpo.begin() as conexao:
        conexao.execute(
            schedule_bands.update()
            .where(schedule_bands.c.id == "f2")
            .values(
                start_at=datetime.combine(_SEG, time(10)), end_at=datetime.combine(_SEG, time(14))
            )
        )
    with pytest.raises(DuplicateShiftBandError):
        repo.find_by_id(_T, _U, ScheduleId("s1"))


def test_save_nao_regrava_periodo_nem_calendario(
    repo: PostgresScheduleRepository, banco_limpo: Engine
) -> None:
    """Período e calendário são da criação: o `save` grava só a versão na raiz."""
    v1 = _escala()
    repo.add(v1, _mudanca(None))
    with _statements(banco_limpo) as emitidos:
        save_as_read(repo, v1.enable_band(ShiftBandId("f1"), _faixa(_SEG, 10)), 1, _mudanca(1))
    (update,) = [s for s in emitidos if s.startswith("UPDATE schedules")]
    assert update.startswith("UPDATE schedules SET version=")
    assert "first_day" not in update.split(" WHERE ")[0]
    with banco_limpo.connect() as conexao:
        assert conexao.execute(select(func.count()).select_from(schedules)).scalar_one() == 1
