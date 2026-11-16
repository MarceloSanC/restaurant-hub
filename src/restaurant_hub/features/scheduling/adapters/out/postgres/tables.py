"""Schema PostgreSQL do bounded context scheduling, em SQLAlchemy 2 **Core**.

**Este arquivo é a fonte única do schema** (ADR 4.4.0001). O Alembic o consome via
`target_metadata`, os repositórios importam as tabelas daqui, e a migration
`0006_scheduling` é o seu registro congelado.

Seis tabelas: o agregado em quatro (`schedules` → `schedule_bands` →
`schedule_demands` → `schedule_assignments`), a trilha (`schedule_changes`) e a
configuração do tenant (`scheduling_settings`). O que nelas carrega lei:

1. **Toda constraint tem nome explícito.** O adapter traduz `IntegrityError` pelo nome
   (ADR 3.3.0004), e nome autogerado varia entre ambientes.
2. **Ids internos são únicos por (tenant, unidade)** (ADR 4.3.0004 §1): a PK de cada
   tabela filha é `(tenant_id, unit_id, id)`. O id da escala é único **no banco
   inteiro** (lei L-SC1): `pk_schedules` não inclui o tenant.
3. **O cerco.** Toda filha carrega `tenant_id`, `unit_id` e `schedule_id` e referencia o
   pai por FK composta que os inclui: demanda de uma escala presa à faixa de outra é
   irrepresentável. As FKs são `CASCADE` — as filhas somem com o agregado.
4. **Dias disjuntos por unidade** (lei L-SC2): exclusion constraint sobre
   `daterange(first_day, first_day + days)`, que é `[)` e cobre exatamente os `days`
   dias. Exige a extensão `btree_gist`, criada pela migration.
5. **Nenhuma FK atravessa o bounded context** (ADR 3.3.0002): `tenant_id`, `unit_id`,
   `employee_id`, `job_function_id` e `author_user_id` são `TEXT` opacos.
6. **Dois regimes de tempo.** Faixas em `TIMESTAMP` **sem** fuso (wall-clock da
   unidade, ADR 4.1.0007); o carimbo da trilha em `TIMESTAMP WITH TIME ZONE`.
7. **A trilha é só de inserção** (ADR 4.4.0002) e a sua FK é `RESTRICT`: apagar uma
   escala exige decidir o destino da trilha dela.
8. **`scheduling_settings` é sempre uma configuração completa**: toda coluna é
   `NOT NULL`, sem default de servidor — o port não inventa default (lei L-CF1).

As regras internas do agregado que só o conjunto vê (par `(início, fim)` distinto entre
faixas, uma demanda por função na faixa, um registro por faixa) **não** viram
constraint: o domínio as impõe na escrita e de novo na reidratação, que passa pelos
construtores.
"""

import dataclasses
from typing import Any

from sqlalchemy import (
    TIMESTAMP,
    Boolean,
    CheckConstraint,
    Column,
    Date,
    ForeignKeyConstraint,
    Index,
    Integer,
    MetaData,
    PrimaryKeyConstraint,
    Table,
    Text,
    Time,
    UniqueConstraint,
    literal_column,
)
from sqlalchemy.dialects.postgresql import JSONB, ExcludeConstraint

from restaurant_hub.features.scheduling.domain.value_objects.operational_calendar import (
    Weekday,
)
from restaurant_hub.features.scheduling.domain.value_objects.validation_config import (
    EnforcementMode,
    PolicyRule,
    ValidationConfig,
    WorkloadDirection,
)

# `MetaData` próprio do BC, somado aos outros em `migrations/env.py`.
scheduling_metadata = MetaData()

# Sem fuso: wall-clock do fuso da unidade (ADR 4.1.0007).
_NAIVE_TIMESTAMP = TIMESTAMP(timezone=False)
# Com fuso: o carimbo da trilha é instante absoluto (ADR 4.4.0002).
_TIMESTAMPTZ = TIMESTAMP(timezone=True)
_NAIVE_TIME = Time(timezone=False)


def _in_list(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


# Conjuntos fechados **derivados** do domínio, nunca repetidos à mão: um valor novo no
# enum chega à `CHECK` por construção.
_WEEKDAYS_IN_LIST = _in_list(tuple(weekday.value for weekday in Weekday))
_MODES_IN_LIST = _in_list(tuple(mode.value for mode in EnforcementMode))
_DIRECTIONS_IN_LIST = _in_list(tuple(direction.value for direction in WorkloadDirection))

# As políticas configuráveis, na ordem dos campos de `ValidationConfig`. Cada uma vira um
# par de colunas `<política>_enabled`/`<política>_mode`. Pública: o mapper lê as colunas
# por esta tupla, para que tabela e mapper não tenham duas listas.
POLICY_FIELDS: tuple[str, ...] = tuple(
    config_field.name
    for config_field in dataclasses.fields(ValidationConfig)
    if config_field.type is PolicyRule
)

# Os quatro limites em minutos e a faixa de cada um, como `ValidationConfig` a impõe.
LIMIT_CHECKS: tuple[tuple[str, str], ...] = (
    ("min_rest_minutes", ">= 0"),
    ("daily_cap_minutes", "> 0"),
    ("weekly_cap_minutes", "> 0"),
    ("workload_tolerance_minutes", ">= 0"),
)

# A faixa de `SchedulePeriod.days`.
_MIN_DAYS, _MAX_DAYS = 1, 31

# Nomes que o tradutor de integridade e os testes citam.
PK_SCHEDULES = "pk_schedules"
EX_SCHEDULES_UNIT_DAYS_DISJOINT = "ex_schedules_unit_days_disjoint"


schedules = Table(
    "schedules",
    scheduling_metadata,
    Column("id", Text, nullable=False),
    Column("tenant_id", Text, nullable=False),
    Column("unit_id", Text, nullable=False),
    Column("first_day", Date, nullable=False),
    Column("days", Integer, nullable=False),
    # O calendário fotografado na criação (ADR 4.1.0009).
    Column("week_start", Text, nullable=False),
    Column("day_cutoff", _NAIVE_TIME, nullable=False),
    Column("version", Integer, nullable=False),
    # Colisão de id é **global** (lei L-SC1).
    PrimaryKeyConstraint("id", name=PK_SCHEDULES),
    # Âncora obrigatória das FKs compostas das faixas.
    UniqueConstraint("tenant_id", "unit_id", "id", name="uq_schedules_tenant_unit_id"),
    # Lei L-SC2. `NOT NULL` nas duas colunas da faixa é load-bearing: limite nulo
    # produziria faixa infinita.
    ExcludeConstraint(
        ("tenant_id", "="),
        ("unit_id", "="),
        (literal_column("daterange(first_day, first_day + days)"), "&&"),
        name=EX_SCHEDULES_UNIT_DAYS_DISJOINT,
        using="gist",
    ),
    CheckConstraint(f"days BETWEEN {_MIN_DAYS} AND {_MAX_DAYS}", name="ck_schedules_days_range"),
    CheckConstraint("version >= 1", name="ck_schedules_version_positive"),
    CheckConstraint(f"week_start IN ({_WEEKDAYS_IN_LIST})", name="ck_schedules_week_start_known"),
    # O acesso das três leituras: endereço (tenant, unidade) e ordem por primeiro dia.
    Index("ix_schedules_tenant_unit_first_day", "tenant_id", "unit_id", "first_day"),
)


schedule_bands = Table(
    "schedule_bands",
    scheduling_metadata,
    Column("tenant_id", Text, nullable=False),
    Column("unit_id", Text, nullable=False),
    Column("id", Text, nullable=False),
    Column("schedule_id", Text, nullable=False),
    # A posição na tupla `Schedule.bands` — a ordem é parte da fidelidade (lei L-SC8).
    Column("position", Integer, nullable=False),
    Column("start_at", _NAIVE_TIMESTAMP, nullable=False),
    Column("end_at", _NAIVE_TIMESTAMP, nullable=False),
    Column("break_minutes", Integer, nullable=False),
    PrimaryKeyConstraint("tenant_id", "unit_id", "id", name="pk_schedule_bands"),
    # Âncora da FK das demandas; também serve a leitura das faixas de uma escala.
    UniqueConstraint(
        "tenant_id", "unit_id", "schedule_id", "id", name="uq_schedule_bands_schedule_id"
    ),
    ForeignKeyConstraint(
        ["tenant_id", "unit_id", "schedule_id"],
        ["schedules.tenant_id", "schedules.unit_id", "schedules.id"],
        name="fk_schedule_bands_schedule",
        ondelete="CASCADE",
    ),
    CheckConstraint("start_at < end_at", name="ck_schedule_bands_period"),
    CheckConstraint("break_minutes >= 0", name="ck_schedule_bands_break_non_negative"),
)


schedule_demands = Table(
    "schedule_demands",
    scheduling_metadata,
    Column("tenant_id", Text, nullable=False),
    Column("unit_id", Text, nullable=False),
    Column("id", Text, nullable=False),
    Column("schedule_id", Text, nullable=False),
    Column("band_id", Text, nullable=False),
    Column("position", Integer, nullable=False),
    # Opaco: a função vive em staff (ADR 3.3.0002).
    Column("job_function_id", Text, nullable=False),
    Column("quantity", Integer, nullable=False),
    PrimaryKeyConstraint("tenant_id", "unit_id", "id", name="pk_schedule_demands"),
    UniqueConstraint(
        "tenant_id", "unit_id", "schedule_id", "id", name="uq_schedule_demands_schedule_id"
    ),
    ForeignKeyConstraint(
        ["tenant_id", "unit_id", "schedule_id", "band_id"],
        [
            "schedule_bands.tenant_id",
            "schedule_bands.unit_id",
            "schedule_bands.schedule_id",
            "schedule_bands.id",
        ],
        name="fk_schedule_demands_band",
        ondelete="CASCADE",
    ),
    CheckConstraint("quantity >= 0", name="ck_schedule_demands_quantity_non_negative"),
)


schedule_assignments = Table(
    "schedule_assignments",
    scheduling_metadata,
    Column("tenant_id", Text, nullable=False),
    Column("unit_id", Text, nullable=False),
    Column("id", Text, nullable=False),
    Column("schedule_id", Text, nullable=False),
    Column("demand_id", Text, nullable=False),
    Column("position", Integer, nullable=False),
    # Opaco: o registro vive em staff, sem FK (ADR 4.1.0006 §3).
    Column("employee_id", Text, nullable=False),
    Column("counts_toward_workload", Boolean, nullable=False),
    Column("function_exception", Boolean, nullable=False),
    # `NULL` = herda o intervalo da faixa; `0` = intervalo próprio de zero. São dois
    # estados (ADR 4.1.0011).
    Column("break_minutes", Integer, nullable=True),
    PrimaryKeyConstraint("tenant_id", "unit_id", "id", name="pk_schedule_assignments"),
    ForeignKeyConstraint(
        ["tenant_id", "unit_id", "schedule_id", "demand_id"],
        [
            "schedule_demands.tenant_id",
            "schedule_demands.unit_id",
            "schedule_demands.schedule_id",
            "schedule_demands.id",
        ],
        name="fk_schedule_assignments_demand",
        ondelete="CASCADE",
    ),
    CheckConstraint(
        "break_minutes IS NULL OR break_minutes >= 0",
        name="ck_schedule_assignments_break_non_negative",
    ),
    # Não é otimização: é o índice das colunas da FK. Sem ele, o `CASCADE` de cada
    # demanda apagada — toda reescrita de filhas no `save` — varre a tabela inteira; é
    # também o acesso da leitura das alocações de uma escala.
    Index(
        "ix_schedule_assignments_demand",
        "tenant_id",
        "unit_id",
        "schedule_id",
        "demand_id",
    ),
)


schedule_changes = Table(
    "schedule_changes",
    scheduling_metadata,
    Column("schedule_id", Text, nullable=False),
    # Ordinal da mudança na escala: 1 na criação, depois 2, 3…
    Column("seq", Integer, nullable=False),
    # Opaco: o login vive em identity.
    Column("author_user_id", Text, nullable=False),
    Column("occurred_at", _TIMESTAMPTZ, nullable=False),
    # `NULL` na criação.
    Column("previous_version", Integer, nullable=True),
    Column("resulting_version", Integer, nullable=False),
    Column("operations", JSONB, nullable=False),
    Column("acknowledged", JSONB, nullable=False),
    PrimaryKeyConstraint("schedule_id", "seq", name="pk_schedule_changes"),
    ForeignKeyConstraint(
        ["schedule_id"],
        ["schedules.id"],
        name="fk_schedule_changes_schedule",
        ondelete="RESTRICT",
    ),
    CheckConstraint("seq >= 1", name="ck_schedule_changes_seq_positive"),
    CheckConstraint(
        "jsonb_typeof(operations) = 'array'", name="ck_schedule_changes_operations_is_array"
    ),
    CheckConstraint(
        "jsonb_typeof(acknowledged) = 'array'", name="ck_schedule_changes_acknowledged_is_array"
    ),
)


def _policy_columns() -> list[Column[Any]]:
    columns: list[Column[Any]] = []
    for policy in POLICY_FIELDS:
        columns.append(Column(f"{policy}_enabled", Boolean, nullable=False))
        columns.append(Column(f"{policy}_mode", Text, nullable=False))
    return columns


def _policy_checks() -> list[CheckConstraint]:
    return [
        CheckConstraint(
            f"{policy}_mode IN ({_MODES_IN_LIST})",
            name=f"ck_scheduling_settings_{policy}_mode_known",
        )
        for policy in POLICY_FIELDS
    ]


def _limit_columns() -> list[Column[Any]]:
    return [Column(name, Integer, nullable=False) for name, _ in LIMIT_CHECKS]


def _limit_checks() -> list[CheckConstraint]:
    return [
        CheckConstraint(f"{name} {bound}", name=f"ck_scheduling_settings_{name}_range")
        for name, bound in LIMIT_CHECKS
    ]


scheduling_settings = Table(
    "scheduling_settings",
    scheduling_metadata,
    # Opaco: o restaurante vive em identity. A configuração é do tenant (ADR 4.1.0003).
    Column("tenant_id", Text, nullable=False),
    Column("week_start", Text, nullable=False),
    Column("day_cutoff", _NAIVE_TIME, nullable=False),
    *_policy_columns(),
    *_limit_columns(),
    Column("workload_direction", Text, nullable=False),
    PrimaryKeyConstraint("tenant_id", name="pk_scheduling_settings"),
    CheckConstraint(
        f"week_start IN ({_WEEKDAYS_IN_LIST})", name="ck_scheduling_settings_week_start_known"
    ),
    *_policy_checks(),
    *_limit_checks(),
    CheckConstraint(
        f"workload_direction IN ({_DIRECTIONS_IN_LIST})",
        name="ck_scheduling_settings_workload_direction_known",
    ),
)
