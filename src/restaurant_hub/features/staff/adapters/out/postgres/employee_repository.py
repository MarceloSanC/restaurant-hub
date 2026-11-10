"""Adapter Postgres de `EmployeeRepository` — L-E1…L-E7, `L-ORD` e a atomicidade das duas pontas.

O repositório com regra de verdade desta Stage: agregado de **quatro** tabelas,
ordem de checagem normativa e a atomicidade que a §5.18/§5.20 fecham nas duas
pontas — escrita **e** leitura.

**Fronteira transacional** (D8; precedente literal do concept 2.3 §7 Decisão 6):
o repositório recebe um `Engine` e abre a própria transação por método público.
A skill `repository-pattern` recomenda transação controlada de fora; staff não a
tem porque nenhum use case de staff escreve duas vezes em staff (ADR 2.6.0002
§2) — identity, que tem, ganhou a unidade de trabalho na Stage 2.6 (ADR
2.6.0001). As leituras daqui rodam em `REPEATABLE READ` (ADR 3.3.0006 §c), e uma
unidade aberta no nível default as perderia: mais um motivo para staff não
compartilhar a de identity. O núcleo reusado
opera sobre `Connection`, que é o ponto de troca quando esse consumidor existir.

Seis decisões deste arquivo carregam lei e não são estilo:

1. **Em `add`, L-E1 precede L-E4** (§5.5). Isso exige o
   `SELECT id FROM employees WHERE id = :id` **explícito**, e explicitamente
   **sem** `tenant_id`: a colisão de id é global (a PK não o inclui). A ordem
   natural do SQL é a inversa — a colisão só apareceria no `INSERT`, depois da
   pré-checagem referencial —, e uma entrada que viola as **duas** leis
   responderia `JobFunctionNotFoundError` onde o fake responde
   `EmployeeAlreadyExistsError`. Nenhum dos 46 testes de lei herdados
   discrimina esse caso; quem o trava é CA5b, no contrato (Task 09).
2. **Em `update`, o lookup é `SELECT unit_id … FOR UPDATE`** e vem antes de
   tudo (§5.4). Duas coisas ao mesmo tempo: a ordem — tenant divergente é
   `EmployeeNotFoundError`, **nunca** `EmployeeRelocationError`, que
   confirmaria a existência do registro alheio — e o `FOR UPDATE`, que
   serializa duas edições concorrentes do **mesmo** registro. Sem ele o
   resultado final é idêntico em qualquer teste de estado; quem reprova a
   omissão é CA6b (Task 08).
3. **As filhas são escritas por DIFERENÇA, nunca por reescrita cega** (§5.20).
   Apagar todos os vínculos e reinseri-los produz o mesmo estado final e passa
   em **todos** os testes de lei — e foi medido contra o banco real: ao
   reinserir, a transação pega `FOR KEY SHARE` nas linhas de `job_functions`,
   invertendo a ordem de lock em relação a um `delete_job_function`
   concorrente ⇒ `40P01 DeadlockDetected`. E `40P01` é `OperationalError`, não
   `IntegrityError`: **escapa do tradutor** e vira 500 na 3.4. Por diferença,
   um `update` que não mexe no conjunto não emite statement nenhum nas filhas
   e portanto não pega lock nenhum. É a peça mais fácil de "simplificar"
   depois, e a regressão que a protege é da Task 08.
4. **`find_by_id` e `list_by_unit` leem sob `REPEATABLE READ`** (§5.18). Os
   dois montam o agregado a partir de quatro tabelas em statements separados, e
   sob `READ COMMITTED` (o default) **cada statement pega um snapshot novo**:
   uma escrita concorrente que comite no meio produz uma entidade que nunca
   existiu — ou, com um `delete` concorrente, um funcionário sem função
   nenhuma, que a §5.11 faz levantar `EmptyJobFunctionsError` num caminho que o
   port (`-> Employee | None`) não prevê. Medido: sob `REPEATABLE READ` o
   problema desaparece.
5. **A id ausente de L-E4 é determinística** (§5.15). A pré-checagem percorre
   `sorted(job_function_ids)` e reporta a **menor** ausente; o backstop (a
   corrida que a FK pega) renderiza o **conjunto** com `sorted()`. Sem isso,
   `frozenset` itera por `PYTHONHASHSEED` e o teste de contrato que exige
   `"f97"` falharia **de forma intermitente** contra `[postgres]`. A diferença
   entre as duas mensagens é também o **único** discriminador observável de
   qual das duas camadas de guarda respondeu (CA8c).
6. **`list_by_unit` filtra `active` no SQL**, não em Python (§5.17). Hoje as
   duas formas são indistinguíveis por teste — o resultado é o mesmo — e isso
   está declarado: é restrição de implementação, não invariante observável
   nesta Stage. Ela existe porque a 3.4 acrescenta `LIMIT`/`OFFSET`, e filtro
   em Python **depois** do fetch pagina errado.

E a ordem, lei do port desde esta Stage (`L-ORD`, ADR 3.3.0003):
`ORDER BY name COLLATE "C", id COLLATE "C"` na listagem, com a colação nas
**duas** colunas — `COLLATE` liga-se ao operando à sua esquerda, e um `id` sem
ela volta a depender da colação do banco justamente no termo que a paginação da
3.4 usa como cursor. Aqui o desempate por `id` é **alcançável por dado**:
homônimos são legítimos (concept 3.1 §5.2). Dentro do agregado,
`unavailabilities` reidrata por `ORDER BY start_at`, que é ordem total por
funcionário porque períodos do mesmo registro não se sobrepõem.
"""

from collections import defaultdict
from collections.abc import Iterator, Sequence
from contextlib import contextmanager

from sqlalchemy import Connection, Engine, exists, select
from sqlalchemy.exc import IntegrityError

from restaurant_hub.features.staff.adapters.out.postgres import mappers
from restaurant_hub.features.staff.adapters.out.postgres.integrity_errors import (
    ON_WRITE_EMPLOYEE,
    constraint_name,
    translate,
)
from restaurant_hub.features.staff.adapters.out.postgres.tables import (
    employee_job_functions,
    employee_shift_preferences,
    employee_unavailabilities,
    employees,
    job_functions,
)
from restaurant_hub.features.staff.application.errors import (
    EmployeeAlreadyExistsError,
    EmployeeHasLoginError,
    EmployeeNotFoundError,
    EmployeeRelocationError,
    JobFunctionNotFoundError,
)
from restaurant_hub.features.staff.domain.entities.employee import Employee
from restaurant_hub.features.staff.domain.value_objects.identifiers import (
    EmployeeId,
    JobFunctionId,
    TenantId,
    UnitId,
    UserId,
)

# Ordem total do port (`L-ORD`). As duas colunas levam a colação explícita — ver
# o docstring do módulo.
_TOTAL_ORDER = (
    employees.c.name.collate("C"),
    employees.c.id.collate("C"),
)

# Colunas que **nunca** entram no `SET` de um `UPDATE`, e cada uma por uma lei
# diferente: `id` é a identidade; `tenant_id` não é atualizável (§5.3); `unit_id`
# é imutável (L-E3) e já foi conferido contra o gravado — deixá-lo no `SET`
# tornaria "mover o funcionário de unidade" um estado produzível por uma escrita
# que se parece com uma edição de cadastro.
_IMMUTABLE_COLUMNS = frozenset({"id", "tenant_id", "unit_id"})

# Colunas que o `update` também não grava, mas por outro motivo: têm escrita
# **própria** no port. `user_id` é escrito só por `link_login` (`L-LINK`, issue
# #68): no `SET` do `update`, uma entidade lida antes de um vínculo concorrente
# apagaria o vínculo gravado depois dela — e a conta criada em identity ficaria
# órfã. Não é imutável (nasce `NULL` e é definido uma vez); só não é deste
# método.
_COLUMNS_WITH_OWN_WRITE = frozenset({"user_id"})

# `REPEATABLE READ` nas leituras de agregado (§5.18) — ver a nota 4 do docstring.
_SINGLE_SNAPSHOT = "REPEATABLE READ"


class PostgresEmployeeRepository:
    """Implementação PostgreSQL do port `EmployeeRepository`."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    # ---- escrita ----------------------------------------------------------

    def add(self, employee: Employee) -> None:
        """L-E1 (inserção, id global) + L-E4 (validade referencial), nesta ordem."""
        try:
            with self._engine.begin() as connection:
                self._add(connection, employee)
        except IntegrityError as error:
            # `from error` preserva a cadeia de causa: sem ela, o diagnóstico de
            # um conflito de integridade perde o SQL e a constraint originais.
            raise translate(
                error, ON_WRITE_EMPLOYEE, self._conflict_detail(error, employee)
            ) from error

    def update(self, employee: Employee) -> None:
        """L-E2 (`UPDATE`, não upsert) + L-E3 (localização imutável) + L-E4.

        A ordem das três é o contrato, não detalhe: existência no tenant,
        depois unidade, depois conjunto de funções — e as três guardas rodam na
        **mesma** transação da escrita, senão a ordem é decorativa sob
        concorrência (§5.4).
        """
        try:
            with self._engine.begin() as connection:
                self._update(connection, employee)
        except IntegrityError as error:
            raise translate(
                error, ON_WRITE_EMPLOYEE, self._conflict_detail(error, employee)
            ) from error

    def link_login(
        self, tenant_id: TenantId, unit_id: UnitId, employee_id: EmployeeId, user_id: UserId
    ) -> None:
        """`L-LINK` — o vínculo, só se o **gravado** ainda não tiver um (issue #68).

        Checagem e escrita numa transação só, com a linha do registro presa por
        `FOR UPDATE` **antes** das guardas — a mesma forma do `update` (nota 2
        do módulo). Sem o lock, dois R17 concorrentes leriam os dois "sem
        vínculo" e o segundo `UPDATE` trocaria o do primeiro em silêncio.

        As guardas são as do **domínio**, sobre o agregado gravado: o registro
        é remontado sob o lock e passa por `Employee.link_login`, que chama
        `assert_can_link_login` (vinculado > desligado) e revalida o `user_id`
        no `__post_init__`. É a mesma casa que o fake usa — reescrever a
        precedência aqui em `if`s sobre colunas abriria a segunda fonte, e a
        divergência fake ≢ real que a suíte de contrato existe para impedir.

        **A remontagem roda em `READ COMMITTED`, e não sob o snapshot único da
        nota 4** — de propósito. A linha-pai está presa, e todo escritor das
        filhas (`update`, `delete`) toma esse mesmo lock antes, então nenhuma
        escrita comita entre os quatro statements. `REPEATABLE READ` junto do
        `FOR UPDATE` trocaria a espera do segundo R17 por erro de serialização
        (`40001`) em vez de uma releitura do vínculo já gravado (ADR 0.0.0010).

        O `UPDATE` grava **só** `user_id`. O `WHERE user_id IS NULL` que a issue
        sugeria seria redundante sob o lock: nenhuma escrita concorrente alcança
        a linha entre a guarda e a escrita.
        """
        with self._engine.begin() as connection:
            row = connection.execute(
                select(employees)
                .where(
                    employees.c.id == employee_id,
                    employees.c.tenant_id == tenant_id,
                    employees.c.unit_id == unit_id,
                )
                .with_for_update()
            ).one_or_none()
            if row is None:
                raise EmployeeNotFoundError(employee_id)
            linked = self._build_aggregates(connection, [row])[0].link_login(user_id)
            connection.execute(
                employees.update()
                .where(
                    employees.c.id == employee_id,
                    employees.c.tenant_id == tenant_id,
                )
                .values(user_id=linked.user_id)
            )

    def delete(self, tenant_id: TenantId, unit_id: UnitId, employee_id: EmployeeId) -> None:
        """L-E5 — remoção definitiva; as filhas somem por `CASCADE` (§5.10).

        O `WHERE` traz o endereço de **três** partes (ADR 3.4.0007): registro de
        outra unidade do mesmo tenant não é alcançado, e o lookup vazio o
        reporta como `EmployeeNotFoundError` — o mesmo erro do registro de outro
        tenant, sem distinção observável.

        **`L-DEL-LINK` — a guarda do vínculo decide sob o lock** (issue #108,
        ADR 0.0.0013). O lookup é `SELECT user_id … FOR UPDATE` no endereço, e
        só depois vêm a guarda e o `DELETE`, na mesma transação — a forma de
        `link_login` e do `update` (nota 2 do módulo). Um R17 que vincula antes
        do lock é visto (o `FOR UPDATE` espera o commit dele e relê a linha);
        um que chega depois espera esta remoção e encontra o registro sumido.
        Sem o lock, o `DELETE` apagaria um registro vinculado entre a leitura do
        use case e a escrita, e a conta criada em identity ficaria órfã.

        Antes da #108 o `rowcount` do `DELETE` era a checagem de existência; sob
        o lock a linha não some entre o lookup e a escrita, e o `rowcount` deixou
        de carregar informação.

        **`EmployeeInUseError` não tem produtor em v1** e isso é declarado, não
        esquecido: nada no escopo atual referencia o registro de funcionário.
        Quem passa a produzi-lo é o Step 4 (alocação), pela FK que ele
        acrescentar — e é lá que um `ON_DELETE_EMPLOYEE` entra neste arquivo.
        Por isso não há tradução aqui: uma `IntegrityError` neste `DELETE` hoje
        é bug, e vesti-la de erro de negócio esconderia o defeito.
        """
        with self._engine.begin() as connection:
            row = connection.execute(
                select(employees.c.user_id)
                .where(
                    employees.c.id == employee_id,
                    employees.c.tenant_id == tenant_id,
                    employees.c.unit_id == unit_id,
                )
                .with_for_update()
            ).one_or_none()
            if row is None:
                raise EmployeeNotFoundError(employee_id)
            if row.user_id is not None:
                raise EmployeeHasLoginError(employee_id)
            connection.execute(
                employees.delete().where(
                    employees.c.id == employee_id,
                    employees.c.tenant_id == tenant_id,
                )
            )

    # ---- leitura ----------------------------------------------------------

    def find_by_id(
        self, tenant_id: TenantId, unit_id: UnitId, employee_id: EmployeeId
    ) -> Employee | None:
        """Registro **do tenant e da unidade**, ou `None`. Não filtra por estado
        (ADR 3.2.0006).

        O `WHERE` traz o endereço de **três** partes (ADR 3.4.0007), e o `None`
        de "outra unidade" é indistinguível do `None` de "não existe": a lei
        nasceu na docstring do `Protocol`, e este `WHERE` a implementa — não o
        contrário.

        Sob snapshot único (§5.18): os quatro statements que montam o agregado
        enxergam **o mesmo** estado do banco.
        """
        with self._in_single_snapshot() as connection:
            row = connection.execute(
                select(employees).where(
                    employees.c.id == employee_id,
                    employees.c.tenant_id == tenant_id,
                    employees.c.unit_id == unit_id,
                )
            ).one_or_none()
            if row is None:
                return None
            return self._build_aggregates(connection, [row])[0]

    def list_by_unit(
        self, tenant_id: TenantId, unit_id: UnitId, *, include_inactive: bool = False
    ) -> tuple[Employee, ...]:
        """L-E6 — só a unidade pedida, só ativos por default; `L-ORD` — em ordem total."""
        conditions = [
            employees.c.tenant_id == tenant_id,
            employees.c.unit_id == unit_id,
        ]
        if not include_inactive:
            # No SQL, não em Python — ver a nota 6 do docstring do módulo.
            conditions.append(employees.c.active.is_(True))
        with self._in_single_snapshot() as connection:
            rows = connection.execute(
                select(employees).where(*conditions).order_by(*_TOTAL_ORDER)
            ).all()
            return self._build_aggregates(connection, rows)

    def exists_by_job_function(self, tenant_id: TenantId, job_function_id: JobFunctionId) -> bool:
        """L-E7 — tenant-wide, **sem join e sem filtro de `active`** (§5.16).

        A ausência do filtro é a lei: o desligado ainda aponta para a função, e
        apagá-la deixaria o cadastro dele apontando para função inexistente. E a
        ausência do join com `employees` não é otimização — é o que mantém a
        consulta sobre a tabela de vínculo, que é onde a referência vive.
        """
        with self._engine.connect() as connection:
            found = connection.execute(
                select(
                    exists().where(
                        employee_job_functions.c.tenant_id == tenant_id,
                        employee_job_functions.c.job_function_id == job_function_id,
                    )
                )
            ).scalar_one()
        return bool(found)

    def units_referencing_job_function(
        self, tenant_id: TenantId, job_function_id: JobFunctionId
    ) -> frozenset[UnitId]:
        """L-E8 — unidades dos registros que detêm a função, **sem filtro de `active`**.

        Aqui o join com `employees` é necessário — a unidade mora no registro, não
        no vínculo —, e o par `(employee_id, tenant_id)` é o da FK composta: o join
        não alcança registro de outro tenant nem por coincidência de id.
        """
        with self._engine.connect() as connection:
            rows = connection.execute(
                select(employees.c.unit_id)
                .distinct()
                .select_from(
                    employee_job_functions.join(
                        employees,
                        (employees.c.id == employee_job_functions.c.employee_id)
                        & (employees.c.tenant_id == employee_job_functions.c.tenant_id),
                    )
                )
                .where(
                    employee_job_functions.c.tenant_id == tenant_id,
                    employee_job_functions.c.job_function_id == job_function_id,
                )
            ).all()
        return frozenset(UnitId(row.unit_id) for row in rows)

    # ---- núcleo sobre `Connection` (ponto de troca para um futuro UoW) -----

    def _add(self, connection: Connection, employee: Employee) -> None:
        self._guard_free_id(connection, employee.id)
        self._guard_job_functions(connection, employee)
        connection.execute(employees.insert().values(**mappers.employee_to_row(employee)))
        self._insert_children(connection, employee)

    def _update(self, connection: Connection, employee: Employee) -> None:
        # (1) Lookup por `(tenant_id, id)`, com `FOR UPDATE`. Precede a
        # comparação de unidade DE PROPÓSITO (§5.4 vence a L-E3): com tenant
        # alheio o registro não existe naquele escopo, e responder
        # `EmployeeRelocationError` confirmaria a existência do registro de
        # outro restaurante — e ainda vazaria a unidade dele na mensagem.
        stored = connection.execute(
            select(employees.c.unit_id)
            .where(
                employees.c.id == employee.id,
                employees.c.tenant_id == employee.tenant_id,
            )
            .with_for_update()
        ).one_or_none()
        if stored is None:
            raise EmployeeNotFoundError(employee.id)
        # (2) Localização imutável — erro INTRA-tenant (L-E3).
        if stored.unit_id != employee.unit_id:
            raise EmployeeRelocationError(employee.id, stored.unit_id, employee.unit_id)
        # (3) Validade referencial do conjunto (L-E4).
        self._guard_job_functions(connection, employee)

        mutable = {
            column: value
            for column, value in mappers.employee_to_row(employee).items()
            if column not in _IMMUTABLE_COLUMNS | _COLUMNS_WITH_OWN_WRITE
        }
        connection.execute(
            employees.update()
            .where(
                employees.c.id == employee.id,
                employees.c.tenant_id == employee.tenant_id,
            )
            .values(**mutable)
        )
        self._sync_children(connection, employee)

    # ---- guardas ----------------------------------------------------------

    @staticmethod
    def _guard_free_id(connection: Connection, employee_id: EmployeeId) -> None:
        """L-E1 — colisão de id, checada **globalmente** e **antes** de L-E4.

        Sem `tenant_id` no `WHERE`: a PK não o inclui, e um lookup escopado
        aceitaria aqui uma inserção que o `INSERT` seguinte rejeitaria — com o
        erro certo, mas depois de a pré-checagem referencial já ter respondido
        outro (§5.5).
        """
        found = connection.execute(
            select(employees.c.id).where(employees.c.id == employee_id)
        ).one_or_none()
        if found is not None:
            raise EmployeeAlreadyExistsError(employee_id)

    @staticmethod
    def _guard_job_functions(connection: Connection, employee: Employee) -> None:
        """L-E4 — toda id do conjunto existe **no mesmo tenant**.

        Id existente em outro tenant conta como **ausente**: a resolução é
        escopada, e a alternativa vazaria a existência da função alheia.

        Uma ida ao banco só, e a iteração de report em `sorted()`: a menor id
        ausente em ordem lexicográfica é a reportada, **deterministicamente**
        (§5.15). O conjunto nunca é vazio — `Employee` recusa isso na
        construção (`EmptyJobFunctionsError`) —, então não há caminho de
        `IN ()` a defender.
        """
        requested = sorted(employee.job_function_ids)
        existing = {
            row.id
            for row in connection.execute(
                select(job_functions.c.id).where(
                    job_functions.c.tenant_id == employee.tenant_id,
                    job_functions.c.id.in_(requested),
                )
            ).all()
        }
        for job_function_id in requested:
            if job_function_id not in existing:
                raise JobFunctionNotFoundError(job_function_id)

    # ---- filhas: inserção e sincronização por diferença --------------------

    @staticmethod
    def _insert_children(connection: Connection, employee: Employee) -> None:
        """As três filhas de um agregado novo.

        O `executemany` do SQLAlchemy recusa lista vazia, e duas das três podem
        legitimamente ser vazias (sem indisponibilidade, sem preferência) — a de
        vínculos nunca é, porque o conjunto de funções é não-vazio por
        invariante de `Employee`.
        """
        connection.execute(
            employee_job_functions.insert(), mappers.job_function_link_rows(employee)
        )
        periods = mappers.unavailability_rows(employee)
        if periods:
            connection.execute(employee_unavailabilities.insert(), periods)
        preferences = mappers.shift_preference_rows(employee)
        if preferences:
            connection.execute(employee_shift_preferences.insert(), preferences)

    def _sync_children(self, connection: Connection, employee: Employee) -> None:
        """Escrita por **diferença** nas três filhas — ver a nota 3 do módulo.

        A regra é a mesma nas três: apaga só o que saiu, insere só o que entrou,
        e **não emite statement nenhum** quando nada mudou. O `DELETE` vem antes
        do `INSERT` porque as chaves podem se cruzar: um período cujo `end`
        mudou tem o mesmo `start_at` (que é a PK) na linha velha e na nova.
        """
        self._sync_job_functions(connection, employee)
        self._sync_unavailabilities(connection, employee)
        self._sync_shift_preference(connection, employee)

    @staticmethod
    def _sync_job_functions(connection: Connection, employee: Employee) -> None:
        stored_ids = {
            JobFunctionId(row.job_function_id)
            for row in connection.execute(
                select(employee_job_functions.c.job_function_id).where(
                    employee_job_functions.c.employee_id == employee.id
                )
            ).all()
        }
        removed_ids = stored_ids - employee.job_function_ids
        added_ids = employee.job_function_ids - stored_ids
        if removed_ids:
            connection.execute(
                employee_job_functions.delete().where(
                    employee_job_functions.c.employee_id == employee.id,
                    employee_job_functions.c.job_function_id.in_(sorted(removed_ids)),
                )
            )
        if added_ids:
            # Filtra as linhas do mapper em vez de montá-las aqui: é lá que vive
            # a denormalização do `tenant_id` ancorada pelas duas FKs compostas,
            # e reescrevê-la aqui criaria a segunda fonte.
            connection.execute(
                employee_job_functions.insert(),
                [
                    row
                    for row in mappers.job_function_link_rows(employee)
                    if row["job_function_id"] in added_ids
                ],
            )

    @staticmethod
    def _sync_unavailabilities(connection: Connection, employee: Employee) -> None:
        stored_keys = {
            (row.start_at, row.end_at)
            for row in connection.execute(
                select(employee_unavailabilities).where(
                    employee_unavailabilities.c.employee_id == employee.id
                )
            ).all()
        }
        desired_keys = {(period.start, period.end) for period in employee.unavailabilities}
        removed_keys = stored_keys - desired_keys
        added_keys = desired_keys - stored_keys
        if removed_keys:
            connection.execute(
                employee_unavailabilities.delete().where(
                    employee_unavailabilities.c.employee_id == employee.id,
                    # Por `start_at`, que é a PK junto do funcionário.
                    employee_unavailabilities.c.start_at.in_(
                        sorted(start for start, _ in removed_keys)
                    ),
                )
            )
        if added_keys:
            connection.execute(
                employee_unavailabilities.insert(),
                [
                    row
                    for row in mappers.unavailability_rows(employee)
                    if (row["start_at"], row["end_at"]) in added_keys
                ],
            )

    @staticmethod
    def _sync_shift_preference(connection: Connection, employee: Employee) -> None:
        stored_keys = {
            row.period
            for row in connection.execute(
                select(employee_shift_preferences.c.period).where(
                    employee_shift_preferences.c.employee_id == employee.id
                )
            ).all()
        }
        desired_rows = mappers.shift_preference_rows(employee)
        desired_keys = {row["period"] for row in desired_rows}
        removed_keys = stored_keys - desired_keys
        added_keys = desired_keys - stored_keys
        if removed_keys:
            connection.execute(
                employee_shift_preferences.delete().where(
                    employee_shift_preferences.c.employee_id == employee.id,
                    employee_shift_preferences.c.period.in_(sorted(removed_keys)),
                )
            )
        if added_keys:
            connection.execute(
                employee_shift_preferences.insert(),
                [row for row in desired_rows if row["period"] in added_keys],
            )

    # ---- montagem do agregado ---------------------------------------------

    @contextmanager
    def _in_single_snapshot(self) -> Iterator[Connection]:
        """Conexão em `REPEATABLE READ`, com a transação aberta explicitamente.

        O nível é execution option da **conexão** e precisa ser posto antes de
        qualquer statement; o `begin()` explícito existe para que a fronteira do
        snapshot esteja escrita, e não implícita no autobegin (§5.18).
        """
        with (
            self._engine.connect().execution_options(
                isolation_level=_SINGLE_SNAPSHOT
            ) as connection,
            connection.begin(),
        ):
            yield connection

    @staticmethod
    def _build_aggregates(
        connection: Connection, rows: Sequence[mappers.Row]
    ) -> tuple[Employee, ...]:
        """Monta N agregados em **quatro** statements, não em `1 + 3N`.

        `find_by_id` passa por aqui com uma linha só de propósito: um segundo
        caminho de montagem seria um segundo lugar onde a ordem dos períodos, ou
        o `None` de preferência ausente, poderiam divergir entre a leitura
        singular e a listagem — e a divergência apareceria como bug de
        apresentação, não como falha de teste.
        """
        if not rows:
            return ()
        ids = [row.id for row in rows]

        function_ids: dict[str, list[str]] = defaultdict(list)
        for link in connection.execute(
            select(
                employee_job_functions.c.employee_id,
                employee_job_functions.c.job_function_id,
            ).where(employee_job_functions.c.employee_id.in_(ids))
        ).all():
            function_ids[link.employee_id].append(link.job_function_id)

        # `ORDER BY start_at` é a cláusula normativa (§5.13); agrupar por
        # `append` preserva essa ordem dentro de cada funcionário.
        periods: dict[str, list[mappers.Row]] = defaultdict(list)
        for period in connection.execute(
            select(employee_unavailabilities)
            .where(employee_unavailabilities.c.employee_id.in_(ids))
            .order_by(employee_unavailabilities.c.start_at)
        ).all():
            periods[period.employee_id].append(period)

        preferences: dict[str, list[str]] = defaultdict(list)
        for preference in connection.execute(
            select(
                employee_shift_preferences.c.employee_id,
                employee_shift_preferences.c.period,
            ).where(employee_shift_preferences.c.employee_id.in_(ids))
        ).all():
            preferences[preference.employee_id].append(preference.period)

        return tuple(
            mappers.row_to_employee(
                row,
                job_function_ids=function_ids[row.id],
                unavailabilities=periods[row.id],
                shift_periods=preferences[row.id],
            )
            for row in rows
        )

    @staticmethod
    def _conflict_detail(error: IntegrityError, employee: Employee) -> str:
        """Qual valor entra na mensagem depende de **qual** regra foi violada.

        `translate` recebe um `detail` só (contrato do concept §4), e as
        constraints alcançáveis por uma escrita de funcionário conflitam em
        coisas diferentes: as de identidade, no id do funcionário; a FK de
        vínculo, no conjunto de funções.

        No caso da FK — o **backstop** de L-E4, alcançável só quando a função
        some entre a pré-checagem e a escrita — o adapter **não sabe qual** id
        sumiu na corrida: o Postgres reporta a constraint, não o valor. Reportar
        um palpite seria descrever o conflito errado com a confiança de quem
        sabe; a mensagem cita o **conjunto**, renderizado com `sorted()`
        (§5.15). É essa diferença de forma — id exato contra conjunto — que torna
        observável qual das duas camadas de guarda respondeu (CA8c).
        """
        if constraint_name(error) == "fk_employee_job_functions_job_function":
            return str(sorted(employee.job_function_ids))
        return employee.id
