"""Port de saída: persistência da escala e da trilha de mudanças (ADR 4.3.0004).

**Uma escrita carrega a mudança.** `add` e `save` recebem a `ScheduleChange` — quem,
quando, versão anterior, operações efetivas e violações aceitas — e o adapter (Stage 4.4)
grava estado e trilha **na mesma transação**. Cada use case escreve uma vez, então a
regra 10 do `check_layout` (ADR 2.6.0002 §5) não exige unidade de trabalho.

`ScheduleChange` **não define método algum**: a regra 10 classifica como escrita todo
método não-leitura de classe declarada em `*_repository.py`.

**Leis** (suíte `tests/contract/features/scheduling/test_schedule_repository_laws.py`):

- **L-SC1 — `add` é inserção.** Id de escala já gravado ⇒ `IdentifierInUseError`.
- **L-SC2 — dias disjuntos.** `add` cujo período cruza dia de outra escala do mesmo
  (tenant, unidade) ⇒ `SchedulePeriodTakenError` (invariante 4 da 4.1). Atômica no
  adapter; limite de concorrência declarado (ADR 3.2.0001).
- **L-SC3 — estado e trilha juntos.** A mudança é gravada com o estado, ou nenhum dos dois.
- **L-SC4 — `save` otimista.** Inexistente no endereço ⇒ `ScheduleNotFoundError`; versão
  gravada ≠ `expected_version` ⇒ `ScheduleVersionConflictError` (com a atual); id interno
  já usado por **outra** escala do mesmo (tenant, unidade) ⇒ `IdentifierInUseError`.
  Ordem: endereço → versão → ids.
- **L-SC5 — endereço de três partes.** Outro tenant ou unidade ⇒ `None`, e nunca aparece
  em listagem.
- **L-SC6 — recorte.** `list_in_range` = as escalas que cruzam [first_day, last_day],
  ordenadas por first_day.
- **L-SC7 — anteriores.** `list_ending_before` = last_day < before, da mais recente, no
  máximo `limit`.
- **L-SC8 — fidelidade.** O lido é o gravado, campo a campo, inclusive a versão.
"""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol

from restaurant_hub.features.scheduling.application.dtos.commands import ScheduleOperation
from restaurant_hub.features.scheduling.domain.entities.schedule import Schedule
from restaurant_hub.features.scheduling.domain.value_objects.identifiers import (
    ScheduleId,
    TenantId,
    UnitId,
)
from restaurant_hub.features.scheduling.domain.value_objects.violation import Violation


@dataclass(frozen=True)
class ScheduleChange:
    """O registro de uma mudança — a entrada da trilha de auditoria (4.4).

    Attributes:
        author_user_id: quem — o `user_id` do escopo autorizado.
        occurred_at: quando — `Clock.now()`.
        previous_version: a versão sobre a qual a mudança foi feita; `None` na criação.
        operations: o quê — as operações **efetivas**, em ordem (no-ops fora).
        acknowledged: as violações `warn` introduzidas e aceitas conscientemente.
    """

    author_user_id: str
    occurred_at: datetime
    previous_version: int | None
    operations: tuple[ScheduleOperation, ...]
    acknowledged: tuple[Violation, ...]


class ScheduleRepository(Protocol):
    """Escalas por (tenant, unidade), com a trilha de cada escrita."""

    def add(self, schedule: Schedule, change: ScheduleChange) -> None:
        """Insere a escala nova com a sua mudança de criação (L-SC1, L-SC2, L-SC3)."""
        ...

    def save(self, schedule: Schedule, expected_version: int, change: ScheduleChange) -> None:
        """Substitui a escala se a gravada está em `expected_version` (L-SC3, L-SC4)."""
        ...

    def find_by_id(
        self, tenant_id: TenantId, unit_id: UnitId, schedule_id: ScheduleId
    ) -> Schedule | None:
        """A escala no endereço de três partes, ou `None` (L-SC5)."""
        ...

    def list_in_range(
        self, tenant_id: TenantId, unit_id: UnitId, first_day: date, last_day: date
    ) -> tuple[Schedule, ...]:
        """As escalas da unidade que cruzam o recorte, por first_day (L-SC6)."""
        ...

    def list_ending_before(
        self, tenant_id: TenantId, unit_id: UnitId, before: date, limit: int
    ) -> tuple[Schedule, ...]:
        """As escalas que terminam antes de `before`, mais recente primeiro (L-SC7)."""
        ...
