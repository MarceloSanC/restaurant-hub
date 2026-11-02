"""Use case: provisionar um tenant — o restaurante e o seu primeiro `owner`.

**Restaurante e dono são uma unidade de trabalho** (ADR 0.0.0013, sobre o port
do ADR 2.6.0001). Antes, o provisionamento eram duas chamadas — criar o
restaurante, depois criar o dono —, e uma falha entre elas deixava um
restaurante que ninguém opera: o `platform_admin` só detém `manage_platform` e
não age dentro do tenant. Aqui, se o `users.add` falha (inclusive pelo índice
único de e-mail, numa corrida com outro cadastro), o `restaurants.add` é
desfeito.

**As duas escritas são chamadas diretas aos repositórios**, e não a
`CreateRestaurantUseCase`/`CreateUserUseCase`: a regra 10 do `check_layout`
enxerga escrita por atributo de repositório, e escrita alcançada pelo `execute`
de outro use case é ponto cego declarado dela (ADR 2.6.0002 §5).

**O papel é o literal `Role.OWNER`, aqui** — não vem do command. Com ele, "nenhum
caminho emite `platform_admin`" vale para este use case qualquer que seja o
adapter que o chame (ADR 0.0.0013 §3; ADR 2.4.0003 §2b).

**A autorização fica na borda**, como em todo use case de identity (ADR 2.4.0003
§1): este use case não recebe ator. O ADR 3.7.0001 trouxe a autorização para
dentro dos use cases de **staff**, não de identity (ADR 0.0.0013 §4).

Ordem: o nome (invariante do domínio, local e grátis) primeiro; depois a
unicidade global do e-mail, antes de qualquer escrita; o hash fora da unidade,
para não alongar a janela de lock (ADR 2.6.0001 §2).
"""

from restaurant_hub.features.identity.application.dtos.commands import (
    ProvisionRestaurantCommand,
)
from restaurant_hub.features.identity.application.dtos.results import (
    ProvisionedRestaurantResult,
    to_user_result,
)
from restaurant_hub.features.identity.application.errors import EmailAlreadyRegisteredError
from restaurant_hub.features.identity.application.ports.out.password_hasher import (
    PasswordHasher,
)
from restaurant_hub.features.identity.application.ports.out.restaurant_repository import (
    RestaurantRepository,
)
from restaurant_hub.features.identity.application.ports.out.unit_of_work import UnitOfWork
from restaurant_hub.features.identity.application.ports.out.user_repository import (
    UserRepository,
)
from restaurant_hub.features.identity.domain.entities.restaurant import Restaurant
from restaurant_hub.features.identity.domain.entities.user import User
from restaurant_hub.features.identity.domain.value_objects.identifiers import (
    RestaurantId,
    UserId,
)
from restaurant_hub.features.identity.domain.value_objects.role import Role
from restaurant_hub.shared.application.ports.out.id_generator import IdGenerator


class ProvisionRestaurantUseCase:
    """Cria o restaurante e o seu `owner`, tudo ou nada."""

    def __init__(
        self,
        restaurants: RestaurantRepository,
        users: UserRepository,
        hasher: PasswordHasher,
        id_generator: IdGenerator,
        unit_of_work: UnitOfWork,
    ) -> None:
        self._restaurants = restaurants
        self._users = users
        self._hasher = hasher
        self._id_generator = id_generator
        self._unit_of_work = unit_of_work

    def execute(self, command: ProvisionRestaurantCommand) -> ProvisionedRestaurantResult:
        """Provisiona o tenant.

        Raises:
            InvalidNameError: nome do restaurante vazio (invariante do domínio).
            EmailAlreadyRegisteredError: e-mail do dono já usado em qualquer tenant —
                pela checagem prévia ou, numa corrida, pelo índice único dentro da
                unidade (e então o restaurante é desfeito).
        """
        restaurant = Restaurant(
            id=RestaurantId(str(self._id_generator.next_id())),
            name=command.name,
        )

        if self._users.exists_by_email(command.owner_email):
            raise EmailAlreadyRegisteredError(command.owner_email.value)

        owner = User(
            id=UserId(str(self._id_generator.next_id())),
            email=command.owner_email,
            role=Role.OWNER,
            tenant_id=restaurant.id,
        )
        password_hash = self._hasher.hash(command.owner_plain_password)

        with self._unit_of_work.transaction():
            self._restaurants.add(restaurant)
            self._users.add(owner, password_hash, ())

        return ProvisionedRestaurantResult(
            id=restaurant.id,
            name=restaurant.name,
            owner=to_user_result(owner, ()),
        )
