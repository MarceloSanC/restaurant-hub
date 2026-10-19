"""Testes da política de indisponibilidade — CA3, CA4, CA11, CA16."""

from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from restaurant_hub.features.scheduling.domain.services.validation.unavailability_policy import (
    UnavailabilityPolicy,
)
from restaurant_hub.features.scheduling.domain.value_objects.identifiers import (
    AssignmentId,
    EmployeeId,
)
from restaurant_hub.features.scheduling.domain.value_objects.validation_config import (
    EnforcementMode,
    PolicyKind,
)
from restaurant_hub.features.scheduling.domain.value_objects.violation import Violation
from tests.unit.features.scheduling.domain.services.validation.scenario import (
    SEGUNDA,
    Turno,
    config,
    contexto,
    em,
    escala,
    fatos,
)

pytestmark = pytest.mark.unit

_POLITICA = UnavailabilityPolicy()


def _avaliar(*janelas: tuple[datetime, datetime]) -> tuple[Violation, ...]:
    avaliada = escala([Turno("ana", em(0, 8), em(0, 16))])
    return _POLITICA.evaluate(contexto(avaliada, fatos("ana", indisponivel=janelas)), config())


def test_kind() -> None:
    assert _POLITICA.kind is PolicyKind.UNAVAILABILITY


def test_alocacao_sobre_ferias_viola_com_a_faixa_inteira() -> None:
    (violacao,) = _avaliar((em(-3, 0), em(10, 0)))

    assert violacao == Violation(
        policy=PolicyKind.UNAVAILABILITY,
        mode=EnforcementMode.BLOCK,
        employee_id=EmployeeId("ana"),
        demand_id=None,
        operational_days=(SEGUNDA,),
        assignment_ids=frozenset({AssignmentId("s-a0")}),
        observed=Decimal(480),
        limit=Decimal(0),
    )
    assert violacao.key.assignment_ids == {AssignmentId("s-a0")}


@pytest.mark.parametrize(
    "janela", [(em(0, 16), em(0, 20)), (em(0, 4), em(0, 8)), (em(1, 0), em(2, 0))]
)
def test_adjacente_ou_disjunta_nao_viola(janela: tuple[datetime, datetime]) -> None:
    assert _avaliar(janela) == ()


def test_um_minuto_dentro_viola() -> None:
    (violacao,) = _avaliar((em(0, 15, 59), em(0, 20)))

    assert violacao.observed == Decimal(1)


def test_janelas_sobrepostas_sao_unidas_e_nao_somadas() -> None:
    (violacao,) = _avaliar((em(0, 9), em(0, 12)), (em(0, 10), em(0, 13)), (em(0, 14), em(0, 15)))

    # 09-13 unidas (240) + 14-15 (60); somadas dariam 420.
    assert violacao.observed == Decimal(300)


def test_janela_contida_em_outra_nao_conta_duas_vezes() -> None:
    # A terceira janela vem depois de uma contida: o fim corrente é o da maior (15h).
    (violacao,) = _avaliar((em(0, 9), em(0, 15)), (em(0, 10), em(0, 11)), (em(0, 12), em(0, 13)))

    assert violacao.observed == Decimal(360)


def test_janelas_fora_de_ordem_sao_unidas() -> None:
    (violacao,) = _avaliar((em(0, 14), em(0, 15)), (em(0, 10), em(0, 13)), (em(0, 9), em(0, 12)))

    assert violacao.observed == Decimal(300)


def test_janela_com_segundos_da_minutos_fracionarios_exatos() -> None:
    (violacao,) = _avaliar((em(0, 10).replace(second=30), em(0, 20)))

    assert violacao.observed == Decimal("359.5")


def test_janela_com_microssegundos_e_exata() -> None:
    (violacao,) = _avaliar((em(0, 15, 59).replace(second=59, microsecond=999_999), em(0, 20)))

    assert violacao.observed == Decimal(1) / Decimal(60_000_000)


def test_o_modo_e_sempre_block() -> None:
    (violacao,) = _avaliar((em(0, 8), em(0, 9)))

    assert violacao.mode is EnforcementMode.BLOCK


def test_ignora_a_alocacao_da_vizinha() -> None:
    anterior_dia = SEGUNDA - timedelta(days=7)
    anterior = escala(
        [Turno("ana", em(0, 8, base=anterior_dia), em(0, 16, base=anterior_dia))],
        schedule_id="p",
        first_day=anterior_dia,
    )
    ferias = fatos("ana", indisponivel=[(em(-7, 0), em(-6, 0))])

    assert _POLITICA.evaluate(contexto(escala([]), ferias, previous=anterior), config()) == ()


def test_registro_sem_indisponibilidade_nao_viola() -> None:
    assert _avaliar() == ()
