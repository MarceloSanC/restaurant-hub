"""Testes do VO SchedulePeriod (value_objects/schedule_period.py) — CA8.

O lado "desalinhado" de CA8 (`period_starting_on`) é do calendário e vive em
`test_operational_calendar.py`.
"""

from datetime import date, timedelta

import pytest

from restaurant_hub.features.scheduling.domain.exceptions.errors import (
    InvalidSchedulePeriodError,
)
from restaurant_hub.features.scheduling.domain.value_objects.schedule_period import (
    SchedulePeriod,
)

pytestmark = pytest.mark.unit

_SEGUNDA = date(2026, 9, 28)
_SEMANA = 7
_TETO = 31


@pytest.mark.parametrize("days", [0, -1, _TETO + 1, 100_000])
def test_contagem_fora_de_1_a_31_e_recusada(days: int) -> None:
    with pytest.raises(InvalidSchedulePeriodError, match="de 1 a 31 dias"):
        SchedulePeriod(first_day=_SEGUNDA, days=days)


@pytest.mark.parametrize("days", [1, _SEMANA, _TETO])
def test_contagem_nas_bordas_e_aceita(days: int) -> None:
    periodo = SchedulePeriod(first_day=_SEGUNDA, days=days)
    assert periodo.days == days
    assert len(periodo.operational_days) == days
    assert periodo.last_day == _SEGUNDA + timedelta(days=days - 1)


def test_default_e_sete_dias() -> None:
    assert SchedulePeriod(first_day=_SEGUNDA).days == _SEMANA


def test_last_day_com_sete_dias_e_first_day_mais_seis() -> None:
    assert SchedulePeriod(first_day=_SEGUNDA).last_day == _SEGUNDA + timedelta(days=6)


def test_periodo_de_um_dia_comeca_e_termina_no_mesmo_dia() -> None:
    periodo = SchedulePeriod(first_day=_SEGUNDA, days=1)
    assert periodo.last_day == _SEGUNDA
    assert periodo.operational_days == (_SEGUNDA,)


def test_operational_days_em_ordem_sem_repeticao() -> None:
    dias = SchedulePeriod(first_day=_SEGUNDA).operational_days
    assert dias == tuple(_SEGUNDA + timedelta(days=i) for i in range(_SEMANA))
    assert len(set(dias)) == len(dias)
    assert list(dias) == sorted(dias)
    assert isinstance(dias, tuple)


def test_operational_days_atravessa_a_virada_de_mes() -> None:
    dias = SchedulePeriod(first_day=_SEGUNDA).operational_days
    assert dias[-1] == date(2026, 10, 4)


@pytest.mark.parametrize("deslocamento", range(_SEMANA))
def test_contains_e_verdadeiro_nos_sete_dias(deslocamento: int) -> None:
    periodo = SchedulePeriod(first_day=_SEGUNDA)
    assert periodo.contains(_SEGUNDA + timedelta(days=deslocamento)) is True


@pytest.mark.parametrize(
    "dia",
    [
        pytest.param(_SEGUNDA - timedelta(days=1), id="anterior_ao_primeiro"),
        pytest.param(_SEGUNDA + timedelta(days=_SEMANA), id="seguinte_ao_ultimo"),
    ],
)
def test_contains_e_falso_fora_das_bordas(dia: date) -> None:
    assert SchedulePeriod(first_day=_SEGUNDA).contains(dia) is False


def test_periodo_compara_por_valor() -> None:
    assert SchedulePeriod(first_day=_SEGUNDA) == SchedulePeriod(first_day=_SEGUNDA, days=_SEMANA)
    assert hash(SchedulePeriod(first_day=_SEGUNDA)) == hash(SchedulePeriod(first_day=_SEGUNDA))
    assert SchedulePeriod(first_day=_SEGUNDA) != SchedulePeriod(first_day=_SEGUNDA, days=_TETO)
