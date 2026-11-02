"""Testes das mutações da raiz Schedule — lei da versão e matriz de erros.

CA11 (cada mutação devolve nova instância com `version + 1` e deixa a original
intacta), CA12 (a matriz método x exceção da §6 do concept), CA20 (as guardas de
remoção), CA21 (reagendamento preservador), CA25 (uma vaga por registro na
faixa), CA5 (faixa que termina depois do período) e a cláusula de gravação de
CA14 (`assign` grava as duas marcas que recebe).

As duas varreduras deste arquivo crescem com as mutações:

- `_MUTACOES` é a lista da lei da versão, **cobrada contra a classe** (as
  públicas de `Schedule` que devolvem `Schedule`);
- `_MATRIZ_DAS_MUTACOES` é a matriz de erros, **cobrada contra a §6 do concept**:
  toda célula (método da raiz x exceção) que a tabela nomeia tem de estar nela ou
  na matriz das leituras (`test_schedule.py`).
"""

import dataclasses
import re
import typing
from collections.abc import Callable
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

from restaurant_hub.features.scheduling.domain.entities.assignment import Assignment
from restaurant_hub.features.scheduling.domain.entities.schedule import Schedule
from restaurant_hub.features.scheduling.domain.entities.shift_band import ShiftBand
from restaurant_hub.features.scheduling.domain.entities.shift_demand import ShiftDemand
from restaurant_hub.features.scheduling.domain.exceptions import errors
from restaurant_hub.features.scheduling.domain.exceptions.errors import (
    AssignmentNotFoundError,
    DuplicateAssignmentError,
    DuplicateAssignmentInBandError,
    DuplicateEntityIdError,
    DuplicateShiftBandError,
    DuplicateShiftDemandError,
    InvalidAssignmentBreakError,
    InvalidTimeRangeError,
    SchedulingError,
    ShiftBandDayChangeError,
    ShiftBandInUseError,
    ShiftBandNotFoundError,
    ShiftDemandInUseError,
    ShiftDemandNotFoundError,
    TimeRangeOutsidePeriodError,
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
from tests.unit.features.scheduling.domain.test_schedule import _MATRIZ_DAS_LEITURAS

pytestmark = pytest.mark.unit

_SEGUNDA = date(2026, 9, 28)
_QUARTA = date(2026, 9, 30)
_QUINTA = date(2026, 10, 1)
_SEXTA = date(2026, 10, 2)
_DOMINGO = date(2026, 10, 4)
_SEGUNDA_SEGUINTE = date(2026, 10, 5)
_CONCEPT = Path(__file__).resolve().parents[5] / "docs/stages/4.1-scheduling-domain/concept.md"


def _as(dia: date, hora: int, minuto: int = 0) -> datetime:
    return datetime(dia.year, dia.month, dia.day, hora, minuto)


def _tr(dia: date, hora: int, horas: int, break_minutes: int = 0) -> TimeRange:
    inicio = _as(dia, hora)
    return TimeRange(start=inicio, end=inicio + timedelta(hours=horas), break_minutes=break_minutes)


def _base(version: int = 1, break_da_ana: int | None = None) -> Schedule:
    """Escala de referência.

    - `f1` sexta 16:00-00:00: `d1` cozinheiro com a Ana (`a1`), `d2` atendente vazia;
    - `f2` sexta 08:00-12:00: `d3` barman vazia;
    - `f3` quarta 10:00-14:00: sem demandas.
    """
    return Schedule(
        id=ScheduleId("escala-1"),
        tenant_id=TenantId("tenant-1"),
        unit_id=UnitId("unidade-1"),
        period=SchedulePeriod(first_day=_SEGUNDA),
        calendar=OperationalCalendar.default(),
        bands=(
            ShiftBand(
                id=ShiftBandId("f1"),
                time_range=_tr(_SEXTA, 16, 8),
                demands=(
                    ShiftDemand(
                        id=ShiftDemandId("d1"),
                        job_function_id=JobFunctionId("cozinheiro"),
                        quantity=DemandQuantity(1),
                        assignments=(
                            Assignment(
                                id=AssignmentId("a1"),
                                employee_id=EmployeeId("ana"),
                                break_minutes=break_da_ana,
                            ),
                        ),
                    ),
                    ShiftDemand(
                        id=ShiftDemandId("d2"),
                        job_function_id=JobFunctionId("atendente"),
                        quantity=DemandQuantity(1),
                    ),
                ),
            ),
            ShiftBand(
                id=ShiftBandId("f2"),
                time_range=_tr(_SEXTA, 8, 4),
                demands=(
                    ShiftDemand(
                        id=ShiftDemandId("d3"),
                        job_function_id=JobFunctionId("barman"),
                        quantity=DemandQuantity(2),
                    ),
                ),
            ),
            ShiftBand(id=ShiftBandId("f3"), time_range=_tr(_QUARTA, 10, 4)),
        ),
        version=version,
    )


def _retrato(escala: Schedule) -> tuple[object, ...]:
    """O estado da árvore, por valor — **sem** a versão.

    A versão fica fora de propósito (Checkpoint C do bloco 3, item 4): com ela
    dentro, "o estado mudou" seria verdade para qualquer mutação que só
    incrementasse a versão. Quem precisa da versão a confere à parte.
    """
    return tuple(
        (
            faixa.id,
            faixa.time_range,
            tuple(
                (
                    demanda.id,
                    demanda.job_function_id,
                    demanda.quantity,
                    tuple(
                        (
                            a.id,
                            a.employee_id,
                            a.counts_toward_workload,
                            a.function_exception,
                            a.break_minutes,
                        )
                        for a in demanda.assignments
                    ),
                )
                for demanda in faixa.demands
            ),
        )
        for faixa in escala.bands
    )


# --- CA11: a lei da versão, cobrada contra a classe -----------------------------------

_Mutacao = Callable[[Schedule], Schedule]

# Uma chamada válida de cada mutação sobre `_base()`. As chaves são a lista da lei
# da versão; `test_a_lista_de_mutacoes_e_a_da_classe` a cobra contra `Schedule`.
_MUTACOES: dict[str, _Mutacao] = {
    "enable_band": lambda e: e.enable_band(ShiftBandId("f9"), _tr(_QUINTA, 10, 4)),
    "reschedule_band": lambda e: e.reschedule_band(
        ShiftBandId("f1"), _as(_SEXTA, 17), _as(_SEXTA + timedelta(days=1), 1)
    ),
    "disable_band": lambda e: e.disable_band(ShiftBandId("f3")),
    "declare_demand": lambda e: e.declare_demand(
        ShiftDemandId("d9"), ShiftBandId("f3"), JobFunctionId("cozinheiro"), DemandQuantity(1)
    ),
    "change_demand_quantity": lambda e: e.change_demand_quantity(
        ShiftDemandId("d1"), DemandQuantity(3)
    ),
    "withdraw_demand": lambda e: e.withdraw_demand(ShiftDemandId("d2")),
    "assign": lambda e: e.assign(AssignmentId("a9"), ShiftDemandId("d2"), EmployeeId("caio")),
    "unassign": lambda e: e.unassign(AssignmentId("a1")),
    "declare_workload_counting": lambda e: e.declare_workload_counting(AssignmentId("a1"), False),
    # Task 10: as 2 mutações de intervalo (a lei da versão passa de 9 para 11).
    "redeclare_band_break": lambda e: e.redeclare_band_break(ShiftBandId("f1"), 30),
    "declare_allocation_break": lambda e: e.declare_allocation_break(AssignmentId("a1"), 30),
}


def test_a_lista_de_mutacoes_e_a_da_classe() -> None:
    # As públicas de Schedule que devolvem Schedule. Uma mutação nova sem entrada
    # na lista (e portanto sem a lei da versão) reprova aqui.
    mutacoes = {
        nome
        for nome, membro in vars(Schedule).items()
        if not nome.startswith("_")
        and callable(membro)
        and typing.get_type_hints(membro).get("return") is Schedule
    }
    assert mutacoes == set(_MUTACOES)


@pytest.mark.parametrize("mutacao", list(_MUTACOES))
@pytest.mark.parametrize("version", [1, 5])
def test_cada_mutacao_devolve_nova_instancia_com_versao_mais_um(mutacao: str, version: int) -> None:
    original = _base(version=version)
    antes = _retrato(original)
    resultado = _MUTACOES[mutacao](original)
    assert resultado is not original
    assert resultado.version == version + 1
    assert original.version == version
    assert _retrato(original) == antes
    assert _retrato(resultado) != antes


# --- CA12: a matriz método x exceção --------------------------------------------------

_Cenario = Callable[[Schedule], object]

_MATRIZ_DAS_MUTACOES: tuple[tuple[str, type[SchedulingError], _Cenario], ...] = (
    # ShiftBandNotFoundError
    (
        "reschedule_band",
        ShiftBandNotFoundError,
        lambda e: e.reschedule_band(ShiftBandId("x"), _as(_SEXTA, 9), _as(_SEXTA, 10)),
    ),
    ("disable_band", ShiftBandNotFoundError, lambda e: e.disable_band(ShiftBandId("x"))),
    (
        "declare_demand",
        ShiftBandNotFoundError,
        lambda e: e.declare_demand(
            ShiftDemandId("d9"), ShiftBandId("x"), JobFunctionId("cozinheiro"), DemandQuantity(1)
        ),
    ),
    # ShiftDemandNotFoundError
    (
        "change_demand_quantity",
        ShiftDemandNotFoundError,
        lambda e: e.change_demand_quantity(ShiftDemandId("x"), DemandQuantity(1)),
    ),
    ("withdraw_demand", ShiftDemandNotFoundError, lambda e: e.withdraw_demand(ShiftDemandId("x"))),
    (
        "assign",
        ShiftDemandNotFoundError,
        lambda e: e.assign(AssignmentId("a9"), ShiftDemandId("x"), EmployeeId("caio")),
    ),
    # AssignmentNotFoundError
    ("unassign", AssignmentNotFoundError, lambda e: e.unassign(AssignmentId("x"))),
    (
        "declare_workload_counting",
        AssignmentNotFoundError,
        lambda e: e.declare_workload_counting(AssignmentId("x"), False),
    ),
    # TimeRangeOutsidePeriodError — os 2 caminhos
    (
        "enable_band",
        TimeRangeOutsidePeriodError,
        lambda e: e.enable_band(ShiftBandId("f9"), _tr(_SEGUNDA_SEGUINTE, 10, 4)),
    ),
    (
        "reschedule_band",
        TimeRangeOutsidePeriodError,
        lambda e: e.reschedule_band(
            ShiftBandId("f1"), _as(_SEGUNDA_SEGUINTE, 16), _as(_SEGUNDA_SEGUINTE, 20)
        ),
    ),
    # DuplicateShiftBandError — os 2 caminhos (o par de OUTRA faixa, intervalo diferente)
    (
        "enable_band",
        DuplicateShiftBandError,
        lambda e: e.enable_band(ShiftBandId("f9"), _tr(_SEXTA, 8, 4, break_minutes=30)),
    ),
    (
        "reschedule_band",
        DuplicateShiftBandError,
        lambda e: e.reschedule_band(ShiftBandId("f1"), _as(_SEXTA, 8), _as(_SEXTA, 12)),
    ),
    # reagendamento para outro dia operacional dentro do período
    (
        "reschedule_band",
        ShiftBandDayChangeError,
        lambda e: e.reschedule_band(ShiftBandId("f1"), _as(_QUINTA, 16), _as(_QUINTA, 23)),
    ),
    # encurtar a faixa abaixo do intervalo declarado de uma alocação
    (
        "reschedule_band",
        InvalidAssignmentBreakError,
        lambda e: e.reschedule_band(ShiftBandId("f1"), _as(_SEXTA, 16), _as(_SEXTA, 17)),
    ),
    # guardas de remoção
    ("disable_band", ShiftBandInUseError, lambda e: e.disable_band(ShiftBandId("f1"))),
    ("withdraw_demand", ShiftDemandInUseError, lambda e: e.withdraw_demand(ShiftDemandId("d1"))),
    # duplicidades de demanda e de alocação
    (
        "declare_demand",
        DuplicateShiftDemandError,
        lambda e: e.declare_demand(
            ShiftDemandId("d9"), ShiftBandId("f1"), JobFunctionId("cozinheiro"), DemandQuantity(1)
        ),
    ),
    (
        "assign",
        DuplicateAssignmentError,
        lambda e: e.assign(AssignmentId("a9"), ShiftDemandId("d1"), EmployeeId("ana")),
    ),
    (
        "assign",
        DuplicateAssignmentInBandError,
        lambda e: e.assign(AssignmentId("a9"), ShiftDemandId("d2"), EmployeeId("ana")),
    ),
    # ids internos repetidos pelas mutações (a raiz revalida o agregado inteiro)
    (
        "enable_band",
        DuplicateEntityIdError,
        lambda e: e.enable_band(ShiftBandId("f2"), _tr(_QUINTA, 10, 4)),
    ),
    (
        "declare_demand",
        DuplicateEntityIdError,
        lambda e: e.declare_demand(
            ShiftDemandId("d3"), ShiftBandId("f3"), JobFunctionId("cozinheiro"), DemandQuantity(1)
        ),
    ),
    (
        "assign",
        DuplicateEntityIdError,
        lambda e: e.assign(AssignmentId("a1"), ShiftDemandId("d3"), EmployeeId("caio")),
    ),
    # destino com start >= end: a recusa sai do TimeRange reconstruído pela faixa
    (
        "reschedule_band",
        InvalidTimeRangeError,
        lambda e: e.reschedule_band(ShiftBandId("f1"), _as(_SEXTA, 16), _as(_SEXTA, 15)),
    ),
    # Task 10: as linhas das 2 mutações de intervalo
    (
        "redeclare_band_break",
        ShiftBandNotFoundError,
        lambda e: e.redeclare_band_break(ShiftBandId("x"), 30),
    ),
    (
        "redeclare_band_break",
        InvalidTimeRangeError,
        lambda e: e.redeclare_band_break(ShiftBandId("f1"), 8 * 60),
    ),
    (
        "declare_allocation_break",
        AssignmentNotFoundError,
        lambda e: e.declare_allocation_break(AssignmentId("x"), 30),
    ),
    (
        "declare_allocation_break",
        InvalidAssignmentBreakError,
        lambda e: e.declare_allocation_break(AssignmentId("a1"), 8 * 60),
    ),
)


@pytest.mark.parametrize(
    ("metodo", "excecao", "cenario"),
    _MATRIZ_DAS_MUTACOES,
    ids=[f"{m}-{x.__name__}" for m, x, _ in _MATRIZ_DAS_MUTACOES],
)
def test_cada_celula_da_matriz_recusa_e_deixa_a_original_intacta(
    metodo: str, excecao: type[SchedulingError], cenario: _Cenario
) -> None:
    original = _base(break_da_ana=90)
    antes = _retrato(original)
    with pytest.raises(excecao):
        cenario(original)
    assert _retrato(original) == antes
    assert original.version == 1
    assert metodo in _MUTACOES


def _celulas_da_secao_6() -> set[tuple[str, str]]:
    """As células (método da raiz, exceção) que a tabela §6 do concept nomeia."""
    texto = _CONCEPT.read_text(encoding="utf-8")
    secao = texto.split("## 6. Casos de erro e exceções", 1)[1].split("\n## 7.", 1)[0]
    metodos_da_raiz = {nome for nome, membro in vars(Schedule).items() if callable(membro)}
    celulas: set[tuple[str, str]] = set()
    for linha in secao.splitlines():
        colunas = linha.split("|")
        if len(colunas) < 4 or not colunas[2].strip().startswith("`"):  # noqa: PLR2004
            continue
        excecao = colunas[2].strip().strip("`")
        for nome in re.findall(r"`([a-z_]+)`", colunas[1]):
            if nome in metodos_da_raiz:
                celulas.add((nome, excecao))
    return celulas


# Quantas células (método da raiz x exceção) a §6 nomeia hoje. É o piso exato da
# leitura da tabela: se o parser deixar de ver uma linha, a contagem cai e reprova.
_CELULAS_DA_SECAO_6 = 33


def test_a_matriz_e_a_secao_6_do_concept_coincidem() -> None:
    # Nos dois sentidos (Checkpoint C do bloco 3, item 1): toda célula que a §6
    # nomeia é produzida por um cenário da matriz, e toda célula produzida está
    # na §6. Apagar uma linha da matriz ou da tabela reprova.
    celulas = _celulas_da_secao_6()
    assert len(celulas) == _CELULAS_DA_SECAO_6
    produzidas = {(m, x.__name__) for m, x, _ in _MATRIZ_DAS_MUTACOES} | {
        (m, x.__name__) for m, x in _MATRIZ_DAS_LEITURAS
    }
    assert celulas <= produzidas, sorted(celulas - produzidas)
    assert produzidas <= celulas, sorted(produzidas - celulas)


def test_a_matriz_so_usa_excecoes_do_bc() -> None:
    for _, excecao, _ in _MATRIZ_DAS_MUTACOES:
        assert vars(errors)[excecao.__name__] is excecao


# --- CA5: a faixa que termina depois do período ---------------------------------------


def test_enable_band_aceita_a_faixa_do_ultimo_dia_que_termina_depois_do_periodo() -> None:
    domingo_a_noite = _tr(_DOMINGO, 22, 8)
    escala = _base().enable_band(ShiftBandId("f9"), domingo_a_noite)
    assert escala.band(ShiftBandId("f9")).time_range.end.date() == _SEGUNDA_SEGUINTE
    assert escala.operational_day_of(escala.band(ShiftBandId("f9"))) == _DOMINGO


def test_enable_band_cria_a_faixa_sem_demandas() -> None:
    escala = _base().enable_band(ShiftBandId("f9"), _tr(_QUINTA, 10, 4))
    assert escala.band(ShiftBandId("f9")).demands == ()
    assert escala.band(ShiftBandId("f9")).time_range == _tr(_QUINTA, 10, 4)


def test_enable_band_com_id_repetido_e_recusado_pela_raiz() -> None:
    with pytest.raises(DuplicateEntityIdError, match="ShiftBandId"):
        _base().enable_band(ShiftBandId("f2"), _tr(_QUINTA, 10, 4))


# --- CA20: as guardas de remoção e o caso sem alocação --------------------------------


def test_disable_band_sem_alocacao_descarta_as_demandas_junto() -> None:
    escala = _base().disable_band(ShiftBandId("f2"))
    with pytest.raises(ShiftBandNotFoundError):
        escala.band(ShiftBandId("f2"))
    with pytest.raises(ShiftDemandNotFoundError):
        escala.locate_demand(ShiftDemandId("d3"))
    assert [faixa.id for faixa in escala.bands] == [ShiftBandId("f1"), ShiftBandId("f3")]


def test_disable_band_com_alocacao_e_recusado_sem_cascata() -> None:
    original = _base()
    with pytest.raises(ShiftBandInUseError):
        original.disable_band(ShiftBandId("f1"))
    assert original.locate_assignment(AssignmentId("a1"))[2].employee_id == EmployeeId("ana")


def test_disable_band_depois_de_desalocar_passa() -> None:
    escala = _base().unassign(AssignmentId("a1")).disable_band(ShiftBandId("f1"))
    assert [faixa.id for faixa in escala.bands] == [ShiftBandId("f2"), ShiftBandId("f3")]
    assert escala.version == 3  # noqa: PLR2004


def test_withdraw_demand_com_n_positivo_e_sem_alocados_passa() -> None:
    escala = _base().withdraw_demand(ShiftDemandId("d3"))
    assert escala.band(ShiftBandId("f2")).demands == ()


def test_withdraw_demand_com_alocacao_e_recusado() -> None:
    with pytest.raises(ShiftDemandInUseError):
        _base().withdraw_demand(ShiftDemandId("d1"))


# --- CA21 (parcial): reagendamento preservador ----------------------------------------


def test_reschedule_band_preserva_ids_demandas_alocacoes_e_intervalo() -> None:
    original = _base(break_da_ana=30)
    original = dataclasses.replace(
        original,
        bands=(original.bands[0].with_band_break(60), *original.bands[1:]),
    )
    reagendada = original.reschedule_band(
        ShiftBandId("f1"), _as(_SEXTA, 17), _as(_SEXTA + timedelta(days=1), 1)
    )
    faixa = reagendada.band(ShiftBandId("f1"))
    assert faixa.time_range == TimeRange(
        start=_as(_SEXTA, 17), end=_as(_SEXTA + timedelta(days=1), 1), break_minutes=60
    )
    # Conteúdo, não só ids: o retrato das demandas é o mesmo.
    assert _retrato(reagendada)[0][2] == _retrato(original)[0][2]
    assert reagendada.bands[0].id == ShiftBandId("f1")


def test_reschedule_band_para_a_madrugada_do_mesmo_dia_operacional_passa() -> None:
    # Sábado 01:00 ainda é sexta com corte 05:00: não é mudança de dia.
    reagendada = _base().reschedule_band(
        ShiftBandId("f2"), _as(_SEXTA + timedelta(days=1), 1), _as(_SEXTA + timedelta(days=1), 4)
    )
    assert reagendada.operational_day_of(reagendada.band(ShiftBandId("f2"))) == _SEXTA


def test_reschedule_band_para_o_dia_seguinte_depois_do_corte_e_mudanca_de_dia() -> None:
    # Sábado 05:00 já é sábado: a borda exata do corte.
    with pytest.raises(ShiftBandDayChangeError):
        _base().reschedule_band(
            ShiftBandId("f2"),
            _as(_SEXTA + timedelta(days=1), 5),
            _as(_SEXTA + timedelta(days=1), 9),
        )


def test_reschedule_band_nao_colide_com_a_propria_faixa() -> None:
    # Destino que se sobrepõe ao próprio par antigo não é colisão.
    reagendada = _base().reschedule_band(ShiftBandId("f1"), _as(_SEXTA, 15), _as(_SEXTA, 23))
    assert reagendada.band(ShiftBandId("f1")).time_range.start == _as(_SEXTA, 15)


def test_reschedule_band_com_destino_que_cruza_o_corte_e_do_dia_do_start() -> None:
    # Sexta 22:00 a sábado 06:00: o fim cai depois do corte de sábado, e o dia é o
    # do início (§5.8, ADR 4.1.0008) — Checkpoint C do bloco 3, item 2.
    reagendada = _base().reschedule_band(
        ShiftBandId("f1"), _as(_SEXTA, 22), _as(_SEXTA + timedelta(days=1), 6)
    )
    faixa = reagendada.band(ShiftBandId("f1"))
    assert reagendada.calendar.operational_day_of(faixa.time_range.end) != _SEXTA
    assert reagendada.operational_day_of(faixa) == _SEXTA


def test_reschedule_band_cujo_start_cai_no_dia_anterior_e_recusado_mesmo_com_fim_no_dia() -> None:
    # Quinta 22:00 a sexta 06:00: o fim é da sexta (o dia da faixa), o início não.
    with pytest.raises(ShiftBandDayChangeError):
        _base().reschedule_band(ShiftBandId("f1"), _as(_QUINTA, 22), _as(_SEXTA, 6))


def test_reschedule_band_do_ultimo_dia_para_depois_do_periodo_pelo_fim_e_aceito() -> None:
    # ADR 4.1.0008 §3 pelo caminho do reagendamento: domingo 22:00 a segunda 06:00.
    escala = _base().enable_band(ShiftBandId("f9"), _tr(_DOMINGO, 18, 3))
    reagendada = escala.reschedule_band(
        ShiftBandId("f9"), _as(_DOMINGO, 22), _as(_SEGUNDA_SEGUINTE, 6)
    )
    assert reagendada.operational_day_of(reagendada.band(ShiftBandId("f9"))) == _DOMINGO


# --- CA25 (fecha): uma vaga por registro na faixa, nos dois sentidos ------------------


def test_segunda_vaga_da_mesma_ana_na_mesma_faixa_e_recusada() -> None:
    original = _base()
    with pytest.raises(DuplicateAssignmentInBandError):
        original.assign(AssignmentId("a9"), ShiftDemandId("d2"), EmployeeId("ana"))
    # Versão não incrementa; o agregado anterior fica intacto e a vaga de
    # atendente, descoberta.
    assert original.version == 1
    assert original.locate_demand(ShiftDemandId("d1"))[1].allocated == 1
    assert original.locate_demand(ShiftDemandId("d2"))[1].allocated == 0


def test_mesma_ana_na_mesma_demanda_levanta_a_outra_excecao() -> None:
    with pytest.raises(DuplicateAssignmentError):
        _base().assign(AssignmentId("a9"), ShiftDemandId("d1"), EmployeeId("ana"))


def test_mesma_ana_em_faixas_distintas_sobrepostas_e_aceita() -> None:
    escala = (
        _base()
        .enable_band(ShiftBandId("f9"), _tr(_SEXTA, 18, 5))
        .declare_demand(
            ShiftDemandId("d9"), ShiftBandId("f9"), JobFunctionId("atendente"), DemandQuantity(1)
        )
        .assign(AssignmentId("a9"), ShiftDemandId("d9"), EmployeeId("ana"))
    )
    cozinha, salao = escala.band(ShiftBandId("f1")), escala.band(ShiftBandId("f9"))
    assert cozinha.time_range.overlaps(salao.time_range)
    assert cozinha.assignment_count == 1
    assert salao.assignment_count == 1


# --- CA14 (gravação): assign grava as duas marcas que recebe --------------------------


@pytest.mark.parametrize(
    ("conta", "excecao_de_funcao"),
    [(True, False), (False, True), (False, False), (True, True)],
)
def test_assign_grava_as_duas_marcas_e_o_intervalo_nasce_none(
    conta: bool, excecao_de_funcao: bool
) -> None:
    escala = _base().assign(
        AssignmentId("a9"),
        ShiftDemandId("d2"),
        EmployeeId("caio"),
        counts_toward_workload=conta,
        function_exception=excecao_de_funcao,
    )
    alocacao = escala.locate_assignment(AssignmentId("a9"))[2]
    assert alocacao.counts_toward_workload is conta
    assert alocacao.function_exception is excecao_de_funcao
    assert alocacao.break_minutes is None


def test_assign_sem_marcas_usa_os_defaults() -> None:
    alocacao = (
        _base()
        .assign(AssignmentId("a9"), ShiftDemandId("d2"), EmployeeId("caio"))
        .locate_assignment(AssignmentId("a9"))[2]
    )
    assert alocacao.counts_toward_workload is True
    assert alocacao.function_exception is False


def test_declare_workload_counting_alterna_a_marca() -> None:
    escala = _base().declare_workload_counting(AssignmentId("a1"), False)
    assert escala.locate_assignment(AssignmentId("a1"))[2].counts_toward_workload is False


# --- demais caminhos positivos --------------------------------------------------------


def test_change_demand_quantity_abaixo_dos_alocados_passa() -> None:
    escala = _base().change_demand_quantity(ShiftDemandId("d1"), DemandQuantity(0))
    _, demanda = escala.locate_demand(ShiftDemandId("d1"))
    assert demanda.quantity == DemandQuantity(0)
    assert demanda.allocated == 1


def test_declare_demand_cria_a_demanda_na_faixa() -> None:
    escala = _base().declare_demand(
        ShiftDemandId("d9"), ShiftBandId("f3"), JobFunctionId("cozinheiro"), DemandQuantity(2)
    )
    faixa, demanda = escala.locate_demand(ShiftDemandId("d9"))
    assert faixa.id == ShiftBandId("f3")
    assert demanda.quantity == DemandQuantity(2)
    assert demanda.assignments == ()


def test_declare_demand_com_id_de_outra_faixa_e_recusado_pela_raiz() -> None:
    with pytest.raises(DuplicateEntityIdError, match="ShiftDemandId"):
        _base().declare_demand(
            ShiftDemandId("d3"), ShiftBandId("f3"), JobFunctionId("cozinheiro"), DemandQuantity(1)
        )


def test_assign_com_id_de_alocacao_repetido_e_recusado_pela_raiz() -> None:
    with pytest.raises(DuplicateEntityIdError, match="AssignmentId"):
        _base().assign(AssignmentId("a1"), ShiftDemandId("d3"), EmployeeId("caio"))


def test_unassign_retira_so_a_alocacao() -> None:
    escala = _base().unassign(AssignmentId("a1"))
    with pytest.raises(AssignmentNotFoundError):
        escala.locate_assignment(AssignmentId("a1"))
    assert escala.locate_demand(ShiftDemandId("d1"))[1].allocated == 0


def test_enable_band_nao_produz_invalid_time_range_error() -> None:
    # enable_band recebe um TimeRange já construído: a recusa de valor é do
    # construtor do TimeRange, antes da chamada — por isso a §6 não tem a célula
    # `enable_band` x `InvalidTimeRangeError`.
    with pytest.raises(InvalidTimeRangeError):
        _tr(_QUINTA, 10, 4, break_minutes=240)


# --- auditoria de mutação (R34/R36): o intervalo da faixa sobrevive às mutações ------


def _base_com_intervalo_na_faixa() -> Schedule:
    base = _base()
    return dataclasses.replace(base, bands=(base.bands[0].with_band_break(60), *base.bands[1:]))


@pytest.mark.parametrize(
    "mutacao",
    [
        "assign",
        "unassign",
        "change_demand_quantity",
        "declare_workload_counting",
        "declare_allocation_break",
    ],
)
def test_mutacoes_de_demanda_e_alocacao_preservam_o_intervalo_da_faixa(mutacao: str) -> None:
    # As 5 reconstroem a faixa por `_replacing_demand`. Valor ABSOLUTO, e não "igual ao
    # antes": uma reconstrução que zerasse o intervalo da faixa passaria numa
    # comparação com um arranjo que também passou por ela (auditoria, R34/R36).
    depois = _MUTACOES[mutacao](_base_com_intervalo_na_faixa())
    assert depois.band(ShiftBandId("f1")).time_range == _tr(_SEXTA, 16, 8, break_minutes=60)


def test_quem_herda_continua_com_sete_horas_depois_de_outra_alocacao() -> None:
    escala = _base_com_intervalo_na_faixa().assign(
        AssignmentId("a9"), ShiftDemandId("d1"), EmployeeId("bia")
    )
    assert escala.worked_minutes_of(AssignmentId("a1")) == 7 * 60
