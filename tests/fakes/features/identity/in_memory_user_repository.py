"""Fake in-memory de `UserRepository`.

Duas escolhas deliberadas, que existem para o fake não ser *mais gentil* que a
persistência real:

- **Índice de e-mail global**, não por tenant — é assim que a unicidade é
  definida (kickoff #2), e um fake escopado por tenant esconderia a violação.
- **`seed_membership`** grava vínculo sem validar dono, permitindo simular um
  adapter que devolve vínculo de terceiro. É o cenário do CA12: a visibilidade
  não pode depender de o repositório filtrar direito, porque quem casa
  `user_id` **e** `unit_id` é o domínio.
"""

from collections.abc import Sequence

from restaurant_hub.features.identity.application.dtos.credentials import UserCredentials
from restaurant_hub.features.identity.application.dtos.identifiers import PasswordHash
from restaurant_hub.features.identity.application.errors import (
    EmailAlreadyRegisteredError,
)
from restaurant_hub.features.identity.application.ports.out.user_repository import (
    UserRepository,
)
from restaurant_hub.features.identity.domain.entities.user import User
from restaurant_hub.features.identity.domain.value_objects.email import Email
from restaurant_hub.features.identity.domain.value_objects.identifiers import UserId
from restaurant_hub.features.identity.domain.value_objects.unit_membership import (
    UnitMembership,
)


class InMemoryUserRepository:
    """Implementação in-memory do port, guardando usuário, hash e vínculos."""

    def __init__(self) -> None:
        self.users: dict[UserId, User] = {}
        self.password_hashes: dict[UserId, PasswordHash] = {}
        self.memberships: list[UnitMembership] = []
        self.emails: dict[str, UserId] = {}
        # Quando True, `list_memberships` devolve vínculos de QUALQUER usuário,
        # simulando um adapter permissivo (uma query sem `WHERE user_id`, por
        # exemplo). Serve para provar que a visibilidade não depende de o
        # repositório filtrar corretamente — CA12 / concept §5.13.
        self.leak_foreign_memberships = False

    def add(
        self,
        user: User,
        password_hash: PasswordHash,
        memberships: Sequence[UnitMembership] = (),
    ) -> None:
        # Inserção, não upsert (contrato do port). Sobrescrever em silêncio faria
        # o fake aceitar o que o índice único do Postgres rejeita — e trocaria,
        # sem aviso, qual credencial aquele e-mail autentica.
        existing = self.emails.get(user.email.value)
        if existing is not None and existing != user.id:
            raise EmailAlreadyRegisteredError(user.email.value)
        self.users[user.id] = user
        self.password_hashes[user.id] = password_hash
        self.emails[user.email.value] = user.id
        self.memberships.extend(memberships)

    def find_by_id(self, user_id: UserId) -> User | None:
        return self.users.get(user_id)

    def exists_by_email(self, email: Email) -> bool:
        return email.value in self.emails

    def find_credentials_by_email(self, email: Email) -> UserCredentials | None:
        user_id = self.emails.get(email.value)
        if user_id is None:
            return None
        return UserCredentials(
            user=self.users[user_id],
            password_hash=self.password_hashes[user_id],
        )

    def list_memberships(self, user_id: UserId) -> tuple[UnitMembership, ...]:
        if self.leak_foreign_memberships:
            return tuple(self.memberships)
        return tuple(m for m in self.memberships if m.user_id == user_id)

    # ---- ganchos de teste (não fazem parte do port) ----

    def seed_membership(self, membership: UnitMembership) -> None:
        """Grava vínculo sem validar dono — simula adapter permissivo (CA12)."""
        self.memberships.append(membership)

    def list_all_memberships(self) -> tuple[UnitMembership, ...]:
        """Todos os vínculos gravados, para asserção direta nos testes."""
        return tuple(self.memberships)


_conforms: UserRepository = InMemoryUserRepository()
