"""Port de saída: a decisão de acesso que os use cases de identity consomem (Stage 2.7).

Os use cases de identity que agem em nome de um ator autenticado autorizam o alvo do
próprio command **antes de qualquer outra instrução** (ADR 0.0.0020, ADR 2.7.0001).
Quem decide continua sendo um só: `AuthorizeActionUseCase`, que cumpre este port
estruturalmente. O use case **declara** o requisito; não o avalia.

**Um port de saída sem adapter — divergência declarada do LAYOUT §5** (ADR 2.7.0001
§Decision 2). A decisão de acesso é do próprio identity, então não há mundo externo
a adaptar; o port existe para que o use case dependa de interface e para que o teste
negue com um dublê (`tests/fakes/features/identity/stub_action_authorizers.py`).

**`required_permissions_for_role` mora aqui** pelo mesmo motivo que o vocabulário de
staff mora no módulo do port dele (ADR 3.7.0001 §Decision 5): o use case precisa da
regra e não pode importar o adapter HTTP, onde ela nasceu (Stage 2.4). A borda a
reexporta, e o que ela decide continua igual.
"""

from typing import Protocol

from restaurant_hub.features.identity.application.dtos.commands import (
    AuthorizeActionCommand,
)
from restaurant_hub.features.identity.application.dtos.results import AuthorizedActor
from restaurant_hub.features.identity.domain.value_objects.permission import Permission
from restaurant_hub.features.identity.domain.value_objects.role import Role


class ActionAuthorizer(Protocol):
    """Autoriza um pedido de ação, ou levanta o erro da primeira checagem que falhar."""

    def execute(self, command: AuthorizeActionCommand) -> AuthorizedActor:
        """Mesmo contrato de `AuthorizeActionUseCase.execute` (ADR 2.2.0002)."""
        ...


def required_permissions_for_role(target_role: Role) -> frozenset[Permission]:
    """Permissões exigidas para **criar** um usuário do papel `target_role`.

    "Não se concede o que não se detém" (concept 2.4 §5 regra 4): quem cria precisa
    de `manage_users` **e** de tudo o que o papel criado passa a ter. Sem isso um
    `manager` (que tem `manage_users`) criaria um `owner` (que tem `manage_tenant`)
    e escalaria privilégio numa requisição. E como nenhum papel detém
    `manage_users` e `manage_platform` ao mesmo tempo, ninguém cria um
    `platform_admin` por este requisito (ADR 2.4.0003 §2b).

    **O conjunto é derivado do mapa de papéis da 2.1**, não de uma tabela nova.
    Duas fontes de verdade sobre o que cada papel pode divergiriam, e a divergência
    apareceria como escalada silenciosa.
    """
    return frozenset({Permission.MANAGE_USERS}) | target_role.permissions
