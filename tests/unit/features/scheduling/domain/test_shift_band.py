"""Testes da entidade ShiftBand (entities/shift_band.py).

Fecha CA25 no lado da **reidratação** (construção direta com o mesmo registro em
duas demandas da faixa). Parcial de CA10 (as quatro recusas da construção),
CA15, CA22 (`ShiftBandId`) e CA23 (intervalo efetivo e divergência no nível da
faixa). Toda checagem par a par é provada com o par **não consecutivo** numa
coleção de 3.
"""

import dataclasses
from datetime import datetime

import pytest

from restaurant_hub.features.scheduling.domain.entities.assignment import Assignment
from restaurant_hub.features.scheduling.domain.entities.shift_band import ShiftBand
from restaurant_hub.features.scheduling.domain.entities.shift_demand import ShiftDemand
from restaurant_hub.features.scheduling.domain.exceptions.errors import (
    DuplicateAssignmentError,
    DuplicateAssignmentInBandError,
    DuplicateEntityIdError,
    DuplicateShiftDemandError,
    InvalidAssignmentBreakError,
    InvalidIdentifierError,
    InvalidTimeRangeError,
)
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

pytestmark = pytest.mark.unit

# Sexta 2026-10-02, 16:00 a sábado 00:00 — 480 minutos nominais.
_INICIO = datetime(2026, 10, 2, 16, 0)
_FIM = datetime(2026, 10, 3, 0, 0)
_NOMINAL = 480
_UMA_HORA = 60
_ID = ShiftBandId("faixa-1")


def _faixa_16_00(break_minutes: int = 0) -> TimeRange:
    return TimeRange(start=_INICIO, end=_FIM, break_minutes=break_minutes)


def _aloc(aloc: str, funcionario: str, break_minutes: int | None = None) -> Assignment:
    return Assignment(
        id=AssignmentId(aloc), employee_id=EmployeeId(funcionario), break_minutes=break_minutes
    )


def _dem(dem: str, funcao: str, *alocacoes: Assignment) -> ShiftDemand:
    return ShiftDemand(
        id=ShiftDemandId(dem),
        job_function_id=JobFunctionId(funcao),
        quantity=DemandQuantity(1),
        assignments=alocacoes,
    )


def _banda(*demandas: ShiftDemand, break_minutes: int = 0) -> ShiftBand:
    return ShiftBand(id=_ID, time_range=_faixa_16_00(break_minutes), demands=demandas)


# --- CA10 (parcial): as quatro recusas da construção ----------------------------------


def test_mesma_funcao_em_demandas_nao_consecutivas_e_recusada() -> None:
    with pytest.raises(DuplicateShiftDemandError):
        _banda(_dem("d1", "cozinheiro"), _dem("d2", "atendente"), _dem("d3", "cozinheiro"))


def test_mesmo_shift_demand_id_nao_consecutivo_e_recusado() -> None:
    with pytest.raises(DuplicateEntityIdError, match="ShiftDemandId"):
        _banda(_dem("d1", "cozinheiro"), _dem("d2", "atendente"), _dem("d1", "barman"))


def test_intervalo_da_alocacao_igual_ao_nominal_e_recusado_em_qualquer_posicao() -> None:
    # A alocação inválida é a última de 3: o laço que olhasse só a primeira passaria.
    with pytest.raises(InvalidAssignmentBreakError, match="duração nominal da faixa"):
        _banda(
            _dem("d1", "cozinheiro", _aloc("a1", "ana", 30), _aloc("a2", "bia")),
            _dem("d2", "atendente", _aloc("a3", "caio", _NOMINAL)),
        )


def test_intervalo_da_alocacao_acima_do_nominal_e_recusado() -> None:
    with pytest.raises(InvalidAssignmentBreakError):
        _banda(_dem("d1", "cozinheiro", _aloc("a1", "ana", _NOMINAL + 1)))


def test_intervalo_da_alocacao_nominal_menos_um_e_aceito() -> None:
    banda = _banda(_dem("d1", "cozinheiro", _aloc("a1", "ana", _NOMINAL - 1)))
    assert banda.assignment_count == 1


def test_mesmo_registro_em_demandas_nao_consecutivas_e_recusado() -> None:
    # Caminho da reidratação da 4.4 — nenhuma mutação atravessa (CA25).
    with pytest.raises(DuplicateAssignmentInBandError):
        _banda(
            _dem("d1", "cozinheiro", _aloc("a1", "ana")),
            _dem("d2", "atendente", _aloc("a2", "bia")),
            _dem("d3", "barman", _aloc("a3", "ana")),
        )


def test_mesmo_registro_em_alocacoes_nao_consecutivas_de_duas_demandas_e_recusado() -> None:
    # Coleção de 3 alocações; o par (ana, ana) está nas posições 0 e 2.
    with pytest.raises(DuplicateAssignmentInBandError):
        _banda(
            _dem("d1", "cozinheiro", _aloc("a1", "ana"), _aloc("a2", "bia")),
            _dem("d2", "atendente", _aloc("a3", "ana")),
        )


def test_mesmo_registro_na_mesma_demanda_levanta_a_outra_excecao() -> None:
    # As duas linhas da §6 são disjuntas por nível: na mesma demanda sai
    # DuplicateAssignmentError (da ShiftDemand), nunca a da faixa.
    with pytest.raises(DuplicateAssignmentError):
        _banda(_dem("d1", "cozinheiro", _aloc("a1", "ana"), _aloc("a2", "ana")))


def test_mesmo_registro_em_faixas_distintas_e_aceito() -> None:
    # Faixas distintas, mesmo sobrepostas, são caso de política (§5.18, §5.23).
    cozinha = _banda(_dem("d1", "cozinheiro", _aloc("a1", "ana")))
    salao = ShiftBand(
        id=ShiftBandId("faixa-2"),
        time_range=TimeRange(start=datetime(2026, 10, 2, 18, 0), end=datetime(2026, 10, 2, 23, 0)),
        demands=(_dem("d2", "atendente", _aloc("a2", "ana")),),
    )
    assert cozinha.time_range.overlaps(salao.time_range)
    assert cozinha.assignment_count == 1
    assert salao.assignment_count == 1


def test_tres_demandas_distintas_sao_aceitas() -> None:
    banda = _banda(
        _dem("d1", "cozinheiro", _aloc("a1", "ana"), _aloc("a2", "bia")),
        _dem("d2", "atendente", _aloc("a3", "caio")),
        _dem("d3", "barman"),
    )
    assert banda.assignment_count == 3  # noqa: PLR2004


# --- assignment_count -----------------------------------------------------------------


def test_assignment_count_soma_todas_as_demandas() -> None:
    assert _banda().assignment_count == 0
    assert _banda(_dem("d1", "cozinheiro")).assignment_count == 0
    banda = _banda(
        _dem("d1", "cozinheiro", _aloc("a1", "ana")),
        _dem("d2", "atendente", _aloc("a2", "bia"), _aloc("a3", "caio")),
    )
    assert banda.assignment_count == 3  # noqa: PLR2004


# --- CA23 (nível da faixa): intervalo efetivo e divergência ---------------------------


def test_cenario_do_sponsor_sete_e_oito_horas_na_mesma_faixa() -> None:
    cozinheiro = _aloc("a1", "ana", _UMA_HORA)
    atendente = _aloc("a2", "bia")
    banda = _banda(_dem("d1", "cozinheiro", cozinheiro), _dem("d2", "atendente", atendente))

    assert banda.effective_break_of(cozinheiro) == _UMA_HORA
    assert banda.has_break_divergence(cozinheiro) is True
    assert banda.time_range.worked_minutes(banda.effective_break_of(cozinheiro)) == 7 * 60

    assert banda.effective_break_of(atendente) == 0
    assert banda.has_break_divergence(atendente) is False
    assert banda.time_range.worked_minutes(banda.effective_break_of(atendente)) == 8 * 60


def test_alocacao_sem_declaracao_herda_o_intervalo_da_faixa() -> None:
    alocacao = _aloc("a1", "ana")
    banda = _banda(_dem("d1", "cozinheiro", alocacao), break_minutes=_UMA_HORA)
    assert banda.effective_break_of(alocacao) == _UMA_HORA
    assert banda.has_break_divergence(alocacao) is False


def test_declarado_igual_ao_da_faixa_nao_diverge() -> None:
    alocacao = _aloc("a1", "ana", _UMA_HORA)
    banda = _banda(_dem("d1", "cozinheiro", alocacao), break_minutes=_UMA_HORA)
    assert banda.effective_break_of(alocacao) == _UMA_HORA
    assert banda.has_break_divergence(alocacao) is False


def test_declarado_zero_em_faixa_com_intervalo_diverge() -> None:
    # 0 declarado é declaração, não ausência.
    alocacao = _aloc("a1", "ana", 0)
    banda = _banda(_dem("d1", "cozinheiro", alocacao), break_minutes=_UMA_HORA)
    assert banda.effective_break_of(alocacao) == 0
    assert banda.has_break_divergence(alocacao) is True


def test_divergencia_e_derivada_e_acompanha_o_intervalo_da_faixa() -> None:
    alocacao = _aloc("a1", "ana", _UMA_HORA)
    banda = _banda(_dem("d1", "cozinheiro", alocacao))
    assert banda.has_break_divergence(alocacao) is True
    assert banda.with_band_break(_UMA_HORA).has_break_divergence(alocacao) is False
    assert "has_break_divergence" not in {campo.name for campo in dataclasses.fields(ShiftBand)}


# --- rescheduled_to -------------------------------------------------------------------


def test_rescheduled_to_preserva_intervalo_demandas_e_alocacoes() -> None:
    demandas = (
        _dem("d1", "cozinheiro", _aloc("a1", "ana", 30)),
        _dem("d2", "atendente", _aloc("a2", "bia")),
    )
    original = ShiftBand(id=_ID, time_range=_faixa_16_00(_UMA_HORA), demands=demandas)
    novo_inicio, novo_fim = datetime(2026, 10, 2, 17, 0), datetime(2026, 10, 3, 1, 0)

    reagendada = original.rescheduled_to(novo_inicio, novo_fim)

    assert reagendada is not original
    assert reagendada.time_range == TimeRange(
        start=novo_inicio, end=novo_fim, break_minutes=_UMA_HORA
    )
    # Por atributo, não por `==` (que compara só ids — Checkpoint C do bloco 2,
    # item 5): uma reconstrução que zerasse intervalo ou marcas passaria.
    assert reagendada.demands is original.demands
    assert [
        (a.id, a.employee_id, a.counts_toward_workload, a.function_exception, a.break_minutes)
        for d in reagendada.demands
        for a in d.assignments
    ] == [
        (AssignmentId("a1"), EmployeeId("ana"), True, False, 30),
        (AssignmentId("a2"), EmployeeId("bia"), True, False, None),
    ]
    assert original.time_range == _faixa_16_00(_UMA_HORA)


def test_rescheduled_to_abaixo_do_intervalo_de_uma_alocacao_e_recusado() -> None:
    original = _banda(_dem("d1", "cozinheiro", _aloc("a1", "ana", _UMA_HORA)))
    with pytest.raises(InvalidAssignmentBreakError):
        original.rescheduled_to(_INICIO, datetime(2026, 10, 2, 17, 0))


def test_rescheduled_to_abaixo_do_intervalo_da_faixa_e_recusado_pelo_time_range() -> None:
    original = _banda(break_minutes=_UMA_HORA)
    with pytest.raises(InvalidTimeRangeError):
        original.rescheduled_to(_INICIO, datetime(2026, 10, 2, 17, 0))


# --- os quatro construtores derivados -------------------------------------------------


def test_with_band_break_troca_so_o_intervalo_da_faixa() -> None:
    alocacao = _aloc("a1", "ana", 30)
    original = _banda(_dem("d1", "cozinheiro", alocacao))
    redeclarada = original.with_band_break(_UMA_HORA)
    assert redeclarada is not original
    assert redeclarada.time_range == _faixa_16_00(_UMA_HORA)
    assert redeclarada.demands[0].assignments == (alocacao,)
    assert redeclarada.demands[0].assignments[0].break_minutes == 30  # noqa: PLR2004
    assert original.time_range == _faixa_16_00()


def test_with_band_break_igual_ao_nominal_e_recusado_pelo_time_range() -> None:
    with pytest.raises(InvalidTimeRangeError):
        _banda().with_band_break(_NOMINAL)


@pytest.mark.parametrize(
    ("faixa_antes", "faixa_depois"),
    [
        pytest.param(_UMA_HORA, 0, id="faixa_desce_abaixo_da_alocacao"),
        pytest.param(0, 3 * _UMA_HORA, id="faixa_passa_a_exceder_a_alocacao"),
    ],
)
def test_with_band_break_nao_limita_o_intervalo_da_alocacao(
    faixa_antes: int, faixa_depois: int
) -> None:
    # O teto do intervalo da alocação é a duração nominal, não o intervalo da
    # faixa (concept §5.6): nas duas direções a faixa redeclarada é válida e só
    # diverge — a segunda é a direção literal da cláusula que o [deviation] da
    # Task 07 refuta (§7).
    alocacao = _aloc("a1", "ana", 2 * _UMA_HORA)
    banda = _banda(_dem("d1", "cozinheiro", alocacao), break_minutes=faixa_antes)
    redeclarada = banda.with_band_break(faixa_depois)
    assert redeclarada.time_range.break_minutes == faixa_depois
    assert redeclarada.effective_break_of(alocacao) == 2 * _UMA_HORA
    assert redeclarada.has_break_divergence(alocacao) is True


def test_with_demand_acrescenta_no_fim() -> None:
    original = _banda(_dem("d1", "cozinheiro"))
    nova = _dem("d2", "atendente", _aloc("a1", "ana"))
    acrescida = original.with_demand(nova)
    assert acrescida is not original
    assert acrescida.demands[-1] is nova
    assert len(original.demands) == 1


def test_with_demand_de_funcao_repetida_e_recusado() -> None:
    original = _banda(_dem("d1", "cozinheiro"))
    with pytest.raises(DuplicateShiftDemandError):
        original.with_demand(_dem("d2", "cozinheiro"))
    assert len(original.demands) == 1


def test_with_demand_revalida_a_vaga_unica_e_o_teto_do_intervalo() -> None:
    original = _banda(_dem("d1", "cozinheiro", _aloc("a1", "ana")))
    with pytest.raises(DuplicateAssignmentInBandError):
        original.with_demand(_dem("d2", "atendente", _aloc("a2", "ana")))
    with pytest.raises(InvalidAssignmentBreakError):
        original.with_demand(_dem("d2", "atendente", _aloc("a2", "bia", _NOMINAL)))


def test_with_demands_substitui_o_conjunto() -> None:
    original = _banda(_dem("d1", "cozinheiro"))
    novas = (_dem("d2", "atendente"), _dem("d3", "barman"))
    substituida = original.with_demands(novas)
    assert substituida is not original
    assert substituida.demands == novas
    assert [d.id for d in original.demands] == [ShiftDemandId("d1")]


def test_with_demands_de_funcao_repetida_e_recusado() -> None:
    with pytest.raises(DuplicateShiftDemandError):
        _banda().with_demands(
            (_dem("d1", "cozinheiro"), _dem("d2", "atendente"), _dem("d3", "cozinheiro"))
        )


def test_without_demand_retira_so_a_demanda_do_id() -> None:
    d1, d2, d3 = _dem("d1", "cozinheiro"), _dem("d2", "atendente"), _dem("d3", "barman")
    original = _banda(d1, d2, d3)
    reduzida = original.without_demand(ShiftDemandId("d2"))
    assert reduzida is not original
    assert reduzida.demands == (d1, d3)
    assert original.demands == (d1, d2, d3)


def test_without_demand_de_id_inexistente_e_no_op_silencioso() -> None:
    # A recusa ShiftDemandNotFoundError é da raiz (Task 09).
    original = _banda(_dem("d1", "cozinheiro"))
    assert original.without_demand(ShiftDemandId("nao-existe")).demands == original.demands


# --- CA22, CA15 e a forma da coleção --------------------------------------------------


@pytest.mark.parametrize("vazio", ["", "   "])
def test_shift_band_id_vazio_e_recusado(vazio: str) -> None:
    with pytest.raises(InvalidIdentifierError, match="faixa"):
        ShiftBand(id=ShiftBandId(vazio), time_range=_faixa_16_00())


def test_demands_e_tupla() -> None:
    assert isinstance(_banda(_dem("d1", "cozinheiro")).demands, tuple)
    assert isinstance(_banda().with_demand(_dem("d1", "cozinheiro")).demands, tuple)


def test_faixa_e_frozen() -> None:
    with pytest.raises(dataclasses.FrozenInstanceError):
        _banda().time_range = _faixa_16_00(30)  # type: ignore[misc]


def test_igualdade_e_hash_por_id_ignoram_o_conteudo() -> None:
    a = _banda()
    b = ShiftBand(
        id=_ID,
        time_range=TimeRange(start=datetime(2026, 10, 5, 8, 0), end=datetime(2026, 10, 5, 12, 0)),
        demands=(_dem("d1", "cozinheiro"),),
    )
    assert a == b
    assert hash(a) == hash(b)
    assert a != ShiftBand(id=ShiftBandId("faixa-2"), time_range=_faixa_16_00())
    assert a.__eq__("faixa-1") is NotImplemented


# --- auditoria de mutação (B04, B02) ---------------------------------------------------


def test_intervalo_da_alocacao_entre_o_trabalhado_e_o_nominal_da_faixa_e_aceito() -> None:
    # O teto é a duração NOMINAL (480), não a trabalhada da faixa (480 - 60 = 420):
    # 479 fica entre as duas e tem de passar (auditoria, B04).
    alocacao = _aloc("a1", "ana", _NOMINAL - 1)
    banda = _banda(_dem("d1", "cozinheiro", alocacao), break_minutes=_UMA_HORA)
    assert banda.effective_break_of(alocacao) == _NOMINAL - 1


def test_demanda_repetida_por_inteiro_levanta_a_colisao_de_id_primeiro() -> None:
    # Mesmo id e mesma função: a precedência é colisão de id (§7, [decision] da
    # auditoria de mutação) — é a "linha repetida" da reidratação da 4.4.
    demanda = _dem("d1", "cozinheiro")
    with pytest.raises(DuplicateEntityIdError, match="ShiftDemandId"):
        _banda(demanda, _dem("d1", "cozinheiro"))
