"""Testes da política de descanso entre jornadas — CA3, CA4, CA5 (descanso), CA11, CA16."""

from datetime import timedelta
from decimal import Decimal

import pytest

from restaurant_hub.features.scheduling.domain.services.validation import (
    rest_between_shifts_policy,
)
from restaurant_hub.features.scheduling.domain.value_objects.identifiers import AssignmentId
from restaurant_hub.features.scheduling.domain.value_objects.validation_config import (
    EnforcementMode,
    PolicyKind,
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

_POLITICA = rest_between_shifts_policy.RestBetweenShiftsPolicy()
_ANTERIOR = SEGUNDA - timedelta(days=7)
_SEGUINTE = SEGUNDA + timedelta(days=7)
_TERCA = SEGUNDA + timedelta(days=1)


def _avaliar(*turnos: Turno, **campos: object) -> tuple[Violation, ...]:
    return _POLITICA.evaluate(contexto(escala(turnos)), config(**campos))


def test_kind() -> None:
    assert _POLITICA.kind is PolicyKind.REST_BETWEEN_SHIFTS


def test_fechamento_e_abertura_violam_com_o_descanso_medido() -> None:
    (violacao,) = _avaliar(Turno("ana", em(0, 16), em(1, 0)), Turno("ana", em(1, 8), em(1, 16)))

    assert violacao == Violation(
        policy=PolicyKind.REST_BETWEEN_SHIFTS,
        mode=EnforcementMode.WARN,
        employee_id="ana",  # type: ignore[arg-type]
        demand_id=None,
        operational_days=(SEGUNDA, _TERCA),
        assignment_ids=frozenset({AssignmentId("s-a0"), AssignmentId("s-a1")}),
        observed=Decimal(480),
        limit=Decimal(660),
    )
    assert violacao.key.assignment_ids == frozenset()


def test_descanso_igual_ao_minimo_nao_viola() -> None:
    # Terça 05:00 é o início do dia operacional de terça: 18:00 → 05:00 = 11h.
    assert _avaliar(Turno("ana", em(0, 8), em(0, 18)), Turno("ana", em(1, 5), em(1, 11))) == ()


def test_um_minuto_abaixo_do_minimo_viola() -> None:
    (violacao,) = _avaliar(Turno("ana", em(0, 8), em(0, 18, 1)), Turno("ana", em(1, 5), em(1, 11)))

    assert violacao.observed == Decimal(659)
    assert violacao.operational_days == (SEGUNDA, _TERCA)


def test_minimo_configurado_vale() -> None:
    turnos = (Turno("ana", em(0, 16), em(1, 0)), Turno("ana", em(1, 8), em(1, 16)))

    assert _avaliar(*turnos, min_rest_minutes=480) == ()
    (violacao,) = _avaliar(*turnos, min_rest_minutes=481)
    assert violacao.limit == Decimal(481)


def test_usa_o_maior_fim_e_o_menor_inicio_e_so_essas_alocacoes() -> None:
    (violacao,) = _avaliar(
        Turno("ana", em(0, 8), em(0, 12)),
        Turno("ana", em(0, 18), em(0, 23)),
        Turno("ana", em(1, 7), em(1, 11)),
        Turno("ana", em(1, 15), em(1, 20), function=ATENDENTE),
    )

    assert violacao.observed == Decimal(480)
    assert violacao.assignment_ids == {AssignmentId("s-a1"), AssignmentId("s-a2")}


def test_o_maior_fim_nao_e_o_ultimo_inicio() -> None:
    # 08-23 termina depois de 18-20, embora comece antes.
    (violacao,) = _avaliar(
        Turno("ana", em(0, 8), em(0, 23)),
        Turno("ana", em(0, 18), em(0, 20), function=ATENDENTE),
        Turno("ana", em(1, 7), em(1, 11)),
    )

    assert violacao.observed == Decimal(480)
    assert violacao.assignment_ids == {AssignmentId("s-a0"), AssignmentId("s-a2")}


def test_pula_dias_sem_alocacao_e_pareia_os_dias_trabalhados() -> None:
    # Segunda e quarta, terça vazia: o par é (segunda, quarta), com 40h de descanso.
    (violacao,) = _avaliar(
        Turno("ana", em(0, 8), em(0, 16)),
        Turno("ana", em(2, 8), em(2, 16)),
        min_rest_minutes=3000,
    )

    assert violacao.operational_days == (SEGUNDA, SEGUNDA + timedelta(days=2))
    assert violacao.observed == Decimal(2400)


def test_dias_sem_alocacao_no_meio_e_descanso_longo_nao_violam() -> None:
    assert _avaliar(Turno("ana", em(0, 8), em(0, 16)), Turno("ana", em(3, 8), em(3, 16))) == ()


def test_lacuna_no_mesmo_dia_operacional_nao_conta() -> None:
    # Jornada partida 08-12 + 22-02: 10h de lacuna, mesmo dia operacional (limite v1).
    assert _avaliar(Turno("ana", em(0, 8), em(0, 12)), Turno("ana", em(0, 22), em(1, 2))) == ()


def test_contiguas_que_atravessam_o_corte_dao_descanso_zero() -> None:
    (violacao,) = _avaliar(Turno("ana", em(4, 21), em(5, 5)), Turno("ana", em(5, 5), em(5, 13)))

    assert violacao.observed == Decimal(0)
    assert violacao.operational_days == (SEGUNDA + timedelta(days=4), SEGUNDA + timedelta(days=5))


def test_descanso_negativo_quando_ha_sobreposicao_entre_dias() -> None:
    (violacao,) = _avaliar(Turno("ana", em(0, 22), em(1, 6)), Turno("ana", em(1, 5), em(1, 9)))

    assert violacao.observed == Decimal(-60)


def test_registros_distintos_nao_se_misturam() -> None:
    assert _avaliar(Turno("ana", em(0, 16), em(1, 0)), Turno("bruno", em(1, 8), em(1, 16))) == ()


def test_descanso_contra_a_escala_anterior() -> None:
    anterior = escala(
        [Turno("ana", em(6, 16, base=_ANTERIOR), em(0, 0))], schedule_id="p", first_day=_ANTERIOR
    )
    avaliada = escala([Turno("ana", em(0, 8), em(0, 16))])

    (violacao,) = _POLITICA.evaluate(contexto(avaliada, previous=anterior), config())

    assert violacao.operational_days == (SEGUNDA - timedelta(days=1), SEGUNDA)
    assert violacao.assignment_ids == {AssignmentId("p-a0"), AssignmentId("s-a0")}


def test_descanso_contra_a_escala_seguinte() -> None:
    avaliada = escala([Turno("ana", em(6, 16), em(7, 0))])
    seguinte = escala(
        [Turno("ana", em(0, 8, base=_SEGUINTE), em(0, 16, base=_SEGUINTE))],
        schedule_id="n",
        first_day=_SEGUINTE,
    )

    (violacao,) = _POLITICA.evaluate(contexto(avaliada, next=seguinte), config())

    assert violacao.operational_days == (SEGUNDA + timedelta(days=6), _SEGUINTE)


def test_par_interno_a_vizinha_nao_e_reportado() -> None:
    anterior = escala(
        [
            Turno("ana", em(2, 16, base=_ANTERIOR), em(3, 0, base=_ANTERIOR)),
            Turno("ana", em(3, 8, base=_ANTERIOR), em(3, 16, base=_ANTERIOR)),
        ],
        schedule_id="p",
        first_day=_ANTERIOR,
    )

    assert _POLITICA.evaluate(contexto(escala([]), previous=anterior), config()) == ()
