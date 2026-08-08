"""Store único do par acoplado de fakes do BC staff — e o holder que o entrega.

**Por que um store, e não dois dicionários isolados.** As leis L-JF3 (remoção
guardada) e L-E4 (validade referencial) falam de dados que vivem **no outro
agregado**: um `InMemoryJobFunctionRepository` isolado não teria como saber se
algum funcionário referencia a função, e um `InMemoryEmployeeRepository` isolado
não teria como saber se a função existe. Com os dois fakes como **visões** de um
store único, as duas leis são verificáveis — e um par construído sobre stores
diferentes é **erro de teste**, não configuração válida.

**Os dicionários são planos** (`dict[Id, Entidade]`, sem aninhamento por
tenant), de propósito: o filtro por `tenant_id` vira comparação de campo,
espelhando o `WHERE tenant_id = …` da 3.3, e é isso que permite a colisão
**global** de id de L-JF1/L-E1 — que é o comportamento da chave primária.

Este módulo é **entregável de primeira classe**, não andaime: `StaffFakes` é o
holder que a Stage 3.3 parametriza no teste de contrato (o par de fakes contra
os adapters Postgres), porque as leis cross-agregado só são verificáveis sobre o
par.
"""

from dataclasses import dataclass, field

from restaurant_hub.features.staff.application.ports.out.employee_repository import (
    EmployeeRepository,
)
from restaurant_hub.features.staff.application.ports.out.job_function_repository import (
    JobFunctionRepository,
)
from restaurant_hub.features.staff.domain.entities.employee import Employee
from restaurant_hub.features.staff.domain.entities.job_function import JobFunction
from restaurant_hub.features.staff.domain.value_objects.identifiers import (
    EmployeeId,
    JobFunctionId,
)


@dataclass
class InMemoryStaffStore:
    """Estado compartilhado pelas duas visões do par.

    Attributes:
        job_functions: funções por id — **global**, sem aninhamento por tenant.
        employees: registros por id — idem.
        calls: registro das chamadas recebidas pelos fakes, no formato
            `"<visão>.<método>"`. Não é enfeite: os critérios "não tocou o port"
            (concept §11 — nome vazio não dispara `find_by_name` nem `add`)
            asserem esta lista **vazia**, e um contador por fake não distinguiria
            "não consultou" de "consultou o outro".
    """

    job_functions: dict[JobFunctionId, JobFunction] = field(default_factory=dict)
    employees: dict[EmployeeId, Employee] = field(default_factory=dict)
    calls: list[str] = field(default_factory=list)

    def record(self, call: str) -> None:
        """Registra uma chamada recebida por uma das visões."""
        self.calls.append(call)


@dataclass(frozen=True)
class StaffFakes:
    """O par acoplado **e** o store que ele compartilha.

    Devolve os **três** objetos, e não só o par, porque os critérios "não tocou
    o port" precisam de `fakes.store.calls`: sem o store no holder, o teste só o
    alcançaria por atributo de um dos fakes, acoplando a suíte à representação
    interna do fake — exatamente o que a skill `pytest-with-fakes` manda evitar.

    Os dois repositórios são anotados com o **`Protocol`**, não com a classe
    concreta: é o que torna este holder reusável pela 3.3, que o preenche com os
    adapters Postgres sem mudar uma linha dos testes de lei.
    """

    store: InMemoryStaffStore
    job_functions: JobFunctionRepository
    employees: EmployeeRepository


def staff_repositories() -> StaffFakes:
    """Constrói o par sobre um store novo — a **única** forma usada na Stage.

    Nenhum teste desta Stage instancia um fake diretamente: fazê-lo abriria a
    porta para um par sobre stores diferentes, no qual L-JF3 e L-E4 passariam
    **vacuamente** (nenhuma referência cruzada seria enxergada).
    """
    # `noqa: PLC0415` — import local, e não no topo, por necessidade e não por
    # estilo: os dois fakes importam `InMemoryStaffStore` DESTE módulo (precisam
    # dele no construtor e na linha `_conforms`), então um import de topo aqui
    # fecharia um ciclo. O holder em si não precisa deles — é anotado com os
    # `Protocol`, e é justamente isso que o torna reusável pela 3.3.
    from tests.fakes.features.staff.in_memory_employee_repository import (  # noqa: PLC0415
        InMemoryEmployeeRepository,
    )
    from tests.fakes.features.staff.in_memory_job_function_repository import (  # noqa: PLC0415
        InMemoryJobFunctionRepository,
    )

    store = InMemoryStaffStore()
    return StaffFakes(
        store=store,
        job_functions=InMemoryJobFunctionRepository(store),
        employees=InMemoryEmployeeRepository(store),
    )
