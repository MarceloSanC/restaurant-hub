"""Adapter Postgres de `UserRepository`.

O repositório com mais regra da Stage. Três pontos merecem atenção:

**1. `add` é atômico de verdade.** Usuário, credencial e vínculos entram numa
única `engine.begin()`, como o docstring do port exige. Se qualquer parte falhar
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
    nome_da_constraint,
    traduzir,
)
from restaurant_hub.features.identity.adapters.out.postgres.tables import (
    unit_memberships,
    users,
)
from restaurant_hub.features.identity.application.dtos.credentials import UserCredentials
from restaurant_hub.features.identity.application.dtos.identifiers import PasswordHash
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
            with self._engine.begin() as conexao:
                self._add(conexao, user, password_hash, memberships)
        except IntegrityError as erro:
            # Qual valor entra na mensagem depende de QUAL regra foi violada: o
            # e-mail para o conflito de e-mail, o id para os demais. Uma mensagem
            # dizendo "e-mail já registrado: user-42" seria pior que nenhuma.
            detalhe = user.email.value if nome_da_constraint(erro) == "uq_users_email" else user.id
            raise traduzir(erro, detalhe) from erro

    def find_by_id(self, user_id: UserId) -> User | None:
        with self._engine.connect() as conexao:
            return self._find_by_id(conexao, user_id)

    def exists_by_email(self, email: Email) -> bool:
        """Unicidade é **global**, não escopada por tenant (kickoff #2).

        Por isso não há `WHERE tenant_id = ...` aqui: acrescentá-lo deixaria o
        mesmo login existir em dois restaurantes, e passaria em qualquer teste que
        só usasse um tenant.
        """
        with self._engine.connect() as conexao:
            achado = conexao.execute(
                select(users.c.id).where(users.c.email == email.value)
            ).one_or_none()
            return achado is not None

    def find_credentials_by_email(self, email: Email) -> UserCredentials | None:
        """Usuário + hash numa ida só — `authenticate_user` precisa dos dois."""
        with self._engine.connect() as conexao:
            linha = conexao.execute(select(users).where(users.c.email == email.value)).one_or_none()
            if linha is None:
                return None
            return UserCredentials(
                user=mappers.linha_para_usuario(linha),
                password_hash=PasswordHash(linha.password_hash),
            )

    def list_memberships(self, user_id: UserId) -> tuple[UnitMembership, ...]:
        with self._engine.connect() as conexao:
            linhas = conexao.execute(
                select(unit_memberships).where(unit_memberships.c.user_id == user_id)
            ).all()
            return tuple(mappers.linha_para_vinculo(linha) for linha in linhas)

    # ---- núcleo sobre `Connection` (ponto de troca para um futuro UoW) ----

    def _add(
        self,
        conexao: Connection,
        user: User,
        password_hash: PasswordHash,
        memberships: Sequence[UnitMembership],
    ) -> None:
        conexao.execute(users.insert().values(**mappers.usuario_para_linha(user, password_hash)))
        vinculos = list(memberships)
        if not vinculos:
            return
        # O `tenant_id` do vínculo vem do usuário dono, não do próprio
        # `UnitMembership` (que só carrega dois ids). As FKs compostas rejeitam a
        # linha se ele não bater com o tenant da unidade — é assim que vínculo
        # cross-tenant fica irrepresentável.
        conexao.execute(
            unit_memberships.insert(),
            [mappers.vinculo_para_linha(v, user.tenant_id) for v in vinculos],  # type: ignore[arg-type]
        )

    def _find_by_id(self, conexao: Connection, user_id: UserId) -> User | None:
        # Colunas explícitas, sem `password_hash`: material de credencial que não é
        # carregado não vaza em log nem em traceback.
        linha = conexao.execute(
            select(users.c.id, users.c.email, users.c.role, users.c.tenant_id).where(
                users.c.id == user_id
            )
        ).one_or_none()
        return mappers.linha_para_usuario(linha) if linha is not None else None
