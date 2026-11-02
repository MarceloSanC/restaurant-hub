"""Use case `delete_job_function` — a guarda de remoção (Task 08).

Esta suíte cobre a **segunda** regra cross-agregado delegada pela 3.1
(concept §5.9). O teste que mais importa é o de precedência: função do tenant A,
**referenciada**, apagada com `tenant_id` do B tem de devolver `NotFound` — o
erro não pode confirmar que ela existe *nem* que está em uso.

> **Por que esta suíte assere `store.calls`, e não só o erro levantado.**
> O par de fakes já impõe L-JF3 por conta própria: apagar função referenciada
> levanta `JobFunctionInUseError` **mesmo que o use case não tenha guarda
> nenhuma**. Uma suíte que olhasse só o tipo do erro e o estado final seria
> verde com o `execute` reduzido a uma linha (`job_functions.delete(...)`) — e
> a dependência `employees` viraria código morto sem que ninguém notasse.
>
> Isso importa porque a tabela ao final do concept §5 declara **duas** camadas
> de enforcement com limites honestos diferentes: a checagem no use case
> (check-then-act) e a lei do port (FK `RESTRICT` na 3.3). Se só a segunda tem
> teste, a primeira é conformidade não verificada. `store.calls` é o que torna
> a **conduta** do use case observável — não apenas o seu resultado.
"""

from decimal import Decimal

import pytest

from restaurant_hub.features.staff.application.dtos.commands import DeleteJobFunctionCommand
from restaurant_hub.features.staff.application.errors import (
    JobFunctionInUseError,
    JobFunctionNotFoundError,
    StaffApplicationError,
)
from restaurant_hub.features.staff.application.use_cases.delete_job_function import (
    DeleteJobFunctionUseCase,
)
from restaurant_hub.features.staff.domain.entities.employee import Employee
from restaurant_hub.features.staff.domain.entities.job_function import JobFunction
from restaurant_hub.features.staff.domain.exceptions.errors import StaffError
from restaurant_hub.features.staff.domain.value_objects.identifiers import (
    EmployeeId,
    JobFunctionId,
    TenantId,
    UnitId,
)
from restaurant_hub.features.staff.domain.value_objects.workload_profile import FixedSchedule
from tests.fakes.features.staff.in_memory_staff_store import StaffFakes, staff_repositories
from tests.fakes.features.staff.stub_access_guards import TEST_ACTOR, PermissiveAccessGuard

pytestmark = pytest.mark.unit

_A = TenantId("tenant-a")
_B = TenantId("tenant-b")
_U1 = UnitId("u1")
_U2 = UnitId("u2")
_F1 = JobFunctionId("f1")


def _com_funcao_no_tenant_a() -> StaffFakes:
    fakes = staff_repositories()
    fakes.job_functions.add(JobFunction(id=_F1, tenant_id=_A, name="Cozinheiro"))
    return fakes


def _funcionario(
    fakes: StaffFakes,
    *,
    tenant: TenantId = _A,
    unit: UnitId = _U1,
    funcao: JobFunctionId = _F1,
    active: bool = True,
) -> None:
    """Grava UM funcionário — cada teste desta suíte precisa de no máximo um."""
    fakes.employees.add(
        Employee(
            id=EmployeeId("e1"),
            tenant_id=tenant,
            unit_id=unit,
            name="Maria",
            workload_profile=FixedSchedule(weekly_hours=Decimal("44")),
            shift_preference=None,
            job_function_ids=frozenset({funcao}),
            active=active,
        )
    )


def _apagar(fakes: StaffFakes) -> DeleteJobFunctionUseCase:
    return DeleteJobFunctionUseCase(
        fakes.job_functions, fakes.employees, guard=PermissiveAccessGuard()
    )


def test_remove_funcao_sem_referencias() -> None:
    fakes = _com_funcao_no_tenant_a()
    antes = len(fakes.store.calls)
    _apagar(fakes).execute(
        DeleteJobFunctionCommand(actor=TEST_ACTOR, tenant_id=_A, job_function_id=_F1)
    )
    # Capturado ANTES da releitura, que também registraria uma chamada.
    conduta = list(fakes.store.calls[antes:])

    assert fakes.job_functions.find_by_id(_A, _F1) is None
    # A conduta do caminho feliz, na ordem obrigatória de §5.16: existência,
    # guarda de referências, remoção. A sequência inteira, porque cada elo
    # sozinho é removível sem que o resultado observável mude.
    assert conduta == [
        "job_functions.find_by_id",
        "employees.exists_by_job_function",
        "job_functions.delete",
    ]


def test_funcao_referenciada_nao_e_removida_e_a_remocao_nem_e_tentada() -> None:
    """A guarda do **use case** impede a chamada; ela não é só um erro esperado.

    Sem `"job_functions.delete" not in calls`, este teste passaria com o
    `execute` reduzido a `self._job_functions.delete(...)`: o fake levantaria
    `JobFunctionInUseError` pela lei L-JF3 e o estado final seria idêntico. O
    que distingue as duas camadas de enforcement do concept §5 é **quem** para
    a operação — e isso só é observável em `calls`.
    """
    fakes = _com_funcao_no_tenant_a()
    _funcionario(fakes)
    antes = len(fakes.store.calls)

    with pytest.raises(JobFunctionInUseError):
        _apagar(fakes).execute(
            DeleteJobFunctionCommand(actor=TEST_ACTOR, tenant_id=_A, job_function_id=_F1)
        )

    assert "job_functions.delete" not in fakes.store.calls[antes:]
    assert fakes.job_functions.find_by_id(_A, _F1) is not None


def test_referenciador_em_outra_unidade_do_tenant_bloqueia() -> None:
    """A guarda é tenant-wide porque a **função** é tenant-scoped (workforce §3.2)."""
    fakes = _com_funcao_no_tenant_a()
    _funcionario(fakes, unit=_U2)
    antes = len(fakes.store.calls)

    with pytest.raises(JobFunctionInUseError):
        _apagar(fakes).execute(
            DeleteJobFunctionCommand(actor=TEST_ACTOR, tenant_id=_A, job_function_id=_F1)
        )

    assert "job_functions.delete" not in fakes.store.calls[antes:]
    assert fakes.job_functions.find_by_id(_A, _F1) is not None


def test_referenciador_desligado_tambem_bloqueia() -> None:
    """O desligado sobrevive com a história e ainda aponta para a função.

    Uma implementação que contasse só ativos apagaria a função e deixaria o
    registro desligado apontando para função inexistente — furando a invariante
    "ao menos uma função" da 3.1 no momento em que alguém o recontratasse.
    """
    fakes = _com_funcao_no_tenant_a()
    _funcionario(fakes, active=False)
    antes = len(fakes.store.calls)

    with pytest.raises(JobFunctionInUseError):
        _apagar(fakes).execute(
            DeleteJobFunctionCommand(actor=TEST_ACTOR, tenant_id=_A, job_function_id=_F1)
        )

    assert "job_functions.delete" not in fakes.store.calls[antes:]
    assert fakes.job_functions.find_by_id(_A, _F1) is not None


def test_referencia_de_outro_tenant_nao_bloqueia_a_remocao() -> None:
    """A guarda conta referências **do tenant da função**, não do mundo.

    Restatement do lado positivo: o escopo de `exists_by_job_function` já é lei
    do port (L-E7, travada na Task 06), então este teste **não** é o que pega um
    fake que ignorasse `tenant_id`. Ele existe como caso de negócio legível —
    "o restaurante A consegue apagar a própria função mesmo havendo um
    homônimo em uso no B" — e é barato o bastante para valer por isso.
    """
    fakes = _com_funcao_no_tenant_a()
    fakes.job_functions.add(JobFunction(id=JobFunctionId("f-b"), tenant_id=_B, name="Cozinheiro"))
    _funcionario(fakes, tenant=_B, funcao=JobFunctionId("f-b"))

    _apagar(fakes).execute(
        DeleteJobFunctionCommand(actor=TEST_ACTOR, tenant_id=_A, job_function_id=_F1)
    )
    assert fakes.job_functions.find_by_id(_A, _F1) is None


def test_apagar_funcao_inexistente_e_not_found() -> None:
    fakes = staff_repositories()
    with pytest.raises(JobFunctionNotFoundError):
        _apagar(fakes).execute(
            DeleteJobFunctionCommand(
                actor=TEST_ACTOR, tenant_id=_A, job_function_id=JobFunctionId("fantasma")
            )
        )


def test_precedencia_not_found_vence_in_use_com_tenant_alheio() -> None:
    """Par duplo de §5.16: as duas checagens falhariam; **NotFound vence**.

    Este é o cenário em que a ordem importa de verdade. A função existe e está
    **em uso** no tenant A; o pedido vem com `tenant_id` do B. Se a guarda de
    referências rodasse primeiro, a resposta seria `JobFunctionInUseError` — e
    esse erro sozinho confirma ao tenant B que a função existe **e** que há
    alguém usando-a no restaurante alheio (§5.4).

    Asserção por **tipo exato**: `pytest.raises(JobFunctionNotFoundError)` puro
    não distinguiria "acertou a precedência" de "levantou outra coisa".

    E o tipo **não basta** para provar a ordem. `exists_by_job_function` é
    tenant-scoped, então com o `tenant_id` do B ela devolveria `False` e a
    execução cairia no mesmo `JobFunctionNotFoundError` — a inversão das duas
    checagens é **invisível no resultado**. O que a torna visível é a guarda de
    referências **nunca ter sido consultada**: a existência barrou antes.
    """
    fakes = _com_funcao_no_tenant_a()
    _funcionario(fakes)  # a função está EM USO no tenant A
    antes = len(fakes.store.calls)

    with pytest.raises((StaffError, StaffApplicationError)) as excecao:
        _apagar(fakes).execute(
            DeleteJobFunctionCommand(actor=TEST_ACTOR, tenant_id=_B, job_function_id=_F1)
        )
    assert type(excecao.value) is JobFunctionNotFoundError

    conduta = fakes.store.calls[antes:]
    assert "employees.exists_by_job_function" not in conduta
    assert "job_functions.delete" not in conduta
    assert fakes.job_functions.find_by_id(_A, _F1) is not None


def test_apagar_funcao_de_outro_tenant_sem_referencias_tambem_e_not_found() -> None:
    """A meia-verdade do teste acima, isolada: nem sem uso o tenant B a alcança."""
    fakes = _com_funcao_no_tenant_a()
    with pytest.raises(JobFunctionNotFoundError):
        _apagar(fakes).execute(
            DeleteJobFunctionCommand(actor=TEST_ACTOR, tenant_id=_B, job_function_id=_F1)
        )
    assert fakes.job_functions.find_by_id(_A, _F1) is not None
