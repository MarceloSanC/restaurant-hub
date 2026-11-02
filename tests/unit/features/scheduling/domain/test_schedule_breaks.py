"""Testes das mutações de intervalo e da cláusula de no-op da raiz Schedule.

Fecha CA23 (o intervalo nos dois níveis e a divergência, pela raiz), CA11b (as
quatro mutações idempotentes de valor devolvem `self`), CA21 (encurtar a faixa
abaixo de um intervalo já declarado) e CA14 (nenhum método público da v1 altera
`function_exception` numa alocação existente — estado da v1, não
irrevogabilidade).
"""

import inspect
from collections.abc import Callable
from datetime import date, datetime, timedelta

import pytest

from restaurant_hub.features.scheduling.domain.entities.assignment import Assignment
from restaurant_hub.features.scheduling.domain.entities.schedule import Schedule
from restaurant_hub.features.scheduling.domain.exceptions.errors import (
    DuplicateShiftBandError,
    InvalidAssignmentBreakError,
    InvalidTimeRangeError,
)
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
from tests.unit.features.scheduling.domain.test_schedule_mutations import _MUTACOES

pytestmark = pytest.mark.unit

_SEGUNDA = date(2026, 9, 28)
_SEXTA = date(2026, 10, 2)
_UMA_HORA = 60
_COZINHEIRO, _ATENDENTE = AssignmentId("a-coz"), AssignmentId("a-ate")
_TOTAL_DE_MUTACOES = 11


def _as(dia: date, hora: int) -> datetime:
    return datetime(dia.year, dia.month, dia.day, hora, 0)


def _cenario_do_sponsor() -> Schedule:
    """Sexta 16:00-00:00 com intervalo 0; cozinheiro (Ana) e atendente (Bia)."""
    return (
        Schedule(
            id=ScheduleId("escala-1"),
            tenant_id=TenantId("tenant-1"),
            unit_id=UnitId("unidade-1"),
            period=SchedulePeriod(first_day=_SEGUNDA),
            calendar=OperationalCalendar.default(),
        )
        .enable_band(
            ShiftBandId("f1"),
            TimeRange(start=_as(_SEXTA, 16), end=_as(_SEXTA, 16) + timedelta(hours=8)),
        )
        .declare_demand(
            ShiftDemandId("d-coz"),
            ShiftBandId("f1"),
            JobFunctionId("cozinheiro"),
            DemandQuantity(1),
        )
        .declare_demand(
            ShiftDemandId("d-ate"), ShiftBandId("f1"), JobFunctionId("atendente"), DemandQuantity(1)
        )
        .assign(_COZINHEIRO, ShiftDemandId("d-coz"), EmployeeId("ana"))
        .assign(_ATENDENTE, ShiftDemandId("d-ate"), EmployeeId("bia"))
    )


# --- CA23 (fecha): o intervalo nos dois níveis ----------------------------------------


def test_sete_e_oito_horas_na_mesma_faixa() -> None:
    # O estado parte de declare_allocation_break (Checkpoint C do bloco 2, obs-B):
    # a raiz localiza a alocação e delega à faixa que a contém.
    escala = _cenario_do_sponsor().declare_allocation_break(_COZINHEIRO, _UMA_HORA)

    assert escala.effective_break_minutes_of(_COZINHEIRO) == _UMA_HORA
    assert escala.worked_minutes_of(_COZINHEIRO) == 7 * 60
    assert escala.has_break_divergence(_COZINHEIRO) is True

    assert escala.effective_break_minutes_of(_ATENDENTE) == 0
    assert escala.worked_minutes_of(_ATENDENTE) == 8 * 60
    assert escala.has_break_divergence(_ATENDENTE) is False


def test_declare_allocation_break_none_volta_a_herdar_e_zera_a_divergencia() -> None:
    declarada = _cenario_do_sponsor().declare_allocation_break(_COZINHEIRO, _UMA_HORA)
    herdando = declarada.declare_allocation_break(_COZINHEIRO, None)
    assert herdando.locate_assignment(_COZINHEIRO)[2].break_minutes is None
    assert herdando.has_break_divergence(_COZINHEIRO) is False
    assert herdando.worked_minutes_of(_COZINHEIRO) == 8 * 60
    assert herdando.version == declarada.version + 1


@pytest.mark.parametrize("intervalo", [-1, 8 * 60, 8 * 60 + 1])
def test_intervalo_da_alocacao_fora_dos_limites_e_recusado(intervalo: int) -> None:
    original = _cenario_do_sponsor()
    with pytest.raises(InvalidAssignmentBreakError):
        original.declare_allocation_break(_COZINHEIRO, intervalo)
    assert original.locate_assignment(_COZINHEIRO)[2].break_minutes is None


def test_intervalo_da_alocacao_nominal_menos_um_e_aceito() -> None:
    escala = _cenario_do_sponsor().declare_allocation_break(_COZINHEIRO, 8 * 60 - 1)
    assert escala.worked_minutes_of(_COZINHEIRO) == 1


def test_redeclare_band_break_muda_as_horas_de_quem_herda_e_so_deles() -> None:
    escala = (
        _cenario_do_sponsor()
        .declare_allocation_break(_COZINHEIRO, _UMA_HORA)
        .redeclare_band_break(ShiftBandId("f1"), 30)
    )
    assert escala.worked_minutes_of(_ATENDENTE) == 8 * 60 - 30
    assert escala.worked_minutes_of(_COZINHEIRO) == 7 * 60
    assert escala.has_break_divergence(_COZINHEIRO) is True
    assert escala.has_break_divergence(_ATENDENTE) is False


def test_redeclare_band_break_ate_o_intervalo_da_alocacao_zera_a_divergencia() -> None:
    escala = (
        _cenario_do_sponsor()
        .declare_allocation_break(_COZINHEIRO, _UMA_HORA)
        .redeclare_band_break(ShiftBandId("f1"), _UMA_HORA)
    )
    assert escala.has_break_divergence(_COZINHEIRO) is False


@pytest.mark.parametrize("intervalo", [-1, 8 * 60])
def test_redeclare_band_break_fora_dos_limites_levanta_o_erro_do_time_range(
    intervalo: int,
) -> None:
    with pytest.raises(InvalidTimeRangeError):
        _cenario_do_sponsor().redeclare_band_break(ShiftBandId("f1"), intervalo)


def test_redeclare_band_break_nao_recusa_por_causa_da_alocacao() -> None:
    # O teto da alocação é a duração nominal (§7, [deviation] da Task 07): a faixa
    # passa a exceder o intervalo declarado da alocação e nada é recusado.
    escala = (
        _cenario_do_sponsor()
        .declare_allocation_break(_COZINHEIRO, 30)
        .redeclare_band_break(ShiftBandId("f1"), 3 * _UMA_HORA)
    )
    assert escala.effective_break_minutes_of(_COZINHEIRO) == 30  # noqa: PLR2004
    assert escala.has_break_divergence(_COZINHEIRO) is True


def test_duas_faixas_de_mesmo_par_e_intervalos_diferentes_nao_consecutivas() -> None:
    # 1ª e 3ª 16:00-00:00 (intervalos 0 e 60), 2ª 18:00-23:00: a chave é (start, end).
    escala = _cenario_do_sponsor().enable_band(
        ShiftBandId("f2"), TimeRange(start=_as(_SEXTA, 18), end=_as(_SEXTA, 23))
    )
    with pytest.raises(DuplicateShiftBandError):
        escala.enable_band(
            ShiftBandId("f3"),
            TimeRange(
                start=_as(_SEXTA, 16),
                end=_as(_SEXTA, 16) + timedelta(hours=8),
                break_minutes=_UMA_HORA,
            ),
        )


# --- CA21 (fecha): encurtar a faixa abaixo de um intervalo já declarado ---------------


def test_encurtar_abaixo_do_intervalo_da_faixa_levanta_o_erro_do_time_range() -> None:
    escala = _cenario_do_sponsor().redeclare_band_break(ShiftBandId("f1"), 2 * _UMA_HORA)
    with pytest.raises(InvalidTimeRangeError):
        escala.reschedule_band(ShiftBandId("f1"), _as(_SEXTA, 16), _as(_SEXTA, 18))


def test_encurtar_abaixo_do_intervalo_da_alocacao_nomeia_o_encurtamento() -> None:
    escala = _cenario_do_sponsor().declare_allocation_break(_COZINHEIRO, 2 * _UMA_HORA)
    with pytest.raises(InvalidAssignmentBreakError, match="reagendamento encurta a faixa") as exc:
        escala.reschedule_band(ShiftBandId("f1"), _as(_SEXTA, 16), _as(_SEXTA, 18))
    # A causa de construção fica encadeada para depuração.
    assert isinstance(exc.value.__cause__, InvalidAssignmentBreakError)


def test_encurtar_ate_acima_do_intervalo_da_alocacao_passa() -> None:
    escala = _cenario_do_sponsor().declare_allocation_break(_COZINHEIRO, 2 * _UMA_HORA)
    reagendada = escala.reschedule_band(ShiftBandId("f1"), _as(_SEXTA, 16), _as(_SEXTA, 19))
    assert reagendada.worked_minutes_of(_COZINHEIRO) == _UMA_HORA


# --- CA11b (fecha): a cláusula de no-op -----------------------------------------------

_NO_OPS: dict[str, Callable[[Schedule], Schedule]] = {
    "reschedule_band": lambda e: e.reschedule_band(
        ShiftBandId("f1"), _as(_SEXTA, 16), _as(_SEXTA, 16) + timedelta(hours=8)
    ),
    "redeclare_band_break": lambda e: e.redeclare_band_break(ShiftBandId("f1"), 0),
    # Stage 4.3 (D2): a quinta idempotente — o próprio N.
    "change_demand_quantity": lambda e: e.change_demand_quantity(
        ShiftDemandId("d-coz"), DemandQuantity(1)
    ),
    "declare_workload_counting": lambda e: e.declare_workload_counting(_COZINHEIRO, True),
    "declare_allocation_break_herdando": lambda e: e.declare_allocation_break(_ATENDENTE, None),
    "declare_allocation_break_declarado": lambda e: e.declare_allocation_break(
        _COZINHEIRO, _UMA_HORA
    ),
}


@pytest.mark.parametrize("no_op", list(_NO_OPS))
def test_mutacao_com_o_valor_corrente_devolve_self(no_op: str) -> None:
    original = _cenario_do_sponsor().declare_allocation_break(_COZINHEIRO, _UMA_HORA)
    resultado = _NO_OPS[no_op](original)
    assert resultado is original
    assert resultado.version == original.version


def test_no_op_de_reschedule_band_nao_vira_duplicidade_com_outras_faixas() -> None:
    # Com outra faixa no agregado, o próprio par devolve self sem DuplicateShiftBandError.
    escala = _cenario_do_sponsor().enable_band(
        ShiftBandId("f2"), TimeRange(start=_as(_SEXTA, 18), end=_as(_SEXTA, 23))
    )
    assert escala.reschedule_band(ShiftBandId("f2"), _as(_SEXTA, 18), _as(_SEXTA, 23)) is escala


def test_as_cinco_idempotentes_sao_mutacoes_da_lei_da_versao() -> None:
    idempotentes = {nome.removesuffix("_herdando").removesuffix("_declarado") for nome in _NO_OPS}
    assert idempotentes <= set(_MUTACOES)
    assert len(idempotentes) == 5  # noqa: PLR2004
    assert len(_MUTACOES) == _TOTAL_DE_MUTACOES


# --- CA14 (fecha): nenhuma mutação de function_exception na v1 ------------------------


def _publicos(classe: type) -> dict[str, Callable[..., object]]:
    return {
        nome: membro
        for nome, membro in vars(classe).items()
        if not nome.startswith("_") and inspect.isfunction(membro)
    }


def test_so_assign_recebe_function_exception_na_superficie_da_raiz() -> None:
    # Estado da v1 — a mutação é lacuna da 4.2 (concept §5.13, §7), não
    # irrevogabilidade. `assign` a recebe só para CRIAR a alocação.
    recebem = {
        nome
        for nome, membro in _publicos(Schedule).items()
        if "function_exception" in inspect.signature(membro).parameters
    }
    assert recebem == {"assign"}


def test_a_alocacao_nao_tem_metodo_que_altere_function_exception() -> None:
    assert set(_publicos(Assignment)) == {"declare_workload_counting", "declare_break"}
    for membro in _publicos(Assignment).values():
        assert "function_exception" not in inspect.signature(membro).parameters


def test_nenhuma_mutacao_da_raiz_altera_function_exception_de_alocacao_existente() -> None:
    # Amostra comportamental, escrita à mão: as 5 mutações que tocam a faixa, a
    # demanda ou a alocação sem removê-la (as demais criam ou removem estado). A
    # prova de CA14 são as duas asserções de assinatura acima; esta confirma que a
    # marca declarada no ato de alocar sobrevive às que a atravessam.
    base = (
        _cenario_do_sponsor()
        .unassign(_COZINHEIRO)
        .assign(_COZINHEIRO, ShiftDemandId("d-coz"), EmployeeId("ana"), function_exception=True)
    )
    chamadas: dict[str, Callable[[Schedule], Schedule]] = {
        "declare_workload_counting": lambda e: e.declare_workload_counting(_COZINHEIRO, False),
        "declare_allocation_break": lambda e: e.declare_allocation_break(_COZINHEIRO, 30),
        "redeclare_band_break": lambda e: e.redeclare_band_break(ShiftBandId("f1"), 30),
        "reschedule_band": lambda e: e.reschedule_band(
            ShiftBandId("f1"), _as(_SEXTA, 17), _as(_SEXTA, 23)
        ),
        "change_demand_quantity": lambda e: e.change_demand_quantity(
            ShiftDemandId("d-coz"), DemandQuantity(3)
        ),
    }
    for nome, chamada in chamadas.items():
        resultado = chamada(base)
        assert resultado.locate_assignment(_COZINHEIRO)[2].function_exception is True, nome


# --- auditoria de mutação (B04, pela raiz) ----------------------------------------------


def test_redeclarar_o_intervalo_da_faixa_acima_do_trabalhado_restante_nao_recusa_alocacao() -> None:
    # Faixa de 8h com intervalo 400 deixa 80 min trabalhados; a alocação que
    # declara 120 continua válida, porque o teto dela é a duração nominal (480).
    escala = (
        _cenario_do_sponsor()
        .declare_allocation_break(_COZINHEIRO, 2 * _UMA_HORA)
        .redeclare_band_break(ShiftBandId("f1"), 400)
    )
    assert escala.worked_minutes_of(_COZINHEIRO) == 6 * 60
