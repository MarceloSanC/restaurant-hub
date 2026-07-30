"""Testes do VO UnavailabilityPeriod (value_objects/unavailability_period.py)."""

import dataclasses
from datetime import UTC, datetime

import pytest

from restaurant_hub.features.staff.domain.exceptions.errors import (
    InvalidUnavailabilityPeriodError,
)
from restaurant_hub.features.staff.domain.value_objects.unavailability_period import (
    UnavailabilityPeriod,
)

pytestmark = pytest.mark.unit


def _periodo(start_hour: int, end_hour: int) -> UnavailabilityPeriod:
    """Período no mesmo dia, delimitado por horas cheias (naive)."""
    return UnavailabilityPeriod(
        start=datetime(2026, 8, 3, start_hour, 0),
        end=datetime(2026, 8, 3, end_hour, 0),
    )


def test_cria_periodo_valido() -> None:
    periodo = _periodo(8, 12)
    assert periodo.start == datetime(2026, 8, 3, 8, 0)
    assert periodo.end == datetime(2026, 8, 3, 12, 0)


def test_inicio_igual_ao_fim_e_rejeitado() -> None:
    # Intervalo semi-aberto [start, end) vazio não representa indisponibilidade.
    with pytest.raises(InvalidUnavailabilityPeriodError, match="início deve anteceder o fim"):
        _periodo(8, 8)


def test_inicio_depois_do_fim_e_rejeitado() -> None:
    with pytest.raises(InvalidUnavailabilityPeriodError, match="início deve anteceder o fim"):
        _periodo(12, 8)


@pytest.mark.parametrize(
    ("start", "end"),
    [
        (datetime(2026, 8, 3, 8, 0, tzinfo=UTC), datetime(2026, 8, 3, 12, 0)),
        (datetime(2026, 8, 3, 8, 0), datetime(2026, 8, 3, 12, 0, tzinfo=UTC)),
        (datetime(2026, 8, 3, 8, 0, tzinfo=UTC), datetime(2026, 8, 3, 12, 0, tzinfo=UTC)),
    ],
    ids=["start_aware", "end_aware", "ambos_aware"],
)
def test_datetime_tz_aware_e_rejeitado(start: datetime, end: datetime) -> None:
    # ADR 3.1.0005: wall-clock do fuso da unidade — tz-aware não entra no domínio.
    with pytest.raises(InvalidUnavailabilityPeriodError, match="ingênuos"):
        UnavailabilityPeriod(start=start, end=end)


@pytest.mark.parametrize(
    ("a", "b", "esperado"),
    [
        pytest.param(_periodo(8, 12), _periodo(10, 14), True, id="parcial_pela_direita"),
        pytest.param(_periodo(10, 14), _periodo(8, 12), True, id="parcial_pela_esquerda"),
        pytest.param(_periodo(8, 16), _periodo(10, 12), True, id="continencia_total"),
        pytest.param(_periodo(8, 12), _periodo(8, 12), True, id="identicos"),
        pytest.param(_periodo(8, 10), _periodo(12, 14), False, id="disjuntos"),
        pytest.param(_periodo(8, 12), _periodo(12, 14), False, id="adjacentes_nao_sobrepoem"),
    ],
)
def test_tabela_verdade_do_overlaps_e_simetrica(
    a: UnavailabilityPeriod, b: UnavailabilityPeriod, esperado: bool
) -> None:
    # Semântica semi-aberta [start, end): adjacentes (fim == início) não conflitam.
    assert a.overlaps(b) is esperado
    assert b.overlaps(a) is esperado


def test_periodo_compara_por_valor() -> None:
    assert _periodo(8, 12) == _periodo(8, 12)
    assert _periodo(8, 12) != _periodo(8, 13)


def test_periodo_e_hashavel() -> None:
    # Frozen ⇒ hashável por valor — a remoção por valor na Task 07 depende disso.
    assert len({_periodo(8, 12), _periodo(8, 12)}) == 1


def test_periodo_e_imutavel() -> None:
    periodo = _periodo(8, 12)
    with pytest.raises(dataclasses.FrozenInstanceError):
        periodo.end = datetime(2026, 8, 3, 13, 0)  # type: ignore[misc]
