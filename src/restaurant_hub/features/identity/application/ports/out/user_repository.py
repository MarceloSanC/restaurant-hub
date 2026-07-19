"""Port de saída: persistência de usuários, credenciais e vínculos de unidade.

Três decisões de forma que valem explicação, porque a Stage 2.3 implementa este
contrato e mudá-lo depois custa caro:

1. **`add` grava usuário, hash e vínculos numa só operação.** Na 2.3 os três são
   a mesma transação; separá-los em três chamadas convidaria a um usuário
   persistido sem credencial.
2. **`exists_by_email` é global, não escopado por tenant** (decisão de kickoff
   #2): o mesmo e-mail não pode existir em dois restaurantes. Existe *além* de
   `find_credentials_by_email` para que a checagem de unicidade não precise
   carregar o hash de uma credencial alheia.
3. **`list_memberships` não precisa filtrar** — quem casa `user_id` **e**
   `unit_id` é `User.can_view_unit`, no domínio. Um adapter que devolva vínculo
   de terceiro não abre buraco de visibilidade, e o teste prova isso.
"""

from collections.abc import Sequence
from typing import Protocol

from restaurant_hub.features.identity.application.dtos.credentials import UserCredentials
from restaurant_hub.features.identity.application.dtos.identifiers import PasswordHash
from restaurant_hub.features.identity.domain.entities.user import User
from restaurant_hub.features.identity.domain.value_objects.email import Email
from restaurant_hub.features.identity.domain.value_objects.identifiers import UserId
from restaurant_hub.features.identity.domain.value_objects.unit_membership import (
    UnitMembership,
)


class UserRepository(Protocol):
    """Contrato de persistência da raiz de agregado `User` e do que a acompanha."""

    def add(
        self,
        user: User,
        password_hash: PasswordHash,
        memberships: Sequence[UnitMembership] = (),
    ) -> None:
        """Persiste usuário, credencial e vínculos como uma única unidade.

        **É inserção, não upsert.** E-mail já registrado levanta
        `EmailAlreadyRegisteredError` — o mesmo erro que `exists_by_email`
        antecipa. A checagem prévia do use case resolve o caso comum com uma
        mensagem melhor; esta regra é a garantia dura, que continua valendo sob
        concorrência, quando duas requisições passam pela checagem antes de
        qualquer uma gravar. Na 2.3 ela é o índice único global sobre o e-mail,
        cujo `IntegrityError` o adapter traduz para esta exceção.

        Sem essa regra no contrato, o fake sobrescreveria em silêncio e o
        Postgres levantaria — divergência que só apareceria no teste de contrato
        da 2.3.
        """
        ...

    def find_by_id(self, user_id: UserId) -> User | None:
        """Devolve o usuário, ou `None` se não existir."""
        ...

    def exists_by_email(self, email: Email) -> bool:
        """True se o e-mail já pertence a algum usuário, em **qualquer** tenant."""
        ...

    def find_credentials_by_email(self, email: Email) -> UserCredentials | None:
        """Devolve usuário + hash numa ida só, ou `None` se o e-mail não existir."""
        ...

    def list_memberships(self, user_id: UserId) -> tuple[UnitMembership, ...]:
        """Vínculos de unidade associados ao usuário."""
        ...
