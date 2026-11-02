"""Lei L-CF1 do `ScheduleConfigRepository` (concept 4.3 §4; CA21)."""

import pytest

from restaurant_hub.features.scheduling.application.ports.out.schedule_config_repository import (
    ScheduleConfigRepository,
    SchedulingSettings,
)
from tests.contract.features.scheduling.conftest import T1, T2

pytestmark = pytest.mark.contract


def test_l_cf1_devolve_a_configuracao_gravada_do_tenant(
    config_world: tuple[ScheduleConfigRepository, SchedulingSettings],
) -> None:
    repo, gravada = config_world
    assert repo.find_settings(T1) == gravada


def test_l_cf1_tenant_sem_configuracao_devolve_none_e_nunca_a_de_outro(
    config_world: tuple[ScheduleConfigRepository, SchedulingSettings],
) -> None:
    repo, _ = config_world
    assert repo.find_settings(T2) is None
