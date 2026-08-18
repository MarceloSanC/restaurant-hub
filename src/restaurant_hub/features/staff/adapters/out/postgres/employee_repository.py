"""Adapter Postgres de `EmployeeRepository` — L-E1…L-E7, `L-ORD` e a atomicidade das duas pontas.

O repositório com regra de verdade desta Stage: agregado de **quatro** tabelas,
ordem de checagem normativa e a atomicidade que a §5.18/§5.20 fecham nas duas
pontas — escrita **e** leitura.

**Fronteira transacional** (D8; precedente literal do concept 2.3 §7 Decisão 6):
o repositório recebe um `Engine` e abre a própria transação por método público.
A skill `repository-pattern` recomenda o oposto — transação controlada por um
unit-of-work externo —, e o desvio é o mesmo que identity assumiu, pela mesma
razão: os ports da 3.2 são síncronos e sem UoW, `application` está proibida de
importar SQLAlchemy (contrato `staff-application-purity`) e nenhum use case
desta Stage precisa de atomicidade **entre** repositórios. O núcleo reusado
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
)

# Ordem total do port (`L-ORD`). As duas colunas levam a colação explícita — ver
# o docstring do módulo.
_ORDEM_TOTAL = (
    employees.c.name.collate("C"),
    employees.c.id.collate("C"),
)

# Colunas que **nunca** entram no `SET` de um `UPDATE`, e cada uma por uma lei
# diferente: `id` é a identidade; `tenant_id` não é atualizável (§5.3); `unit_id`
# é imutável (L-E3) e já foi conferido contra o gravado — deixá-lo no `SET`
# tornaria "mover o funcionário de unidade" um estado produzível por uma escrita
# que se parece com uma edição de cadastro.
_COLUNAS_IMUTAVEIS = frozenset({"id", "tenant_id", "unit_id"})

# `REPEATABLE READ` nas leituras de agregado (§5.18) — ver a nota 4 do docstring.
_SNAPSHOT_UNICO = "REPEATABLE READ"


class PostgresEmployeeRepository:
    """Implementação PostgreSQL do port `EmployeeRepository`."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    # ---- escrita ----------------------------------------------------------

    def add(self, employee: Employee) -> None:
        """L-E1 (inserção, id global) + L-E4 (validade referencial), nesta ordem."""
        try:
            with self._engine.begin() as conexao:
                self._add(conexao, employee)
        except IntegrityError as erro:
            # `from erro` preserva a cadeia de causa: sem ela, o diagnóstico de
            # um conflito de integridade perde o SQL e a constraint originais.
            raise translate(
                erro, ON_WRITE_EMPLOYEE, self._detalhe_do_conflito(erro, employee)
            ) from erro

    def update(self, employee: Employee) -> None:
        """L-E2 (`UPDATE`, não upsert) + L-E3 (localização imutável) + L-E4.

        A ordem das três é o contrato, não detalhe: existência no tenant,
        depois unidade, depois conjunto de funções — e as três guardas rodam na
        **mesma** transação da escrita, senão a ordem é decorativa sob
        concorrência (§5.4).
        """
        try:
            with self._engine.begin() as conexao:
                self._update(conexao, employee)
        except IntegrityError as erro:
            raise translate(
                erro, ON_WRITE_EMPLOYEE, self._detalhe_do_conflito(erro, employee)
            ) from erro

    def delete(self, tenant_id: TenantId, unit_id: UnitId, employee_id: EmployeeId) -> None:
        """L-E5 — remoção definitiva; as filhas somem por `CASCADE` (§5.10).

        O `WHERE` traz o endereço de **três** partes (ADR 3.4.0007): registro de
        outra unidade do mesmo tenant não é alcançado, e o `rowcount` zero o
        reporta como `EmployeeNotFoundError` — o mesmo erro do registro de outro
        tenant, sem distinção observável.

        O `rowcount` do próprio `DELETE` é a checagem: um `SELECT` antes tornaria
        checagem e escrita duas operações, e entre elas o registro poderia sumir
        (precedente literal do `set_password_hash` de identity).

        **`EmployeeInUseError` não tem produtor em v1** e isso é declarado, não
        esquecido: nada no escopo atual referencia o registro de funcionário.
        Quem passa a produzi-lo é o Step 4 (alocação), pela FK que ele
        acrescentar — e é lá que um `ON_DELETE_EMPLOYEE` entra neste arquivo.
        Por isso não há tradução aqui: uma `IntegrityError` neste `DELETE` hoje
        é bug, e vesti-la de erro de negócio esconderia o defeito.
        """
        with self._engine.begin() as conexao:
            resultado = conexao.execute(
                employees.delete().where(
                    employees.c.id == employee_id,
                    employees.c.tenant_id == tenant_id,
                    employees.c.unit_id == unit_id,
                )
            )
            if resultado.rowcount == 0:
                raise EmployeeNotFoundError(employee_id)

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
        with self._sob_snapshot_unico() as conexao:
            linha = conexao.execute(
                select(employees).where(
                    employees.c.id == employee_id,
                    employees.c.tenant_id == tenant_id,
                    employees.c.unit_id == unit_id,
                )
            ).one_or_none()
            if linha is None:
                return None
            return self._montar_agregados(conexao, [linha])[0]

    def list_by_unit(
        self, tenant_id: TenantId, unit_id: UnitId, *, include_inactive: bool = False
    ) -> tuple[Employee, ...]:
        """L-E6 — só a unidade pedida, só ativos por default; `L-ORD` — em ordem total."""
        condicoes = [
            employees.c.tenant_id == tenant_id,
            employees.c.unit_id == unit_id,
        ]
        if not include_inactive:
            # No SQL, não em Python — ver a nota 6 do docstring do módulo.
            condicoes.append(employees.c.active.is_(True))
        with self._sob_snapshot_unico() as conexao:
            linhas = conexao.execute(
                select(employees).where(*condicoes).order_by(*_ORDEM_TOTAL)
            ).all()
            return self._montar_agregados(conexao, linhas)

    def exists_by_job_function(self, tenant_id: TenantId, job_function_id: JobFunctionId) -> bool:
        """L-E7 — tenant-wide, **sem join e sem filtro de `active`** (§5.16).

        A ausência do filtro é a lei: o desligado ainda aponta para a função, e
        apagá-la deixaria o cadastro dele apontando para função inexistente. E a
        ausência do join com `employees` não é otimização — é o que mantém a
        consulta sobre a tabela de vínculo, que é onde a referência vive.
        """
        with self._engine.connect() as conexao:
            achado = conexao.execute(
                select(
                    exists().where(
                        employee_job_functions.c.tenant_id == tenant_id,
                        employee_job_functions.c.job_function_id == job_function_id,
                    )
                )
            ).scalar_one()
        return bool(achado)

    # ---- núcleo sobre `Connection` (ponto de troca para um futuro UoW) -----

    def _add(self, conexao: Connection, employee: Employee) -> None:
        self._guard_id_livre(conexao, employee.id)
        self._guard_job_functions(conexao, employee)
        conexao.execute(employees.insert().values(**mappers.employee_to_row(employee)))
        self._inserir_filhas(conexao, employee)

    def _update(self, conexao: Connection, employee: Employee) -> None:
        # (1) Lookup por `(tenant_id, id)`, com `FOR UPDATE`. Precede a
        # comparação de unidade DE PROPÓSITO (§5.4 vence a L-E3): com tenant
        # alheio o registro não existe naquele escopo, e responder
        # `EmployeeRelocationError` confirmaria a existência do registro de
        # outro restaurante — e ainda vazaria a unidade dele na mensagem.
        gravado = conexao.execute(
            select(employees.c.unit_id)
            .where(
                employees.c.id == employee.id,
                employees.c.tenant_id == employee.tenant_id,
            )
            .with_for_update()
        ).one_or_none()
        if gravado is None:
            raise EmployeeNotFoundError(employee.id)
        # (2) Localização imutável — erro INTRA-tenant (L-E3).
        if gravado.unit_id != employee.unit_id:
            raise EmployeeRelocationError(employee.id, gravado.unit_id, employee.unit_id)
        # (3) Validade referencial do conjunto (L-E4).
        self._guard_job_functions(conexao, employee)

        mutaveis = {
            coluna: valor
            for coluna, valor in mappers.employee_to_row(employee).items()
            if coluna not in _COLUNAS_IMUTAVEIS
        }
        conexao.execute(
            employees.update()
            .where(
                employees.c.id == employee.id,
                employees.c.tenant_id == employee.tenant_id,
            )
            .values(**mutaveis)
        )
        self._sincronizar_filhas(conexao, employee)

    # ---- guardas ----------------------------------------------------------

    @staticmethod
    def _guard_id_livre(conexao: Connection, employee_id: EmployeeId) -> None:
        """L-E1 — colisão de id, checada **globalmente** e **antes** de L-E4.

        Sem `tenant_id` no `WHERE`: a PK não o inclui, e um lookup escopado
        aceitaria aqui uma inserção que o `INSERT` seguinte rejeitaria — com o
        erro certo, mas depois de a pré-checagem referencial já ter respondido
        outro (§5.5).
        """
        achado = conexao.execute(
            select(employees.c.id).where(employees.c.id == employee_id)
        ).one_or_none()
        if achado is not None:
            raise EmployeeAlreadyExistsError(employee_id)

    @staticmethod
    def _guard_job_functions(conexao: Connection, employee: Employee) -> None:
        """L-E4 — toda id do conjunto existe **no mesmo tenant**.

        Id existente em outro tenant conta como **ausente**: a resolução é
        escopada, e a alternativa vazaria a existência da função alheia.

        Uma ida ao banco só, e a iteração de report em `sorted()`: a menor id
        ausente em ordem lexicográfica é a reportada, **deterministicamente**
        (§5.15). O conjunto nunca é vazio — `Employee` recusa isso na
        construção (`EmptyJobFunctionsError`) —, então não há caminho de
        `IN ()` a defender.
        """
        pedidas = sorted(employee.job_function_ids)
        existentes = {
            linha.id
            for linha in conexao.execute(
                select(job_functions.c.id).where(
                    job_functions.c.tenant_id == employee.tenant_id,
                    job_functions.c.id.in_(pedidas),
                )
            ).all()
        }
        for job_function_id in pedidas:
            if job_function_id not in existentes:
                raise JobFunctionNotFoundError(job_function_id)

    # ---- filhas: inserção e sincronização por diferença --------------------

    @staticmethod
    def _inserir_filhas(conexao: Connection, employee: Employee) -> None:
        """As três filhas de um agregado novo.

        O `executemany` do SQLAlchemy recusa lista vazia, e duas das três podem
        legitimamente ser vazias (sem indisponibilidade, sem preferência) — a de
        vínculos nunca é, porque o conjunto de funções é não-vazio por
        invariante de `Employee`.
        """
        conexao.execute(employee_job_functions.insert(), mappers.job_function_link_rows(employee))
        periodos = mappers.unavailability_rows(employee)
        if periodos:
            conexao.execute(employee_unavailabilities.insert(), periodos)
        preferencias = mappers.shift_preference_rows(employee)
        if preferencias:
            conexao.execute(employee_shift_preferences.insert(), preferencias)

    def _sincronizar_filhas(self, conexao: Connection, employee: Employee) -> None:
        """Escrita por **diferença** nas três filhas — ver a nota 3 do módulo.

        A regra é a mesma nas três: apaga só o que saiu, insere só o que entrou,
        e **não emite statement nenhum** quando nada mudou. O `DELETE` vem antes
        do `INSERT` porque as chaves podem se cruzar: um período cujo `end`
        mudou tem o mesmo `start_at` (que é a PK) na linha velha e na nova.
        """
        self._sincronizar_funcoes(conexao, employee)
        self._sincronizar_indisponibilidades(conexao, employee)
        self._sincronizar_preferencia(conexao, employee)

    @staticmethod
    def _sincronizar_funcoes(conexao: Connection, employee: Employee) -> None:
        gravadas = {
            JobFunctionId(linha.job_function_id)
            for linha in conexao.execute(
                select(employee_job_functions.c.job_function_id).where(
                    employee_job_functions.c.employee_id == employee.id
                )
            ).all()
        }
        removidas = gravadas - employee.job_function_ids
        acrescentadas = employee.job_function_ids - gravadas
        if removidas:
            conexao.execute(
                employee_job_functions.delete().where(
                    employee_job_functions.c.employee_id == employee.id,
                    employee_job_functions.c.job_function_id.in_(sorted(removidas)),
                )
            )
        if acrescentadas:
            # Filtra as linhas do mapper em vez de montá-las aqui: é lá que vive
            # a denormalização do `tenant_id` ancorada pelas duas FKs compostas,
            # e reescrevê-la aqui criaria a segunda fonte.
            conexao.execute(
                employee_job_functions.insert(),
                [
                    linha
                    for linha in mappers.job_function_link_rows(employee)
                    if linha["job_function_id"] in acrescentadas
                ],
            )

    @staticmethod
    def _sincronizar_indisponibilidades(conexao: Connection, employee: Employee) -> None:
        gravados = {
            (linha.start_at, linha.end_at)
            for linha in conexao.execute(
                select(employee_unavailabilities).where(
                    employee_unavailabilities.c.employee_id == employee.id
                )
            ).all()
        }
        desejados = {(periodo.start, periodo.end) for periodo in employee.unavailabilities}
        removidos = gravados - desejados
        acrescentados = desejados - gravados
        if removidos:
            conexao.execute(
                employee_unavailabilities.delete().where(
                    employee_unavailabilities.c.employee_id == employee.id,
                    # Por `start_at`, que é a PK junto do funcionário.
                    employee_unavailabilities.c.start_at.in_(
                        sorted(inicio for inicio, _ in removidos)
                    ),
                )
            )
        if acrescentados:
            conexao.execute(
                employee_unavailabilities.insert(),
                [
                    linha
                    for linha in mappers.unavailability_rows(employee)
                    if (linha["start_at"], linha["end_at"]) in acrescentados
                ],
            )

    @staticmethod
    def _sincronizar_preferencia(conexao: Connection, employee: Employee) -> None:
        gravados = {
            linha.period
            for linha in conexao.execute(
                select(employee_shift_preferences.c.period).where(
                    employee_shift_preferences.c.employee_id == employee.id
                )
            ).all()
        }
        linhas_desejadas = mappers.shift_preference_rows(employee)
        desejados = {linha["period"] for linha in linhas_desejadas}
        removidos = gravados - desejados
        acrescentados = desejados - gravados
        if removidos:
            conexao.execute(
                employee_shift_preferences.delete().where(
                    employee_shift_preferences.c.employee_id == employee.id,
                    employee_shift_preferences.c.period.in_(sorted(removidos)),
                )
            )
        if acrescentados:
            conexao.execute(
                employee_shift_preferences.insert(),
                [linha for linha in linhas_desejadas if linha["period"] in acrescentados],
            )

    # ---- montagem do agregado ---------------------------------------------

    @contextmanager
    def _sob_snapshot_unico(self) -> Iterator[Connection]:
        """Conexão em `REPEATABLE READ`, com a transação aberta explicitamente.

        O nível é execution option da **conexão** e precisa ser posto antes de
        qualquer statement; o `begin()` explícito existe para que a fronteira do
        snapshot esteja escrita, e não implícita no autobegin (§5.18).
        """
        with (
            self._engine.connect().execution_options(isolation_level=_SNAPSHOT_UNICO) as conexao,
            conexao.begin(),
        ):
            yield conexao

    @staticmethod
    def _montar_agregados(
        conexao: Connection, linhas: Sequence[mappers.Row]
    ) -> tuple[Employee, ...]:
        """Monta N agregados em **quatro** statements, não em `1 + 3N`.

        `find_by_id` passa por aqui com uma linha só de propósito: um segundo
        caminho de montagem seria um segundo lugar onde a ordem dos períodos, ou
        o `None` de preferência ausente, poderiam divergir entre a leitura
        singular e a listagem — e a divergência apareceria como bug de
        apresentação, não como falha de teste.
        """
        if not linhas:
            return ()
        ids = [linha.id for linha in linhas]

        funcoes: dict[str, list[str]] = defaultdict(list)
        for vinculo in conexao.execute(
            select(
                employee_job_functions.c.employee_id,
                employee_job_functions.c.job_function_id,
            ).where(employee_job_functions.c.employee_id.in_(ids))
        ).all():
            funcoes[vinculo.employee_id].append(vinculo.job_function_id)

        # `ORDER BY start_at` é a cláusula normativa (§5.13); agrupar por
        # `append` preserva essa ordem dentro de cada funcionário.
        periodos: dict[str, list[mappers.Row]] = defaultdict(list)
        for periodo in conexao.execute(
            select(employee_unavailabilities)
            .where(employee_unavailabilities.c.employee_id.in_(ids))
            .order_by(employee_unavailabilities.c.start_at)
        ).all():
            periodos[periodo.employee_id].append(periodo)

        preferencias: dict[str, list[str]] = defaultdict(list)
        for preferencia in conexao.execute(
            select(
                employee_shift_preferences.c.employee_id,
                employee_shift_preferences.c.period,
            ).where(employee_shift_preferences.c.employee_id.in_(ids))
        ).all():
            preferencias[preferencia.employee_id].append(preferencia.period)

        return tuple(
            mappers.row_to_employee(
                linha,
                job_function_ids=funcoes[linha.id],
                unavailabilities=periodos[linha.id],
                shift_periods=preferencias[linha.id],
            )
            for linha in linhas
        )

    @staticmethod
    def _detalhe_do_conflito(erro: IntegrityError, employee: Employee) -> str:
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
        if constraint_name(erro) == "fk_employee_job_functions_job_function":
            return str(sorted(employee.job_function_ids))
        return employee.id
