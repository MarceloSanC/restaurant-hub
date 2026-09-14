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

from collections.abc import Callable
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
from restaurant_hub.features.staff.application.ports.out.identity_gateway import (
    IdentityGateway,
    LoginDelivery,
)
from restaurant_hub.features.staff.application.ports.out.job_function_repository import (
    JobFunctionRepository,
)
from restaurant_hub.features.staff.domain.value_objects.identifiers import (
    TenantId,
    UnitId,
    UserId,
)
from tests.conftest import truncar_tudo
from tests.fakes.features.staff.in_memory_identity_gateway import (
    FakeTenantUnknown,
    FakeUnitOfAnotherTenant,
    FakeUnitUnknown,
    InMemoryIdentityGateway,
)
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
        #
        # A limpeza é no **setup**, e não no teardown — convenção do projeto
        # inteiro (`tests/integration/conftest.py`, `tests/e2e/.../conftest.py` e
        # o conftest de contrato de identity fazem o mesmo). Cada suíte garante o
        # banco vazio de que **ela** precisa, em vez de confiar na higiene da
        # anterior; o preço é que o último teste da sessão deixa linhas gravadas,
        # o que é inócuo porque nenhuma suíte pressupõe banco limpo na entrada
        # sem truncar. Simetrizar só aqui tornaria este arquivo o único
        # divergente — e a divergência é que confunde.
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


# ---------------------------------------------------------------------------
# Stage 3.5 — o contrato do `IdentityGateway` (concept 3.5 §4, L-IG1…L-IG4)
# ---------------------------------------------------------------------------
#
# Mesma disciplina do par de repositórios, com uma diferença que a forma do
# holder carrega: as leis do gateway falam de efeitos que **só o outro lado da
# fronteira enxerga** (o papel do `User` criado, a membership, o token que redime
# o login) e de cenários que cada implementação produz **do seu jeito** (e-mail já
# usado; unidade inexistente; envio que falha). Um corpo de teste que soubesse
# como cada lado produz o cenário estaria ramificando por implementação — e é
# isso que `test_no_implementation_branching.py` proíbe. Por isso o holder leva,
# além do gateway, **funções de observação e de arranjo**: o corpo chama
# `holder.email_ja_usado(...)` e assere o efeito; quem sabe se isso significa
# "acrescentar ao set do fake" ou "semear um User no repositório de identity" é
# este arquivo, que é onde a ramificação **deve** existir.
#
# `IMPLEMENTACOES_DO_GATEWAY` é constante própria: `IMPLEMENTACOES` (acima) fixa
# as implementações do par de repositórios e é asserida exata pelo módulo de
# CA2; misturar as duas listas faria uma asserção sobre repositórios reprovar
# por causa do gateway. A Task 09 da Stage 3.5 acrescenta `"real"` aqui.
IMPLEMENTACOES_DO_GATEWAY = ("fake",)


@dataclass(frozen=True)
class CenarioCru:
    """Um cenário de L-IG2 "sobe cru": qual argumento, com que valor, e o tipo que sobe.

    O corpo do teste recebe **o tipo esperado** em vez da instância porque, do
    lado real, a instância é criada por identity no ato — ninguém a tem antes.
    O que as duas implementações têm em comum é o **tipo** que atravessa. E
    recebe o **nome do argumento** (`"tenant_id"` ou `"unit_id"`) para não ter
    de decidir, por si, que argumento carrega o valor — decidir seria ramificar.
    """

    argumento: str
    valor: str
    tipo_esperado: type[Exception]


@dataclass(frozen=True)
class GatewaySobContrato:
    """O gateway de uma implementação mais o que o contrato precisa ver e arranjar.

    Attributes:
        gateway: a implementação sob contrato (fake ou real).
        tenant_id: um restaurante que **existe** deste lado.
        unit_id: uma unidade **desse** restaurante que existe deste lado.
        login_role_of: o papel do login criado — o fake responde `"employee"`
            por definição (L-IG1 diz que o papel é do port); o real lê o `User`.
        token_redeems: se `setup_link` redime **aquele** `user_id`.
        entregue_em_maos: se o login foi provisionado para entrega em mãos —
            observável no real pelo prazo do token (concept D9), no fake pelo
            ledger.
        foi_revogado: se `revoke_login_sessions` alcançou o login.
        enviados_para: os links enviados para um e-mail, na ordem.
        email_ja_usado: **arranjo** — faz o e-mail passar a estar em uso.
        email_invalido: **arranjo** — devolve um e-mail que este lado recusa.
        unidade_inexistente / unidade_de_outro_tenant / tenant_inexistente:
            **arranjo** — devolvem o valor que produz a falha crua e o tipo que
            sobe deste lado.
        envio_falha: **arranjo** — faz o próximo envio levantar a instância dada.
    """

    gateway: IdentityGateway
    tenant_id: TenantId
    unit_id: UnitId
    login_role_of: Callable[[UserId], str | None]
    token_redeems: Callable[[UserId, str], bool]
    entregue_em_maos: Callable[[UserId], bool]
    foi_revogado: Callable[[UserId], bool]
    enviados_para: Callable[[str], list[str]]
    email_ja_usado: Callable[[str], None]
    email_invalido: Callable[[], str]
    unidade_inexistente: Callable[[], CenarioCru]
    unidade_de_outro_tenant: Callable[[], CenarioCru]
    tenant_inexistente: Callable[[], CenarioCru]
    envio_falha: Callable[[Exception], None]


def _gateway_fake() -> GatewaySobContrato:
    fake = InMemoryIdentityGateway()
    tenant = TenantId("tenant-contrato")
    unidade = UnitId("unidade-contrato")

    def unidade_inexistente() -> CenarioCru:
        fantasma = UnitId("unidade-fantasma")
        fake.raw_errors_by_unit[fantasma] = FakeUnitUnknown()
        return CenarioCru(argumento="unit_id", valor=fantasma, tipo_esperado=FakeUnitUnknown)

    def unidade_de_outro_tenant() -> CenarioCru:
        alheia = UnitId("unidade-alheia")
        fake.raw_errors_by_unit[alheia] = FakeUnitOfAnotherTenant()
        return CenarioCru(argumento="unit_id", valor=alheia, tipo_esperado=FakeUnitOfAnotherTenant)

    def tenant_inexistente() -> CenarioCru:
        fantasma = TenantId("tenant-fantasma")
        fake.raw_errors_by_tenant[fantasma] = FakeTenantUnknown()
        return CenarioCru(argumento="tenant_id", valor=fantasma, tipo_esperado=FakeTenantUnknown)

    def email_invalido() -> str:
        fake.invalid_emails.add("nao-e-email")
        return "nao-e-email"

    def envio_falha(excecao: Exception) -> None:
        fake.fail_send_with = excecao

    return GatewaySobContrato(
        gateway=fake,
        tenant_id=tenant,
        unit_id=unidade,
        login_role_of=lambda user_id: "employee" if user_id in fake.logins else None,
        token_redeems=lambda user_id, link: (
            user_id in fake.logins and fake.logins[user_id].setup_link == link
        ),
        entregue_em_maos=lambda user_id: fake.logins[user_id].delivery is LoginDelivery.LINK,
        foi_revogado=lambda user_id: user_id in fake.revoked,
        enviados_para=lambda email: [link for (para, link) in fake.sent if para == email],
        email_ja_usado=fake.used_emails.add,
        email_invalido=email_invalido,
        unidade_inexistente=unidade_inexistente,
        unidade_de_outro_tenant=unidade_de_outro_tenant,
        tenant_inexistente=tenant_inexistente,
        envio_falha=envio_falha,
    )


@pytest.fixture(params=IMPLEMENTACOES_DO_GATEWAY)
def gateway(request: pytest.FixtureRequest) -> GatewaySobContrato:
    """Parametriza a suíte de leis do gateway sobre as implementações do port.

    Só o fake até a Task 09 da Stage 3.5, que acrescenta o
    `LocalIdentityGateway` sobre a fachada de identity — montada sobre os fakes
    de identity, sem banco: o contrato é sobre a **tradução**, não sobre a
    persistência.
    """
    if request.param == "fake":
        return _gateway_fake()

    raise AssertionError(f"implementação desconhecida no contrato do gateway: {request.param!r}")
