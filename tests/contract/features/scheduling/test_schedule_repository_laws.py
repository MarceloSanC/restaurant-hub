"""Leis L-SC1…L-SC8 do `ScheduleRepository` (concept 4.3 §4; CA21, CA02).

Parametrizada pela fixture `schedule_repo` (conftest): o mesmo corpo para cada
implementação. A semeadura usa o próprio port (`add`/`save`).

**A fidelidade (L-SC8) é comparada por projeção** (`support.project`): as entidades são
iguais por id, então `lida.bands == gravada.bands` não compara conteúdo. Os casos da Stage
4.4 (fidelidade depois de `save`, id interno no `add`, relato canônico do id, ordem do
`add`) travam o que a lei passou a enunciar no docstring do port.
"""

import dataclasses
from collections.abc import Callable
from datetime import UTC, date, datetime, time, timedelta

import pytest

from restaurant_hub.features.scheduling.application.dtos.commands import EnableBand
from restaurant_hub.features.scheduling.application.errors import (
    IdentifierInUseError,
    ScheduleNotFoundError,
    SchedulePeriodTakenError,
    ScheduleVersionConflictError,
)
from restaurant_hub.features.scheduling.application.ports.out.schedule_repository import (
    ScheduleChange,
    ScheduleRepository,
)
from restaurant_hub.features.scheduling.domain.entities.schedule import Schedule
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
    OperationalCalendar,
)
from restaurant_hub.features.scheduling.domain.value_objects.schedule_period import (
    SchedulePeriod,
)
from restaurant_hub.features.scheduling.domain.value_objects.time_range import TimeRange
from tests.contract.features.scheduling.support import project

pytestmark = pytest.mark.contract

_T, _U = TenantId("t1"), UnitId("u1")
_SEG = date(2026, 11, 2)
_SEMANA = timedelta(days=7)
# Aware: `occurred_at` é instante absoluto (`Clock.now()`); ingênuo está fora do contrato.
_QUANDO = datetime(2026, 11, 1, 12, 0, tzinfo=UTC)


def _escala(sid: str, first_day: date = _SEG, *, tenant: str = _T, unit: str = _U) -> Schedule:
    return Schedule(
        id=ScheduleId(sid),
        tenant_id=TenantId(tenant),
        unit_id=UnitId(unit),
        period=SchedulePeriod(first_day=first_day),
        calendar=OperationalCalendar.default(),
    )


def _mudanca(previous: int | None = None) -> ScheduleChange:
    return ScheduleChange(
        author_user_id="user-ger",
        occurred_at=_QUANDO,
        previous_version=previous,
        operations=(),
        acknowledged=(),
    )


def _com_faixa(escala: Schedule, band_id: str = "f1") -> Schedule:
    inicio = datetime.combine(escala.period.first_day, time(10))
    return escala.enable_band(
        ShiftBandId(band_id), TimeRange(start=inicio, end=inicio + timedelta(hours=4))
    )


def test_l_sc8_lido_e_o_gravado_campo_a_campo(schedule_repo: ScheduleRepository) -> None:
    escala = (
        _com_faixa(_escala("s1"))
        .declare_demand(
            ShiftDemandId("d1"), ShiftBandId("f1"), JobFunctionId("c"), DemandQuantity(2)
        )
        .assign(AssignmentId("a1"), ShiftDemandId("d1"), EmployeeId("ana"), function_exception=True)
    )
    schedule_repo.add(escala, _mudanca())
    lida = schedule_repo.find_by_id(_T, _U, ScheduleId("s1"))
    assert lida is not None
    assert (lida.version, lida.period, lida.calendar, lida.bands) == (
        escala.version,
        escala.period,
        escala.calendar,
        escala.bands,
    )
    _, _, alocacao = lida.locate_assignment(AssignmentId("a1"))
    assert alocacao.function_exception is True


def test_l_sc1_add_com_id_ja_gravado_recusa(schedule_repo: ScheduleRepository) -> None:
    schedule_repo.add(_escala("s1"), _mudanca())
    with pytest.raises(IdentifierInUseError):
        schedule_repo.add(_escala("s1", _SEG + _SEMANA), _mudanca())


@pytest.mark.parametrize("deslocamento", [0, 3, -6])
def test_l_sc2_periodo_que_cruza_outra_escala_da_unidade_recusa(
    schedule_repo: ScheduleRepository, deslocamento: int
) -> None:
    schedule_repo.add(_escala("s1"), _mudanca())
    outra = Schedule(
        id=ScheduleId("s2"),
        tenant_id=_T,
        unit_id=_U,
        period=SchedulePeriod(first_day=_SEG + timedelta(days=deslocamento), days=7),
        calendar=OperationalCalendar(
            week_start=OperationalCalendar.default().week_start.from_date(
                _SEG + timedelta(days=deslocamento)
            ),
            day_cutoff=OperationalCalendar.default().day_cutoff,
        ),
    )
    with pytest.raises(SchedulePeriodTakenError):
        schedule_repo.add(outra, _mudanca())


def test_l_sc2_adjacente_e_outra_unidade_passam(schedule_repo: ScheduleRepository) -> None:
    schedule_repo.add(_escala("s1"), _mudanca())
    schedule_repo.add(_escala("s2", _SEG + _SEMANA), _mudanca())
    schedule_repo.add(_escala("s3", unit="u2"), _mudanca())
    schedule_repo.add(_escala("s4", tenant="t2"), _mudanca())  # mesma unit_id, outro tenant
    assert schedule_repo.find_by_id(_T, UnitId("u2"), ScheduleId("s3")) is not None
    assert schedule_repo.find_by_id(TenantId("t2"), _U, ScheduleId("s4")) is not None


def test_l_sc4_save_otimista(schedule_repo: ScheduleRepository) -> None:
    escala = _escala("s1")
    schedule_repo.add(escala, _mudanca())
    v2 = _com_faixa(escala)
    schedule_repo.save(v2, 1, _mudanca(1))
    lida = schedule_repo.find_by_id(_T, _U, ScheduleId("s1"))
    assert lida is not None
    assert lida.version == 2  # noqa: PLR2004
    with pytest.raises(ScheduleVersionConflictError) as excinfo:
        schedule_repo.save(_com_faixa(escala, "f9"), 1, _mudanca(1))
    assert excinfo.value.current_version == 2  # noqa: PLR2004
    # Manter os próprios ids internos (f1) não é colisão: a escala não colide consigo.
    v3 = v2.redeclare_band_break(ShiftBandId("f1"), 30)
    schedule_repo.save(v3, 2, _mudanca(2))
    relida = schedule_repo.find_by_id(_T, _U, ScheduleId("s1"))
    assert relida is not None
    assert relida.version == 3  # noqa: PLR2004


def test_l_sc4_ordem_endereco_versao_ids(schedule_repo: ScheduleRepository) -> None:
    s1 = _com_faixa(_escala("s1"), "f1")
    schedule_repo.add(s1, _mudanca())
    s2 = _escala("s2", _SEG + _SEMANA)
    schedule_repo.add(s2, _mudanca())
    # versão vencida E id de outra escala ⇒ a versão vem antes dos ids
    with pytest.raises(ScheduleVersionConflictError):
        schedule_repo.save(_com_faixa(s2, "f1"), 7, _mudanca(7))
    # endereço inexistente E versão errada ⇒ o endereço vem antes da versão
    with pytest.raises(ScheduleNotFoundError):
        schedule_repo.save(_escala("s2", _SEG + _SEMANA, unit="u2"), 7, _mudanca(7))


def test_l_sc4_save_de_inexistente_ou_de_outro_endereco_recusa(
    schedule_repo: ScheduleRepository,
) -> None:
    schedule_repo.add(_escala("s1"), _mudanca())
    with pytest.raises(ScheduleNotFoundError):
        schedule_repo.save(_escala("s1", unit="u2"), 1, _mudanca(1))
    with pytest.raises(ScheduleNotFoundError):
        schedule_repo.save(_escala("s9"), 1, _mudanca(1))


def test_l_sc4_id_interno_de_outra_escala_da_unidade_recusa(
    schedule_repo: ScheduleRepository,
) -> None:
    s1 = _com_faixa(_escala("s1"), "f1")
    schedule_repo.add(s1, _mudanca())
    s2 = _escala("s2", _SEG + _SEMANA)
    schedule_repo.add(s2, _mudanca())
    with pytest.raises(IdentifierInUseError) as excinfo:
        schedule_repo.save(_com_faixa(s2, "f1"), 1, _mudanca(1))
    assert excinfo.value.id_type == "ShiftBandId"
    # Em outra unidade o mesmo id é permitido (unicidade por unidade).
    s3 = _escala("s3", unit="u2")
    schedule_repo.add(s3, _mudanca())
    schedule_repo.save(_com_faixa(s3, "f1"), 1, _mudanca(1))
    # Nem em outro tenant com a mesma unit_id.
    s4 = _escala("s4", tenant="t2")
    schedule_repo.add(s4, _mudanca())
    schedule_repo.save(_com_faixa(s4, "f1"), 1, _mudanca(1))


def test_l_sc5_endereco_de_tres_partes(schedule_repo: ScheduleRepository) -> None:
    schedule_repo.add(_escala("s1"), _mudanca())
    assert schedule_repo.find_by_id(TenantId("t2"), _U, ScheduleId("s1")) is None
    assert schedule_repo.find_by_id(_T, UnitId("u2"), ScheduleId("s1")) is None
    assert schedule_repo.list_in_range(_T, UnitId("u2"), _SEG, _SEG) == ()
    assert schedule_repo.list_in_range(TenantId("t2"), _U, _SEG, _SEG) == ()
    assert schedule_repo.list_ending_before(TenantId("t2"), _U, _SEG + 5 * _SEMANA, 10) == ()


def test_l_sc6_recorte_traz_as_que_cruzam_por_first_day(schedule_repo: ScheduleRepository) -> None:
    for sid, semanas in (("s3", 2), ("s1", 0), ("s2", 1)):
        schedule_repo.add(_escala(sid, _SEG + semanas * _SEMANA), _mudanca())
    cruzam = schedule_repo.list_in_range(_T, _U, _SEG + timedelta(days=6), _SEG + _SEMANA)
    assert [e.id for e in cruzam] == ["s1", "s2"]
    todas = schedule_repo.list_in_range(_T, _U, _SEG - _SEMANA, _SEG + 4 * _SEMANA)
    assert [e.id for e in todas] == ["s1", "s2", "s3"]


def test_l_sc7_anteriores_da_mais_recente_ate_o_limite(schedule_repo: ScheduleRepository) -> None:
    for sid, semanas in (("s1", 0), ("s3", 2), ("s2", 1)):
        schedule_repo.add(_escala(sid, _SEG + semanas * _SEMANA), _mudanca())
    antes = _SEG + 2 * _SEMANA  # s3 começa aqui: não terminou antes
    assert [e.id for e in schedule_repo.list_ending_before(_T, _U, antes, 10)] == ["s2", "s1"]
    assert [e.id for e in schedule_repo.list_ending_before(_T, _U, antes, 1)] == ["s2"]
    # last_day == before - 1 entra; last_day == before não entra.
    s2_fim = _SEG + _SEMANA + timedelta(days=6)
    assert [e.id for e in schedule_repo.list_ending_before(_T, _U, s2_fim, 10)] == ["s1"]


def test_l_sc3_a_mudanca_e_gravada_com_o_estado(
    schedule_repo: ScheduleRepository,
    trail_of: Callable[[str], tuple[ScheduleChange, ...]],
) -> None:
    escala = _escala("s1")
    criacao = _mudanca()
    schedule_repo.add(escala, criacao)
    operacao = EnableBand(
        ShiftBandId("f1"),
        TimeRange(start=datetime.combine(_SEG, time(10)), end=datetime.combine(_SEG, time(14))),
    )
    edicao = ScheduleChange(
        author_user_id="user-ger",
        occurred_at=_QUANDO,
        previous_version=1,
        operations=(operacao,),
        acknowledged=(),
    )
    schedule_repo.save(_com_faixa(escala), 1, edicao)
    assert trail_of("s1") == (criacao, edicao)
    # Recusa não grava a mudança.
    with pytest.raises(ScheduleVersionConflictError):
        schedule_repo.save(_com_faixa(escala, "f9"), 1, _mudanca(1))
    assert trail_of("s1") == (criacao, edicao)


# --- Stage 4.4: o que a lei passou a enunciar ---------------------------------------------


def _faixa(dia: date, hora: int, *, horas: int = 4, intervalo: int = 0) -> TimeRange:
    inicio = datetime.combine(dia, time(hora))
    return TimeRange(start=inicio, end=inicio + timedelta(hours=horas), break_minutes=intervalo)


def _escala_rica(sid: str = "s1") -> Schedule:
    """Três itens por nível, fora da ordem dos ids, com valores não-default em cada campo."""
    return (
        _escala(sid)
        .enable_band(ShiftBandId("f3"), _faixa(_SEG, 10, intervalo=30))
        .enable_band(ShiftBandId("f1"), _faixa(_SEG, 15))
        .enable_band(ShiftBandId("f2"), _faixa(_SEG, 22))  # cruza a meia-noite
        .declare_demand(
            ShiftDemandId("d3"), ShiftBandId("f3"), JobFunctionId("cozinheiro"), DemandQuantity(2)
        )
        .declare_demand(
            ShiftDemandId("d1"), ShiftBandId("f3"), JobFunctionId("atendente"), DemandQuantity(0)
        )
        .declare_demand(
            ShiftDemandId("d2"), ShiftBandId("f3"), JobFunctionId("caixa"), DemandQuantity(1)
        )
        .assign(AssignmentId("a3"), ShiftDemandId("d3"), EmployeeId("ana"), function_exception=True)
        .assign(
            AssignmentId("a1"), ShiftDemandId("d3"), EmployeeId("bia"), counts_toward_workload=False
        )
        .assign(AssignmentId("a2"), ShiftDemandId("d3"), EmployeeId("caio"))
        .declare_allocation_break(AssignmentId("a1"), 0)
        .declare_allocation_break(AssignmentId("a2"), 15)
    )


def test_l_sc8_fidelidade_de_conteudo_e_de_ordem_depois_de_add(
    schedule_repo: ScheduleRepository,
) -> None:
    escala = _escala_rica()
    schedule_repo.add(escala, _mudanca())
    lida = schedule_repo.find_by_id(_T, _U, ScheduleId("s1"))
    assert lida is not None
    assert project(lida) == project(escala)
    (listada,) = schedule_repo.list_in_range(_T, _U, _SEG, _SEG)
    assert project(listada) == project(escala)
    (anterior,) = schedule_repo.list_ending_before(_T, _U, _SEG + _SEMANA, 5)
    assert project(anterior) == project(escala)


def test_l_sc8_fidelidade_depois_de_save_que_altera_remove_e_reordena(
    schedule_repo: ScheduleRepository,
) -> None:
    escala = _escala_rica()
    schedule_repo.add(escala, _mudanca())
    alterada = (
        escala.disable_band(ShiftBandId("f1"))  # a faixa do meio sai
        .redeclare_band_break(ShiftBandId("f3"), 45)
        .change_demand_quantity(ShiftDemandId("d3"), DemandQuantity(5))
        .withdraw_demand(ShiftDemandId("d1"))  # a demanda do meio sai
        .unassign(AssignmentId("a1"))  # a alocação do meio sai
        .declare_workload_counting(AssignmentId("a3"), False)
        .declare_allocation_break(AssignmentId("a2"), None)
        .enable_band(ShiftBandId("f0"), _faixa(_SEG + timedelta(days=6), 22))  # passa do último dia
    )
    reordenada = dataclasses.replace(alterada, bands=tuple(reversed(alterada.bands)))
    schedule_repo.save(reordenada, escala.version, _mudanca(escala.version))
    lida = schedule_repo.find_by_id(_T, _U, ScheduleId("s1"))
    assert lida is not None
    assert project(lida) == project(reordenada)
    assert project(lida) != project(escala)
    (listada,) = schedule_repo.list_in_range(_T, _U, _SEG, _SEG)
    assert project(listada) == project(reordenada)


def _escala_com_internos(
    sid: str, first_day: date, *, band: str, demand: str, assignment: str
) -> Schedule:
    return (
        _escala(sid, first_day)
        .enable_band(ShiftBandId(band), _faixa(first_day, 10))
        .declare_demand(
            ShiftDemandId(demand), ShiftBandId(band), JobFunctionId("c"), DemandQuantity(1)
        )
        .assign(AssignmentId(assignment), ShiftDemandId(demand), EmployeeId("ana"))
    )


@pytest.mark.parametrize(
    ("ids", "esperado"),
    [
        ({"band": "f1", "demand": "d9", "assignment": "a9"}, ("ShiftBandId", "f1")),
        ({"band": "f9", "demand": "d1", "assignment": "a9"}, ("ShiftDemandId", "d1")),
        ({"band": "f9", "demand": "d9", "assignment": "a1"}, ("AssignmentId", "a1")),
    ],
)
def test_l_sc4_add_com_id_interno_de_outra_escala_da_unidade_recusa(
    schedule_repo: ScheduleRepository, ids: dict[str, str], esperado: tuple[str, str]
) -> None:
    schedule_repo.add(
        _escala_com_internos("s1", _SEG, band="f1", demand="d1", assignment="a1"), _mudanca()
    )
    with pytest.raises(IdentifierInUseError) as excinfo:
        schedule_repo.add(_escala_com_internos("s2", _SEG + _SEMANA, **ids), _mudanca())
    assert (excinfo.value.id_type, excinfo.value.value) == esperado
    assert schedule_repo.find_by_id(_T, _U, ScheduleId("s2")) is None


@pytest.mark.parametrize("via", ["add", "save"])
def test_l_sc4_o_id_relatado_e_o_canonico_e_nao_o_da_ordem_de_gravacao(
    schedule_repo: ScheduleRepository, via: str
) -> None:
    """Tipo antes de escala; menor id por codepoint antes de ordem de gravação e de colação.

    A escala mais antiga colide por alocação e pela faixa `"a"`; a mais nova, pela faixa
    `"B"`. Quem varresse escala por escala relataria a alocação; quem ordenasse como um
    locale relataria `"a"`. O canônico é a faixa `"B"` (0x42 < 0x61).
    """
    schedule_repo.add(
        _escala_com_internos("s1", _SEG, band="a", demand="d1", assignment="x1"), _mudanca()
    )
    schedule_repo.add(
        _escala_com_internos("s2", _SEG + _SEMANA, band="B", demand="d2", assignment="x2"),
        _mudanca(),
    )
    terceira = _SEG + 2 * _SEMANA
    colidente = (
        _escala("s3", terceira)
        .enable_band(ShiftBandId("a"), _faixa(terceira, 8))
        .enable_band(ShiftBandId("B"), _faixa(terceira, 14))
        .declare_demand(
            ShiftDemandId("d3"), ShiftBandId("a"), JobFunctionId("c"), DemandQuantity(1)
        )
        .assign(AssignmentId("x1"), ShiftDemandId("d3"), EmployeeId("ana"))
    )
    with pytest.raises(IdentifierInUseError) as excinfo:
        if via == "add":
            schedule_repo.add(colidente, _mudanca())
        else:
            schedule_repo.add(_escala("s3", terceira), _mudanca())
            schedule_repo.save(colidente, 1, _mudanca(1))
    assert (excinfo.value.id_type, excinfo.value.value) == ("ShiftBandId", "B")


def test_l_sc1_a_ordem_do_add_e_id_da_escala_periodo_ids_internos(
    schedule_repo: ScheduleRepository,
) -> None:
    schedule_repo.add(
        _escala_com_internos("s1", _SEG, band="f1", demand="d1", assignment="a1"), _mudanca()
    )
    # id de escala repetido E período cruzado ⇒ o id vem antes do período
    with pytest.raises(IdentifierInUseError) as excinfo:
        schedule_repo.add(_escala("s1"), _mudanca())
    assert excinfo.value.id_type == "ScheduleId"
    # período cruzado E id interno em uso ⇒ o período vem antes dos ids
    with pytest.raises(SchedulePeriodTakenError):
        schedule_repo.add(
            _escala_com_internos("s2", _SEG, band="f1", demand="d1", assignment="a1"), _mudanca()
        )


def _vizinha(sid: str, first_day: date) -> Schedule:
    """Escala rica com ids internos disjuntos dos de `_escala_rica`, e conteúdo diferente."""
    return (
        _escala(sid, first_day)
        .enable_band(ShiftBandId("g2"), _faixa(first_day, 9, intervalo=15))
        .enable_band(ShiftBandId("g1"), _faixa(first_day + timedelta(days=1), 18))
        .declare_demand(
            ShiftDemandId("e1"), ShiftBandId("g2"), JobFunctionId("atendente"), DemandQuantity(3)
        )
        .assign(AssignmentId("b1"), ShiftDemandId("e1"), EmployeeId("dani"))
    )


def test_l_sc8_escalas_vizinhas_da_unidade_nao_se_misturam_nem_sao_tocadas_pelo_save(
    schedule_repo: ScheduleRepository,
) -> None:
    """Fidelidade com **duas** escalas com filhas na unidade (auditoria de testes da 4.4).

    Uma leitura que juntasse as filhas pela unidade, e não pela escala, ou um `save` que
    reescrevesse as faixas da unidade inteira, passariam por toda suíte de uma escala só.
    """
    s1 = _escala_rica("s1")
    s2 = _vizinha("s2", _SEG + _SEMANA)
    schedule_repo.add(s1, _mudanca())
    schedule_repo.add(s2, _mudanca())
    recorte = schedule_repo.list_in_range(_T, _U, _SEG, _SEG + 2 * _SEMANA)
    assert [project(e) for e in recorte] == [project(s1), project(s2)]
    anteriores = schedule_repo.list_ending_before(_T, _U, _SEG + 3 * _SEMANA, 5)
    assert [project(e) for e in anteriores] == [project(s2), project(s1)]

    s2_alterada = s2.disable_band(ShiftBandId("g1"))
    schedule_repo.save(s2_alterada, s2.version, _mudanca(s2.version))
    lida_s1 = schedule_repo.find_by_id(_T, _U, ScheduleId("s1"))
    lida_s2 = schedule_repo.find_by_id(_T, _U, ScheduleId("s2"))
    assert lida_s1 is not None
    assert lida_s2 is not None
    assert project(lida_s1) == project(s1)
    assert project(lida_s2) == project(s2_alterada)


def test_l_sc1_id_de_escala_colide_em_outro_tenant(schedule_repo: ScheduleRepository) -> None:
    schedule_repo.add(_escala("s1"), _mudanca())
    with pytest.raises(IdentifierInUseError) as excinfo:
        schedule_repo.add(_escala("s1", tenant="t2"), _mudanca())
    assert (excinfo.value.id_type, excinfo.value.value) == ("ScheduleId", "s1")
    assert schedule_repo.find_by_id(TenantId("t2"), _U, ScheduleId("s1")) is None


def test_l_sc5_save_no_endereco_de_outro_tenant_e_escala_inexistente(
    schedule_repo: ScheduleRepository,
) -> None:
    schedule_repo.add(_escala("s1"), _mudanca())
    with pytest.raises(ScheduleNotFoundError):
        schedule_repo.save(_com_faixa(_escala("s1", tenant="t2")), 1, _mudanca(1))
    lida = schedule_repo.find_by_id(_T, _U, ScheduleId("s1"))
    assert lida is not None
    assert lida.bands == ()
