"""Fake in-memory de `JobFunctionRepository` — visão de funções do store do par.

Implementa as cinco leis L-JF1…L-JF5 do concept §4 **e a `L-ORD`**
(ADR 3.3.0003, Stage 3.3). **Não é atalho de teste:** um fake que virasse upsert
em silêncio faria a suíte passar verde enquanto o Postgres da 3.3 rejeitaria a
mesma escrita — o defeito histórico do BC identity (ADR 2.3.0003). Os testes que
travam as leis vivem na Task 06.

**Sobre a ordenação (`L-ORD`):** o `sorted()` do Python sobre `str` compara por
**codepoint**, e foi medido contra o Postgres como **idêntico** a
`ORDER BY name COLLATE "C", id COLLATE "C"`. É essa coincidência — e não uma
conveniência — que permite à suíte de contrato ter um corpo só para as duas
implementações. Qualquer normalização aqui (`casefold`, remoção de acento)
reintroduziria a divergência que a lei existe para remover.
"""

from collections.abc import Iterable

from restaurant_hub.features.staff.application.errors import (
    JobFunctionAlreadyExistsError,
    JobFunctionInUseError,
    JobFunctionNameAlreadyExistsError,
    JobFunctionNotFoundError,
)
from restaurant_hub.features.staff.application.ports.out.job_function_repository import (
    JobFunctionRepository,
)
from restaurant_hub.features.staff.domain.entities.job_function import JobFunction
from restaurant_hub.features.staff.domain.value_objects.identifiers import (
    JobFunctionId,
    TenantId,
    UnitId,
)
from tests.fakes.features.staff.in_memory_staff_store import InMemoryStaffStore


def _em_ordem(job_functions: Iterable[JobFunction]) -> tuple[JobFunction, ...]:
    """`L-ORD` — por `name`, desempatando por `id`, sem normalização alguma."""
    return tuple(sorted(job_functions, key=lambda funcao: (funcao.name, funcao.id)))


class InMemoryJobFunctionRepository:
    """Visão de funções do `InMemoryStaffStore` compartilhado."""

    def __init__(self, store: InMemoryStaffStore) -> None:
        self._store = store

    # --- escrita -------------------------------------------------------------

    def add(self, job_function: JobFunction) -> None:
        """L-JF1 — inserção, não upsert; id global, nome por tenant."""
        self._store.record("job_functions.add")
        # Colisão de id é GLOBAL, não por tenant: na 3.3 o id é a chave
        # primária, e olhar só dentro do tenant aceitaria o que o banco recusa.
        if job_function.id in self._store.job_functions:
            raise JobFunctionAlreadyExistsError(job_function.id)
        self._guard_name(job_function)
        self._store.job_functions[job_function.id] = job_function

    def update_enablement(self, job_function: JobFunction) -> None:
        """L-JF7 — substitui só a habilitação; função ausente no tenant ⇒ `NotFound`."""
        self._store.record("job_functions.update_enablement")
        gravada = self._find(job_function.tenant_id, job_function.id)
        if gravada is None:
            raise JobFunctionNotFoundError(job_function.id)
        self._store.job_functions[job_function.id] = gravada.with_enablement(
            job_function.unit_enablement
        )

    def update(self, job_function: JobFunction) -> None:
        """L-JF2 — `UPDATE`, não upsert; a guarda de nome ignora a própria função."""
        self._store.record("job_functions.update")
        # Lookup por (tenant_id, id) ANTES de qualquer outra guarda (§5.4).
        #
        # NOTA (não há teste que discrimine esta ordem AQUI, e é esperado):
        # `_guard_name` já é tenant-scoped, então inverter as duas linhas seria
        # **inobservável** — com tenant alheio a busca de homônima não acha
        # nada e a execução cai no mesmo `JobFunctionNotFoundError`. A ordem
        # fica explícita mesmo assim porque a 3.3 herda este método como
        # especificação, e lá as duas checagens têm custo e efeito diferentes
        # (índice único vs. lookup por PK). Onde a ordem É discriminável, ela
        # está travada por teste: `delete` (NotFound vence InUse) e
        # `EmployeeRepository.update` (NotFound vence Relocation).
        if self._find(job_function.tenant_id, job_function.id) is None:
            raise JobFunctionNotFoundError(job_function.id)
        self._guard_name(job_function)
        # L-JF2 grava **só o nome** (Stage 3.11): a habilitação gravada sobrevive,
        # qualquer que seja a da entidade recebida — espelha o `SET name` do
        # adapter real.
        gravada = self._store.job_functions[job_function.id]
        self._store.job_functions[job_function.id] = gravada.rename(job_function.name)

    def delete(self, tenant_id: TenantId, job_function_id: JobFunctionId) -> None:
        """L-JF3 — remoção guardada por referências, de registros ativos e inativos."""
        self._store.record("job_functions.delete")
        if self._find(tenant_id, job_function_id) is None:
            raise JobFunctionNotFoundError(job_function_id)
        # A referência conta em qualquer unidade do tenant e independentemente
        # do estado do funcionário: o desligado ainda aponta para a função.
        referenciada = any(
            employee.tenant_id == tenant_id and job_function_id in employee.job_function_ids
            for employee in self._store.employees.values()
        )
        if referenciada:
            raise JobFunctionInUseError(job_function_id)
        del self._store.job_functions[job_function_id]

    # --- leitura -------------------------------------------------------------

    def find_by_id(self, tenant_id: TenantId, job_function_id: JobFunctionId) -> JobFunction | None:
        """Função do tenant, ou `None` — função de outro tenant devolve `None`."""
        self._store.record("job_functions.find_by_id")
        return self._find(tenant_id, job_function_id)

    def find_by_name(self, tenant_id: TenantId, name: str) -> JobFunction | None:
        """Homônima do tenant, ou `None`. Comparação **verbatim** (workforce §3.2)."""
        self._store.record("job_functions.find_by_name")
        for job_function in self._store.job_functions.values():
            if job_function.tenant_id == tenant_id and job_function.name == name:
                return job_function
        return None

    def find_all_by_ids(
        self, tenant_id: TenantId, job_function_ids: frozenset[JobFunctionId]
    ) -> tuple[JobFunction, ...]:
        """L-JF4 — devolve só as encontradas; id ausente não é erro aqui.

        `L-ORD` — ordenado por `(name, id)`; o parâmetro é `frozenset` e não
        carrega ordem alguma para o resultado herdar.
        """
        self._store.record("job_functions.find_all_by_ids")
        return _em_ordem(
            job_function
            for job_function in self._store.job_functions.values()
            if job_function.tenant_id == tenant_id and job_function.id in job_function_ids
        )

    def list_by_tenant(self, tenant_id: TenantId) -> tuple[JobFunction, ...]:
        """L-JF5 — todas as do tenant, nenhuma de outro; sem flag de estado.

        `L-ORD` — ordenado por `(name, id)`.
        """
        self._store.record("job_functions.list_by_tenant")
        return _em_ordem(
            job_function
            for job_function in self._store.job_functions.values()
            if job_function.tenant_id == tenant_id
        )

    def list_by_unit(self, tenant_id: TenantId, unit_id: UnitId) -> tuple[JobFunction, ...]:
        """L-JF6 — as do tenant habilitadas na unidade; `L-ORD` — por `(name, id)`."""
        self._store.record("job_functions.list_by_unit")
        return _em_ordem(
            job_function
            for job_function in self._store.job_functions.values()
            if job_function.tenant_id == tenant_id and job_function.is_enabled_in(unit_id)
        )

    # --- internos ------------------------------------------------------------

    def _find(self, tenant_id: TenantId, job_function_id: JobFunctionId) -> JobFunction | None:
        """Lookup por `(tenant_id, id)` — espelha o `WHERE tenant_id = … AND id = …`."""
        job_function = self._store.job_functions.get(job_function_id)
        if job_function is None or job_function.tenant_id != tenant_id:
            return None
        return job_function

    def _guard_name(self, job_function: JobFunction) -> None:
        """Unicidade de nome no tenant, **ignorando a própria função**.

        Sem o `is not` por id, renomear uma função para o nome que ela já tem
        falharia — e é justamente o caso que o `find_by_name` do port existe
        para distinguir.
        """
        homonima = next(
            (
                existente
                for existente in self._store.job_functions.values()
                if existente.tenant_id == job_function.tenant_id
                and existente.name == job_function.name
                and existente.id != job_function.id
            ),
            None,
        )
        if homonima is not None:
            raise JobFunctionNameAlreadyExistsError(job_function.name)


_conforms: JobFunctionRepository = InMemoryJobFunctionRepository(InMemoryStaffStore())
