"""Adapter Postgres de `ScheduleRepository` — L-SC1 a L-SC8, com a trilha na mesma transação.

**Protocolo de escrita** (ADR 4.4.0003; concept 4.4 §5.2–§5.5). `add` e `save` abrem **uma**
transação e, nela:

1. tomam o **lock da unidade** — `pg_advisory_xact_lock` sobre o hash de
   `(tenant_id, unit_id)`, liberado no commit ou no rollback. Serializa os escritores de
   escala da unidade; é convenção da aplicação, e todo escritor futuro destas tabelas tem
   de tomá-lo (`unit_lock_statement`);
2. rodam as checagens da lei **explicitamente, na ordem da lei** — `add`: id da escala →
   período → ids internos; `save`: endereço → versão → ids internos. Sob o lock e em
   `READ COMMITTED`, cada comando vê o que o escritor anterior comitou;
3. gravam a raiz, **reescrevem as filhas** (o `save` apaga as faixas e o `CASCADE` leva
   demandas e alocações; depois reinsere o agregado com as posições) e inserem a linha da
   trilha.

Qualquer recusa ou falha desfaz tudo — nem estado nem trilha (L-SC3). As constraints são a
garantia do banco, não a fonte do erro; só `pk_schedules` e a exclusion constraint são
traduzidas, no `add` (`integrity_errors.ON_ADD_SCHEDULE`).

O `save` grava a versão e as filhas, **nunca** o período nem o calendário: são da criação, e
uma escala que chegue com outros está fora do contrato do port — por isso o `save` não tem
como violar L-SC2.

**A trilha é só de inserção** (ADR 4.4.0002): este módulo não tem `UPDATE` nem `DELETE`
sobre `schedule_changes` (varredura em `test_schedule_repository_static.py`).

**Leituras em snapshot único** (concept §5.9): raiz e filhas numa transação
`REPEATABLE READ`, para que um `save` concorrente nunca produza a versão de um estado com as
faixas de outro. Toda leitura filtra tenant **e** unidade (L-SC5).
"""

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import date, timedelta

from sqlalchemy import Connection, Engine, Executable, func, select
from sqlalchemy.exc import IntegrityError

from restaurant_hub.features.scheduling.adapters.out.postgres import mappers
from restaurant_hub.features.scheduling.adapters.out.postgres.integrity_errors import (
    ON_ADD_SCHEDULE,
    translate,
)
from restaurant_hub.features.scheduling.adapters.out.postgres.tables import (
    schedule_assignments,
    schedule_bands,
    schedule_changes,
    schedule_demands,
    schedules,
)
from restaurant_hub.features.scheduling.application.errors import (
    IdentifierInUseError,
    ScheduleNotFoundError,
    SchedulePeriodTakenError,
    ScheduleVersionConflictError,
)
from restaurant_hub.features.scheduling.application.ports.out.schedule_repository import (
    ScheduleChange,
)
from restaurant_hub.features.scheduling.domain.entities.schedule import Schedule
from restaurant_hub.features.scheduling.domain.value_objects.identifiers import (
    ScheduleId,
    TenantId,
    UnitId,
)

# Separa tenant e unidade na chave do lock: `("ab", "c")` e `("a", "bc")` não colidem por
# concatenação. É o caractere de controle "unit separator", válido em `text`.
_LOCK_KEY_SEPARATOR = "\x1f"

_SINGLE_SNAPSHOT = "REPEATABLE READ"

# O último dia **exclusivo** de cada escala gravada: `daterange(first_day, first_day + days)`.
_END_EXCLUSIVE = schedules.c.first_day + schedules.c.days

# Os ids internos por tipo, na ordem do relato canônico de L-SC4 (faixa → demanda → alocação).
_INTERNAL_ID_TABLES = (
    ("ShiftBandId", schedule_bands),
    ("ShiftDemandId", schedule_demands),
    ("AssignmentId", schedule_assignments),
)


def unit_lock_statement(tenant_id: str, unit_id: str) -> Executable:
    """O lock transacional da unidade — a chave de `add` e de `save` (ADR 4.4.0003 §1)."""
    key = func.hashtextextended(f"{tenant_id}{_LOCK_KEY_SEPARATOR}{unit_id}", 0)
    return select(func.pg_advisory_xact_lock(key))


def schedule_id_taken_statement(schedule_id: str) -> Executable:
    """L-SC1: o id da escala em **qualquer** tenant."""
    return select(schedules.c.id).where(schedules.c.id == schedule_id)


def period_taken_statement(schedule: Schedule) -> Executable:
    """L-SC2: alguma escala da unidade cobre um dos dias do período? (faixas `[)`)."""
    period = schedule.period
    return select(schedules.c.id).where(
        schedules.c.tenant_id == schedule.tenant_id,
        schedules.c.unit_id == schedule.unit_id,
        schedules.c.first_day < period.last_day + timedelta(days=1),
        period.first_day < _END_EXCLUSIVE,
    )


def internal_ids_in_use_statements(schedule: Schedule) -> tuple[tuple[str, Executable], ...]:
    """L-SC4: por tipo, os ids internos da escala já usados por **outra** escala da unidade."""
    demands = [demand for band in schedule.bands for demand in band.demands]
    ids_by_type: dict[str, list[str]] = {
        "ShiftBandId": [band.id for band in schedule.bands],
        "ShiftDemandId": [demand.id for demand in demands],
        "AssignmentId": [a.id for demand in demands for a in demand.assignments],
    }
    statements: list[tuple[str, Executable]] = []
    for id_type, table in _INTERNAL_ID_TABLES:
        ids = ids_by_type[id_type]
        if not ids:
            continue
        statements.append(
            (
                id_type,
                select(table.c.id).where(
                    table.c.tenant_id == schedule.tenant_id,
                    table.c.unit_id == schedule.unit_id,
                    table.c.schedule_id != schedule.id,
                    # `sorted`: texto do SQL estável entre execuções.
                    table.c.id.in_(sorted(ids)),
                ),
            )
        )
    return tuple(statements)


def stored_version_statement(schedule: Schedule) -> Executable:
    """A versão gravada no endereço de três partes (L-SC4, L-SC5)."""
    return select(schedules.c.version).where(
        schedules.c.id == schedule.id,
        schedules.c.tenant_id == schedule.tenant_id,
        schedules.c.unit_id == schedule.unit_id,
    )


def next_seq_statement(schedule_id: str) -> Executable:
    """O próximo ordinal da trilha da escala; sob o lock, nenhum escritor concorre."""
    return select(func.coalesce(func.max(schedule_changes.c.seq), 0) + 1).where(
        schedule_changes.c.schedule_id == schedule_id
    )


class PostgresScheduleRepository:
    """Implementação PostgreSQL do port `ScheduleRepository`."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    # ---- escrita ----------------------------------------------------------

    def add(self, schedule: Schedule, change: ScheduleChange) -> None:
        """L-SC1, L-SC2, L-SC4 no `add`, L-SC3 — na ordem id → período → ids internos."""
        try:
            with self._engine.begin() as connection:
                connection.execute(unit_lock_statement(schedule.tenant_id, schedule.unit_id))
                if connection.execute(schedule_id_taken_statement(schedule.id)).first():
                    raise IdentifierInUseError("ScheduleId", schedule.id)
                if connection.execute(period_taken_statement(schedule)).first():
                    raise SchedulePeriodTakenError()
                self._check_internal_ids(connection, schedule)
                rows = mappers.schedule_to_rows(schedule)
                connection.execute(schedules.insert().values(rows.root))
                self._insert_children(connection, rows)
                connection.execute(
                    schedule_changes.insert().values(mappers.change_to_row(schedule, change, 1))
                )
        except IntegrityError as error:
            # Só a corrida entre unidades (mesmo id de escala, locks distintos) chega aqui
            # pelo caminho do adapter; `from error` preserva a cadeia de causa.
            raise translate(error, ON_ADD_SCHEDULE, schedule.id) from error

    def save(self, schedule: Schedule, expected_version: int, change: ScheduleChange) -> None:
        """L-SC4 (endereço → versão → ids internos) e L-SC3; reescreve as filhas."""
        with self._engine.begin() as connection:
            connection.execute(unit_lock_statement(schedule.tenant_id, schedule.unit_id))
            stored_version = connection.execute(stored_version_statement(schedule)).scalar()
            if stored_version is None:
                raise ScheduleNotFoundError(schedule.id)
            if stored_version != expected_version:
                raise ScheduleVersionConflictError(expected_version, stored_version)
            self._check_internal_ids(connection, schedule)
            connection.execute(
                schedules.update()
                .where(
                    schedules.c.id == schedule.id,
                    schedules.c.tenant_id == schedule.tenant_id,
                    schedules.c.unit_id == schedule.unit_id,
                )
                # Só a versão: período e calendário são da criação.
                .values(version=schedule.version)
            )
            connection.execute(
                schedule_bands.delete().where(
                    schedule_bands.c.tenant_id == schedule.tenant_id,
                    schedule_bands.c.unit_id == schedule.unit_id,
                    schedule_bands.c.schedule_id == schedule.id,
                )
            )
            self._insert_children(connection, mappers.schedule_to_rows(schedule))
            seq = connection.execute(next_seq_statement(schedule.id)).scalar_one()
            connection.execute(
                schedule_changes.insert().values(mappers.change_to_row(schedule, change, seq))
            )

    # ---- leitura ----------------------------------------------------------

    def find_by_id(
        self, tenant_id: TenantId, unit_id: UnitId, schedule_id: ScheduleId
    ) -> Schedule | None:
        """A escala no endereço de três partes, ou `None` (L-SC5)."""
        with self._in_single_snapshot() as connection:
            root = connection.execute(
                select(schedules).where(
                    schedules.c.id == schedule_id,
                    schedules.c.tenant_id == tenant_id,
                    schedules.c.unit_id == unit_id,
                )
            ).one_or_none()
            if root is None:
                return None
            return self._build(connection, tenant_id, unit_id, [root])[0]

    def list_in_range(
        self, tenant_id: TenantId, unit_id: UnitId, first_day: date, last_day: date
    ) -> tuple[Schedule, ...]:
        """L-SC6: as que cruzam `[first_day, last_day]`, por `first_day` crescente."""
        with self._in_single_snapshot() as connection:
            roots = connection.execute(
                select(schedules)
                .where(
                    schedules.c.tenant_id == tenant_id,
                    schedules.c.unit_id == unit_id,
                    schedules.c.first_day <= last_day,
                    first_day < _END_EXCLUSIVE,
                )
                .order_by(schedules.c.first_day)
            ).all()
            return self._build(connection, tenant_id, unit_id, roots)

    def list_ending_before(
        self, tenant_id: TenantId, unit_id: UnitId, before: date, limit: int
    ) -> tuple[Schedule, ...]:
        """L-SC7: `last_day < before`, da mais recente, no máximo `limit` (no SQL)."""
        with self._in_single_snapshot() as connection:
            roots = connection.execute(
                select(schedules)
                .where(
                    schedules.c.tenant_id == tenant_id,
                    schedules.c.unit_id == unit_id,
                    # last_day < before ⇔ first_day + days <= before
                    before >= _END_EXCLUSIVE,
                )
                .order_by(schedules.c.first_day.desc())
                .limit(limit)
            ).all()
            return self._build(connection, tenant_id, unit_id, roots)

    # ---- núcleo -----------------------------------------------------------

    @staticmethod
    def _check_internal_ids(connection: Connection, schedule: Schedule) -> None:
        """Primeiro tipo em conflito e, dele, o menor id por codepoint (`min` do Python)."""
        for id_type, statement in internal_ids_in_use_statements(schedule):
            in_use = connection.execute(statement).scalars().all()
            if in_use:
                raise IdentifierInUseError(id_type, min(in_use))

    @staticmethod
    def _insert_children(connection: Connection, rows: mappers.ScheduleRows) -> None:
        # Da raiz para as netas: cada FK composta encontra o pai já gravado.
        for table, children in (
            (schedule_bands, rows.bands),
            (schedule_demands, rows.demands),
            (schedule_assignments, rows.assignments),
        ):
            if children:
                connection.execute(table.insert(), list(children))

    @staticmethod
    def _build(
        connection: Connection, tenant_id: str, unit_id: str, roots: Sequence[mappers.Row]
    ) -> tuple[Schedule, ...]:
        """Monta N escalas em quatro statements, com as filhas agrupadas por escala."""
        if not roots:
            return ()
        ids = sorted(root.id for root in roots)
        children: dict[str, list[list[mappers.Row]]] = {sid: [[], [], []] for sid in ids}
        for index, table in enumerate((schedule_bands, schedule_demands, schedule_assignments)):
            for row in connection.execute(
                select(table).where(
                    table.c.tenant_id == tenant_id,
                    table.c.unit_id == unit_id,
                    table.c.schedule_id.in_(ids),
                )
            ):
                children[row.schedule_id][index].append(row)
        return tuple(mappers.rows_to_schedule(root, *children[root.id]) for root in roots)

    @contextmanager
    def _in_single_snapshot(self) -> Iterator[Connection]:
        """Conexão em `REPEATABLE READ`, com a transação aberta antes do primeiro statement."""
        with (
            self._engine.connect().execution_options(
                isolation_level=_SINGLE_SNAPSHOT
            ) as connection,
            connection.begin(),
        ):
            yield connection
