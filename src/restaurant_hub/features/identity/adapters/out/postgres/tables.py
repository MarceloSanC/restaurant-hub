"""Schema PostgreSQL do bounded context identity, em SQLAlchemy 2 **Core**.

Core e não ORM declarativo (regra de stack do CLAUDE.md): as tabelas são dados,
não classes, e o mapeamento domínio↔linha é explícito em `mappers.py`. Isso
mantém as entidades da 2.1 livres de qualquer herança de framework — elas são
`frozen` e a persistência não tem como afrouxá-las por acidente.

**Este arquivo é a fonte única do schema.** O Alembic o consome via
`target_metadata` e os repositórios importam as tabelas daqui; não há uma segunda
descrição do schema em lugar nenhum.

Três coisas neste arquivo carregam invariante e não são estilo:

1. **Toda constraint tem nome explícito.** O adapter traduz `IntegrityError` em
   exceção de domínio identificando **qual** regra foi violada pelo nome da
   constraint (ADR 2.3.0002). Nome autogerado varia entre ambientes e faria a
   tradução falhar em produção sem falhar em teste.
2. **O discriminador de tenant só existe onde é dado de verdade.**
   `unit_memberships` o carrega `NOT NULL` com **duas** FKs compostas, porque é a
   única tabela em que ligação cross-tenant é representável. `sessions` **não** o
   carrega: o DTO `Session` não tem tenant, então a coluna seria inatingível pelo
   port e impossível para o fake — e, sendo o tenant de um `platform_admin` nulo,
   uma FK composta sobre ela seria MATCH SIMPLE e ficaria desligada justamente no
   caso privilegiado.
3. **`users.role` é `NOT NULL` e o `NOT NULL` é load-bearing.** Uma CHECK em
   Postgres só rejeita em `FALSE`; com `role` nulo, o predicado do iff avalia
   `NULL` e a linha **passa**. Sem o `NOT NULL`, a constraint de tenancy teria um
   buraco de lógica ternária.

O schema inteiro foi exercitado contra PostgreSQL 16 antes de ser aprovado — ver
o §9 do concept desta Stage para os resultados do probe.
"""

from sqlalchemy import (
    CheckConstraint,
    Column,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    MetaData,
    PrimaryKeyConstraint,
    Table,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import TIMESTAMP

from restaurant_hub.features.identity.application.dtos.setup_tokens import (
    SetupTokenPurpose,
)
from restaurant_hub.features.identity.domain.value_objects.role import Role

# `MetaData` próprio do BC (não global do projeto): cada bounded context descreve
# o seu schema, e um `MetaData` compartilhado faria o Alembic de um BC enxergar
# tabelas de outro.
identity_metadata = MetaData()

# Papéis aceitos pelo banco, derivados do enum de domínio em vez de repetidos à
# mão. Repetir a lista aqui criaria duas fontes de verdade que divergem no dia em
# que um papel novo entrar em `Role` — e a divergência só apareceria como
# `IntegrityError` em produção.
_ROLE_VALUES = tuple(role.value for role in Role)
_ROLE_IN_LIST = ", ".join(f"'{value}'" for value in _ROLE_VALUES)

# Mesma disciplina para o propósito do token: derivado do enum, não repetido à
# mão. Um propósito novo em `SetupTokenPurpose` sem entrada aqui viraria
# `IntegrityError` em produção, e só lá.
_PURPOSE_IN_LIST = ", ".join(f"'{purpose.value}'" for purpose in SetupTokenPurpose)

# Timestamps com fuso e precisão de microssegundo (a mesma do `datetime` do
# Python). Precisão reduzida truncaria silenciosamente e faria o round-trip
# devolver um instante diferente do gravado.
_TIMESTAMPTZ = TIMESTAMP(timezone=True)


restaurants = Table(
    "restaurants",
    identity_metadata,
    Column("id", Text, nullable=False),
    Column("name", Text, nullable=False),
    PrimaryKeyConstraint("id", name="pk_restaurants"),
)


units = Table(
    "units",
    identity_metadata,
    Column("id", Text, nullable=False),
    Column("restaurant_id", Text, nullable=False),
    Column("name", Text, nullable=False),
    PrimaryKeyConstraint("id", name="pk_units"),
    ForeignKeyConstraint(["restaurant_id"], ["restaurants.id"], name="fk_units_restaurant"),
    # Âncora **obrigatória**, não redundância: o Postgres exige índice único
    # cobrindo as colunas referenciadas por uma FK composta, e
    # `fk_memberships_unit` aponta para `(id, restaurant_id)`. Sem isto a
    # migration não roda.
    UniqueConstraint("id", "restaurant_id", name="uq_units_id_restaurant"),
)


users = Table(
    "users",
    identity_metadata,
    Column("id", Text, nullable=False),
    Column("email", Text, nullable=False),
    Column("role", Text, nullable=False),
    # Nulo **se e somente se** o papel for platform_admin — ver a CHECK abaixo.
    Column("tenant_id", Text, nullable=True),
    # Relação 1:1 obrigatória com a credencial, escrita na mesma transação que o
    # usuário (docstring de `UserRepository.add`). Tabela separada só compraria um
    # join e o risco de usuário sem credencial. `find_by_id` não seleciona esta
    # coluna.
    Column("password_hash", Text, nullable=False),
    PrimaryKeyConstraint("id", name="pk_users"),
    # Unicidade **global** de e-mail, sem tenant na chave (decisão de kickoff #2).
    # Um índice `(tenant_id, email)` passaria no uso comum e deixaria o mesmo
    # login existir em dois restaurantes.
    UniqueConstraint("email", name="uq_users_email"),
    # O VO `Email` normaliza (trim + lowercase) na construção, mas o Postgres
    # compara texto byte a byte: sem esta CHECK, `A@X.com` e `a@x.com` seriam duas
    # linhas aceitas que reidratam para o mesmo login. A constraint torna explícita
    # no banco a garantia que hoje só existe no domínio.
    CheckConstraint("email = lower(btrim(email))", name="ck_users_email_normalized"),
    CheckConstraint(f"role IN ({_ROLE_IN_LIST})", name="ck_users_role_known"),
    # O **iff** de tenancy (ADR 2.1.0002), não apenas "permite nulo".
    CheckConstraint(
        "(role = 'platform_admin') = (tenant_id IS NULL)",
        name="ck_users_tenant_iff_platform_admin",
    ),
    ForeignKeyConstraint(["tenant_id"], ["restaurants.id"], name="fk_users_tenant"),
    # Âncora da FK composta de `unit_memberships` — mesma obrigatoriedade da de
    # `units`.
    UniqueConstraint("id", "tenant_id", name="uq_users_id_tenant"),
)


unit_memberships = Table(
    "unit_memberships",
    identity_metadata,
    Column("user_id", Text, nullable=False),
    Column("unit_id", Text, nullable=False),
    # `NOT NULL` é o que mantém as FKs compostas **ativas**: uma FK composta em
    # Postgres é MATCH SIMPLE por default e é ignorada por inteiro quando qualquer
    # coluna referenciante é nula. Com a coluna nula, o "cerco" abaixo seria
    # decorativo.
    Column("tenant_id", Text, nullable=False),
    # Vínculo é **relação, não multiconjunto** (invariante #15 da 2.2).
    PrimaryKeyConstraint("user_id", "unit_id", name="pk_unit_memberships"),
    # As duas FKs juntas tornam vínculo cross-tenant **irrepresentável**: a
    # unidade tem de pertencer ao tenant declarado, e o usuário também. Só uma
    # delas deixaria o outro lado livre — que é metade do cerco e nenhuma
    # garantia.
    ForeignKeyConstraint(
        ["unit_id", "tenant_id"],
        ["units.id", "units.restaurant_id"],
        name="fk_memberships_unit",
    ),
    # Efeito colateral desejado: `platform_admin` tem `tenant_id` nulo e nenhuma
    # linha de `users` casa com um tenant não nulo para ele, então o banco passa a
    # impor o `PlatformAdminMembershipError` que só o domínio impunha.
    ForeignKeyConstraint(
        ["user_id", "tenant_id"],
        ["users.id", "users.tenant_id"],
        name="fk_memberships_user",
    ),
)


sessions = Table(
    "sessions",
    identity_metadata,
    Column("id", Text, nullable=False),
    Column("user_id", Text, ForeignKey("users.id", name="fk_sessions_user"), nullable=False),
    # Apenas o **fingerprint**, nunca o valor do refresh token (ADR 2.2.0001). Um
    # dump deste banco não devolve nenhum refresh utilizável — e é por isso que
    # não existe coluna capaz de guardar o valor.
    Column("refresh_token_fingerprint", Text, nullable=False),
    Column("issued_at", _TIMESTAMPTZ, nullable=False),
    Column("expires_at", _TIMESTAMPTZ, nullable=False),
    # Nulo enquanto a sessão nunca foi revogada. `revoke` preserva o instante da
    # PRIMEIRA revogação, que é o dado que a forense de reuso de token precisa.
    Column("revoked_at", _TIMESTAMPTZ, nullable=True),
    PrimaryKeyConstraint("id", name="pk_sessions"),
    # Único: `find_by_fingerprint` devolve **uma** sessão, e sem a unicidade o
    # adapter teria de escolher entre linhas empatadas — escolha que o fake
    # in-memory resolveria por ordem de inserção, criando divergência.
    UniqueConstraint("refresh_token_fingerprint", name="uq_sessions_fingerprint"),
    # `revoke_all_for_user` varre por usuário.
    Index("ix_sessions_user_id", "user_id"),
    # `purge_expired` varre por expiração — sem o índice, o expurgo é sequencial.
    Index("ix_sessions_expires_at", "expires_at"),
)


password_setup_tokens = Table(
    "password_setup_tokens",
    identity_metadata,
    Column("id", Text, nullable=False),
    Column(
        "user_id",
        Text,
        ForeignKey("users.id", name="fk_setup_tokens_user"),
        nullable=False,
    ),
    Column("purpose", Text, nullable=False),
    # Apenas o **fingerprint**, nunca o valor do token — mesma disciplina de
    # `sessions` (ADR 2.2.0001). Não existe coluna capaz de guardar o valor,
    # então um dump deste banco não devolve nenhum link de convite utilizável, e
    # a garantia é estrutural em vez de depender de disciplina de escrita.
    Column("token_fingerprint", Text, nullable=False),
    Column("issued_at", _TIMESTAMPTZ, nullable=False),
    Column("expires_at", _TIMESTAMPTZ, nullable=False),
    # Nulo enquanto o token nunca foi usado. É esta coluna que torna o uso único
    # verificável: `consume` faz `UPDATE ... WHERE consumed_at IS NULL`, e o
    # `rowcount` decide quem venceu a corrida entre duas redenções simultâneas.
    Column("consumed_at", _TIMESTAMPTZ, nullable=True),
    PrimaryKeyConstraint("id", name="pk_password_setup_tokens"),
    # Único: `find_by_fingerprint` devolve **um** token, e sem a unicidade o
    # adapter teria de escolher entre linhas empatadas — escolha que o fake
    # in-memory resolveria por ordem de inserção, criando divergência silenciosa.
    UniqueConstraint("token_fingerprint", name="uq_setup_tokens_fingerprint"),
    CheckConstraint(f"purpose IN ({_PURPOSE_IN_LIST})", name="ck_setup_tokens_purpose_known"),
    # `invalidate_all_for_user` varre por usuário.
    Index("ix_setup_tokens_user_id", "user_id"),
    # `purge_expired` varre por expiração — sem o índice, o expurgo é sequencial.
    Index("ix_setup_tokens_expires_at", "expires_at"),
)
