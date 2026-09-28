"""CA13 — o domínio NÃO recusa nenhuma das oito situações de política (§5.18).

A lista é a do ADR 4.1.0003 (a), fechada em oito; cada teste monta a situação
pelas mutações da raiz e afirma que ela **salva** (nenhuma exceção, estado
presente). Quem as avalia, com modo configurável, é a 4.2.

**Rótulo honesto de testabilidade** (concept §11): para (3) indisponibilidade,
(7) carga contratada e o lado "função não detida" de (8), o domínio não tem
sujeito capaz de expressar a condição. A asserção é de **superfície** — o
agregado não tem campo que expresse indisponibilidade, carga contratada ou o
conjunto de funções do registro, derivada dos campos das quatro entidades —
**mais** o aceite do estado que as representa.
"""

import dataclasses
from datetime import date, datetime, timedelta

import pytest

from restaurant_hub.features.scheduling.domain.entities.assignment import Assignment
from restaurant_hub.features.scheduling.domain.entities.schedule import Schedule
from restaurant_hub.features.scheduling.domain.entities.shift_band import ShiftBand
from restaurant_hub.features.scheduling.domain.entities.shift_demand import ShiftDemand
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

pytestmark = pytest.mark.unit

_SEGUNDA = date(2026, 9, 28)
_ANA = EmployeeId("ana")

# Todos os campos das quatro entidades (concept §4). Cobrado contra as classes:
# um campo novo tem de entrar aqui, e a asserção de superfície o examina.
_CAMPOS_DO_AGREGADO = {
    Schedule: {"id", "tenant_id", "unit_id", "period", "calendar", "bands", "version"},
    ShiftBand: {"id", "time_range", "demands"},
    ShiftDemand: {"id", "job_function_id", "quantity", "assignments"},
    Assignment: {
        "id",
        "employee_id",
        "counts_toward_workload",
        "function_exception",
        "break_minutes",
    },
}

# Radicais que nomeariam o dado das três situações sem sujeito no domínio.
_SUJEITOS_AUSENTES = ("unavailab", "indisponib", "contract", "workload_profile", "job_functions")


def _vazia() -> Schedule:
    return Schedule(
        id=ScheduleId("escala-1"),
        tenant_id=TenantId("tenant-1"),
        unit_id=UnitId("unidade-1"),
        period=SchedulePeriod(first_day=_SEGUNDA),
        calendar=OperationalCalendar.default(),
    )


def _dia(deslocamento: int, hora: int) -> datetime:
    return datetime(2026, 9, 28, hora, 0) + timedelta(days=deslocamento)


def _com_faixa(
    escala: Schedule, n: int, inicio: datetime, horas: int, funcao: str = "cozinheiro"
) -> Schedule:
    """Habilita a faixa `f{n}` com a demanda `d{n}` da função e aloca a Ana (`a{n}`)."""
    return (
        escala.enable_band(
            ShiftBandId(f"f{n}"),
            TimeRange(start=inicio, end=inicio + timedelta(hours=horas)),
        )
        .declare_demand(
            ShiftDemandId(f"d{n}"), ShiftBandId(f"f{n}"), JobFunctionId(funcao), DemandQuantity(1)
        )
        .assign(AssignmentId(f"a{n}"), ShiftDemandId(f"d{n}"), _ANA)
    )


def _minutos_da_ana(escala: Schedule) -> int:
    return sum(
        escala.worked_minutes_of(alocacao.id)
        for faixa in escala.bands
        for demanda in faixa.demands
        for alocacao in demanda.assignments
        if alocacao.employee_id == _ANA
    )


def test_1_mesmo_registro_em_faixas_distintas_sobrepostas_da_mesma_funcao() -> None:
    escala = _com_faixa(_com_faixa(_vazia(), 1, _dia(2, 16), 8), 2, _dia(2, 18), 5)
    assert escala.bands[0].time_range.overlaps(escala.bands[1].time_range)
    assert escala.bands[0].demands[0].job_function_id == escala.bands[1].demands[0].job_function_id


def test_2_mesmo_registro_em_funcoes_diferentes_em_faixas_sobrepostas() -> None:
    escala = _com_faixa(
        _com_faixa(_vazia(), 1, _dia(2, 16), 8, "cozinheiro"), 2, _dia(2, 18), 5, "atendente"
    )
    assert escala.bands[0].time_range.overlaps(escala.bands[1].time_range)
    assert escala.bands[0].demands[0].job_function_id != escala.bands[1].demands[0].job_function_id


def test_3_alocacao_em_faixa_que_cobriria_indisponibilidade() -> None:
    # Sem sujeito no domínio: nenhuma consulta a staff; o aceite é incondicional.
    escala = _com_faixa(_vazia(), 1, _dia(0, 8), 8)
    assert escala.locate_assignment(AssignmentId("a1"))[2].employee_id == _ANA


def test_4_descanso_entre_jornadas_abaixo_de_11h() -> None:
    # Segunda até 23:00 e terça a partir de 06:00: 7h de descanso.
    escala = _com_faixa(_com_faixa(_vazia(), 1, _dia(0, 15), 8), 2, _dia(1, 6), 6)
    descanso = escala.bands[1].time_range.start - escala.bands[0].time_range.end
    assert descanso < timedelta(hours=11)


def test_5_soma_acima_de_10h_no_dia() -> None:
    escala = _com_faixa(_com_faixa(_vazia(), 1, _dia(2, 6), 6), 2, _dia(2, 13), 6)
    assert _minutos_da_ana(escala) > 10 * 60


def test_6_soma_acima_de_44h_na_semana() -> None:
    escala = _vazia()
    for n in range(1, 7):
        escala = _com_faixa(escala, n, _dia(n - 1, 8), 8)
    assert _minutos_da_ana(escala) > 44 * 60


def test_7_soma_acima_da_carga_contratada() -> None:
    # Sem sujeito: nenhuma carga contratada no domínio; 12h num dia salvam.
    escala = _com_faixa(_vazia(), 1, _dia(3, 8), 12)
    assert _minutos_da_ana(escala) == 12 * 60


def test_8_funcao_nao_detida_e_alocados_acima_de_n() -> None:
    escala = (
        _vazia()
        .enable_band(ShiftBandId("f1"), TimeRange(start=_dia(4, 16), end=_dia(5, 0)))
        .declare_demand(
            ShiftDemandId("d1"), ShiftBandId("f1"), JobFunctionId("cozinheiro"), DemandQuantity(1)
        )
        .assign(AssignmentId("a1"), ShiftDemandId("d1"), _ANA, function_exception=True)
        .assign(AssignmentId("a2"), ShiftDemandId("d1"), EmployeeId("bia"))
        .change_demand_quantity(ShiftDemandId("d1"), DemandQuantity(0))
    )
    _, demanda = escala.locate_demand(ShiftDemandId("d1"))
    assert demanda.allocated > demanda.quantity.value
    assert demanda.assignments[0].function_exception is True


def test_a_superficie_dos_campos_e_a_enumerada() -> None:
    for entidade, esperados in _CAMPOS_DO_AGREGADO.items():
        assert {campo.name for campo in dataclasses.fields(entidade)} == esperados


def test_o_agregado_nao_tem_campo_para_indisponibilidade_carga_ou_funcoes_do_registro() -> None:
    # Rótulo honesto: é o que torna (3), (7) e o lado "função não detida" de (8)
    # inexprimíveis como recusa aqui.
    campos = {nome for esperados in _CAMPOS_DO_AGREGADO.values() for nome in esperados}
    for radical in _SUJEITOS_AUSENTES:
        assert not [campo for campo in campos if radical in campo], radical
