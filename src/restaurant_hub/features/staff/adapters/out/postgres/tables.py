"""Schema PostgreSQL do bounded context staff, em SQLAlchemy 2 **Core**.

Core e não ORM declarativo (regra de stack do CLAUDE.md): as tabelas são dados,
não classes, e o mapeamento domínio↔linha é explícito em `mappers.py`. As
entidades da 3.1 continuam `frozen` e livres de qualquer herança de framework —
a persistência não tem como afrouxá-las por acidente.

**Este arquivo é a fonte única do schema.** O Alembic o consome via
`target_metadata` e os repositórios importam as tabelas daqui; não há uma segunda
descrição do schema em lugar nenhum (a migration é registro histórico congelado,
não uma segunda fonte — ver o docstring de `migrations/versions/0002_*`).

Cinco coisas neste arquivo carregam invariante e não são estilo:

1. **Toda constraint tem nome explícito.** O adapter traduz `IntegrityError` em
   exceção de aplicação identificando **qual** regra foi violada pelo nome da
   constraint (ADR 3.3.0004). Nome autogerado varia entre ambientes e faria a
   tradução falhar em produção sem falhar em teste.
2. **O discriminador de tenant só existe onde ancora um cerco** (D2,
   ADR 3.3.0001). `employee_job_functions` o carrega `NOT NULL` com **duas** FKs
   compostas, porque é a única tabela em que ligação cross-tenant é
   representável (funcionário de A com função de B). `employee_unavailabilities`
   e `employee_shift_preferences` **não** o carregam: a única referência delas é
   o próprio `employee_id`, e uma coluna de tenant ali seria denormalização sem
   cerco a ancorar — a mesma razão pela qual `sessions` não a tem em identity.
3. **Nenhuma FK atravessa a fronteira do bounded context** (D1, ADR 3.3.0002).
   `tenant_id` e `unit_id` são `Text NOT NULL` **opacos**, sem FK para
   `restaurants`/`units` de identity. Uma FK física amarraria os dois BCs ao
   mesmo banco para sempre e faria a suíte de contrato de staff precisar semear
   identity para provar staff.
4. **`weekly_hours` é `NUMERIC` sem precisão declarada.** `FixedSchedule` aceita
   qualquer `Decimal` finito positivo, e uma `NUMERIC(5,2)` — a escolha
   "natural" para horas semanais — arredonda em silêncio (medido:
   `22.555 → 22.56`, `0.001 → 0.00`), corrompendo dado contra a disciplina
   verbatim do projeto. Tipo de coluna é contrato, não detalhe.
5. **Instantes são `TIMESTAMP` SEM fuso**, o oposto de identity, e a inversão é
   deliberada: `UnavailabilityPeriod` guarda wall-clock do fuso da unidade e
   **rejeita** tz-aware na construção (ADR 3.1.0005). Texto vai em `TEXT`, nunca
   `CHAR(n)` — o padding quebraria o round-trip verbatim de nome.

O schema inteiro foi exercitado contra PostgreSQL 16 antes de ser aprovado — ver
o §9 do concept desta Stage para os resultados do probe.
"""

from sqlalchemy import (
    TIMESTAMP,
    Boolean,
    CheckConstraint,
    Column,
    ForeignKeyConstraint,
    Index,
    MetaData,
    Numeric,
    PrimaryKeyConstraint,
    Table,
    Text,
    UniqueConstraint,
    true,
)

from restaurant_hub.features.staff.domain.value_objects.shift_preference import DayPeriod

# `MetaData` próprio do BC (não global do projeto): cada bounded context descreve
# o seu schema, e um `MetaData` compartilhado faria o Alembic de um BC enxergar
# tabelas de outro e propor drops indevidos no autogenerate. `migrations/env.py`
# **combina** os dois metadatas, como o comentário daquele arquivo instrui.
staff_metadata = MetaData()

# Discriminador persistido do perfil de jornada — as duas únicas variantes de
# `WorkloadProfile = FixedSchedule | OnDemand`.
#
# **Estas constantes são públicas de propósito, e a razão é que elas atravessam
# módulo.** Ao contrário dos períodos (logo abaixo), o discriminador **não tem de
# onde ser derivado**: a união é de dois dataclasses sem string discriminadora, e
# antes desta linha os literais `"fixed"`/`"on_demand"` só existiam na prosa do
# concept §9. É aqui que eles passam a existir em código, e é daqui que o
# `mappers.py` os consome nas duas direções (leitura e escrita) para escolher
# entre `FixedSchedule` e `OnDemand`. Repetir o literal lá recriaria a segunda
# fonte que esta constante existe para eliminar, e a divergência só apareceria
# como violação de `ck_employees_workload_kind_known` em produção.
#
# Um terceiro perfil em `WorkloadProfile` se acrescenta **aqui**, e a `CHECK`
# acompanha por construção.
WORKLOAD_KIND_FIXED = "fixed"
WORKLOAD_KIND_ON_DEMAND = "on_demand"
WORKLOAD_KINDS = (WORKLOAD_KIND_FIXED, WORKLOAD_KIND_ON_DEMAND)

_WORKLOAD_KIND_IN_LIST = ", ".join(f"'{kind}'" for kind in WORKLOAD_KINDS)

# Períodos aceitos pelo banco, **derivados** do enum de domínio em vez de
# repetidos à mão — precedente literal de `_ROLE_VALUES`/`_PURPOSE_IN_LIST` no
# `tables.py` de identity. Repetir a lista criaria duas fontes de verdade que
# divergem no dia em que um período novo entrar em `DayPeriod`, e a divergência
# só apareceria como `IntegrityError` em produção.
_PERIOD_VALUES = tuple(period.value for period in DayPeriod)
_PERIOD_IN_LIST = ", ".join(f"'{value}'" for value in _PERIOD_VALUES)

# Sem fuso: wall-clock do fuso da unidade (ADR 3.1.0005). Sem precisão
# declarada, que em Postgres é microssegundo — a mesma do `datetime` do Python;
# precisão reduzida truncaria em silêncio e o round-trip devolveria outro
# instante.
_NAIVE_TIMESTAMP = TIMESTAMP(timezone=False)


job_functions = Table(
    "job_functions",
    staff_metadata,
    Column("id", Text, nullable=False),
    # Opaco: o restaurante dono vive em identity e **não** é referenciado por FK
    # (ADR 3.3.0002).
    Column("tenant_id", Text, nullable=False),
    Column("name", Text, nullable=False),
    # Stage 3.11 — metade da habilitação por unidade (ADR 3.11.0001): verdadeiro =
    # a função vale em **toda** unidade do restaurante, presente e futura, e não há
    # linha em `job_function_units`. O `DEFAULT true` é o da migration `0005`: as
    # funções anteriores à Stage nascem em todas as unidades sem que staff leia as
    # unidades de identity. A coerência entre flag e vínculos (exatamente um dos dois) é
    # invariante do domínio (`UnitEnablement`), imposta na escrita pelo adapter e na
    # reidratação pelo `__post_init__` — nenhuma constraint a expressa entre tabelas.
    Column("enabled_in_all_units", Boolean, nullable=False, server_default=true()),
    # Colisão de id é **global** (L-JF1): a PK não inclui o tenant, e um índice
    # `(tenant_id, id)` no lugar dela aceitaria a inserção que o port recusa.
    PrimaryKeyConstraint("id", name="pk_job_functions"),
    # Unicidade de nome **verbatim e por tenant** (workforce §3.2; §5.6): sem
    # `lower()`, sem `btrim`. `'cozinheiro '` ao lado de `'Cozinheiro'` é aceito,
    # e foi medido no probe. Este índice também é o que serve `find_by_name` e
    # `list_by_tenant` — daí não haver um terceiro índice sobre `tenant_id`
    # (D5, ADR 3.3.0005).
    UniqueConstraint("tenant_id", "name", name="uq_job_functions_tenant_name"),
    # Âncora **obrigatória**, não redundância com a PK: o Postgres exige índice
    # único cobrindo exatamente as colunas referenciadas por uma FK composta, e
    # `fk_employee_job_functions_job_function` aponta para `(id, tenant_id)`.
    # Sem isto a migration não roda.
    UniqueConstraint("id", "tenant_id", name="uq_job_functions_id_tenant"),
)


# Stage 3.11 — a outra metade da habilitação: as unidades em que uma função **não**
# habilitada em todas vale (ADR 3.11.0001). Filha do agregado `JobFunction`, não
# referência a ele: some com a função (`CASCADE`), e o `RESTRICT` de
# `employee_job_functions` continua sendo quem guarda a remoção (L-JF3).
job_function_units = Table(
    "job_function_units",
    staff_metadata,
    Column("job_function_id", Text, nullable=False),
    # `NOT NULL` pela mesma razão de `employee_job_functions`: com a coluna nula a
    # FK composta MATCH SIMPLE seria ignorada, e o vínculo poderia apontar para
    # função de outro tenant.
    Column("tenant_id", Text, nullable=False),
    # Opaco: a unidade vive em identity, sem FK (ADR 3.3.0002).
    Column("unit_id", Text, nullable=False),
    # Conjunto, não multiconjunto: `UnitEnablement.unit_ids` é `frozenset`.
    PrimaryKeyConstraint("job_function_id", "unit_id", name="pk_job_function_units"),
    ForeignKeyConstraint(
        ["job_function_id", "tenant_id"],
        ["job_functions.id", "job_functions.tenant_id"],
        name="fk_job_function_units_job_function",
        ondelete="CASCADE",
    ),
    # Serve `list_by_unit` (L-JF6): "funções habilitadas nesta unidade do tenant".
    Index("ix_job_function_units_tenant_unit", "tenant_id", "unit_id"),
)


employees = Table(
    "employees",
    staff_metadata,
    Column("id", Text, nullable=False),
    # Os dois opacos, sem FK cross-BC (ADR 3.3.0002). A consistência
    # `unit_id` ↔ `tenant_id` é premissa da borda (concept §3), não desta camada.
    Column("tenant_id", Text, nullable=False),
    Column("unit_id", Text, nullable=False),
    Column("name", Text, nullable=False),
    # Discriminador da união `WorkloadProfile`. `NOT NULL` é load-bearing: uma
    # CHECK em Postgres só rejeita em `FALSE`, e com o discriminador nulo o
    # predicado do iff avaliaria `NULL` e a linha passaria.
    Column("workload_kind", Text, nullable=False),
    # `NUMERIC` **sem precisão** — ver a nota 4 do docstring do módulo. Anulável
    # porque `OnDemand` não carrega carga; o iff abaixo é o que amarra as duas
    # colunas.
    Column("weekly_hours", Numeric, nullable=True),
    Column("active", Boolean, nullable=False),
    # O login em identity vinculado ao registro (Stage 3.5, ADR 3.5.0004).
    # Opaco e **sem FK** para `users` — nenhuma FK atravessa BC (ADR 3.3.0002),
    # como `tenant_id` e `unit_id` acima. Anulável: login é opcional e explícito
    # por registro (workforce §3.8). **Sem UNIQUE**: `workforce.md` §3.7 admite
    # vários registros apontando para o mesmo `User` por vínculos explícitos.
    # **Sem índice**: nenhum acesso por `user_id` nesta Stage; índice acompanha
    # acesso medido (ADR 3.3.0005) e entra com `find_by_user_id` no Step 4.
    Column("user_id", Text, nullable=True),
    # Colisão de id é **global** (L-E1), pelo mesmo motivo de `job_functions`.
    PrimaryKeyConstraint("id", name="pk_employees"),
    # Âncora obrigatória da FK composta de `employee_job_functions`.
    UniqueConstraint("id", "tenant_id", name="uq_employees_id_tenant"),
    CheckConstraint(
        f"workload_kind IN ({_WORKLOAD_KIND_IN_LIST})",
        name="ck_employees_workload_kind_known",
    ),
    # O **iff** da jornada, não apenas "permite nulo": barra `fixed` sem horas
    # **e** `on_demand` com horas. Medido no probe — é o que impede a linha que
    # reidrataria para um `WorkloadProfile` impossível.
    CheckConstraint(
        f"(workload_kind = '{WORKLOAD_KIND_FIXED}') = (weekly_hours IS NOT NULL)",
        name="ck_employees_workload_iff_hours",
    ),
    # `FixedSchedule` exige carga positiva e finita; o banco impõe a metade que
    # sabe expressar. `IS NULL OR` mantém `on_demand` legal.
    CheckConstraint(
        "weekly_hours IS NULL OR weekly_hours > 0",
        name="ck_employees_weekly_hours_positive",
    ),
    # `list_by_unit` varre por `(tenant_id, unit_id)` — o acesso medido (D5).
    Index("ix_employees_tenant_unit", "tenant_id", "unit_id"),
)


employee_job_functions = Table(
    "employee_job_functions",
    staff_metadata,
    Column("employee_id", Text, nullable=False),
    Column("job_function_id", Text, nullable=False),
    # `NOT NULL` é o que mantém as duas FKs compostas **ativas**: FK composta em
    # Postgres é MATCH SIMPLE por default e fica ignorada por inteiro quando
    # qualquer coluna referenciante é nula. Com a coluna nula, o cerco abaixo
    # seria decorativo.
    Column("tenant_id", Text, nullable=False),
    # Vínculo é **relação, não multiconjunto**: `job_function_ids` é um
    # `frozenset` no agregado.
    PrimaryKeyConstraint("employee_id", "job_function_id", name="pk_employee_job_functions"),
    # As duas FKs juntas tornam vínculo cross-tenant **irrepresentável**: a
    # função tem de pertencer ao tenant declarado, e o funcionário também. Uma só
    # deixaria o outro lado livre — metade do cerco e nenhuma garantia
    # (ADR 3.3.0001).
    #
    # `CASCADE` no lado do funcionário: os filhos do agregado somem com o
    # agregado (§5.10).
    ForeignKeyConstraint(
        ["employee_id", "tenant_id"],
        ["employees.id", "employees.tenant_id"],
        name="fk_employee_job_functions_employee",
        ondelete="CASCADE",
    ),
    # `RESTRICT` no lado da função: é **esta** constraint que implementa a
    # remoção guardada de L-JF3, contando funcionário ativo **e** desligado (a
    # tabela de vínculo não conhece o estado). É também a constraint de dois
    # significados que o ADR 3.3.0004 traduz por operação.
    ForeignKeyConstraint(
        ["job_function_id", "tenant_id"],
        ["job_functions.id", "job_functions.tenant_id"],
        name="fk_employee_job_functions_job_function",
        ondelete="RESTRICT",
    ),
    # Não é otimização: sem ele o `RESTRICT` acima varre a tabela inteira a cada
    # remoção de função, e é também o índice de `exists_by_job_function` (L-E7).
    Index("ix_employee_job_functions_function", "job_function_id", "tenant_id"),
)


employee_unavailabilities = Table(
    "employee_unavailabilities",
    staff_metadata,
    Column("employee_id", Text, nullable=False),
    # Sem `tenant_id`: a única referência desta tabela é o próprio funcionário,
    # e não há ligação cross-tenant a cercar (D2).
    Column("start_at", _NAIVE_TIMESTAMP, nullable=False),
    Column("end_at", _NAIVE_TIMESTAMP, nullable=False),
    # `start_at` na PK: períodos do mesmo funcionário não se sobrepõem, logo o
    # início é único por registro — e é por isso que `ORDER BY start_at` é ordem
    # **total** na reidratação (`L-ORD`, ADR 3.3.0003).
    PrimaryKeyConstraint("employee_id", "start_at", name="pk_employee_unavailabilities"),
    ForeignKeyConstraint(
        ["employee_id"],
        ["employees.id"],
        name="fk_employee_unavailabilities_employee",
        ondelete="CASCADE",
    ),
    # Semi-aberto `[start, end)`: `start == end` é intervalo vazio e é recusado,
    # exatamente como `UnavailabilityPeriod.__post_init__` recusa.
    CheckConstraint("start_at < end_at", name="ck_employee_unavailabilities_period"),
)


employee_shift_preferences = Table(
    "employee_shift_preferences",
    staff_metadata,
    Column("employee_id", Text, nullable=False),
    Column("period", Text, nullable=False),
    # **Sem linha ⇒ `shift_preference = None`**; preferência declarada nunca é
    # vazia (ADR 3.1.0004), então "nenhuma linha" e "preferência vazia" não são
    # dois estados — são o mesmo, e é o único que o schema sabe representar.
    PrimaryKeyConstraint("employee_id", "period", name="pk_employee_shift_preferences"),
    ForeignKeyConstraint(
        ["employee_id"],
        ["employees.id"],
        name="fk_employee_shift_preferences_employee",
        ondelete="CASCADE",
    ),
    CheckConstraint(
        f"period IN ({_PERIOD_IN_LIST})",
        name="ck_employee_shift_preferences_period_known",
    ),
)
