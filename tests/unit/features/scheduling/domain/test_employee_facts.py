"""Testes dos fatos de staff por dados (value_objects/employee_facts.py) — CA10 (parte)."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from restaurant_hub.features.scheduling.domain.exceptions.errors import (
    InvalidEvaluationInputError,
)
from restaurant_hub.features.scheduling.domain.value_objects.employee_facts import (
    EmployeeFacts,
    UnavailabilityWindow,
)
from restaurant_hub.features.scheduling.domain.value_objects.identifiers import (
    EmployeeId,
    JobFunctionId,
)

pytestmark = pytest.mark.unit

_INICIO = datetime(2026, 9, 28, 8, 0)
_FIM = datetime(2026, 10, 19, 8, 0)


def test_janela_aceita_semanas_e_segundos() -> None:
    # Três semanas, início com segundos: nada disso é recusado (espelha staff).
    janela = UnavailabilityWindow(start=_INICIO.replace(second=30), end=_FIM)

    assert (janela.start.second, (janela.end - janela.start).days) == (30, 20)


@pytest.mark.parametrize(
    ("start", "end", "trecho"),
    [
        (_INICIO, _INICIO, "anteceder"),
        (_FIM, _INICIO, "anteceder"),
        (_INICIO.replace(tzinfo=UTC), _FIM, "ingênuos"),
        (_INICIO, _FIM.replace(tzinfo=UTC), "ingênuos"),
    ],
)
def test_janela_recusa_vazia_invertida_e_tz_aware(
    start: datetime, end: datetime, trecho: str
) -> None:
    with pytest.raises(InvalidEvaluationInputError, match=trecho):
        UnavailabilityWindow(start=start, end=end)


def _fatos(horas: Decimal | None) -> EmployeeFacts:
    return EmployeeFacts(
        employee_id=EmployeeId("ana"),
        active=True,
        job_function_ids=frozenset({JobFunctionId("cozinheiro")}),
        contracted_weekly_hours=horas,
        unavailabilities=(),
    )


@pytest.mark.parametrize("horas", [None, Decimal("22.5"), Decimal("0.01"), Decimal(44)])
def test_fatos_aceitam_sob_demanda_e_carga_positiva_fracionaria(horas: Decimal | None) -> None:
    fatos = _fatos(horas)

    assert fatos.contracted_weekly_hours == horas


@pytest.mark.parametrize(
    "horas", [Decimal(0), Decimal(-1), Decimal("NaN"), Decimal("sNaN"), Decimal("Infinity")]
)
def test_fatos_recusam_carga_nao_finita_ou_nao_positiva(horas: Decimal) -> None:
    with pytest.raises(InvalidEvaluationInputError, match="carga semanal"):
        _fatos(horas)


def test_fatos_recusam_carga_que_nao_e_decimal() -> None:
    with pytest.raises(InvalidEvaluationInputError, match="Decimal"):
        _fatos(22.5)  # type: ignore[arg-type]


@pytest.mark.parametrize("campo", ["start", "end"])
def test_janela_recusa_data_sem_hora(campo: str) -> None:
    instantes = {"start": _INICIO, "end": _FIM}
    instantes[campo] = instantes[campo].date()  # type: ignore[assignment]

    with pytest.raises(InvalidEvaluationInputError, match="datetime"):
        UnavailabilityWindow(**instantes)  # type: ignore[arg-type]
