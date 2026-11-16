"""Autorização de uma habilitação por unidade — compartilhada por dois use cases.

Módulo privado (prefixo `_`, como `_inputs.py` e `_publish.py` de scheduling):
não é use case, e a varredura "um arquivo por use case" o ignora. Mora aqui
porque `CreateJobFunctionUseCase` e `SetJobFunctionUnitsUseCase` aplicam **a
mesma** regra de alcance (ADR 3.11.0001 §4 e §5), e duas cópias de uma regra de
acesso divergem em silêncio.

**A regra** (concept 3.11 R4/R5):

- **unidades nomeadas** — `manage_job_functions` em **cada** unidade, uma
  autorização por alvo (L-AG4), em ordem estável (`sorted`): identity roda o
  passo de visibilidade sempre que a unidade é nomeada, então o gerente só
  alcança as unidades de que é membro;
- **todas as unidades** — `manage_tenant` no tenant: decidir o catálogo do
  restaurante inteiro é ato de restaurante, e é a permissão de restaurante que o
  guard expõe sem que staff leia papel (ADR 3.11.0001 §4).

As duas funções **não** autorizam o tenant com `manage_job_functions`: isso é do
use case, antes de tudo (ADR 3.7.0001 §4). A exceção do guard sobe crua (L-AG2).
"""

from restaurant_hub.features.staff.application.ports.out.access_guard import (
    PERMISSION_MANAGE_JOB_FUNCTIONS,
    PERMISSION_MANAGE_TENANT,
    AccessGuard,
    Actor,
)
from restaurant_hub.features.staff.domain.value_objects.identifiers import TenantId, UnitId


def authorize_enablement(
    guard: AccessGuard,
    actor: Actor,
    tenant_id: TenantId,
    unit_ids: frozenset[UnitId] | None,
) -> None:
    """Autoriza o ator a habilitar uma função em `unit_ids` (`None` = todas)."""
    if unit_ids is None:
        guard.authorize(actor, PERMISSION_MANAGE_TENANT, tenant_id=tenant_id)
        return
    _authorize_units(guard, actor, tenant_id, unit_ids)


def authorize_enablement_change(
    guard: AccessGuard,
    actor: Actor,
    tenant_id: TenantId,
    *,
    old: frozenset[UnitId] | None,
    new: frozenset[UnitId] | None,
) -> None:
    """Autoriza só **o que muda** entre duas habilitações (`None` = todas).

    Igual ⇒ nada a autorizar. Se um dos lados é "todas" e os dois diferem, a
    mudança alcança o restaurante inteiro ⇒ `manage_tenant`. Entre dois conjuntos,
    cada unidade acrescentada **e** cada removida é um alvo (ADR 3.11.0001 §5): é o
    que deixa o gerente habilitar na sua unidade uma função que vale em outra, sem
    alcançar a outra, e o que o impede de remover unidade que não enxerga.
    """
    if old == new:
        return
    if old is None or new is None:
        guard.authorize(actor, PERMISSION_MANAGE_TENANT, tenant_id=tenant_id)
        return
    _authorize_units(guard, actor, tenant_id, old ^ new)


def _authorize_units(
    guard: AccessGuard, actor: Actor, tenant_id: TenantId, unit_ids: frozenset[UnitId]
) -> None:
    for unit_id in sorted(unit_ids):
        guard.authorize(
            actor, PERMISSION_MANAGE_JOB_FUNCTIONS, tenant_id=tenant_id, unit_id=unit_id
        )
