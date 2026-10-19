"""Testes da política de sobre-cobertura — CA3, CA4, CA8, CA11, CA16."""

from datetime import timedelta
from decimal import Decimal

import pytest

from restaurant_hub.features.scheduling.domain.services.validation.over_coverage_policy import (
    OverCoveragePolicy,
)
from restaurant_hub.features.scheduling.domain.value_objects.identifiers import (
    AssignmentId,
    ShiftDemandId,
)
from restaurant_hub.features.scheduling.domain.value_objects.validation_config import (
    EnforcementMode,
    PolicyKind,
    PolicyRule,
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

_POLITICA = OverCoveragePolicy()
_INICIO, _FIM = em(2, 16), em(3, 0)
_CHAVE = (_INICIO, _FIM, ATENDENTE)


def _atendentes(*nomes: str) -> list[Turno]:
    return [Turno(nome, _INICIO, _FIM, function=ATENDENTE) for nome in nomes]


def _avaliar(turnos: list[Turno], alvo: int, *extras: object) -> tuple[Violation, ...]:
    avaliada = escala(turnos, quantidades={_CHAVE: alvo})
    return _POLITICA.evaluate(contexto(avaliada, *extras), config())  # type: ignore[arg-type]


def test_kind() -> None:
    assert _POLITICA.kind is PolicyKind.OVER_COVERAGE


def test_alocados_acima_do_alvo_violam_com_a_demanda_como_sujeito() -> None:
    (violacao,) = _avaliar(_atendentes("ana", "bruno", "carla"), 2)

    assert violacao == Violation(
        policy=PolicyKind.OVER_COVERAGE,
        mode=EnforcementMode.WARN,
        employee_id=None,
        demand_id=ShiftDemandId("s-b0-atendente"),
        operational_days=(SEGUNDA + timedelta(days=2),),
        assignment_ids=frozenset(AssignmentId(f"s-a{indice}") for indice in range(3)),
        observed=Decimal(3),
        limit=Decimal(2),
    )
    assert violacao.key.assignment_ids == violacao.assignment_ids


def test_alocados_iguais_ao_alvo_nao_violam() -> None:
    assert _avaliar(_atendentes("ana", "bruno"), 2) == ()


def test_alvo_zero_com_alocado_viola() -> None:
    (violacao,) = _avaliar(_atendentes("ana"), 0)

    assert (violacao.observed, violacao.limit) == (Decimal(1), Decimal(0))


def test_alocacao_de_inativo_nao_conta() -> None:
    turnos = _atendentes("ana", "bruno", "carla")

    assert _avaliar(turnos, 2, fatos("carla", funcoes=(ATENDENTE,), ativo=False)) == ()
    (violacao,) = _avaliar(turnos, 1, fatos("carla", funcoes=(ATENDENTE,), ativo=False))
    assert violacao.assignment_ids == {AssignmentId("s-a0"), AssignmentId("s-a1")}


def test_reduzir_n_sobre_o_mesmo_conjunto_mantem_a_key_e_piora_a_medida() -> None:
    turnos = _atendentes("ana", "bruno", "carla")

    (com_dois,) = _avaliar(turnos, 2)
    (com_um,) = _avaliar(turnos, 1)

    assert com_dois.key == com_um.key
    assert (com_dois.limit, com_um.limit) == (Decimal(2), Decimal(1))


def test_alocar_mais_um_muda_a_key() -> None:
    (tres,) = _avaliar(_atendentes("ana", "bruno", "carla"), 2)
    (quatro,) = _avaliar(_atendentes("ana", "bruno", "carla", "davi"), 2)

    assert tres.key != quatro.key


def test_faixas_sobrepostas_da_mesma_funcao_contam_separadas() -> None:
    # 2 atendentes 16h-00h (alvo 2) + 1 atendente 18h-22h (alvo 1): ninguém sobra.
    turnos = [
        *_atendentes("ana", "bruno"),
        Turno("carla", em(2, 18), em(2, 22), function=ATENDENTE),
    ]
    avaliada = escala(turnos, quantidades={_CHAVE: 2, (em(2, 18), em(2, 22), ATENDENTE): 1})

    assert _POLITICA.evaluate(contexto(avaliada), config()) == ()


def test_demandas_distintas_da_mesma_faixa_contam_separadas() -> None:
    turnos = [*_atendentes("ana"), Turno("bruno", _INICIO, _FIM, function=COZINHEIRO)]
    avaliada = escala(turnos, quantidades={_CHAVE: 1, (_INICIO, _FIM, COZINHEIRO): 1})

    assert _POLITICA.evaluate(contexto(avaliada), config()) == ()


def test_o_dia_da_violacao_e_o_dia_operacional_da_faixa() -> None:
    # Quinta 02:00 é antes do corte (05:00): a faixa é do dia operacional de quarta.
    inicio, fim = em(3, 2), em(3, 6)
    avaliada = escala(
        [Turno("ana", inicio, fim, function=ATENDENTE)],
        quantidades={(inicio, fim, ATENDENTE): 0},
    )

    (violacao,) = _POLITICA.evaluate(contexto(avaliada), config())

    assert violacao.operational_days == (SEGUNDA + timedelta(days=2),)


def test_ignora_a_vizinha() -> None:
    anterior_dia = SEGUNDA - timedelta(days=7)
    inicio, fim = em(2, 16, base=anterior_dia), em(3, 0, base=anterior_dia)
    anterior = escala(
        [Turno("ana", inicio, fim), Turno("bruno", inicio, fim)],
        schedule_id="p",
        first_day=anterior_dia,
        quantidades={(inicio, fim, COZINHEIRO): 0},
    )

    assert _POLITICA.evaluate(contexto(escala([]), previous=anterior), config()) == ()


def test_o_modo_vem_da_config() -> None:
    avaliada = escala(_atendentes("ana"), quantidades={_CHAVE: 0})
    bloqueio = config(over_coverage=PolicyRule(enabled=True, mode=EnforcementMode.BLOCK))

    (violacao,) = _POLITICA.evaluate(contexto(avaliada), bloqueio)

    assert violacao.mode is EnforcementMode.BLOCK
