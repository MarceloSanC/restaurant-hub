"""`PostgresUserRepository` contra PostgreSQL real — CA3-CA8, CA15.

Boa parte destes testes escreve por `INSERT` direto, sem passar pelo repositório.
É deliberado: o objetivo é provar que a **garantia está no banco**, e não apenas no
código Python que normalmente escreve nele. Uma invariante que só o domínio impõe
some no dia em que alguém rodar um script de migração de dados.
"""

from typing import NamedTuple

import pytest
from sqlalchemy import Engine, event, text
from sqlalchemy.exc import IntegrityError

from restaurant_hub.features.identity.adapters.out.postgres import mappers
from restaurant_hub.features.identity.adapters.out.postgres.restaurant_repository import (
    PostgresRestaurantRepository,
)
from restaurant_hub.features.identity.adapters.out.postgres.unit_repository import (
    PostgresUnitRepository,
)
from restaurant_hub.features.identity.adapters.out.postgres.user_repository import (
    PostgresUserRepository,
)
from restaurant_hub.features.identity.application.dtos.identifiers import PasswordHash
from restaurant_hub.features.identity.application.errors import (
    EmailAlreadyRegisteredError,
    UserAlreadyExistsError,
    UserNotFoundError,
)
from restaurant_hub.features.identity.domain.entities.restaurant import Restaurant
from restaurant_hub.features.identity.domain.entities.unit import Unit
from restaurant_hub.features.identity.domain.entities.user import User
from restaurant_hub.features.identity.domain.exceptions.errors import (
    InvalidIdentifierError,
    InvalidRoleError,
    MissingTenantError,
    PlatformAdminTenantError,
)
from restaurant_hub.features.identity.domain.value_objects.email import Email
from restaurant_hub.features.identity.domain.value_objects.identifiers import (
    RestaurantId,
    UnitId,
    UserId,
)
from restaurant_hub.features.identity.domain.value_objects.role import Role
from restaurant_hub.features.identity.domain.value_objects.unit_membership import (
    UnitMembership,
)

pytestmark = pytest.mark.integration

_HASH = PasswordHash("hashed::s3nha")


@pytest.fixture
def cenario(banco_limpo: Engine) -> Engine:
    """Dois tenants, cada um com uma unidade — a base do isolamento."""
    restaurantes = PostgresRestaurantRepository(banco_limpo)
    unidades = PostgresUnitRepository(banco_limpo)
    restaurantes.add(Restaurant(id=RestaurantId("rest-a"), name="Cantina A"))
    restaurantes.add(Restaurant(id=RestaurantId("rest-b"), name="Cantina B"))
    unidades.add(Unit(id=UnitId("unit-a1"), restaurant_id=RestaurantId("rest-a"), name="Centro"))
    unidades.add(Unit(id=UnitId("unit-b1"), restaurant_id=RestaurantId("rest-b"), name="Outra"))
    return banco_limpo


def _user(
    user_id: str = "user-1",
    email: str = "dono@x.com",
    tenant: str | None = "rest-a",
    role: Role = Role.OWNER,
) -> User:
    return User(
        id=UserId(user_id),
        email=Email(email),
        role=role,
        tenant_id=RestaurantId(tenant) if tenant is not None else None,
    )


# ---------------------------------------------------------------------------
# Round-trip e leitura
# ---------------------------------------------------------------------------


def test_usuario_faz_round_trip_campo_a_campo(cenario: Engine) -> None:
    repo = PostgresUserRepository(cenario)
    repo.add(_user(), _HASH)

    lido = repo.find_by_id(UserId("user-1"))

    assert lido is not None
    assert lido.id == "user-1"
    assert lido.email == Email("dono@x.com")
    assert lido.role is Role.OWNER
    assert lido.tenant_id == "rest-a"


def test_find_by_id_inexistente_devolve_none(cenario: Engine) -> None:
    """CA3."""
    assert PostgresUserRepository(cenario).find_by_id(UserId("fantasma")) is None


def test_find_credentials_devolve_usuario_e_hash_numa_ida(cenario: Engine) -> None:
    repo = PostgresUserRepository(cenario)
    repo.add(_user(), _HASH)

    credencial = repo.find_credentials_by_email(Email("dono@x.com"))

    assert credencial is not None
    assert credencial.user.id == "user-1"
    assert credencial.password_hash == _HASH


def test_find_credentials_de_email_inexistente_devolve_none(cenario: Engine) -> None:
    assert PostgresUserRepository(cenario).find_credentials_by_email(Email("ninguem@x.com")) is None


def test_platform_admin_faz_round_trip_com_tenant_nulo(cenario: Engine) -> None:
    repo = PostgresUserRepository(cenario)
    repo.add(_user("admin-1", "adm@x.com", tenant=None, role=Role.PLATFORM_ADMIN), _HASH)

    lido = repo.find_by_id(UserId("admin-1"))
    assert lido is not None
    assert lido.tenant_id is None
    assert lido.role is Role.PLATFORM_ADMIN


def test_find_by_id_nao_seleciona_o_password_hash(cenario: Engine) -> None:
    """O SQL emitido não pode mencionar `password_hash` — gate de regressão.

    O docstring do repositório promete que o hash "não vaza em log, traceback nem
    repr", e a promessa se sustenta em `find_by_id` listar as colunas
    explicitamente. Mas trocar esse `select(...)` por um `select(users)` não
    derrubava teste nenhum: `User` não tem campo de senha, então o hash a mais
    seria silenciosamente descartado pelo mapper — e continuaria aparecendo no
    log de SQL e no traceback de qualquer erro daquela query.

    Asserir sobre a entidade devolvida não pega isso. Só asserir sobre o **texto
    da query** pega, porque é exatamente aí que o dado vaza.
    """
    repo = PostgresUserRepository(cenario)
    repo.add(_user(), _HASH)

    queries: list[str] = []

    def capturar(
        conn: object, cursor: object, statement: str, *args: object, **kwargs: object
    ) -> None:
        queries.append(statement)

    event.listen(cenario, "before_cursor_execute", capturar)
    try:
        assert repo.find_by_id(UserId("user-1")) is not None
    finally:
        event.remove(cenario, "before_cursor_execute", capturar)

    assert queries, "nenhum SQL capturado — o listener não observou a query"
    assert not any("password_hash" in q for q in queries), (
        f"`find_by_id` mencionou password_hash no SQL: {queries}"
    )


# ---------------------------------------------------------------------------
# Unicidade de e-mail — I2 / CA5
# ---------------------------------------------------------------------------


def test_email_duplicado_em_outro_tenant_e_rejeitado(cenario: Engine) -> None:
    """CA5 — a unicidade é GLOBAL.

    Este é o teste que um índice `(tenant_id, email)` passaria: os dois usuários
    estão em tenants diferentes, e mesmo assim o segundo tem de ser recusado.
    """
    repo = PostgresUserRepository(cenario)
    repo.add(_user("user-1", "dono@x.com", tenant="rest-a"), _HASH)

    with pytest.raises(EmailAlreadyRegisteredError):
        repo.add(_user("user-2", "dono@x.com", tenant="rest-b"), _HASH)


def test_email_duplicado_ignorando_caixa_e_rejeitado(cenario: Engine) -> None:
    """O VO normaliza antes de o SQL ver, então a caixa não cria uma segunda conta."""
    repo = PostgresUserRepository(cenario)
    repo.add(_user("user-1", "dono@x.com"), _HASH)

    with pytest.raises(EmailAlreadyRegisteredError):
        repo.add(_user("user-2", "DONO@X.COM", tenant="rest-b"), _HASH)


def test_insert_direto_com_email_nao_normalizado_e_rejeitado(cenario: Engine) -> None:
    """A CHECK do banco cobre o caminho que não passa pelo VO.

    Sem `ck_users_email_normalized`, um script de migração poderia gravar
    `A@X.com` e `a@x.com` como duas linhas — que reidratam para o mesmo login,
    porque o VO normaliza na leitura. O índice único sozinho não pega isso: o
    Postgres compara texto byte a byte.
    """
    with pytest.raises(IntegrityError) as exc, cenario.begin() as conexao:
        conexao.execute(
            text(
                "INSERT INTO users (id, email, role, tenant_id, password_hash) "
                "VALUES ('u9', 'DONO@X.com', 'owner', 'rest-a', 'h')"
            )
        )
    assert "ck_users_email_normalized" in str(exc.value)


def test_usuario_duplicado_levanta_erro_de_id_e_nao_de_email(cenario: Engine) -> None:
    """CA6 — id duplicado não é conflito de e-mail.

    O e-mail é do próprio usuário; reportar `EmailAlreadyRegisteredError` faria a
    2.4 responder "e-mail já registrado" para uma requisição cujo e-mail está
    livre.
    """
    repo = PostgresUserRepository(cenario)
    repo.add(_user(), _HASH)

    with pytest.raises(UserAlreadyExistsError):
        repo.add(_user(), _HASH)


# ---------------------------------------------------------------------------
# Conteúdo do `detalhe` traduzido — I11 / CA20
# ---------------------------------------------------------------------------
#
# A classe do erro já é asserida acima. O que estes dois testes travam é o VALOR
# que entra na mensagem: o repositório escolhe entre `user.email.value` e
# `user.id` conforme a constraint violada, e sem asserção o ternário colapsa para
# um dos lados sem derrubar teste nenhum. A mensagem errada não quebra fluxo — ela
# apenas manda quem está diagnosticando procurar pelo valor que não está em
# conflito, que é o pior modo de falhar de uma mensagem de erro.


def test_detalhe_do_email_duplicado_traz_o_email_e_nao_o_id(cenario: Engine) -> None:
    """`uq_users_email` → o valor em conflito é o e-mail.

    O id de quem tentou gravar está livre; citá-lo ("e-mail já registrado:
    'user-2'") apontaria para o dado errado.
    """
    repo = PostgresUserRepository(cenario)
    repo.add(_user("user-1", "dono@x.com", tenant="rest-a"), _HASH)

    with pytest.raises(EmailAlreadyRegisteredError) as exc:
        repo.add(_user("user-2", "dono@x.com", tenant="rest-b"), _HASH)

    mensagem = str(exc.value)
    assert "dono@x.com" in mensagem, f"mensagem sem o e-mail em conflito: {mensagem!r}"
    assert "user-2" not in mensagem, f"mensagem citou o id, que não está em conflito: {mensagem!r}"


def test_detalhe_do_id_duplicado_traz_o_id_e_nao_o_email(cenario: Engine) -> None:
    """`pk_users` → o valor em conflito é o id.

    O e-mail do segundo `add` é outro e está livre, então uma mensagem que o
    citasse acusaria um dado que não tem problema nenhum.
    """
    repo = PostgresUserRepository(cenario)
    repo.add(_user("user-1", "dono@x.com", tenant="rest-a"), _HASH)

    with pytest.raises(UserAlreadyExistsError) as exc:
        repo.add(_user("user-1", "outro@x.com", tenant="rest-a"), _HASH)

    mensagem = str(exc.value)
    assert "user-1" in mensagem, f"mensagem sem o id em conflito: {mensagem!r}"
    assert "outro@x.com" not in mensagem, (
        f"mensagem citou o e-mail, que não está em conflito: {mensagem!r}"
    )


# ---------------------------------------------------------------------------
# Tenancy imposta pelo banco — I3 / CA7
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("descricao", "sql"),
    [
        (
            "platform_admin COM tenant",
            "INSERT INTO users (id, email, role, tenant_id, password_hash) "
            "VALUES ('u1', 'a@x.com', 'platform_admin', 'rest-a', 'h')",
        ),
        (
            "papel de restaurante SEM tenant",
            "INSERT INTO users (id, email, role, tenant_id, password_hash) "
            "VALUES ('u2', 'b@x.com', 'owner', NULL, 'h')",
        ),
        (
            "role nulo (buraco de lógica ternária, barrado pelo NOT NULL)",
            "INSERT INTO users (id, email, role, tenant_id, password_hash) "
            "VALUES ('u3', 'c@x.com', NULL, 'rest-a', 'h')",
        ),
        (
            "role fora do conjunto fechado",
            "INSERT INTO users (id, email, role, tenant_id, password_hash) "
            "VALUES ('u4', 'd@x.com', 'wizard', 'rest-a', 'h')",
        ),
    ],
)
def test_banco_rejeita_violacao_de_tenancy(cenario: Engine, descricao: str, sql: str) -> None:
    """CA7 — o iff está no banco, não só no domínio.

    O caso do `role` nulo é o que justifica o `NOT NULL`: uma CHECK em Postgres só
    rejeita em `FALSE`, então sem ele o predicado do iff avaliaria `NULL` e a linha
    passaria.
    """
    with pytest.raises(IntegrityError), cenario.begin() as conexao:
        conexao.execute(text(sql))


def test_banco_aceita_platform_admin_sem_tenant(cenario: Engine) -> None:
    """O outro lado do iff: o nulo é permitido exatamente para esse papel."""
    with cenario.begin() as conexao:
        conexao.execute(
            text(
                "INSERT INTO users (id, email, role, tenant_id, password_hash) "
                "VALUES ('adm', 'adm@x.com', 'platform_admin', NULL, 'h')"
            )
        )
    lido = PostgresUserRepository(cenario).find_by_id(UserId("adm"))
    assert lido is not None and lido.tenant_id is None


# ---------------------------------------------------------------------------
# Vínculos e isolamento — I4 / CA8
# ---------------------------------------------------------------------------


def test_vinculos_sao_gravados_na_mesma_transacao(cenario: Engine) -> None:
    repo = PostgresUserRepository(cenario)
    user = _user()

    repo.add(user, _HASH, [UnitMembership(user_id=user.id, unit_id=UnitId("unit-a1"))])

    assert repo.list_memberships(user.id) == (
        UnitMembership(user_id=UserId("user-1"), unit_id=UnitId("unit-a1")),
    )


def test_add_e_atomico_quando_um_vinculo_falha(cenario: Engine) -> None:
    """CA4 — falha no meio não deixa usuário nem credencial gravados.

    O vínculo aponta para unidade inexistente, então a FK estoura **depois** de o
    usuário já ter sido inserido na mesma transação. Se `add` não fosse atômico,
    sobraria um usuário sem vínculo — e, no caso geral, um usuário sem credencial,
    que é exatamente o cenário que o port existe para impedir.
    """
    repo = PostgresUserRepository(cenario)
    PostgresUnitRepository(cenario).add(
        Unit(id=UnitId("unit-a2"), restaurant_id=RestaurantId("rest-a"), name="Praia")
    )
    user = _user()

    # O TERCEIRO elemento é o inválido (concept §11 CA4). Com um só vínculo, o
    # `executemany` teria uma linha e o teste provaria apenas "a linha do usuário
    # reverteu" — não o caso que importa: dois vínculos já inseridos precisam
    # sumir junto com o terceiro rejeitado.
    vinculos = [
        UnitMembership(user_id=user.id, unit_id=UnitId("unit-a1")),
        UnitMembership(user_id=user.id, unit_id=UnitId("unit-a2")),
        UnitMembership(user_id=user.id, unit_id=UnitId("fantasma")),
    ]

    with pytest.raises(IntegrityError):
        repo.add(user, _HASH, vinculos)

    assert repo.find_by_id(user.id) is None
    assert repo.find_credentials_by_email(Email("dono@x.com")) is None
    with cenario.connect() as conexao:
        total = conexao.execute(text("SELECT count(*) FROM unit_memberships")).scalar_one()
    assert total == 0


def test_vinculo_cross_tenant_e_irrepresentavel(cenario: Engine) -> None:
    """CA8 — o usuário é do tenant A e a unidade do tenant B.

    As duas FKs compostas fecham o cerco: qualquer `tenant_id` que se escolha para
    a linha desagrada uma delas. É o que torna o vínculo cross-tenant
    **irrepresentável**, e não apenas recusado pelo domínio.
    """
    repo = PostgresUserRepository(cenario)
    user = _user(tenant="rest-a")
    repo.add(user, _HASH)

    for tenant_da_linha in ("rest-a", "rest-b"):
        with pytest.raises(IntegrityError), cenario.begin() as conexao:
            conexao.execute(
                text(
                    "INSERT INTO unit_memberships (user_id, unit_id, tenant_id) "
                    f"VALUES ('user-1', 'unit-b1', '{tenant_da_linha}')"
                )
            )


def test_vinculo_de_platform_admin_e_irrepresentavel(cenario: Engine) -> None:
    """O banco passa a impor o `PlatformAdminMembershipError` do domínio.

    `platform_admin` tem `tenant_id` nulo e `unit_memberships.tenant_id` é NOT
    NULL, então nenhuma linha de `users` casa com a FK composta — sem precisar de
    regra nova, cai do desenho.
    """
    repo = PostgresUserRepository(cenario)
    repo.add(_user("adm", "adm@x.com", tenant=None, role=Role.PLATFORM_ADMIN), _HASH)

    with pytest.raises(IntegrityError), cenario.begin() as conexao:
        conexao.execute(
            text(
                "INSERT INTO unit_memberships (user_id, unit_id, tenant_id) "
                "VALUES ('adm', 'unit-a1', 'rest-a')"
            )
        )


def test_list_memberships_nao_devolve_vinculo_de_outro_usuario(cenario: Engine) -> None:
    """O filtro por `user_id` é conforme — mas a visibilidade não depende dele.

    A 2.2 permite explicitamente um adapter permissivo aqui (quem casa usuário e
    unidade é `User.can_view_unit`). O teste fixa o comportamento **deste**
    adapter, não uma garantia de segurança.
    """
    repo = PostgresUserRepository(cenario)
    a = _user("user-a", "a@x.com", tenant="rest-a")
    b = _user("user-b", "b@x.com", tenant="rest-a")
    repo.add(a, _HASH, [UnitMembership(user_id=a.id, unit_id=UnitId("unit-a1"))])
    repo.add(b, _HASH, [UnitMembership(user_id=b.id, unit_id=UnitId("unit-a1"))])

    assert repo.list_memberships(a.id) == (
        UnitMembership(user_id=UserId("user-a"), unit_id=UnitId("unit-a1")),
    )


def test_list_memberships_sem_vinculo_devolve_tupla_vazia(cenario: Engine) -> None:
    repo = PostgresUserRepository(cenario)
    repo.add(_user(), _HASH)
    assert repo.list_memberships(UserId("user-1")) == ()


# ---------------------------------------------------------------------------
# exists_by_email
# ---------------------------------------------------------------------------


def test_exists_by_email_e_global(cenario: Engine) -> None:
    repo = PostgresUserRepository(cenario)
    repo.add(_user("user-1", "dono@x.com", tenant="rest-a"), _HASH)

    assert repo.exists_by_email(Email("dono@x.com")) is True
    assert repo.exists_by_email(Email("DONO@X.COM")) is True
    assert repo.exists_by_email(Email("ninguem@x.com")) is False


# ---------------------------------------------------------------------------
# Reidratação pelo construtor contra linha corrompida — I1 / CA15
# ---------------------------------------------------------------------------


class _Corrompida(NamedTuple):
    """Um cenário de linha inválida de §6, e a exceção que a leitura deve levantar.

    `constraints` são as CHECKs a dropar para que o `INSERT` caiba; `tenant_sql` vai
    inline (e não como bind) porque `NULL` não é um valor de parâmetro aqui — é a
    ausência dele que caracteriza o cenário.
    """

    constraints: tuple[str, ...]
    user_id: str
    role: str
    tenant_sql: str
    esperada: type[Exception]


@pytest.mark.parametrize(
    "caso",
    [
        pytest.param(
            _Corrompida(
                ("ck_users_role_known",), "corrompido", "wizard", "'rest-a'", InvalidRoleError
            ),
            id="papel-fora-do-conjunto-fechado",
        ),
        pytest.param(
            _Corrompida((), "   ", "owner", "'rest-a'", InvalidIdentifierError),
            id="id-vazio",
        ),
        pytest.param(
            _Corrompida(
                ("ck_users_tenant_iff_platform_admin",),
                "corrompido",
                "platform_admin",
                "'rest-a'",
                PlatformAdminTenantError,
            ),
            id="platform-admin-com-tenant",
        ),
        pytest.param(
            _Corrompida(
                ("ck_users_tenant_iff_platform_admin",),
                "corrompido",
                "owner",
                "NULL",
                MissingTenantError,
            ),
            id="papel-de-restaurante-sem-tenant",
        ),
    ],
)
def test_linha_corrompida_levanta_ao_ser_lida(cenario: Engine, caso: _Corrompida) -> None:
    """CA15 contra o banco real, driblando a CHECK para simular corrupção.

    As CHECKs impedem criar a linha inconsistente pelo caminho normal, então o
    teste as desabilita temporariamente para provar a **segunda** linha de defesa:
    mesmo que uma linha inválida exista (migração manual, restore de backup antigo,
    bug de outra Stage), a leitura levanta em vez de devolver um `User` inválido que
    o resto do sistema trataria como legítimo.

    Os quatro cenários de §6 rodam aqui, e não só no unit do mapper, porque o CA15
    é literal sobre isso: as exceções precisam ser exercitadas por `INSERT` direto.
    O unit prova que o mapper valida; só o `INSERT` prova que a linha corrompida
    **cabe** no banco — isto é, que a defesa do construtor não é redundante com a
    do schema. O caso de `id` vazio não dropa constraint nenhuma justamente porque
    o schema não tem CHECK de id não-vazio: ali o construtor é a ÚNICA defesa, e o
    `INSERT` limpo é a evidência disso.
    """
    # A corrupção vive dentro de UMA transação que termina em rollback. A versão
    # anterior deste teste dropava a constraint, commitava e a recriava num
    # `finally` — e o `engine` é de escopo de sessão sobre um banco persistente,
    # então um Ctrl-C dentro dessa janela deixava a constraint permanentemente
    # ausente no banco de dev. Aqui, qualquer interrupção reverte sozinha.
    with cenario.connect() as conexao:
        transacao = conexao.begin()
        try:
            for constraint in caso.constraints:
                conexao.execute(text(f"ALTER TABLE users DROP CONSTRAINT {constraint}"))
            conexao.execute(
                text(
                    "INSERT INTO users (id, email, role, tenant_id, password_hash) "
                    f"VALUES (:id, 'x@x.com', :role, {caso.tenant_sql}, 'h')"
                ),
                {"id": caso.user_id, "role": caso.role},
            )

            # A leitura acontece na MESMA transação, única onde a linha inválida
            # existe — o repositório recebe essa conexão via um Engine efêmero.
            linha = conexao.execute(
                text("SELECT id, email, role, tenant_id FROM users WHERE id = :id"),
                {"id": caso.user_id},
            ).one()

            with pytest.raises(caso.esperada):
                mappers.linha_para_usuario(linha)
        finally:
            transacao.rollback()


@pytest.mark.parametrize(
    ("role", "tenant_sql"),
    [
        pytest.param("platform_admin", "'rest-a'", id="ck-tenant-iff-platform-admin"),
        pytest.param("wizard", "'rest-a'", id="ck-role-known"),
    ],
)
def test_rollback_devolve_as_constraints_dropadas(
    cenario: Engine, role: str, tenant_sql: str
) -> None:
    """As CHECKs que o teste acima dropa voltam sozinhas — é o rollback que garante.

    Sem esta asserção, um `DROP CONSTRAINT` que vazasse da transação deixaria o
    banco de dev permanentemente frouxo e os testes seguintes passariam por engano,
    testando um schema que não é o de produção.
    """
    with pytest.raises(IntegrityError), cenario.begin() as conexao:
        conexao.execute(
            text(
                "INSERT INTO users (id, email, role, tenant_id, password_hash) "
                f"VALUES ('outro', 'y@x.com', :role, {tenant_sql}, 'h')"
            ),
            {"role": role},
        )


# ---------------------------------------------------------------------------
# set_password_hash — Stage 2.5
# ---------------------------------------------------------------------------


def test_set_password_hash_grava_o_hash_novo(cenario: Engine) -> None:
    repo = PostgresUserRepository(cenario)
    repo.add(_user(), _HASH)
    novo = PasswordHash("hashed::nova-senha")

    repo.set_password_hash(UserId("user-1"), novo)

    credenciais = repo.find_credentials_by_email(Email("dono@x.com"))
    assert credenciais is not None
    assert credenciais.password_hash == novo


def test_set_password_hash_nao_altera_identidade(cenario: Engine) -> None:
    """Redefinir a senha não redefine quem a pessoa é.

    E-mail, papel e tenant são os três campos por onde uma escalada passaria se o
    `UPDATE` fosse escrito com `values(**linha)` em vez de só o hash.
    """
    repo = PostgresUserRepository(cenario)
    repo.add(_user(), _HASH)

    repo.set_password_hash(UserId("user-1"), PasswordHash("hashed::outra"))

    lido = repo.find_by_id(UserId("user-1"))
    assert lido is not None
    assert lido.email == Email("dono@x.com")
    assert lido.role is Role.OWNER
    assert lido.tenant_id == "rest-a"


def test_set_password_hash_de_usuario_inexistente_levanta(cenario: Engine) -> None:
    repo = PostgresUserRepository(cenario)

    with pytest.raises(UserNotFoundError):
        repo.set_password_hash(UserId("nao-existe"), PasswordHash("hashed::x"))


def test_set_password_hash_de_usuario_inexistente_nao_cria_linha(cenario: Engine) -> None:
    """É `UPDATE`, não upsert.

    Este método é alcançado por uma rota **pública**, a partir de um token de
    e-mail. Um upsert transformaria um token com `user_id` órfão numa conta nova,
    sem e-mail, sem papel e sem tenant — que as CHECKs de tenancy nem aceitariam,
    mas que não deve sequer ser tentado.
    """
    repo = PostgresUserRepository(cenario)

    with pytest.raises(UserNotFoundError):
        repo.set_password_hash(UserId("fantasma"), PasswordHash("hashed::x"))

    assert repo.find_by_id(UserId("fantasma")) is None


def test_set_password_hash_nao_afeta_outro_usuario(cenario: Engine) -> None:
    repo = PostgresUserRepository(cenario)
    repo.add(_user("user-1", "a@x.com"), _HASH)
    repo.add(_user("user-2", "b@x.com"), _HASH)

    repo.set_password_hash(UserId("user-1"), PasswordHash("hashed::so-do-um"))

    outro = repo.find_credentials_by_email(Email("b@x.com"))
    assert outro is not None
    assert outro.password_hash == _HASH
