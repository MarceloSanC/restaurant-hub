"""Entidade JobFunction — função de trabalho customizável do restaurante.

Raiz de agregado própria, escopo **tenant** (a função é do restaurante, não da
unidade — workforce §3.2); `Employee` a referencia **só por id**. Papel de
trabalho, não papel de acesso (RBAC é de identity).

Entidade **frozen**: transições devolvem nova instância via
`dataclasses.replace`, revalidada pelo `__post_init__` — as invariantes valem
em todos os caminhos de construção, inclusive a reidratação da persistência
(3.3). Igualdade por **identidade**.

A unicidade do nome no tenant e o bloqueio de atribuição de função inativa são
**declarados** aqui e impostos na application/persistência (3.2/3.3 —
concept §5.3/§5.10).
"""

import dataclasses
from dataclasses import dataclass

from restaurant_hub.features.staff.domain.exceptions.errors import (
    InvalidIdentifierError,
    InvalidNameError,
)
from restaurant_hub.features.staff.domain.value_objects.identifiers import (
    JobFunctionId,
    TenantId,
)


@dataclass(frozen=True, eq=False)
class JobFunction:
    """Função de trabalho customizável, com ciclo de vida soft (ADR 3.1.0003).

    Attributes:
        id: identidade da função.
        tenant_id: restaurante dono da função (escopo tenant).
        name: nome verbatim (sem trim/case — ADR 3.1.0002), não-vazio;
            unicidade no tenant é enforcement da 3.2/3.3.
        active: estado do ciclo de vida — inativa não recebe novas
            atribuições (enforcement na 3.2) e preserva referências.
    """

    id: JobFunctionId
    tenant_id: TenantId
    name: str
    active: bool = True

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise InvalidIdentifierError("função")
        if not self.tenant_id.strip():
            raise InvalidIdentifierError("tenant da função")
        if not self.name.strip():
            raise InvalidNameError("função")

    def rename(self, name: str) -> "JobFunction":
        """Renomeia a função — nova instância revalidada (nome verbatim)."""
        return dataclasses.replace(self, name=name)

    def deactivate(self) -> "JobFunction":
        """Desativa a função — idempotente no valor (já inativa não é erro)."""
        return dataclasses.replace(self, active=False)

    def reactivate(self) -> "JobFunction":
        """Reativa a função — idempotente no valor (já ativa não é erro)."""
        return dataclasses.replace(self, active=True)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, JobFunction):
            return NotImplemented
        return self.id == other.id

    def __hash__(self) -> int:
        return hash(self.id)
