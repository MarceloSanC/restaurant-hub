"""Validação do pedido em `_inputs.py` (concept 4.3 §5.15 a §5.17; CA15, CA17, CA18, CA19)."""

from datetime import datetime, time, timedelta

import pytest

from restaurant_hub.features.scheduling.application.errors import InvalidScheduleRequestError
from restaurant_hub.features.scheduling.application.use_cases._inputs import (
    MAX_PAST_LIMIT,
    MAX_RANGE_DAYS,
    require_day,
    require_limit,
    require_range,
)
from tests.unit.features.scheduling.application.conftest import MONDAY

pytestmark = pytest.mark.unit


def test_recorte_de_ate_42_dias_e_aceito_e_43_nao() -> None:
    ultimo = MONDAY + timedelta(days=MAX_RANGE_DAYS - 1)
    assert require_range(MONDAY, ultimo) == (MONDAY, ultimo)
    assert require_range(MONDAY, MONDAY) == (MONDAY, MONDAY)
    with pytest.raises(InvalidScheduleRequestError):
        require_range(MONDAY, ultimo + timedelta(days=1))


def test_recorte_invertido_recusa() -> None:
    with pytest.raises(InvalidScheduleRequestError):
        require_range(MONDAY, MONDAY - timedelta(days=1))


@pytest.mark.parametrize(
    ("primeiro", "ultimo"),
    [(datetime.combine(MONDAY, time(0)), MONDAY), (MONDAY, datetime.combine(MONDAY, time(0)))],
)
def test_recorte_com_datetime_recusa(primeiro: object, ultimo: object) -> None:
    with pytest.raises(InvalidScheduleRequestError):
        require_range(primeiro, ultimo)


@pytest.mark.parametrize("valor", [datetime.combine(MONDAY, time(0)), "2026-11-02", None])
def test_dia_que_nao_e_date_recusa(valor: object) -> None:
    with pytest.raises(InvalidScheduleRequestError):
        require_day(valor, "before")


@pytest.mark.parametrize("limite", [1, 10, MAX_PAST_LIMIT])
def test_limite_dentro_da_faixa(limite: int) -> None:
    assert require_limit(limite) == limite


@pytest.mark.parametrize("limite", [0, -1, MAX_PAST_LIMIT + 1, True, 2.0])
def test_limite_fora_da_faixa_recusa(limite: object) -> None:
    with pytest.raises(InvalidScheduleRequestError):
        require_limit(limite)  # type: ignore[arg-type]
