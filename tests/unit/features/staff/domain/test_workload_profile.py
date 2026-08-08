"""Testes dos VOs de perfil de jornada (value_objects/workload_profile.py)."""

import dataclasses
from decimal import Decimal

import pytest

from restaurant_hub.features.staff.domain.exceptions.errors import InvalidWeeklyHoursError
from restaurant_hub.features.staff.domain.value_objects.workload_profile import (
    FixedSchedule,
    OnDemand,
    WorkloadProfile,
)

pytestmark = pytest.mark.unit


def test_workload_profile_e_a_uniao_dos_dois_perfis() -> None:
    # Trava o alias no contrato: se WorkloadProfile sumisse ou mudasse de
    # forma, este teste quebra (finding do Checkpoint C do bloco 1).
    assert WorkloadProfile == FixedSchedule | OnDemand


@pytest.mark.parametrize("valida", [Decimal("44"), Decimal("22.5"), Decimal("0.5")])
def test_carga_positiva_inteira_ou_fracionaria_e_aceita(valida: Decimal) -> None:
    assert FixedSchedule(weekly_hours=valida).weekly_hours == valida


@pytest.mark.parametrize(
    "invalida",
    [
        Decimal("0"),
        Decimal("-1"),
        Decimal("-22.5"),
        Decimal("NaN"),
        Decimal("sNaN"),
        Decimal("Infinity"),
        Decimal("-Infinity"),
    ],
)
def test_carga_nao_positiva_nan_ou_infinita_e_rejeitada(invalida: Decimal) -> None:
    with pytest.raises(InvalidWeeklyHoursError, match="carga semanal contratada inválida"):
        FixedSchedule(weekly_hours=invalida)


def test_on_demand_nao_expoe_carga_nem_campo_monetario() -> None:
    # Sem dados por decisão (kickoff #11): nem carga contratada nem dinheiro.
    assert dataclasses.fields(OnDemand()) == ()


def test_fixed_schedule_compara_por_valor() -> None:
    assert FixedSchedule(weekly_hours=Decimal("40")) == FixedSchedule(weekly_hours=Decimal("40"))
    assert FixedSchedule(weekly_hours=Decimal("40")) != FixedSchedule(weekly_hours=Decimal("30"))


def test_on_demand_compara_por_valor() -> None:
    # VO sem campos: quaisquer duas instâncias são o mesmo valor.
    assert OnDemand() == OnDemand()


def test_perfis_de_tipos_diferentes_nao_sao_iguais() -> None:
    assert FixedSchedule(weekly_hours=Decimal("40")) != OnDemand()


def test_perfis_sao_hashaveis() -> None:
    # Frozen ⇒ hashável por valor — instâncias equivalentes colapsam no set.
    fixa = FixedSchedule(weekly_hours=Decimal("40"))
    equivalente = FixedSchedule(weekly_hours=Decimal("40"))
    assert len({fixa, equivalente}) == 1
    assert len({OnDemand(), OnDemand()}) == 1


def test_fixed_schedule_e_imutavel() -> None:
    perfil = FixedSchedule(weekly_hours=Decimal("40"))
    with pytest.raises(dataclasses.FrozenInstanceError):
        perfil.weekly_hours = Decimal("30")  # type: ignore[misc]
