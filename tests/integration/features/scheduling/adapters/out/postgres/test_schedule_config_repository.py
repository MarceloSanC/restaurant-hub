"""`PostgresScheduleConfigRepository` contra o Postgres — CA13, metade integração.

A suíte de lei (L-CF1) roda sobre a configuração **default**; aqui a linha é não-default em
todo campo, e gravada por `INSERT` direto, para que coluna trocada entre mapper e tabela não
passe: cada política difere das vizinhas, e os quatro limites são distintos dois a dois.
"""

from datetime import time
from typing import Any

import pytest
from sqlalchemy import Engine

from restaurant_hub.features.scheduling.adapters.out.postgres.schedule_config_repository import (
    PostgresScheduleConfigRepository,
)
from restaurant_hub.features.scheduling.adapters.out.postgres.tables import (
    POLICY_FIELDS,
    scheduling_settings,
)
from restaurant_hub.features.scheduling.domain.exceptions.errors import InvalidDayCutoffError
from restaurant_hub.features.scheduling.domain.value_objects.identifiers import TenantId
from restaurant_hub.features.scheduling.domain.value_objects.operational_calendar import (
    DayCutoff,
    OperationalCalendar,
    Weekday,
)
from restaurant_hub.features.scheduling.domain.value_objects.validation_config import (
    EnforcementMode,
    PolicyRule,
    ValidationConfig,
    WorkloadDirection,
)

pytestmark = [pytest.mark.integration]

# Habilitação e modo alternados por posição: vizinhas sempre diferem em ao menos um.
_REGRAS = {
    policy: PolicyRule(
        enabled=index % 2 == 0,
        mode=EnforcementMode.BLOCK if index % 3 == 0 else EnforcementMode.WARN,
    )
    for index, policy in enumerate(POLICY_FIELDS)
}


def _linha(tenant_id: str, **alteracao: object) -> dict[str, Any]:
    linha: dict[str, Any] = {
        "tenant_id": tenant_id,
        "week_start": "thursday",
        "day_cutoff": time(6, 15),
        "min_rest_minutes": 601,
        "daily_cap_minutes": 602,
        "weekly_cap_minutes": 2603,
        "workload_tolerance_minutes": 4,
        "workload_direction": "both",
    }
    for policy, regra in _REGRAS.items():
        linha[f"{policy}_enabled"] = regra.enabled
        linha[f"{policy}_mode"] = regra.mode.value
    return {**linha, **alteracao}


def _gravar(engine: Engine, linha: dict[str, Any]) -> None:
    with engine.begin() as conexao:
        conexao.execute(scheduling_settings.insert().values(linha))


def test_linha_nao_default_e_lida_campo_a_campo(banco_limpo: Engine) -> None:
    _gravar(banco_limpo, _linha("t1"))
    _gravar(banco_limpo, _linha("t2", week_start="monday", min_rest_minutes=0))
    lida = PostgresScheduleConfigRepository(banco_limpo).find_settings(TenantId("t1"))
    assert lida is not None
    assert lida.calendar == OperationalCalendar(
        week_start=Weekday.THURSDAY, day_cutoff=DayCutoff(time(6, 15))
    )
    assert lida.validation == ValidationConfig(
        **_REGRAS,
        min_rest_minutes=601,
        daily_cap_minutes=602,
        weekly_cap_minutes=2603,
        workload_tolerance_minutes=4,
        workload_direction=WorkloadDirection.BOTH,
    )
    assert lida.validation.overlap.mode is EnforcementMode.BLOCK


def test_tenant_sem_linha_devolve_none(banco_limpo: Engine) -> None:
    _gravar(banco_limpo, _linha("t1"))
    assert PostgresScheduleConfigRepository(banco_limpo).find_settings(TenantId("t9")) is None


def test_corte_com_segundos_aceito_pela_check_levanta_ao_ser_lido(banco_limpo: Engine) -> None:
    """A `CHECK` não expressa minuto inteiro; a reidratação pelo construtor barra."""
    _gravar(banco_limpo, _linha("t1", day_cutoff=time(6, 15, 30)))
    with pytest.raises(InvalidDayCutoffError):
        PostgresScheduleConfigRepository(banco_limpo).find_settings(TenantId("t1"))
