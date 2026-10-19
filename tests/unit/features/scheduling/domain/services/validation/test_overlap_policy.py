"""Testes da política de sobreposição — CA3, CA4, CA11, CA16."""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from restaurant_hub.features.scheduling.domain.services.validation.overlap_policy import (
    OverlapPolicy,
)
from restaurant_hub.features.scheduling.domain.value_objects.identifiers import (
    AssignmentId,
    EmployeeId,
)
from restaurant_hub.features.scheduling.domain.value_objects.validation_config import (
    EnforcementMode,
    PolicyKind,
    PolicyRule,
)
from restaurant_hub.features.scheduling.domain.value_objects.violation import Violation
from tests.unit.features.scheduling.domain.services.validation.scenario import (
    ATENDENTE,
    SEGUNDA,
    Turno,
    config,
    contexto,
    em,
    escala,
)

pytestmark = pytest.mark.unit

_POLITICA = OverlapPolicy()
_ANTERIOR = SEGUNDA - timedelta(days=7)
_SEGUINTE = SEGUNDA + timedelta(days=7)


def test_kind() -> None:
    assert _POLITICA.kind is PolicyKind.OVERLAP


def test_faixas_distintas_sobrepostas_do_mesmo_registro_violam_com_a_interseccao() -> None:
    avaliada = escala(
        [
            Turno("ana", em(2, 16), em(3, 0)),
            Turno("ana", em(2, 18), em(2, 23), function=ATENDENTE),
        ]
    )

    (violacao,) = _POLITICA.evaluate(contexto(avaliada), config())

    assert violacao == Violation(
        policy=PolicyKind.OVERLAP,
        mode=EnforcementMode.BLOCK,
        employee_id=EmployeeId("ana"),
        demand_id=None,
        operational_days=(SEGUNDA + timedelta(days=2),),
        assignment_ids=frozenset({AssignmentId("s-a0"), AssignmentId("s-a1")}),
        observed=Decimal(300),
        limit=Decimal(0),
    )
    assert violacao.key.assignment_ids == violacao.assignment_ids


def test_adjacentes_nao_violam() -> None:
    avaliada = escala([Turno("ana", em(0, 11), em(0, 15)), Turno("ana", em(0, 15), em(0, 19))])

    assert _POLITICA.evaluate(contexto(avaliada), config()) == ()


def test_um_minuto_de_interseccao_viola() -> None:
    avaliada = escala([Turno("ana", em(0, 11), em(0, 15, 1)), Turno("ana", em(0, 15), em(0, 19))])

    (violacao,) = _POLITICA.evaluate(contexto(avaliada), config())

    assert violacao.observed == Decimal(1)


def test_registros_distintos_nao_violam() -> None:
    avaliada = escala([Turno("ana", em(0, 8), em(0, 16)), Turno("bruno", em(0, 10), em(0, 18))])

    assert _POLITICA.evaluate(contexto(avaliada), config()) == ()


def test_o_modo_vem_da_config() -> None:
    avaliada = escala([Turno("ana", em(0, 8), em(0, 16)), Turno("ana", em(0, 10), em(0, 18))])
    em_aviso = config(overlap=PolicyRule(enabled=True, mode=EnforcementMode.WARN))

    (violacao,) = _POLITICA.evaluate(contexto(avaliada), em_aviso)

    assert violacao.mode is EnforcementMode.WARN


def test_dois_dias_operacionais_saem_distintos_e_ordenados() -> None:
    # Sábado 22h-domingo 06h é do sábado; domingo 05h-09h é do domingo: dias distintos.
    avaliada = escala([Turno("ana", em(5, 22), em(6, 6)), Turno("ana", em(6, 5), em(6, 9))])

    (violacao,) = _POLITICA.evaluate(contexto(avaliada), config())

    assert violacao.operational_days == (
        SEGUNDA + timedelta(days=5),
        SEGUNDA + timedelta(days=6),
    )
    assert violacao.observed == Decimal(60)


def test_sobreposicao_contra_a_escala_anterior() -> None:
    anterior = escala(
        [Turno("ana", em(6, 22, base=_ANTERIOR), em(0, 6))], schedule_id="p", first_day=_ANTERIOR
    )
    avaliada = escala([Turno("ana", em(0, 5), em(0, 9))])

    (violacao,) = _POLITICA.evaluate(contexto(avaliada, previous=anterior), config())

    assert violacao.assignment_ids == {AssignmentId("p-a0"), AssignmentId("s-a0")}
    assert violacao.operational_days == (SEGUNDA - timedelta(days=1), SEGUNDA)


def test_sobreposicao_contra_a_escala_seguinte() -> None:
    avaliada = escala([Turno("ana", em(6, 22), em(7, 6))])
    seguinte = escala(
        [Turno("ana", em(0, 5, base=_SEGUINTE), em(0, 9, base=_SEGUINTE))],
        schedule_id="n",
        first_day=_SEGUINTE,
    )

    (violacao,) = _POLITICA.evaluate(contexto(avaliada, next=seguinte), config())

    assert violacao.assignment_ids == {AssignmentId("s-a0"), AssignmentId("n-a0")}


@pytest.mark.parametrize(("lado", "base"), [("previous", _ANTERIOR), ("next", _SEGUINTE)])
def test_sobreposicao_interna_a_vizinha_nao_e_reportada(lado: str, base: date) -> None:
    vizinha = escala(
        [
            Turno("ana", em(2, 8, base=base), em(2, 16, base=base)),
            Turno("ana", em(2, 10, base=base), em(2, 18, base=base)),
        ],
        schedule_id="v",
        first_day=base,
    )
    contexto_ = contexto(escala([]), **{lado: vizinha})  # type: ignore[arg-type]

    assert _POLITICA.evaluate(contexto_, config()) == ()


def test_insercao_fora_de_ordem_da_dias_ordenados() -> None:
    # Domingo inserido antes de sábado; sábado 22h-domingo 06h cruza domingo 05h-09h.
    avaliada = escala([Turno("ana", em(6, 5), em(6, 9)), Turno("ana", em(5, 22), em(6, 6))])

    (violacao,) = _POLITICA.evaluate(contexto(avaliada), config())

    assert violacao.operational_days == (
        SEGUNDA + timedelta(days=5),
        SEGUNDA + timedelta(days=6),
    )
