"""Value object UnitMembership — vínculo mínimo usuário↔unidade.

Esqueleto do vínculo (kickoff #1, ADR 2.1.0001): liga um usuário a uma unidade
para efeito de **visibilidade**, sem papel-por-unidade — o papel do usuário é
único no tenant. Papel-por-unidade é evolução futura e entra como campo aqui, sem
refazer a forma.

É um **registro de associação sem raiz dona**: `User.link_to_unit` o cria impondo
as invariantes de isolamento (mesmo tenant, não `platform_admin`), e tanto `User`
quanto `Unit` o referenciam por id, sem retê-lo. Frozen ⇒ igualdade estrutural,
que é exatamente o que o filtro de visibilidade compara.
"""

from dataclasses import dataclass

from restaurant_hub.features.identity.domain.value_objects.identifiers import (
    UnitId,
    UserId,
)


@dataclass(frozen=True)
class UnitMembership:
    """Vínculo de um usuário a uma unidade.

    Attributes:
        user_id: usuário vinculado.
        unit_id: unidade à qual ele passa a ter acesso.
    """

    user_id: UserId
    unit_id: UnitId
