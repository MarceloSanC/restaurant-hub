"""Testes dos tetos diário e semanal — CA3, CA4, CA5 (teto), CA11, CA16, CA17."""

from datetime import timedelta
from decimal import Decimal

import pytest

from restaurant_hub.features.scheduling.domain.services.validation.max_hours_policy import (
    DailyCapPolicy,
    WeeklyCapPolicy,
)
from restaurant_hub.features.scheduling.domain.value_objects.identifiers import AssignmentId
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
    fatos,
)

pytestmark = pytest.mark.unit

_DIARIO = DailyCapPolicy()
_SEMANAL = WeeklyCapPolicy()
_DIAS_DA_SEMANA = tuple(SEGUNDA + timedelta(days=indice) for indice in range(7))


def test_kinds() -> None:
    assert (_DIARIO.kind, _SEMANAL.kind) == (PolicyKind.DAILY_CAP, PolicyKind.WEEKLY_CAP)


def test_dia_acima_do_teto_viola_com_todas_as_alocacoes_do_dia() -> None:
    avaliada = escala([Turno("ana", em(0, 8), em(0, 14)), Turno("ana", em(0, 15), em(0, 20))])

    (violacao,) = _DIARIO.evaluate(contexto(avaliada), config())

    assert violacao == Violation(
        policy=PolicyKind.DAILY_CAP,
        mode=EnforcementMode.WARN,
        employee_id="ana",  # type: ignore[arg-type]
        demand_id=None,
        operational_days=(SEGUNDA,),
        assignment_ids=frozenset({AssignmentId("s-a0"), AssignmentId("s-a1")}),
        observed=Decimal(660),
        limit=Decimal(600),
    )
    assert violacao.key.assignment_ids == frozenset()


def test_dia_igual_ao_teto_nao_viola_e_um_minuto_a_mais_viola() -> None:
    igual = escala([Turno("ana", em(0, 8), em(0, 18))])
    acima = escala([Turno("ana", em(0, 8), em(0, 18, 1))])

    assert _DIARIO.evaluate(contexto(igual), config()) == ()
    (violacao,) = _DIARIO.evaluate(contexto(acima), config())
    assert violacao.observed == Decimal(601)


def test_o_teto_diario_conta_horas_trabalhadas_sem_o_intervalo() -> None:
    # 11h de relógio com 1h de intervalo da faixa = 10h: no teto, não acima.
    avaliada = escala([Turno("ana", em(0, 8), em(0, 19), band_break=60)])

    assert _DIARIO.evaluate(contexto(avaliada), config()) == ()


def test_o_intervalo_proprio_da_alocacao_e_o_que_conta() -> None:
    avaliada = escala([Turno("ana", em(0, 8), em(0, 19), band_break=60, alloc_break=0)])

    (violacao,) = _DIARIO.evaluate(contexto(avaliada), config())

    assert violacao.observed == Decimal(660)


def test_dias_e_registros_distintos_nao_se_somam() -> None:
    avaliada = escala(
        [
            Turno("ana", em(0, 8), em(0, 16)),
            Turno("ana", em(1, 8), em(1, 16)),
            Turno("bruno", em(0, 8), em(0, 16)),
        ]
    )

    assert _DIARIO.evaluate(contexto(avaliada), config()) == ()


def test_madrugada_soma_no_dia_em_que_a_faixa_comeca() -> None:
    avaliada = escala([Turno("ana", em(0, 14), em(0, 20)), Turno("ana", em(0, 22), em(1, 4))])

    (violacao,) = _DIARIO.evaluate(contexto(avaliada), config())

    assert (violacao.operational_days, violacao.observed) == ((SEGUNDA,), Decimal(720))


def test_contiguas_que_atravessam_o_corte_dao_dois_dias_sem_violar() -> None:
    # Sexta 21h-sábado 05h é da sexta; sábado 05h-13h é do sábado: 8h + 8h (limite v1).
    avaliada = escala([Turno("ana", em(4, 21), em(5, 5)), Turno("ana", em(5, 5), em(5, 13))])

    assert _DIARIO.evaluate(contexto(avaliada), config()) == ()


def test_faixas_distintas_sobrepostas_somam_por_alocacao() -> None:
    # 16h-00h (8h) e 18h-23h (5h) da mesma quarta: 13h, a interseção conta duas vezes.
    avaliada = escala(
        [
            Turno("ana", em(2, 16), em(3, 0)),
            Turno("ana", em(2, 18), em(2, 23), function=ATENDENTE),
        ]
    )

    (violacao,) = _DIARIO.evaluate(contexto(avaliada), config())

    assert violacao.observed == Decimal(780)


def test_dia_de_vizinha_nao_entra_no_teto_diario() -> None:
    anterior_dia = SEGUNDA - timedelta(days=7)
    anterior = escala(
        [Turno("ana", em(3, 6, base=anterior_dia), em(3, 20, base=anterior_dia))],
        schedule_id="p",
        first_day=anterior_dia,
    )

    assert _DIARIO.evaluate(contexto(escala([]), previous=anterior), config()) == ()


def test_inativo_nao_viola_o_teto() -> None:
    avaliada = escala([Turno("ana", em(0, 6), em(0, 20))])

    assert _DIARIO.evaluate(contexto(avaliada, fatos("ana", ativo=False)), config()) == ()


def test_o_modo_vem_da_config() -> None:
    avaliada = escala([Turno("ana", em(0, 6), em(0, 20))])
    bloqueio = config(daily_cap=PolicyRule(enabled=True, mode=EnforcementMode.BLOCK))

    (violacao,) = _DIARIO.evaluate(contexto(avaliada), bloqueio)

    assert violacao.mode is EnforcementMode.BLOCK


def _quatro_turnos_de_onze_horas(extra_minutos: int = 0) -> list[Turno]:
    turnos = [Turno("ana", em(dia, 6), em(dia, 17)) for dia in range(3)]
    return [*turnos, Turno("ana", em(3, 6), em(3, 17, extra_minutos))]


def test_semana_igual_ao_teto_nao_viola() -> None:
    assert _SEMANAL.evaluate(contexto(escala(_quatro_turnos_de_onze_horas())), config()) == ()


def test_semana_um_minuto_acima_viola_com_os_sete_dias_e_todas_as_alocacoes() -> None:
    avaliada = escala(_quatro_turnos_de_onze_horas(1))

    (violacao,) = _SEMANAL.evaluate(contexto(avaliada), config())

    assert violacao.observed == Decimal(2641)
    assert violacao.limit == Decimal(2640)
    assert violacao.operational_days == _DIAS_DA_SEMANA
    assert violacao.assignment_ids == {AssignmentId(f"s-a{indice}") for indice in range(4)}
    assert violacao.key.assignment_ids == frozenset()


def test_o_teto_semanal_configurado_vale() -> None:
    avaliada = escala(_quatro_turnos_de_onze_horas())

    (violacao,) = _SEMANAL.evaluate(contexto(avaliada), config(weekly_cap_minutes=2400))

    assert violacao.limit == Decimal(2400)


def test_semana_da_vizinha_nao_entra_no_teto_semanal() -> None:
    anterior_dia = SEGUNDA - timedelta(days=7)
    anterior = escala(
        [
            Turno("ana", em(dia, 6, base=anterior_dia), em(dia, 20, base=anterior_dia))
            for dia in range(5)
        ],
        schedule_id="p",
        first_day=anterior_dia,
    )
    avaliada = escala([Turno("ana", em(0, 8), em(0, 16))])

    assert _SEMANAL.evaluate(contexto(avaliada, previous=anterior), config()) == ()


def test_o_teto_diario_configurado_vale() -> None:
    avaliada = escala([Turno("ana", em(0, 8), em(0, 16))])

    assert _DIARIO.evaluate(contexto(avaliada), config(daily_cap_minutes=480)) == ()
    (violacao,) = _DIARIO.evaluate(contexto(avaliada), config(daily_cap_minutes=479))
    assert (violacao.observed, violacao.limit) == (Decimal(480), Decimal(479))


def test_o_modo_do_teto_semanal_vem_da_config() -> None:
    avaliada = escala(_quatro_turnos_de_onze_horas(1))
    bloqueio = config(weekly_cap=PolicyRule(enabled=True, mode=EnforcementMode.BLOCK))

    (violacao,) = _SEMANAL.evaluate(contexto(avaliada), bloqueio)

    assert violacao.mode is EnforcementMode.BLOCK


def test_a_semana_soma_por_registro() -> None:
    turnos = [*_quatro_turnos_de_onze_horas(1), Turno("bruno", em(0, 6), em(0, 14))]

    (violacao,) = _SEMANAL.evaluate(contexto(escala(turnos)), config())

    assert (violacao.employee_id, violacao.observed) == ("ana", Decimal(2641))
    assert AssignmentId("s-a4") not in violacao.assignment_ids


def test_duas_semanas_abaixo_do_teto_nao_somam_entre_registros() -> None:
    turnos = [
        Turno(nome, em(dia, 6), em(dia, 17)) for nome in ("ana", "bruno") for dia in (0, 1, 2)
    ]

    assert _SEMANAL.evaluate(contexto(escala(turnos)), config()) == ()
