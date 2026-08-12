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
from sqlalchemy import Engine

from restaurant_hub.features.staff.adapters.out.postgres.employee_repository import (
    PostgresEmployeeRepository,
)
from restaurant_hub.features.staff.adapters.out.postgres.job_function_repository import (
    PostgresJobFunctionRepository,
)
from restaurant_hub.features.staff.application.ports.out.employee_repository import (
    EmployeeRepository,
)
from restaurant_hub.features.staff.application.ports.out.job_function_repository import (
    JobFunctionRepository,
)
from tests.conftest import truncar_tudo
from tests.fakes.features.staff.in_memory_staff_store import staff_repositories

# As implementações sobre as quais a suíte inteira roda. **Constante nomeada, e
# não literal dentro de `params`**, porque é sobre ela que
# `test_no_implementation_branching.py` assere: retirar `"postgres"` daqui faria
# a suíte voltar a exercitar uma implementação só, e o sintoma seria o melhor
# possível — tudo verde, metade do contrato não verificada.
IMPLEMENTACOES = ("fake", "postgres")


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


@pytest.fixture(params=IMPLEMENTACOES)
def repos(request: pytest.FixtureRequest) -> RepositoriosDeStaff:
    """Parametriza a suíte inteira sobre as duas implementações do contrato.

    **É aqui que a Stage cobra o seu objetivo.** As doze leis mais `L-ORD` foram
    escritas na 3.2 como especificação nas docstrings dos ports e travadas contra
    um implementador só; a partir desta linha elas valem para os dois, com **um
    corpo de teste só**. Lei verificada contra um implementador só é lei não
    verificada — foi assim que identity acumulou a dívida que a 2.3 retroagiu
    (ADR 2.3.0003).

    O id do parâmetro aparece no nome do teste (`[fake]` / `[postgres]`), então
    uma divergência é lida direto no output: **o mesmo teste** passa numa
    implementação e falha na outra. É o sintoma que a 2.3 não teve.

    Os dois adapters são construídos sobre o **mesmo** `Engine` — a razão está no
    docstring do módulo: L-JF3 e L-E4 falam de dados que vivem no outro agregado,
    e um par montado sobre bancos diferentes as satisfaria vacuamente.
    """
    if request.param == "fake":
        fakes = staff_repositories()
        return RepositoriosDeStaff(
            job_functions=fakes.job_functions,
            employees=fakes.employees,
        )

    if request.param == "postgres":
        # `engine` vem de `tests/conftest.py` e **falha alto** quando o Postgres
        # não está no ar (ADR 2.3.0001) — o contrato herda a exigência, e é o que
        # impede a suíte de reportar verde por não ter olhado.
        engine: Engine = request.getfixturevalue("engine")
        truncar_tudo(engine)
        return RepositoriosDeStaff(
            job_functions=PostgresJobFunctionRepository(engine),
            employees=PostgresEmployeeRepository(engine),
        )

    # Levantar — em vez de deixar a função cair no `None` implícito — é o que
    # impede um parâmetro novo em `IMPLEMENTACOES` de produzir uma suíte que roda
    # contra nada e reporta verde.
    raise AssertionError(f"implementação desconhecida no contrato de staff: {request.param!r}")
