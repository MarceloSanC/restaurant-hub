"""Testes dos VOs DayPeriod e ShiftPreference (value_objects/shift_preference.py)."""

import dataclasses

import pytest

from restaurant_hub.features.staff.domain.exceptions.errors import EmptyShiftPreferenceError
from restaurant_hub.features.staff.domain.value_objects.shift_preference import (
    DayPeriod,
    ShiftPreference,
)

pytestmark = pytest.mark.unit


def test_day_period_e_um_conjunto_fechado_de_quatro_periodos() -> None:
    # Conjunto fechado (kickoff #6): membro novo ou removido quebra aqui.
    assert {membro.value for membro in DayPeriod} == {
        "morning",
        "afternoon",
        "night",
        "overnight",
    }
    # Os nomes EN também são contrato (concept §4 — identificadores em inglês,
    # CONVENTIONS §1): renomear um membro quebra aqui, não só o valor.
    assert {membro.name for membro in DayPeriod} == {
        "MORNING",
        "AFTERNOON",
        "NIGHT",
        "OVERNIGHT",
    }


@pytest.mark.parametrize(
    "periodos",
    [
        frozenset({DayPeriod.NIGHT}),
        frozenset({DayPeriod.MORNING, DayPeriod.AFTERNOON}),
        frozenset(DayPeriod),
    ],
)
def test_qualquer_subconjunto_nao_vazio_e_aceito(periodos: frozenset[DayPeriod]) -> None:
    assert ShiftPreference(periods=periodos).periods == periodos


def test_conjunto_vazio_e_rejeitado() -> None:
    # "Sem preferência" se expressa com None no Employee, nunca com conjunto vazio.
    with pytest.raises(EmptyShiftPreferenceError, match="ao menos um período"):
        ShiftPreference(periods=frozenset())


def test_preferencia_compara_por_valor() -> None:
    mesma = ShiftPreference(periods=frozenset({DayPeriod.NIGHT, DayPeriod.OVERNIGHT}))
    equivalente = ShiftPreference(periods=frozenset({DayPeriod.OVERNIGHT, DayPeriod.NIGHT}))
    outra = ShiftPreference(periods=frozenset({DayPeriod.MORNING}))
    assert mesma == equivalente
    assert mesma != outra


def test_preferencia_e_hashavel() -> None:
    # Frozen ⇒ hashável por valor — instâncias equivalentes colapsam no set.
    mesma = ShiftPreference(periods=frozenset({DayPeriod.NIGHT}))
    equivalente = ShiftPreference(periods=frozenset({DayPeriod.NIGHT}))
    assert len({mesma, equivalente}) == 1


def test_preferencia_e_imutavel() -> None:
    preferencia = ShiftPreference(periods=frozenset({DayPeriod.MORNING}))
    with pytest.raises(dataclasses.FrozenInstanceError):
        preferencia.periods = frozenset({DayPeriod.NIGHT})  # type: ignore[misc]
