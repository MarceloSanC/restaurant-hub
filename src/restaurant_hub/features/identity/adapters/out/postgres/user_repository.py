"""Adapter Postgres de `UserRepository`.

O repositório com mais regra da Stage. Três pontos merecem atenção:

**1. `add` é atômico de verdade.** Usuário, credencial e vínculos entram numa
única transação (ou num único savepoint, dentro de uma unidade de trabalho — ADR
2.6.0001), como o docstring do port exige. Se qualquer parte falhar
— um vínculo apontando para unidade inexistente, um vínculo cruzando tenant — a
transação inteira reverte e **nada** fica gravado. Sem isso, o caso que o port
existe para impedir (usuário persistido sem credencial, ou com metade dos
vínculos) aconteceria justamente sob concorrência.

**2. `find_by_id` não seleciona `password_hash`.** O hash está na mesma linha, e é
tentador fazer `select(users)`. Não fazemos: quem pede um `User` não precisa do
hash, e material de credencial que não é carregado não vaza em log, traceback nem
repr. `find_credentials_by_email` é o único caminho que o traz, porque é o único
que precisa.

**3. `list_memberships` filtra por `user_id`, e isso é conforme mas não é a
garantia.** A 2.2 é explícita: o port **pode** devolver vínculos de outros
usuários sem quebrar o contrato, porque quem casa usuário e unidade é
`User.can_view_unit`, no domínio. O filtro aqui é o `WHERE` óbvio e barato — mas a
visibilidade não depende dele, e é justamente por isso que o fake da 2.2 mantém o
gancho `leak_foreign_memberships`, que simula um adapter permissivo.
"""

from collections.abc import Sequence

from sqlalchemy import Connection, Engine, select
from sqlalchemy.exc import IntegrityError

from restaurant_hub.features.identity.adapters.out.postgres import mappers
from restaurant_hub.features.identity.adapters.out.postgres.integrity_errors import (
    constraint_name,
    translate,
)
from restaurant_hub.features.identity.adapters.out.postgres.tables import (
    unit_memberships,
    users,
)
from restaurant_hub.features.identity.adapters.out.postgres.unit_connection import (
    for_read,
    for_write,
)
from restaurant_hub.features.identity.application.dtos.credentials import UserCredentials
from restaurant_hub.features.identity.application.dtos.identifiers import PasswordHash
from restaurant_hub.features.identity.application.errors import UserNotFoundError
from restaurant_hub.features.identity.domain.entities.user import User
from restaurant_hub.features.identity.domain.value_objects.email import Email
from restaurant_hub.features.identity.domain.value_objects.identifiers import UserId
from restaurant_hub.features.identity.domain.value_objects.unit_membership import (
    UnitMembership,
)


class PostgresUserRepository:
    """Implementação PostgreSQL do port `UserRepository`."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def add(
        self,
        user: User,
        password_hash: PasswordHash,
        memberships: Sequence[UnitMembership] = (),
    ) -> None:
        """Grava usuário, credencial e vínculos como **uma única** unidade."""
        try:
            with for_write(self._engine) as connection:
                self._add(connection, user, password_hash, memberships)
        except IntegrityError as error:
            # Qual valor entra na mensagem depende de QUAL regra foi violada: o
            # e-mail para o conflito de e-mail, o id para os demais. Uma mensagem
            # dizendo "e-mail já registrado: user-42" seria pior que nenhuma.
            detail = user.email.value if constraint_name(error) == "uq_users_email" else user.id
            raise translate(error, detail) from error

    def find_by_id(self, user_id: UserId) -> User | None:
        with for_read(self._engine) as connection:
            return self._find_by_id(connection, user_id)

    def exists_by_email(self, email: Email) -> bool:
        """Unicidade é **global**, não escopada por tenant (kickoff #2).

        Por isso não há `WHERE tenant_id = ...` aqui: acrescentá-lo deixaria o
        mesmo login existir em dois restaurantes, e passaria em qualquer teste que
        só usasse um tenant.
        """
        with for_read(self._engine) as connection:
            found = connection.execute(
                select(users.c.id).where(users.c.email == email.value)
            ).one_or_none()
            return found is not None

    def find_credentials_by_email(self, email: Email) -> UserCredentials | None:
        """Usuário + hash numa ida só — `authenticate_user` precisa dos dois."""
        with for_read(self._engine) as connection:
            row = connection.execute(
                select(users).where(users.c.email == email.value)
            ).one_or_none()
            if row is None:
                return None
            return UserCredentials(
                user=mappers.row_to_user(row),
                password_hash=PasswordHash(row.password_hash),
            )

    def list_memberships(self, user_id: UserId) -> tuple[UnitMembership, ...]:
        with for_read(self._engine) as connection:
            rows = connection.execute(
                select(unit_memberships).where(unit_memberships.c.user_id == user_id)
            ).all()
            return tuple(mappers.row_to_membership(row) for row in rows)

    # ---- núcleo sobre `Connection` (a mesma dentro ou fora da unidade de trabalho) ----

    def _add(
        self,
        connection: Connection,
        user: User,
        password_hash: PasswordHash,
        memberships: Sequence[UnitMembership],
    ) -> None:
        connection.execute(users.insert().values(**mappers.user_to_row(user, password_hash)))
        membership_list = list(memberships)
        if not membership_list:
            return
        # O `tenant_id` do vínculo vem do usuário dono, não do próprio
        # `UnitMembership` (que só carrega dois ids). As FKs compostas rejeitam a
        # linha se ele não bater com o tenant da unidade — é assim que vínculo
        # cross-tenant fica irrepresentável.
        #
        # Por que o `type: ignore[arg-type]` abaixo é seguro: `user.tenant_id` é
        # `RestaurantId | None` e `membership_to_row` exige `RestaurantId`. O único
        # papel com tenant nulo é `platform_admin`, que não chega aqui —
        # `User.link_to_unit` levanta `PlatformAdminMembershipError` antes (domínio,
        # 2.1); e se chegasse, a coluna é `NOT NULL` sob FK composta. Estreitar o tipo
        # exigiria um `assert` reafirmando invariante que o domínio já garante.
        connection.execute(
            unit_memberships.insert(),
            [mappers.membership_to_row(v, user.tenant_id) for v in membership_list],  # type: ignore[arg-type]
        )

    def set_password_hash(self, user_id: UserId, password_hash: PasswordHash) -> None:
        """`UPDATE` do hash. `rowcount == 0` significa usuário inexistente.

        Usar o `rowcount` — e não um `SELECT` prévio — é o que torna a checagem e
        a escrita a mesma operação. Com o `SELECT` antes, o usuário poderia ser
        removido entre as duas, e o `UPDATE` afetaria zero linhas devolvendo
        sucesso: uma redefinição de senha que reporta "pronto" sem ter gravado
        nada.
        """
        with for_write(self._engine) as connection:
            result = connection.execute(
                users.update().where(users.c.id == user_id).values(password_hash=password_hash)
            )
            if result.rowcount == 0:
                raise UserNotFoundError(user_id)

    def _find_by_id(self, connection: Connection, user_id: UserId) -> User | None:
        # Colunas explícitas, sem `password_hash`: material de credencial que não é
        # carregado não vaza em log nem em traceback.
        row = connection.execute(
            select(users.c.id, users.c.email, users.c.role, users.c.tenant_id).where(
                users.c.id == user_id
            )
        ).one_or_none()
        return mappers.row_to_user(row) if row is not None else None
