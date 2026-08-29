"""Rotas HTTP do BC staff.

**Adapter fino.** Cada rota faz cinco coisas e nada mais: valida os
identificadores que chegaram, declara o requisito de acesso e delega a decisão ao
port, converte texto em value object, chama **exatamente um** use case, e mapeia o
result para o schema de resposta. Não há regra de negócio aqui, e não há decisão
de acesso — essa é do `AuthorizeActionUseCase` de identity, alcançado pelo port.

**A ordem dentro de cada handler é contrato: autenticar → validar → autorizar.**
Autenticar é `Depends` (`CurrentActor`), e por isso acontece antes até da
validação do corpo contra o schema. Validar vem antes de autorizar porque é o que
impede um identificador cru de alcançar `units.find_by_id` **dentro de identity**,
onde o byte NUL vira `DataError` e, por não ser `StaffError` nem `IdentityError`,
**500**. A ordem não é observável pelo status: quem a trava é CA21, asserindo que
o dublê do port não registrou **nenhum** `authorize(...)`.

**O `tenant_id` de todo command e query sai de `AuthorizedScope.tenant_id`, e de
nenhuma outra origem.** Nenhuma rota o nomeia, nenhum schema o aceita: ele vem do
token e é resolvido no `composition_root` (ADR 0.0.0005). Há varredura de AST
sobre este arquivo que reprova qualquer outra origem — sem ela, um campo
`restaurant_id` de corpo consumido aqui passaria pela lista negra dos schemas.

**Nenhuma rota lê `AuthorizedScope.unit_id`.** O escopo **ecoa** a unidade pedida
(`authorize_action.py:113`), então lê-lo devolve o que o path já dizia — até o dia
em que não devolver. A unidade que endereça o registro é sempre a do **path**
(ADR 3.6.0001, ADR 3.4.0007). A varredura de AST que procura o atributo no objeto
do guard é **defesa em profundidade, não a trava**: `getattr`, `astuple` e
`asdict` a contornam. A trava é CA15, com o dublê adversarial.

**Sobre os provedores `_get_*`.** As dependências são resolvidas por
`app.dependency_overrides`, preenchido pelo composition root: as funções abaixo
são apenas as **chaves** desse dicionário e, se alguma for chamada de verdade,
significa que o wiring não aconteceu — daí levantarem em vez de devolverem algo.
Falhar alto é melhor que servir um `None` que só quebra três camadas adiante.

**Conversão texto → value object acontece aqui**, e não num validador Pydantic:
assim uma carga semanal ou um período do dia inválido levanta erro de **domínio**,
que o mapa de `error_handlers` classifica com o corpo de staff, em vez de virar um
`RequestValidationError` do FastAPI — que tem outro corpo e seguiria outro
caminho.
"""

from typing import Annotated, Never

from fastapi import APIRouter, Depends, Response, status

from restaurant_hub.features.staff.application.dtos.commands import (
    CreateEmployeeCommand,
    CreateJobFunctionCommand,
    DeleteEmployeeCommand,
    DeleteJobFunctionCommand,
    RenameEmployeeCommand,
    RenameJobFunctionCommand,
)
from restaurant_hub.features.staff.application.dtos.queries import (
    ListEmployeesQuery,
    ListJobFunctionsQuery,
)
from restaurant_hub.features.staff.application.use_cases.create_employee import (
    CreateEmployeeUseCase,
)
from restaurant_hub.features.staff.application.use_cases.create_job_function import (
    CreateJobFunctionUseCase,
)
from restaurant_hub.features.staff.application.use_cases.delete_employee import (
    DeleteEmployeeUseCase,
)
from restaurant_hub.features.staff.application.use_cases.delete_job_function import (
    DeleteJobFunctionUseCase,
)
from restaurant_hub.features.staff.application.use_cases.list_employees import (
    ListEmployeesUseCase,
)
from restaurant_hub.features.staff.application.use_cases.list_job_functions import (
    ListJobFunctionsUseCase,
)
from restaurant_hub.features.staff.application.use_cases.rename_employee import (
    RenameEmployeeUseCase,
)
from restaurant_hub.features.staff.application.use_cases.rename_job_function import (
    RenameJobFunctionUseCase,
)
from restaurant_hub.features.staff.domain.value_objects.identifiers import (
    EmployeeId,
    JobFunctionId,
    UnitId,
)
from restaurant_hub.features.staff.domain.value_objects.shift_preference import (
    DayPeriod,
    ShiftPreference,
)

from .dependencies import (
    MANAGE_JOB_FUNCTIONS_ACCESS,
    MANAGE_STAFF_IN_UNIT_ACCESS,
    CurrentActor,
    StaffAccessGuard,
    validate_identifier,
)
from .schemas import (
    CreateEmployeeRequest,
    CreateJobFunctionRequest,
    EmployeeResponse,
    JobFunctionResponse,
    RenameEmployeeRequest,
    RenameJobFunctionRequest,
    to_workload_profile,
)

router = APIRouter(tags=["staff"])

_JOB_FUNCTION = "função de trabalho"
_EMPLOYEE = "funcionário"
_UNIT = "unidade"


def _nao_conectado(nome: str) -> Never:
    raise RuntimeError(
        f"dependência {nome!r} não foi conectada pelo composition root — "
        "veja wire_dependencies() e create_app()"
    )


def _get_create_job_function() -> CreateJobFunctionUseCase:
    _nao_conectado("staff_create_job_function")


def _get_list_job_functions() -> ListJobFunctionsUseCase:
    _nao_conectado("staff_list_job_functions")


def _get_rename_job_function() -> RenameJobFunctionUseCase:
    _nao_conectado("staff_rename_job_function")


def _get_delete_job_function() -> DeleteJobFunctionUseCase:
    _nao_conectado("staff_delete_job_function")


def _get_create_employee() -> CreateEmployeeUseCase:
    _nao_conectado("staff_create_employee")


def _get_list_employees() -> ListEmployeesUseCase:
    _nao_conectado("staff_list_employees")


def _get_rename_employee() -> RenameEmployeeUseCase:
    _nao_conectado("staff_rename_employee")


def _get_delete_employee() -> DeleteEmployeeUseCase:
    _nao_conectado("staff_delete_employee")


def _to_shift_preference(periodos: list[str] | None) -> ShiftPreference | None:
    """Lista de textos para value object; `None` significa **sem preferência**.

    `DayPeriod.from_string` é o **único** conversor de período do dia da borda
    (concept §5.15): `DayPeriod(...)` direto levanta `ValueError`, que não é
    `StaffError` e vira 500. Há varredura de AST que reprova a construção direta
    em qualquer módulo deste pacote.
    """
    if periodos is None:
        return None
    return ShiftPreference(periods=frozenset(DayPeriod.from_string(p) for p in periodos))


def _job_function_ids(brutos: list[str]) -> frozenset[JobFunctionId]:
    """Valida **cada elemento** antes de deixá-lo alcançar o repositório.

    `Employee.__post_init__` valida a não-vacuidade do conjunto, mas **nenhum
    elemento** dele; e os ids vão para `find_all_by_ids` antes da construção da
    entidade. Sem esta validação, um NUL dentro da lista produz o mesmo 500 que
    esta Stage existe para fechar (concept §5.14).
    """
    return frozenset(
        JobFunctionId(validate_identifier(bruto, entity=_JOB_FUNCTION)) for bruto in brutos
    )


# ---------------------------------------------------------------------------
# Catálogo de funções de trabalho — recurso **tenant-scoped**
#
# O alvo destas quatro rotas é o restaurante inteiro, **sem unidade**, e a
# ausência é por desenho: `manage_job_functions` está em
# `TENANT_WIDE_PERMISSIONS` (ADR 3.4.0008), e o passo 4 de
# `AuthorizeActionUseCase` dispensa a unidade **por permissão**. Nomear uma
# unidade aqui pediria escopo sobre um recurso que não é da unidade.
# ---------------------------------------------------------------------------


@router.post(
    "/job-functions",
    response_model=JobFunctionResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_job_function(
    payload: CreateJobFunctionRequest,
    actor: CurrentActor,
    guard: StaffAccessGuard,
    use_case: Annotated[CreateJobFunctionUseCase, Depends(_get_create_job_function)],
) -> JobFunctionResponse:
    """Cria uma função no catálogo do restaurante do ator."""
    scope = guard.authorize(actor, MANAGE_JOB_FUNCTIONS_ACCESS.permission)
    result = use_case.execute(
        CreateJobFunctionCommand(tenant_id=scope.tenant_id, name=payload.name)
    )
    return JobFunctionResponse.from_result(result)


@router.get("/job-functions", response_model=list[JobFunctionResponse])
def list_job_functions(
    actor: CurrentActor,
    guard: StaffAccessGuard,
    use_case: Annotated[ListJobFunctionsUseCase, Depends(_get_list_job_functions)],
) -> list[JobFunctionResponse]:
    """Lista o catálogo do restaurante do ator, na ordem total de `L-ORD`."""
    scope = guard.authorize(actor, MANAGE_JOB_FUNCTIONS_ACCESS.permission)
    results = use_case.execute(ListJobFunctionsQuery(tenant_id=scope.tenant_id))
    return [JobFunctionResponse.from_result(result) for result in results]


@router.patch("/job-functions/{job_function_id}", response_model=JobFunctionResponse)
def rename_job_function(
    job_function_id: str,
    payload: RenameJobFunctionRequest,
    actor: CurrentActor,
    guard: StaffAccessGuard,
    use_case: Annotated[RenameJobFunctionUseCase, Depends(_get_rename_job_function)],
) -> JobFunctionResponse:
    """Renomeia uma função do catálogo."""
    identifier = validate_identifier(job_function_id, entity=_JOB_FUNCTION)
    scope = guard.authorize(actor, MANAGE_JOB_FUNCTIONS_ACCESS.permission)
    result = use_case.execute(
        RenameJobFunctionCommand(
            tenant_id=scope.tenant_id,
            job_function_id=JobFunctionId(identifier),
            name=payload.name,
        )
    )
    return JobFunctionResponse.from_result(result)


@router.delete("/job-functions/{job_function_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_job_function(
    job_function_id: str,
    actor: CurrentActor,
    guard: StaffAccessGuard,
    use_case: Annotated[DeleteJobFunctionUseCase, Depends(_get_delete_job_function)],
) -> Response:
    """Remove uma função do catálogo; 409 se algum funcionário ainda a usa."""
    identifier = validate_identifier(job_function_id, entity=_JOB_FUNCTION)
    scope = guard.authorize(actor, MANAGE_JOB_FUNCTIONS_ACCESS.permission)
    use_case.execute(
        DeleteJobFunctionCommand(
            tenant_id=scope.tenant_id,
            job_function_id=JobFunctionId(identifier),
        )
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Funcionário — recurso **unit-scoped**
#
# A unidade vem do **path** e é sempre alvo de autorização (ADR 3.4.0007). A
# chamada ao guard e a construção do command leem a **mesma** variável — dois
# nomes para um valor é como este defeito volta (ADR 3.6.0001 §Implementation
# notes), e é o que o dublê adversarial de CA15 existe para refutar.
# ---------------------------------------------------------------------------


@router.post(
    "/units/{unit_id}/employees",
    response_model=EmployeeResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_employee(
    unit_id: str,
    payload: CreateEmployeeRequest,
    actor: CurrentActor,
    guard: StaffAccessGuard,
    use_case: Annotated[CreateEmployeeUseCase, Depends(_get_create_employee)],
) -> EmployeeResponse:
    """Cria um funcionário na unidade do endereço."""
    unidade = validate_identifier(unit_id, entity=_UNIT)
    job_function_ids = _job_function_ids(payload.job_function_ids)
    scope = guard.authorize(actor, MANAGE_STAFF_IN_UNIT_ACCESS.permission, unit_id=unidade)
    result = use_case.execute(
        CreateEmployeeCommand(
            tenant_id=scope.tenant_id,
            unit_id=UnitId(unidade),
            name=payload.name,
            workload_profile=to_workload_profile(payload.workload_profile),
            job_function_ids=job_function_ids,
            shift_preference=_to_shift_preference(payload.shift_preference),
        )
    )
    return EmployeeResponse.from_result(result)


@router.get("/units/{unit_id}/employees", response_model=list[EmployeeResponse])
def list_employees(
    unit_id: str,
    actor: CurrentActor,
    guard: StaffAccessGuard,
    use_case: Annotated[ListEmployeesUseCase, Depends(_get_list_employees)],
    include_inactive: bool = False,
) -> list[EmployeeResponse]:
    """Lista os funcionários da unidade; desligados só com `include_inactive`."""
    unidade = validate_identifier(unit_id, entity=_UNIT)
    scope = guard.authorize(actor, MANAGE_STAFF_IN_UNIT_ACCESS.permission, unit_id=unidade)
    results = use_case.execute(
        ListEmployeesQuery(
            tenant_id=scope.tenant_id,
            unit_id=UnitId(unidade),
            include_inactive=include_inactive,
        )
    )
    return [EmployeeResponse.from_result(result) for result in results]


@router.patch(
    "/units/{unit_id}/employees/{employee_id}",
    response_model=EmployeeResponse,
)
def rename_employee(  # noqa: PLR0913
    # Seis parâmetros, e a aridade é **estrutural**: dois identificadores de
    # path, o corpo, e as três dependências que o FastAPI resolve. Agrupá-los
    # num objeto esconderia os `Depends` da assinatura — e é justamente a
    # visibilidade deles que §5.1 usa para provar que nenhuma rota é pública.
    unit_id: str,
    employee_id: str,
    payload: RenameEmployeeRequest,
    actor: CurrentActor,
    guard: StaffAccessGuard,
    use_case: Annotated[RenameEmployeeUseCase, Depends(_get_rename_employee)],
) -> EmployeeResponse:
    """Renomeia o funcionário endereçado pela unidade e pelo id."""
    unidade = validate_identifier(unit_id, entity=_UNIT)
    funcionario = validate_identifier(employee_id, entity=_EMPLOYEE)
    scope = guard.authorize(actor, MANAGE_STAFF_IN_UNIT_ACCESS.permission, unit_id=unidade)
    result = use_case.execute(
        RenameEmployeeCommand(
            tenant_id=scope.tenant_id,
            unit_id=UnitId(unidade),
            employee_id=EmployeeId(funcionario),
            name=payload.name,
        )
    )
    return EmployeeResponse.from_result(result)


@router.delete(
    "/units/{unit_id}/employees/{employee_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_employee(
    unit_id: str,
    employee_id: str,
    actor: CurrentActor,
    guard: StaffAccessGuard,
    use_case: Annotated[DeleteEmployeeUseCase, Depends(_get_delete_employee)],
) -> Response:
    """Remove o registro do funcionário endereçado."""
    unidade = validate_identifier(unit_id, entity=_UNIT)
    funcionario = validate_identifier(employee_id, entity=_EMPLOYEE)
    scope = guard.authorize(actor, MANAGE_STAFF_IN_UNIT_ACCESS.permission, unit_id=unidade)
    use_case.execute(
        DeleteEmployeeCommand(
            tenant_id=scope.tenant_id,
            unit_id=UnitId(unidade),
            employee_id=EmployeeId(funcionario),
        )
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
