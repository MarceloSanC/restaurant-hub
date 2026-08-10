"""Entidade JobFunction — função de trabalho customizável do restaurante.

Raiz de agregado própria, escopo **tenant** (a função é do restaurante, não da
unidade — workforce §3.2); `Employee` a referencia **só por id**. Papel de
trabalho, não papel de acesso (RBAC é de identity).

Entidade **frozen**: transições devolvem nova instância via
`dataclasses.replace`, revalidada pelo `__post_init__` — as invariantes valem
em todos os caminhos de construção, inclusive a reidratação da persistência
(3.3). Igualdade por **identidade**.

A unicidade do nome no tenant é **declarada** aqui e imposta na
application/persistência (3.2/3.3 — concept 3.2 §5.5), assim como a **remoção
guardada**: apagar função referenciada por algum funcionário é recusado
(concept 3.2 §5.9).
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
    """Função de trabalho customizável, **sem ciclo de vida** (ADR 3.2.0005).

    A função não tem estado ativo/inativo: função sem atribuição é **inerte**
    — não aparece na operação, não é escalável e não carrega história própria.
    Quem não a quer mais **apaga** (remoção guardada — concept 3.2 §5.9). O
    ADR 3.2.0005 supersede o 3.1.0003, que dera à função um ciclo de vida soft.

    Attributes:
        id: identidade da função.
        tenant_id: restaurante dono da função (escopo tenant).
        name: nome verbatim (sem trim/case — ADR 3.1.0002), não-vazio;
            unicidade no tenant é enforcement da 3.2/3.3.
    """

    id: JobFunctionId
    tenant_id: TenantId
    name: str

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

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, JobFunction):
            return NotImplemented
        return self.id == other.id

    def __hash__(self) -> int:
        return hash(self.id)
