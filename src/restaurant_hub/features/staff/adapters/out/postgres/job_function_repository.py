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
único ponto em que uma operação precisa do resultado de outra. As leituras
embutem a consulta no método público: extrair um privado de um só chamador
seria indireção sem ponto de troca a servir.

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
de unidades não regrave a habilitação antiga. Desde a issue #206 essa escrita é
condicional à habilitação lida pelo chamador, decidida sob o lock da linha.

**As leituras rodam sob `REPEATABLE READ`** (issue #225; ADR 3.3.0006 §c, o
mesmo snapshot único das leituras de agregado de funcionário). Linha e vínculos
são dois statements, e sob `READ COMMITTED` cada um abre snapshot próprio: uma
alteração de "conjunto" para "todas" que comitasse entre os dois deixaria a
leitura com a flag antiga e nenhum vínculo — combinação que `UnitEnablement`
recusa, e a leitura responderia 422. Sob o snapshot único a leitura vê um
instante só, e numa listagem o instante é o mesmo para todas as funções. Leitura
pura em `REPEATABLE READ` não sofre erro de serialização: só a transação que
escreve ou trava linha o sofre (PostgreSQL 16, §13.2.2). O nível é posto pelo
método público, não pelo núcleo sobre `Connection` — uma unidade de trabalho
aberta no nível default perderia o snapshot único destas leituras, o mesmo aviso
do `employee_repository`.

A exceção deliberada fica em `READ COMMITTED`: a remontagem das três escritas
sobre função existente (`update_enablement`, `update` e `delete`, condicionais à
habilitação lida desde as issues #206 e #207), que roda sob o lock da linha e
precisa reler o que a alteração anterior comitou (ver `update_enablement`). Até a
#207 o lookup de `delete` não remontava a habilitação (issue #225); agora remonta,
sob o lock, onde as duas metades não podem vir de instantes diferentes.

E a ordem, que é lei do port desde a Stage 3.3 (`L-ORD`, ADR 3.3.0003):
`ORDER BY name COLLATE "C", id COLLATE "C"` nas duas listagens, com a colação
**nas duas colunas** — `COLLATE` liga-se ao operando à sua esquerda, e um `id`
sem ela volta a depender da colação do banco justamente no termo que a paginação
da 3.4 usa como cursor. Nesta imagem (musl) nenhum resultado distingue a
presença da ausência da cláusula; quem reprova a omissão é a asserção sobre o
SQL compilado (CA10b).
"""

from collections import defaultdict
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
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
from restaurant_hub.features.staff.application.errors import (
    JobFunctionEnablementChangedError,
    JobFunctionNotFoundError,
)
from restaurant_hub.features.staff.domain.entities.job_function import JobFunction
from restaurant_hub.features.staff.domain.value_objects.identifiers import (
    JobFunctionId,
    TenantId,
    UnitId,
)
from restaurant_hub.features.staff.domain.value_objects.unit_enablement import UnitEnablement

# Ordem total do port (`L-ORD`). As duas colunas levam a colação explícita — ver
# o docstring do módulo.
_TOTAL_ORDER = (
    job_functions.c.name.collate("C"),
    job_functions.c.id.collate("C"),
)

# Snapshot único nas leituras (issue #225) — ver o docstring do módulo.
_SINGLE_SNAPSHOT = "REPEATABLE READ"


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

    def update_enablement(self, job_function: JobFunction, expected: UnitEnablement) -> None:
        """L-JF7 — substitui a habilitação, só se a gravada ainda for a `expected`.

        **Escrita condicional sob o lock da linha** (issue #206) — a forma que o
        ADR 0.0.0010 deu a `link_login`. O lookup é `SELECT … FOR NO KEY UPDATE` por
        `(tenant_id, id)`: ausente ⇒ `JobFunctionNotFoundError`. Sob o lock a
        habilitação gravada é remontada (flag + vínculos) e comparada à lida pelo
        chamador; diferente ⇒ `JobFunctionEnablementChangedError`. Só então flag
        e vínculos mudam, na **mesma** transação.

        **Por que o lock fecha a corrida em `READ COMMITTED`.** Todo escritor dos
        vínculos toma a linha-pai antes: este método pelo lock do lookup, `delete`
        pelo `DELETE` (os vínculos saem por `CASCADE`), e `add` só cria vínculos
        de linha que ainda não é visível. Uma segunda alteração que espera no lock
        relê a linha comitada pela primeira, e a consulta dos vínculos, que vem
        depois, abre snapshot novo e vê os vínculos já comitados — compara contra
        o que a primeira gravou, e recusa. `REPEATABLE READ` trocaria essa
        releitura por erro de serialização (`40001`), o motivo que o ADR 0.0.0010
        dá para não usá-lo em `link_login`.

        O `UPDATE` da flag mantém o `tenant_id` no `WHERE` mesmo depois do lookup
        sob lock, como as escritas do registro de funcionário.
        """
        with self._engine.begin() as connection:
            self._lock_unchanged(connection, job_function.tenant_id, job_function.id, expected)
            connection.execute(
                job_functions.update()
                .where(
                    job_functions.c.id == job_function.id,
                    job_functions.c.tenant_id == job_function.tenant_id,
                )
                .values(enabled_in_all_units=job_function.unit_enablement.all_units)
            )
            connection.execute(
                job_function_units.delete().where(
                    job_function_units.c.job_function_id == job_function.id,
                    job_function_units.c.tenant_id == job_function.tenant_id,
                )
            )
            self._insert_units(connection, job_function)

    def update(self, job_function: JobFunction, expected: UnitEnablement) -> None:
        """L-JF2 — `UPDATE` do nome, condicional à habilitação lida (issue #207).

        O lookup sob `FOR NO KEY UPDATE` (o lock que o `UPDATE` de coluna
        não-chave já tomava) responde `JobFunctionNotFoundError` e compara a
        habilitação gravada com `expected` — `JobFunctionEnablementChangedError`
        se mudou —, como em `update_enablement`.

        A guarda de nome de L-JF1 vale aqui **ignorando a própria função**, e o
        índice único resolve isso sozinho: renomear para o nome que a função já
        tem atualiza a própria linha e não colide com ninguém. Uma pré-checagem
        por `find_by_name` teria de reimplementar a exceção de si mesma — e
        ainda seria check-then-act sob concorrência.
        """
        try:
            with self._engine.begin() as connection:
                self._lock_unchanged(connection, job_function.tenant_id, job_function.id, expected)
                self._update(connection, job_function)
        except IntegrityError as error:
            raise translate(error, ON_UPDATE_JOB_FUNCTION, job_function.name) from error

    def delete(
        self, tenant_id: TenantId, job_function_id: JobFunctionId, expected: UnitEnablement
    ) -> None:
        """L-JF3 — remoção guardada pelo `RESTRICT`, com o lookup **antes**.

        A ordem é normativa (§5.4): função ausente **no tenant** responde
        `JobFunctionNotFoundError`, nunca `JobFunctionInUseError` — este último
        confirmaria ao tenant alheio que o registro existe **e** que está em uso
        no restaurante do outro.

        Guarda e escrita rodam na **mesma** transação. Fora dela a ordem seria
        decorativa: entre o `SELECT` e o `DELETE`, um `INSERT` de vínculo
        concorrente mudaria a resposta.

        **Condicional à habilitação lida (issue #207).** O lookup é
        `SELECT … FOR UPDATE` — o lock que o `DELETE` tomaria de qualquer forma,
        tomado antes para que a comparação decida sobre a linha que vai sair — e
        remonta a habilitação para compará-la com `expected`. Sob o lock a
        remontagem é coerente pelo argumento de `update_enablement` (todo escritor
        dos vínculos toma a linha-pai antes), o que substitui o lookup sem
        remontagem que a issue #225 tinha posto aqui.
        """
        try:
            with self._engine.begin() as connection:
                self._lock_unchanged(
                    connection, tenant_id, job_function_id, expected, for_delete=True
                )
                self._delete(connection, tenant_id, job_function_id)
        except IntegrityError as error:
            raise translate(error, ON_DELETE_JOB_FUNCTION, job_function_id) from error

    # ---- leitura ----------------------------------------------------------

    def find_by_id(self, tenant_id: TenantId, job_function_id: JobFunctionId) -> JobFunction | None:
        """Função **do tenant**, ou `None` — id alheio é indistinguível de inexistente."""
        with self._in_single_snapshot() as connection:
            row = connection.execute(
                select(job_functions).where(
                    job_functions.c.id == job_function_id,
                    job_functions.c.tenant_id == tenant_id,
                )
            ).one_or_none()
            if row is None:
                return None
            return self._hydrate(connection, [row])[0]

    def find_by_name(self, tenant_id: TenantId, name: str) -> JobFunction | None:
        """Homônima do tenant, ou `None`. Comparação **verbatim** — `=`, nunca `ILIKE`."""
        with self._in_single_snapshot() as connection:
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
        with self._in_single_snapshot() as connection:
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
        with self._in_single_snapshot() as connection:
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
        with self._in_single_snapshot() as connection:
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

    @contextmanager
    def _in_single_snapshot(self) -> Iterator[Connection]:
        """Conexão em `REPEATABLE READ`, com a transação aberta explicitamente.

        A forma de `PostgresEmployeeRepository._in_single_snapshot`: o nível é
        execution option da **conexão** e vale antes do primeiro statement, e o
        `begin()` explícito escreve a fronteira do snapshot em vez de deixá-la no
        autobegin. O snapshot é tirado no primeiro statement e vale para os dois.
        """
        with (
            self._engine.connect().execution_options(
                isolation_level=_SINGLE_SNAPSHOT
            ) as connection,
            connection.begin(),
        ):
            yield connection

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

    def _lock_unchanged(
        self,
        connection: Connection,
        tenant_id: TenantId,
        job_function_id: JobFunctionId,
        expected: UnitEnablement,
        *,
        for_delete: bool = False,
    ) -> None:
        """Trava a linha, e recusa se ausente ou se a habilitação gravada não é `expected`.

        A condição das três escritas sobre função existente (issues #206 e #207),
        numa cópia só. Ausente no tenant ⇒ `JobFunctionNotFoundError` **antes** da
        comparação; diferente ⇒ `JobFunctionEnablementChangedError`.

        O lock é `FOR NO KEY UPDATE` para as duas escritas de coluna não-chave
        (renomear, mudar unidades): serializa-as entre si e com o `DELETE` sem
        conflitar com o `KEY SHARE` que a FK de `employee_job_functions` toma ao
        atribuir a função a um registro (ADR 3.3.0006 (b)) — atribuir não muda a
        habilitação. Para a remoção é `FOR UPDATE`, o lock que o `DELETE` já
        tomaria (e que já esperava atribuição em curso).
        """
        row = connection.execute(
            select(job_functions)
            .where(
                job_functions.c.id == job_function_id,
                job_functions.c.tenant_id == tenant_id,
            )
            .with_for_update(key_share=not for_delete)
        ).one_or_none()
        if row is None:
            raise JobFunctionNotFoundError(job_function_id)
        if self._hydrate(connection, [row])[0].unit_enablement != expected:
            raise JobFunctionEnablementChangedError(job_function_id)

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
        # O lookup (existência e habilitação, sob `FOR UPDATE`) já rodou em
        # `_lock_unchanged`, na mesma transação.
        connection.execute(
            job_functions.delete().where(
                job_functions.c.id == job_function_id,
                job_functions.c.tenant_id == tenant_id,
            )
        )

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
