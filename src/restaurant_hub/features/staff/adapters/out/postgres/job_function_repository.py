"""Adapter Postgres de `JobFunctionRepository` — L-JF1…L-JF5 e a metade de `L-ORD`.

**Fronteira transacional** (D8; precedente do concept 2.3 §7 Decisão 6): o
repositório recebe um `Engine` e abre a própria transação por método público,
via `engine.begin()`. A skill `repository-pattern` recomenda transação
controlada de fora; staff não a tem porque nenhum use case de staff escreve duas
vezes em staff — cada um escreve uma vez, e a travessia para identity não é
transação (ADR 2.6.0002 §2). Identity ganhou unidade de trabalho na Stage 2.6
(ADR 2.6.0001); quando um use case de staff precisar escrever duas vezes, a
regra 10 do `check_layout` o obriga a decidir.

Para manter a troca barata quando esse consumidor existir, o núcleo reusado
opera sobre `Connection` — as três escritas e o lookup de `delete`, que é o
único ponto em que uma operação precisa do resultado de outra. As três leituras
sem reuso (`find_by_name`, `find_all_by_ids`, `list_by_tenant`) embutem a
consulta no método público: extrair um privado de um só chamador seria
indireção sem ponto de troca a servir.

Três decisões deste arquivo carregam lei e não são estilo:

1. **`add` é `INSERT` puro, sem `ON CONFLICT`** (§5.2, ADR 2.3.0003). Um upsert
   silencioso é a dívida exata que a 2.3 pagou; aqui a colisão vira erro tipado
   pela tradução da constraint.
2. **`tenant_id` nunca entra no `SET`** (§5.3) — só no `WHERE`. O `UPDATE`
   escreve `name` e mais nada, então "mover a função de restaurante" não é um
   estado que este adapter saiba produzir.
3. **A unicidade de nome é verbatim** (§5.6): sem `lower()`, sem `btrim`, sem
   `ILIKE`, nem no `find_by_name` nem em guarda alguma. Normalizar "parece
   certo" e é o erro mais fácil de cometer aqui — recusaria em silêncio nomes
   que o gerente considera distintos, e CA9 existe para reprovar isso.

**Habilitação por unidade (Stage 3.11, ADR 3.11.0001).** A função é gravada em
duas metades — a flag `enabled_in_all_units` na linha e as linhas de
`job_function_units` — e as duas são escritas **na mesma transação** (L-JF1,
L-JF7). A leitura reidrata as duas numa consulta extra por chamada (não por
função), e o `__post_init__` de `UnitEnablement` recusa a combinação incoerente.
`update` (L-JF2) continua gravando **só o nome**: a habilitação tem escrita
própria, `update_enablement`, para que uma renomeação concorrente a uma alteração
de unidades não regrave a habilitação antiga.

E a ordem, que é lei do port desde a Stage 3.3 (`L-ORD`, ADR 3.3.0003):
`ORDER BY name COLLATE "C", id COLLATE "C"` nas duas listagens, com a colação
**nas duas colunas** — `COLLATE` liga-se ao operando à sua esquerda, e um `id`
sem ela volta a depender da colação do banco justamente no termo que a paginação
da 3.4 usa como cursor. Nesta imagem (musl) nenhum resultado distingue a
presença da ausência da cláusula; quem reprova a omissão é a asserção sobre o
SQL compilado (CA10b).
"""

from collections import defaultdict
from collections.abc import Sequence
from typing import Any

from sqlalchemy import Connection, Engine, Row, or_, select
from sqlalchemy.exc import IntegrityError

from restaurant_hub.features.staff.adapters.out.postgres import mappers
from restaurant_hub.features.staff.adapters.out.postgres.integrity_errors import (
    ON_DELETE_JOB_FUNCTION,
    ON_INSERT_JOB_FUNCTION,
    ON_UPDATE_JOB_FUNCTION,
    constraint_name,
    translate,
)
from restaurant_hub.features.staff.adapters.out.postgres.tables import (
    job_function_units,
    job_functions,
)
from restaurant_hub.features.staff.application.errors import JobFunctionNotFoundError
from restaurant_hub.features.staff.domain.entities.job_function import JobFunction
from restaurant_hub.features.staff.domain.value_objects.identifiers import (
    JobFunctionId,
    TenantId,
    UnitId,
)

# Ordem total do port (`L-ORD`). As duas colunas levam a colação explícita — ver
# o docstring do módulo.
_TOTAL_ORDER = (
    job_functions.c.name.collate("C"),
    job_functions.c.id.collate("C"),
)


class PostgresJobFunctionRepository:
    """Implementação PostgreSQL do port `JobFunctionRepository`."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    # ---- escrita ----------------------------------------------------------

    def add(self, job_function: JobFunction) -> None:
        """L-JF1 — inserção, nunca upsert. Id colide globalmente; nome, por tenant."""
        try:
            with self._engine.begin() as connection:
                self._add(connection, job_function)
        except IntegrityError as error:
            # `from error` preserva a cadeia de causa: sem ela, o diagnóstico de
            # um conflito de integridade perde o SQL e a constraint originais.
            raise translate(
                error, ON_INSERT_JOB_FUNCTION, self._conflict_detail(error, job_function)
            ) from error

    def update_enablement(self, job_function: JobFunction) -> None:
        """L-JF7 — substitui a habilitação; função ausente no tenant ⇒ `NotFound`.

        Flag e vínculos mudam na **mesma** transação: o `UPDATE` da flag é também o
        lookup por `(tenant_id, id)` — `rowcount == 0` levanta antes de tocar os
        vínculos, e o rollback garante que nada mudou.
        """
        with self._engine.begin() as connection:
            result = connection.execute(
                job_functions.update()
                .where(
                    job_functions.c.id == job_function.id,
                    job_functions.c.tenant_id == job_function.tenant_id,
                )
                .values(enabled_in_all_units=job_function.unit_enablement.all_units)
            )
            if result.rowcount == 0:
                raise JobFunctionNotFoundError(job_function.id)
            connection.execute(
                job_function_units.delete().where(
                    job_function_units.c.job_function_id == job_function.id,
                    job_function_units.c.tenant_id == job_function.tenant_id,
                )
            )
            self._insert_units(connection, job_function)

    def update(self, job_function: JobFunction) -> None:
        """L-JF2 — `UPDATE` com `rowcount == 0` ⇒ `JobFunctionNotFoundError`.

        A guarda de nome de L-JF1 vale aqui **ignorando a própria função**, e o
        índice único resolve isso sozinho: renomear para o nome que a função já
        tem atualiza a própria linha e não colide com ninguém. Uma pré-checagem
        por `find_by_name` teria de reimplementar a exceção de si mesma — e
        ainda seria check-then-act sob concorrência.
        """
        try:
            with self._engine.begin() as connection:
                self._update(connection, job_function)
        except IntegrityError as error:
            raise translate(error, ON_UPDATE_JOB_FUNCTION, job_function.name) from error

    def delete(self, tenant_id: TenantId, job_function_id: JobFunctionId) -> None:
        """L-JF3 — remoção guardada pelo `RESTRICT`, com o lookup **antes**.

        A ordem é normativa (§5.4): função ausente **no tenant** responde
        `JobFunctionNotFoundError`, nunca `JobFunctionInUseError` — este último
        confirmaria ao tenant alheio que o registro existe **e** que está em uso
        no restaurante do outro.

        Guarda e escrita rodam na **mesma** transação. Fora dela a ordem seria
        decorativa: entre o `SELECT` e o `DELETE`, um `INSERT` de vínculo
        concorrente mudaria a resposta.
        """
        try:
            with self._engine.begin() as connection:
                self._delete(connection, tenant_id, job_function_id)
        except IntegrityError as error:
            raise translate(error, ON_DELETE_JOB_FUNCTION, job_function_id) from error

    # ---- leitura ----------------------------------------------------------

    def find_by_id(self, tenant_id: TenantId, job_function_id: JobFunctionId) -> JobFunction | None:
        """Função **do tenant**, ou `None` — id alheio é indistinguível de inexistente."""
        with self._engine.connect() as connection:
            return self._find_by_id(connection, tenant_id, job_function_id)

    def find_by_name(self, tenant_id: TenantId, name: str) -> JobFunction | None:
        """Homônima do tenant, ou `None`. Comparação **verbatim** — `=`, nunca `ILIKE`."""
        with self._engine.connect() as connection:
            row = connection.execute(
                select(job_functions).where(
                    job_functions.c.tenant_id == tenant_id,
                    job_functions.c.name == name,
                )
            ).one_or_none()
            if row is None:
                return None
            return self._hydrate(connection, [row])[0]

    def find_all_by_ids(
        self, tenant_id: TenantId, job_function_ids: frozenset[JobFunctionId]
    ) -> tuple[JobFunction, ...]:
        """L-JF4 — só as encontradas, sem levantar; `L-ORD` — em ordem total.

        Conjunto vazio devolve `()` **sem ir ao banco**: é o caminho que
        `create_employee` percorre, e uma ida ao banco para perguntar por nada
        seria latência sem informação.
        """
        if not job_function_ids:
            return ()
        with self._engine.connect() as connection:
            rows = connection.execute(
                select(job_functions)
                .where(
                    job_functions.c.tenant_id == tenant_id,
                    # `sorted` só para que o texto do SQL seja estável entre
                    # execuções (`frozenset` itera por `PYTHONHASHSEED`); a
                    # ordem do resultado é a do `ORDER BY`, não a do `IN`.
                    job_functions.c.id.in_(sorted(job_function_ids)),
                )
                .order_by(*_TOTAL_ORDER)
            ).all()
            return self._hydrate(connection, rows)

    def list_by_tenant(self, tenant_id: TenantId) -> tuple[JobFunction, ...]:
        """L-JF5 — todas as do tenant e nenhuma de outro; `L-ORD` — em ordem total."""
        with self._engine.connect() as connection:
            rows = connection.execute(
                select(job_functions)
                .where(job_functions.c.tenant_id == tenant_id)
                .order_by(*_TOTAL_ORDER)
            ).all()
            return self._hydrate(connection, rows)

    def list_by_unit(self, tenant_id: TenantId, unit_id: UnitId) -> tuple[JobFunction, ...]:
        """L-JF6 — as do tenant habilitadas na unidade; `L-ORD` — em ordem total.

        "Habilitada" é a flag de todas as unidades **ou** um vínculo com esta
        unidade. O vínculo é procurado com o `tenant_id` também, embora a FK
        composta já o amarre à função do tenant: é o par que o índice
        `ix_job_function_units_tenant_unit` serve.
        """
        enabled_here = select(job_function_units.c.job_function_id).where(
            job_function_units.c.tenant_id == tenant_id,
            job_function_units.c.unit_id == unit_id,
        )
        with self._engine.connect() as connection:
            rows = connection.execute(
                select(job_functions)
                .where(
                    job_functions.c.tenant_id == tenant_id,
                    or_(
                        job_functions.c.enabled_in_all_units.is_(True),
                        job_functions.c.id.in_(enabled_here),
                    ),
                )
                .order_by(*_TOTAL_ORDER)
            ).all()
            return self._hydrate(connection, rows)

    # ---- núcleo sobre `Connection` (ponto de troca para um futuro UoW) -----

    def _add(self, connection: Connection, job_function: JobFunction) -> None:
        connection.execute(
            job_functions.insert().values(**mappers.job_function_to_row(job_function))
        )
        self._insert_units(connection, job_function)

    @staticmethod
    def _insert_units(connection: Connection, job_function: JobFunction) -> None:
        rows = mappers.job_function_unit_rows(job_function)
        # Função em todas as unidades não tem vínculo a gravar, e um `executemany`
        # com lista vazia não é um no-op no SQLAlchemy.
        if rows:
            connection.execute(job_function_units.insert(), rows)

    @staticmethod
    def _hydrate(connection: Connection, rows: Sequence[Row[Any]]) -> tuple[JobFunction, ...]:
        """Reidrata as funções com os vínculos de unidade, numa consulta só.

        Preserva a ordem de `rows` (a do `ORDER BY` de `L-ORD`): o agrupamento
        dos vínculos é por id, e a tupla devolvida segue a lista recebida.
        """
        if not rows:
            return ()
        restricted = sorted(row.id for row in rows if not row.enabled_in_all_units)
        units_by_function: dict[str, list[str]] = defaultdict(list)
        if restricted:
            for link in connection.execute(
                select(job_function_units.c.job_function_id, job_function_units.c.unit_id).where(
                    job_function_units.c.job_function_id.in_(restricted)
                )
            ):
                units_by_function[link.job_function_id].append(link.unit_id)
        return tuple(
            mappers.row_to_job_function(row, unit_ids=units_by_function.get(row.id, ()))
            for row in rows
        )

    def _update(self, connection: Connection, job_function: JobFunction) -> None:
        result = connection.execute(
            job_functions.update()
            .where(
                job_functions.c.id == job_function.id,
                job_functions.c.tenant_id == job_function.tenant_id,
            )
            # **Só `name`.** `tenant_id` não entra no `SET` (§5.3) e `id` é a
            # identidade: incluí-los tornaria representável mover a função de
            # restaurante por uma escrita que se parece com uma renomeação.
            .values(name=job_function.name)
        )
        if result.rowcount == 0:
            raise JobFunctionNotFoundError(job_function.id)

    def _delete(
        self, connection: Connection, tenant_id: TenantId, job_function_id: JobFunctionId
    ) -> None:
        if self._find_by_id(connection, tenant_id, job_function_id) is None:
            raise JobFunctionNotFoundError(job_function_id)
        connection.execute(
            job_functions.delete().where(
                job_functions.c.id == job_function_id,
                job_functions.c.tenant_id == tenant_id,
            )
        )

    def _find_by_id(
        self, connection: Connection, tenant_id: TenantId, job_function_id: JobFunctionId
    ) -> JobFunction | None:
        row = connection.execute(
            select(job_functions).where(
                job_functions.c.id == job_function_id,
                job_functions.c.tenant_id == tenant_id,
            )
        ).one_or_none()
        if row is None:
            return None
        return self._hydrate(connection, [row])[0]

    @staticmethod
    def _conflict_detail(error: IntegrityError, job_function: JobFunction) -> str:
        """Qual valor entra na mensagem depende de **qual** regra foi violada.

        `translate` recebe um `detail` só (contrato do concept §4), e as duas
        constraints alcançáveis por um `INSERT` conflitam em valores diferentes:
        a PK no `id`, o índice único no `name`. Uma mensagem dizendo "nome de
        função já usado no restaurante: 'f1'" seria pior que nenhuma — descreve
        o conflito errado com a confiança de quem sabe. Precedente literal:
        `user_repository.py` de identity, na mesma situação.
        """
        if constraint_name(error) == "uq_job_functions_tenant_name":
            return job_function.name
        return job_function.id
