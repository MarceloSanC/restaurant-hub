"""Use case: criar uma unidade (filial) sob um restaurante existente.

O restaurante é resolvido **antes** de qualquer escrita: uma unidade órfã teria
um `tenant_id` apontando para nada, e como é justamente esse campo que sustenta o
isolamento row-level (ROADMAP-3), o registro passaria a ser invisível para toda
consulta escopada por tenant — um vazamento silencioso de dado.

**Autoriza antes de qualquer outra instrução** (Stage 2.7, ADR 0.0.0020 §Decision
3): o ator do command precisa de `manage_tenant` **no restaurante do command** — um
`owner` de outro tenant é negado antes da leitura do restaurante, então nem a
existência dele vaza. A borda HTTP continua autorizando o mesmo requisito antes.
"""

from restaurant_hub.features.identity.application.dtos.commands import CreateUnitCommand
from restaurant_hub.features.identity.application.dtos.results import UnitResult
from restaurant_hub.features.identity.application.errors import RestaurantNotFoundError
from restaurant_hub.features.identity.application.ports.out.action_authorizer import (
    ActionAuthorizer,
)
from restaurant_hub.features.identity.application.ports.out.restaurant_repository import (
    RestaurantRepository,
)
from restaurant_hub.features.identity.application.ports.out.unit_repository import (
    UnitRepository,
)
from restaurant_hub.features.identity.application.use_cases.authorize_action import (
    authorize_requirement,
)
from restaurant_hub.features.identity.domain.entities.unit import Unit
from restaurant_hub.features.identity.domain.value_objects.identifiers import UnitId
from restaurant_hub.features.identity.domain.value_objects.permission import Permission
from restaurant_hub.shared.application.ports.out.id_generator import IdGenerator


class CreateUnitUseCase:
    """Cria uma unidade sob um restaurante existente."""

    def __init__(
        self,
        units: UnitRepository,
        restaurants: RestaurantRepository,
        id_generator: IdGenerator,
        authorizer: ActionAuthorizer,
    ) -> None:
        self._units = units
        self._restaurants = restaurants
        self._id_generator = id_generator
        self._authorizer = authorizer

    def execute(self, command: CreateUnitCommand) -> UnitResult:
        """Cria a unidade.

        Raises:
            InvalidAccessTokenError, PermissionDeniedError, TenantScopeRequiredError,
                TenantNotVisibleError: o ator não detém `manage_tenant` no
                restaurante do command (ADR 2.7.0001 §Decision 3).
            RestaurantNotFoundError: o restaurante informado não existe.
            InvalidNameError: nome vazio (invariante do domínio).
        """
        authorize_requirement(
            self._authorizer,
            command.actor_id,
            frozenset({Permission.MANAGE_TENANT}),
            tenant_id=command.restaurant_id,
        )

        if self._restaurants.find_by_id(command.restaurant_id) is None:
            raise RestaurantNotFoundError(command.restaurant_id)

        unit = Unit(
            id=UnitId(str(self._id_generator.next_id())),
            restaurant_id=command.restaurant_id,
            name=command.name,
        )
        self._units.add(unit)
        return UnitResult(
            id=unit.id,
            restaurant_id=unit.restaurant_id,
            name=unit.name,
        )
