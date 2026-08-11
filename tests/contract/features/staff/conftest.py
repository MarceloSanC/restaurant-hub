"""Fixtures do contrato de staff — a MESMA suíte contra o fake e contra o Postgres.

Este arquivo é o mecanismo que a Stage 3.2 encomendou à 3.3. Lá, as doze leis
foram escritas como especificação nas docstrings dos ports e travadas contra um
**único** implementador (o par de fakes); aqui elas passam a valer para os dois,
com **um corpo de teste só**. Leis verificadas contra um implementador só são
leis não verificadas — foi assim que o BC identity acumulou a dívida que a 2.3
teve de retroagir (ADR 2.3.0003).

**As suítes foram MOVIDAS, não copiadas** (`git mv`, ADR 3.3.0007). A skill
`pytest-with-fakes` é literal — "don't duplicate contract tests inside unit
(defeats the point: the contract is single)" — e duas cópias divergem no dia em
que só uma for editada. O `git log --follow` continua alcançando a história de
por que cada lei existe, que é o entregável de maior valor herdado da 3.2.

**Por que os dois repositórios vêm num pacote só** (`RepositoriosDeStaff`), em
vez de uma fixture por port: L-JF3 (remoção guardada) e L-E4 (validade
referencial) falam de dados que vivem **no outro agregado**. Um par montado
sobre stores — ou bancos — diferentes as satisfaria **vacuamente**: a remoção não
enxergaria referenciador nenhum e a resolução não encontraria função nenhuma. É
o mesmo raciocínio do conftest de identity, e o mesmo do docstring de
`InMemoryStaffStore`.

**Por que um holder novo, e não `StaffFakes`.** `StaffFakes` tipa
`store: InMemoryStaffStore` — um campo que o par real **não tem** e não pode
ter. Reusá-lo obrigaria o ramo `postgres` a inventar um store falso só para
preencher o campo, ou o corpo do teste a saber qual implementação está usando.
O holder novo carrega só o que é comum: os dois `Protocol`.

**O que fica de fora, explicitamente:** `store.calls`, a instrumentação
fake-only que os critérios "não tocou o port" da 3.2 usam. Verificado por grep:
**nenhum** dos testes movidos a usa — os que a usam ficaram em
`tests/unit/features/staff/application/`, que é onde eles pertencem. Um contrato
que exigisse `calls` do adapter real estaria inventando requisito, e é o mesmo
critério da CA16 de identity.
"""

from dataclasses import dataclass

import pytest

from restaurant_hub.features.staff.application.ports.out.employee_repository import (
    EmployeeRepository,
)
from restaurant_hub.features.staff.application.ports.out.job_function_repository import (
    JobFunctionRepository,
)
from tests.fakes.features.staff.in_memory_staff_store import staff_repositories


@dataclass(frozen=True)
class RepositoriosDeStaff:
    """O par de repositórios de uma mesma implementação.

    O corpo do teste recebe isto e **não sabe** se está falando com dicionários
    em memória ou com o PostgreSQL. Essa ignorância é o ponto: qualquer `if`
    sobre a implementação transformaria o teste de contrato em dois testes
    diferentes que apenas se parecem — e é isso que
    `test_no_implementation_branching.py` verifica por AST.
    """

    job_functions: JobFunctionRepository
    employees: EmployeeRepository


@pytest.fixture(params=["fake"])
def repos(request: pytest.FixtureRequest) -> RepositoriosDeStaff:
    """Parametriza a suíte inteira sobre as implementações do contrato.

    **Um só parâmetro nesta Task, de propósito.** O `"postgres"` entra na
    Task 09, quando os dois adapters já existirem e já tiverem sido verificados
    lei a lei contra o banco real. A separação é o que torna um vermelho
    diagnosticável: aqui, qualquer falha é da **mecânica do movimento** (mesmos
    testes, mesmas asserções, mesma implementação por trás); lá, qualquer falha
    é **divergência fake↔adapter**. Fundidas, um vermelho seria ambíguo entre as
    duas causas — ambiguidade que o `git bisect` existe para evitar.

    O id do parâmetro aparece no nome do teste (`[fake]`, e depois
    `[postgres]`), então a divergência é lida direto no output: o mesmo teste
    passa numa implementação e falha na outra.
    """
    if request.param == "fake":
        fakes = staff_repositories()
        return RepositoriosDeStaff(
            job_functions=fakes.job_functions,
            employees=fakes.employees,
        )

    # O ramo `postgres` entra na Task 09. Levantar aqui — em vez de deixar a
    # função cair no `None` implícito — é o que impede um parâmetro novo em
    # `params` de produzir uma suíte que roda contra nada e reporta verde.
    raise AssertionError(f"implementação desconhecida no contrato de staff: {request.param!r}")
