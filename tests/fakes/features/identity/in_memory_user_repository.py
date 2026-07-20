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
    UnitMembershipAlreadyExistsError,
    UserAlreadyExistsError,
    UserNotFoundError,
)
from restaurant_hub.features.identity.application.ports.out.user_repository import (
    UserRepository,
)
from restaurant_hub.features.identity.domain.entities.user import User
from restaurant_hub.features.identity.domain.value_objects.email import Email
from restaurant_hub.features.identity.domain.value_objects.identifiers import UnitId, UserId
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
        #
        # A ORDEM das checagens é parte da especificação: id duplicado é checado
        # ANTES do e-mail. Re-gravar o mesmo usuário não é conflito de e-mail (o
        # e-mail é dele), e reportá-lo como tal faria a 2.4 responder "e-mail já
        # registrado" a uma requisição cujo e-mail está livre. Até a Stage 2.3 o
        # fake aceitava esse caso em silêncio, contrariando o próprio docstring do
        # port — ADR 2.3.0003.
        if user.id in self.users:
            raise UserAlreadyExistsError(user.id)
        existing = self.emails.get(user.email.value)
        if existing is not None:
            raise EmailAlreadyRegisteredError(user.email.value)
        # PK composta (user_id, unit_id) na tabela real: vínculo repetido é
        # rejeitado, não acumulado. O use case da 2.2 já deduplica `unit_ids`
        # (invariante #15), então nenhum caminho de produção regride.
        novos = list(memberships)
        vistos: set[tuple[UserId, UnitId]] = set()
        for membership in novos:
            chave = (membership.user_id, membership.unit_id)
            if chave in vistos:
                # Reporta o dono do vínculo repetido, não o do `add`: os dois
                # podem diferir, e apontar para a linha errada custa caro no
                # diagnóstico.
                raise UnitMembershipAlreadyExistsError(membership.user_id)
            vistos.add(chave)
        self.users[user.id] = user
        self.password_hashes[user.id] = password_hash
        self.emails[user.email.value] = user.id
        self.memberships.extend(novos)

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

    def set_password_hash(self, user_id: UserId, password_hash: PasswordHash) -> None:
        # `UPDATE`, não upsert: usuário inexistente levanta e nada é gravado.
        # Um `self.password_hashes[user_id] = ...` direto criaria uma credencial
        # órfã que o Postgres recusa — e faria o teste de "token de usuário
        # apagado" passar verde sobre um caminho que, no banco, falha.
        if user_id not in self.users:
            raise UserNotFoundError(user_id)
        self.password_hashes[user_id] = password_hash

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
