"""Testes do avaliador e do registro das políticas — CA4, CA9, CA12, CA13."""

import dataclasses
from datetime import timedelta
from decimal import Decimal

import pytest

from restaurant_hub.features.scheduling.domain.services.validation.context import (
    EvaluationContext,
)
from restaurant_hub.features.scheduling.domain.services.validation.evaluator import (
    DEFAULT_POLICIES,
    Evaluation,
    evaluate,
)
from restaurant_hub.features.scheduling.domain.value_objects.demand_quantity import (
    DemandQuantity,
)
from restaurant_hub.features.scheduling.domain.value_objects.identifiers import (
    AssignmentId,
    EmployeeId,
    ShiftBandId,
    ShiftDemandId,
)
from restaurant_hub.features.scheduling.domain.value_objects.time_range import TimeRange
from restaurant_hub.features.scheduling.domain.value_objects.validation_config import (
    EnforcementMode,
    PolicyKind,
    PolicyRule,
    ValidationConfig,
)
from restaurant_hub.features.scheduling.domain.value_objects.violation import Violation
from tests.unit.features.scheduling.domain.services.validation.scenario import (
    ATENDENTE,
    COZINHEIRO,
    SEGUNDA,
    Turno,
    config,
    contexto,
    em,
    escala,
    fatos,
)

pytestmark = pytest.mark.unit

_PARAMETROS = {
    "min_rest_minutes",
    "daily_cap_minutes",
    "weekly_cap_minutes",
    "workload_tolerance_minutes",
    "workload_direction",
}


def _as_nove_situacoes(registro: str) -> list[Turno]:
    """Uma escala em que `registro` viola as nove políticas."""
    return [
        # sobreposição (faixas distintas) + teto diário (930 min) + divergência + função
        # não detida
        Turno(registro, em(0, 8), em(0, 18), alloc_break=30),
        Turno(registro, em(0, 15), em(0, 21), function=ATENDENTE),
        # descanso: segunda termina 21h, terça começa 05h
        Turno(registro, em(1, 5), em(1, 21)),
        # semana > 44h e carga > 10h (sobre-cobertura vem da quantidade)
        Turno(registro, em(3, 6), em(3, 20)),
        Turno(registro, em(4, 6), em(4, 20)),
    ]


def _cenario(registro: str = "ana", *, ativo: bool = True) -> EvaluationContext:
    turnos = _as_nove_situacoes(registro)
    avaliada = escala(turnos, quantidades={(em(0, 8), em(0, 18), COZINHEIRO): 0})
    return contexto(
        avaliada,
        fatos(
            registro,
            funcoes=(COZINHEIRO,),
            horas=Decimal(10),
            ativo=ativo,
            indisponivel=[(em(4, 18), em(4, 22))],
        ),
    )


def test_o_registro_tem_uma_politica_por_kind_na_ordem_do_enum() -> None:
    assert [politica.kind for politica in DEFAULT_POLICIES] == list(PolicyKind)


def test_toda_politica_configuravel_tem_campo_na_config() -> None:
    campos = {campo.name for campo in dataclasses.fields(ValidationConfig)} - _PARAMETROS

    assert campos == {kind.value for kind in PolicyKind} - {PolicyKind.UNAVAILABILITY.value}


def test_a_escala_de_referencia_viola_as_nove_politicas() -> None:
    avaliacao = evaluate(_cenario(), ValidationConfig.default())

    assert {violacao.policy for violacao in avaliacao.violations} == set(PolicyKind)


def test_so_as_habilitadas_sao_aplicadas() -> None:
    desligadas = {
        campo: PolicyRule(enabled=False, mode=EnforcementMode.WARN)
        for campo in ("overlap", "daily_cap", "function_mismatch")
    }

    avaliacao = evaluate(_cenario(), config(**desligadas))

    assert {violacao.policy for violacao in avaliacao.violations} == set(PolicyKind) - {
        PolicyKind.OVERLAP,
        PolicyKind.DAILY_CAP,
        PolicyKind.FUNCTION_MISMATCH,
    }


class _Espia:
    def __init__(self, kind: PolicyKind) -> None:
        self._kind = kind
        self.chamadas = 0

    @property
    def kind(self) -> PolicyKind:
        return self._kind

    def evaluate(
        self, context: EvaluationContext, config: ValidationConfig
    ) -> tuple[Violation, ...]:
        self.chamadas += 1
        return ()


def test_politica_desabilitada_nem_e_chamada() -> None:
    ligada, desligada = _Espia(PolicyKind.DAILY_CAP), _Espia(PolicyKind.WEEKLY_CAP)
    config_ = config(weekly_cap=PolicyRule(enabled=False, mode=EnforcementMode.WARN))

    evaluate(_cenario(), config_, (ligada, desligada))

    assert (ligada.chamadas, desligada.chamadas) == (1, 0)


def test_a_indisponibilidade_nao_pode_ser_desligada() -> None:
    tudo_desligado = {
        campo.name: PolicyRule(enabled=False, mode=EnforcementMode.WARN)
        for campo in dataclasses.fields(ValidationConfig)
        if campo.name not in _PARAMETROS
    }

    avaliacao = evaluate(_cenario(), config(**tudo_desligado))

    assert {violacao.policy for violacao in avaliacao.violations} == {PolicyKind.UNAVAILABILITY}
    assert avaliacao.blocking == avaliacao.violations


def test_o_modo_carimbado_e_o_da_config_e_separa_block_de_warn() -> None:
    avaliacao = evaluate(_cenario(), ValidationConfig.default())

    assert {v.policy for v in avaliacao.blocking} == {
        PolicyKind.OVERLAP,
        PolicyKind.UNAVAILABILITY,
    }
    assert set(avaliacao.blocking) | set(avaliacao.warnings) == set(avaliacao.violations)
    assert not set(avaliacao.blocking) & set(avaliacao.warnings)

    em_bloqueio = config(daily_cap=PolicyRule(enabled=True, mode=EnforcementMode.BLOCK))
    assert PolicyKind.DAILY_CAP in {v.policy for v in evaluate(_cenario(), em_bloqueio).blocking}


def test_a_ordem_segue_o_enum_e_nao_depende_da_ordem_do_registro() -> None:
    contexto_ = _cenario()

    direta = evaluate(contexto_, ValidationConfig.default())
    invertida = evaluate(contexto_, ValidationConfig.default(), tuple(reversed(DEFAULT_POLICIES)))

    posicoes = [list(PolicyKind).index(v.policy) for v in direta.violations]
    assert posicoes == sorted(posicoes)
    assert direta == invertida
    assert evaluate(contexto_, ValidationConfig.default()) == direta


def test_dentro_da_politica_a_ordem_e_pelo_dia_e_pelo_registro() -> None:
    # Bruno é alocado antes de Ana na mesma faixa: a emissão natural sai bruno, ana.
    avaliada = escala(
        [
            Turno("ana", em(3, 6), em(3, 20)),
            Turno("bruno", em(0, 6), em(0, 20)),
            Turno("ana", em(0, 6), em(0, 20)),
        ]
    )

    avaliacao = evaluate(contexto(avaliada), ValidationConfig.default())

    diarias = [v for v in avaliacao.violations if v.policy is PolicyKind.DAILY_CAP]
    assert [(v.operational_days[0], v.employee_id) for v in diarias] == [
        (SEGUNDA, "ana"),
        (SEGUNDA, "bruno"),
        (SEGUNDA + timedelta(days=3), "ana"),
    ]


def test_no_mesmo_dia_a_ordem_e_pela_demanda() -> None:
    # A faixa das 14h é habilitada primeiro com a demanda "z"; a das 08h depois, com "a":
    # a emissão sai z, a e a ordem tem de sair a, z.
    raiz = escala([])
    for faixa, demanda, inicio, fim, registro in (
        ("f14", "z", em(0, 14), em(0, 18), "ana"),
        ("f08", "a", em(0, 8), em(0, 12), "bruno"),
    ):
        raiz = raiz.enable_band(ShiftBandId(faixa), TimeRange(inicio, fim))
        raiz = raiz.declare_demand(
            ShiftDemandId(demanda), ShiftBandId(faixa), COZINHEIRO, DemandQuantity(0)
        )
        raiz = raiz.assign(
            AssignmentId(f"x-{registro}"), ShiftDemandId(demanda), EmployeeId(registro)
        )

    avaliacao = evaluate(contexto(raiz), ValidationConfig.default())

    demandas = [v.demand_id for v in avaliacao.violations if v.policy is PolicyKind.OVER_COVERAGE]
    assert demandas == ["a", "z"]


def test_no_mesmo_dia_e_registro_a_ordem_e_pelas_alocacoes() -> None:
    # Bruno abre a faixa das 08h (s-a0); Ana entra às 14h (s-a1) e às 08h (s-a2): a emissão
    # das funções não detidas da Ana sai s-a2, s-a1 e a ordem tem de sair s-a1, s-a2.
    avaliada = escala(
        [
            Turno("bruno", em(0, 8), em(0, 12)),
            Turno("ana", em(0, 14), em(0, 18), function=ATENDENTE),
            Turno("ana", em(0, 8), em(0, 12), function=ATENDENTE),
        ]
    )
    contexto_ = contexto(avaliada, fatos("ana", funcoes=(COZINHEIRO,)))

    avaliacao = evaluate(contexto_, ValidationConfig.default())

    alocacoes = [
        sorted(v.assignment_ids)
        for v in avaliacao.violations
        if v.policy is PolicyKind.FUNCTION_MISMATCH
    ]
    assert alocacoes == [["s-a1"], ["s-a2"]]


def test_registro_inativo_nao_aparece_em_violacao_alguma() -> None:
    avaliacao = evaluate(_cenario(ativo=False), ValidationConfig.default())

    assert avaliacao == Evaluation(violations=())


def test_avaliacao_com_as_duas_vizinhas() -> None:
    anterior_dia, seguinte_dia = SEGUNDA - timedelta(days=7), SEGUNDA + timedelta(days=7)
    anterior = escala(
        [Turno("ana", em(6, 16, base=anterior_dia), em(0, 0))],
        schedule_id="p",
        first_day=anterior_dia,
    )
    seguinte = escala(
        [Turno("ana", em(0, 5, base=seguinte_dia), em(0, 9, base=seguinte_dia))],
        schedule_id="n",
        first_day=seguinte_dia,
    )
    avaliada = escala([Turno("ana", em(0, 8), em(0, 16)), Turno("ana", em(6, 22), em(7, 6))])

    avaliacao = evaluate(
        contexto(avaliada, previous=anterior, next=seguinte), ValidationConfig.default()
    )

    assert [(v.policy, v.operational_days) for v in avaliacao.violations] == [
        (PolicyKind.OVERLAP, (SEGUNDA + timedelta(days=6), seguinte_dia)),
        (PolicyKind.REST_BETWEEN_SHIFTS, (SEGUNDA - timedelta(days=1), SEGUNDA)),
        (PolicyKind.REST_BETWEEN_SHIFTS, (SEGUNDA + timedelta(days=6), seguinte_dia)),
    ]


def test_descanso_negativo_sai_junto_com_a_sobreposicao() -> None:
    avaliada = escala([Turno("ana", em(0, 22), em(1, 6)), Turno("ana", em(1, 5), em(1, 9))])

    avaliacao = evaluate(contexto(avaliada), ValidationConfig.default())

    medidas = {v.policy: v.observed for v in avaliacao.violations}
    assert medidas == {
        PolicyKind.OVERLAP: Decimal(60),
        PolicyKind.REST_BETWEEN_SHIFTS: Decimal(-60),
    }


def test_a_violacao_da_virada_tem_a_mesma_key_dos_dois_lados() -> None:
    # Concept §5.6 / ADR 4.2.0002 Decision 1: domingo 22h-segunda 06h na semana W e
    # segunda 05h-09h na semana N dão sobreposição e descanso, vistos de W e de N.
    seguinte_dia = SEGUNDA + timedelta(days=7)
    semana = escala([Turno("ana", em(6, 22), em(7, 6))])
    seguinte = escala(
        [Turno("ana", em(0, 5, base=seguinte_dia), em(0, 9, base=seguinte_dia))],
        schedule_id="n",
        first_day=seguinte_dia,
    )

    vista_de_w = evaluate(contexto(semana, next=seguinte), ValidationConfig.default())
    vista_de_n = evaluate(contexto(seguinte, previous=semana), ValidationConfig.default())

    chaves_w = {v.key for v in vista_de_w.violations}
    chaves_n = {v.key for v in vista_de_n.violations}
    assert {chave.policy for chave in chaves_w} == {
        PolicyKind.OVERLAP,
        PolicyKind.REST_BETWEEN_SHIFTS,
    }
    assert chaves_w == chaves_n
