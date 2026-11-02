"""DTOs da application de scheduling: imutáveis, ator fora do repr, mapeadores (CA13, CA27)."""

import dataclasses
import inspect
from datetime import date, timedelta

import pytest

from restaurant_hub.features.scheduling.application.dtos import commands, queries, results
from restaurant_hub.features.scheduling.application.dtos.commands import CreateScheduleCommand
from restaurant_hub.features.scheduling.application.ports.out.staff_read_port import StaffMember
from restaurant_hub.features.scheduling.domain.entities.schedule import Schedule
from restaurant_hub.features.scheduling.domain.value_objects.demand_quantity import (
    DemandQuantity,
)
from restaurant_hub.features.scheduling.domain.value_objects.identifiers import (
    AssignmentId,
    EmployeeId,
    JobFunctionId,
    ShiftBandId,
    ShiftDemandId,
)
from restaurant_hub.features.scheduling.domain.value_objects.time_range import TimeRange
from tests.unit.features.scheduling.application.conftest import (
    COOK,
    MONDAY,
    T1,
    U1,
    WAITER,
    at,
    member,
    schedule,
)

pytestmark = pytest.mark.unit

_TUESDAY = date(2026, 11, 3)


def _classes() -> list[type]:
    return [
        c
        for modulo in (commands, queries, results)
        for _, c in inspect.getmembers(modulo, inspect.isclass)
        if c.__module__ == modulo.__name__ and dataclasses.is_dataclass(c)
    ]


@pytest.mark.parametrize("classe", _classes(), ids=lambda c: c.__name__)
def test_todo_dto_e_frozen(classe: type) -> None:
    assert classe.__dataclass_params__.frozen  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    "classe",
    [c for c in _classes() if "actor" in {f.name for f in dataclasses.fields(c)}],
    ids=lambda c: c.__name__,
)
def test_ator_e_o_primeiro_campo_e_fica_fora_do_repr(classe: type) -> None:
    campos = dataclasses.fields(classe)
    assert campos[0].name == "actor"
    assert campos[0].repr is False


def test_todo_command_e_query_carrega_ator() -> None:
    nomes = {c.__name__ for c in _classes() if c.__name__.endswith(("Command", "Query"))}
    com_ator = {
        c.__name__
        for c in _classes()
        if c.__name__ in nomes and "actor" in {f.name for f in dataclasses.fields(c)}
    }
    assert com_ator == nomes
    assert len(nomes) == 7  # noqa: PLR2004


def test_o_ator_nao_aparece_no_repr() -> None:
    comando = CreateScheduleCommand(actor="segredo", tenant_id=T1, unit_id=U1, first_day=MONDAY)
    assert "segredo" not in repr(comando)


def test_a_uniao_de_operacoes_tem_as_onze_mutacoes() -> None:
    assert len(commands.ScheduleOperation.__args__) == 11  # noqa: PLR2004


def _escala() -> Schedule:
    """Ids escolhidos com ordem OPOSTA à das chaves do §5.20, e um empate por chave.

    - faixas: "f9" começa segunda 10h, "f1" terça 18h, "f5" segunda 10h-11h (empate de
      início com f9 → desempata pelo id: f5 antes de f9);
    - demandas inseridas fora de ordem: cozinheiro "d-a" antes de atendente "d-z";
      na faixa f9, duas de função distinta;
    - alocações: "a-z" é Ana, "a-a" é Bruno, "a-m" é outra Ana (empate de nome).
    """
    return (
        schedule()
        .enable_band(ShiftBandId("f1"), TimeRange(start=at(_TUESDAY, 18), end=at(_TUESDAY, 23)))
        .enable_band(
            ShiftBandId("f9"), TimeRange(start=at(MONDAY, 10), end=at(MONDAY, 16), break_minutes=60)
        )
        .enable_band(ShiftBandId("f5"), TimeRange(start=at(MONDAY, 10), end=at(MONDAY, 11)))
        .declare_demand(ShiftDemandId("d-a"), ShiftBandId("f9"), COOK, DemandQuantity(3))
        .declare_demand(ShiftDemandId("d-z"), ShiftBandId("f9"), WAITER, DemandQuantity(2))
        .declare_demand(
            ShiftDemandId("d-x"), ShiftBandId("f1"), JobFunctionId("sumida"), DemandQuantity(1)
        )
        .assign(AssignmentId("a-a"), ShiftDemandId("d-a"), EmployeeId("bruno"))
        .assign(AssignmentId("a-z"), ShiftDemandId("d-a"), EmployeeId("ana"))
        .assign(AssignmentId("a-m"), ShiftDemandId("d-a"), EmployeeId("ana2"))
        .assign(AssignmentId("a-c"), ShiftDemandId("d-z"), EmployeeId("caio"))
        .assign(AssignmentId("a-x"), ShiftDemandId("d-x"), EmployeeId("ana"))
    )


def _staff() -> dict[EmployeeId, StaffMember]:
    return {
        EmployeeId("ana"): member("ana", name="Ana"),
        EmployeeId("ana2"): member("ana2", name="Ana"),
        EmployeeId("bruno"): member("bruno", name="Bruno"),
        EmployeeId("caio"): member("caio", active=False),
    }


_NOMES = {COOK: "Cozinheiro", WAITER: "Atendente"}


def _por_id(resultado: results.ScheduleResult, band_id: str) -> results.BandResult:
    return next(f for f in resultado.bands if f.band_id == band_id)


def test_ca13_a_escala_omite_a_alocacao_de_inativo() -> None:
    resultado = results.to_schedule_result(_escala(), _staff(), _NOMES, ())
    garcom = next(d for d in _por_id(resultado, "f9").demands if d.demand_id == "d-z")
    assert garcom.assignments == ()


def test_ca27_faixas_por_inicio_e_desempate_por_id() -> None:
    resultado = results.to_schedule_result(_escala(), _staff(), _NOMES, ())
    assert [f.band_id for f in resultado.bands] == ["f5", "f9", "f1"]


def test_ca27_demandas_por_funcao_independente_da_insercao() -> None:
    resultado = results.to_schedule_result(_escala(), _staff(), _NOMES, ())
    assert [d.job_function_id for d in _por_id(resultado, "f9").demands] == [
        "atendente",
        "cozinheiro",
    ]


def test_ca27_alocacoes_por_nome_e_desempate_por_id() -> None:
    resultado = results.to_schedule_result(_escala(), _staff(), _NOMES, ())
    cozinha = next(d for d in _por_id(resultado, "f9").demands if d.demand_id == "d-a")
    assert [(a.display_name, a.assignment_id) for a in cozinha.assignments] == [
        ("Ana", "a-m"),
        ("Ana", "a-z"),
        ("Bruno", "a-a"),
    ]
    assert cozinha.job_function_name == "Cozinheiro"
    assert cozinha.assignments[0].worked_minutes == 5 * 60


def test_ca27_funcao_fora_do_catalogo_sai_com_nome_none() -> None:
    resultado = results.to_schedule_result(_escala(), _staff(), _NOMES, ())
    assert _por_id(resultado, "f1").demands[0].job_function_name is None
    assert _por_id(resultado, "f9").operational_day == MONDAY


def test_o_resumo_traz_endereco_periodo_e_versao() -> None:
    escala = _escala()
    resumo = results.to_schedule_summary_result(escala)
    assert (resumo.tenant_id, resumo.unit_id, resumo.first_day, resumo.version) == (
        T1,
        U1,
        MONDAY,
        escala.version,
    )
    assert resumo.last_day == date(2026, 11, 8)


def _semana_seguinte() -> Schedule:
    proxima = MONDAY + timedelta(days=7)
    return (
        schedule("s0", proxima)
        .enable_band(ShiftBandId("g1"), TimeRange(start=at(proxima, 9), end=at(proxima, 12)))
        .declare_demand(ShiftDemandId("e-1"), ShiftBandId("g1"), COOK, DemandQuantity(1))
        .assign(AssignmentId("b-1"), ShiftDemandId("e-1"), EmployeeId("caio"))
        .assign(AssignmentId("b-0"), ShiftDemandId("e-1"), EmployeeId("ana"))
    )


def test_ca13_ca27_calendario_sobre_duas_escalas() -> None:
    cal = results.to_calendar_result(
        _TUESDAY, MONDAY + timedelta(days=7), (_semana_seguinte(), _escala()), _staff(), _NOMES
    )
    assert [s.schedule_id for s in cal.schedules] == ["s1", "s0"]  # por first_day
    assert [f.band_id for f in cal.bands] == ["f1", "g1"]  # segunda (f5/f9) fora do recorte
    (demanda,) = cal.bands[1].demands
    assert [a.assignment_id for a in demanda.assignments] == ["b-0"]  # caio inativo some


def test_ca13_ca27_minha_escala_ordena_e_omite_inativo() -> None:
    staff = _staff()
    minha = results.to_my_schedule_result(
        MONDAY,
        MONDAY + timedelta(days=7),
        (_semana_seguinte(), _escala()),
        frozenset({EmployeeId("ana"), EmployeeId("caio")}),
        staff,
        _NOMES,
    )
    assert [(t.assignment_id, t.job_function_name) for t in minha.shifts] == [
        ("a-z", "Cozinheiro"),
        ("a-x", None),
        ("b-0", "Cozinheiro"),
    ]
    vazio = results.to_my_schedule_result(
        _TUESDAY, _TUESDAY, (_escala(),), frozenset({EmployeeId("bruno")}), staff, _NOMES
    )
    assert vazio.shifts == ()
