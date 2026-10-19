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

**O ator autenticado vai em todo command e query** (Stage 3.7, ADR 3.7.0001): o
use case autoriza de novo, com ele, o mesmo alvo que a rota acabou de autorizar.
A autorização daqui continua — vira defesa em profundidade, não a única linha —,
e é ela que mantém a ordem validar → autorizar antes de qualquer leitura em
identity.

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

from datetime import datetime
from typing import Annotated, Never

from fastapi import APIRouter, Depends, Response, status

from restaurant_hub.features.staff.application.dtos.commands import (
    AssignJobFunctionsCommand,
    ChangeWorkloadProfileCommand,
    CopyEmployeeToUnitCommand,
    CreateEmployeeCommand,
    CreateJobFunctionCommand,
    CreateLoginForEmployeeCommand,
    DeactivateEmployeeCommand,
    DeclareShiftPreferenceCommand,
    DeleteEmployeeCommand,
    DeleteJobFunctionCommand,
    ReactivateEmployeeCommand,
    RegisterUnavailabilityCommand,
    RemoveUnavailabilityCommand,
    RenameEmployeeCommand,
    RenameJobFunctionCommand,
)
from restaurant_hub.features.staff.application.dtos.queries import (
    ListEmployeesQuery,
    ListJobFunctionsQuery,
)
from restaurant_hub.features.staff.application.ports.out.identity_gateway import LoginDelivery
from restaurant_hub.features.staff.application.use_cases.assign_job_functions import (
    AssignJobFunctionsUseCase,
)
from restaurant_hub.features.staff.application.use_cases.change_workload_profile import (
    ChangeWorkloadProfileUseCase,
)
from restaurant_hub.features.staff.application.use_cases.copy_employee_to_unit import (
    CopyEmployeeToUnitUseCase,
)
from restaurant_hub.features.staff.application.use_cases.create_employee import (
    CreateEmployeeUseCase,
)
from restaurant_hub.features.staff.application.use_cases.create_job_function import (
    CreateJobFunctionUseCase,
)
from restaurant_hub.features.staff.application.use_cases.create_login_for_employee import (
    CreateLoginForEmployeeUseCase,
)
from restaurant_hub.features.staff.application.use_cases.deactivate_employee import (
    DeactivateEmployeeUseCase,
)
from restaurant_hub.features.staff.application.use_cases.declare_shift_preference import (
    DeclareShiftPreferenceUseCase,
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
from restaurant_hub.features.staff.application.use_cases.reactivate_employee import (
    ReactivateEmployeeUseCase,
)
from restaurant_hub.features.staff.application.use_cases.register_unavailability import (
    RegisterUnavailabilityUseCase,
)
from restaurant_hub.features.staff.application.use_cases.remove_unavailability import (
    RemoveUnavailabilityUseCase,
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
from restaurant_hub.features.staff.domain.value_objects.unavailability_period import (
    UnavailabilityPeriod,
)

from .dependencies import (
    MANAGE_JOB_FUNCTIONS_ACCESS,
    MANAGE_STAFF_IN_UNIT_ACCESS,
    MANAGE_USERS_IN_UNIT_ACCESS,
    CurrentActor,
    StaffAccessGuard,
    validate_identifier,
)
from .schemas import (
    AssignJobFunctionsRequest,
    ChangeWorkloadProfileRequest,
    CopyEmployeeRequest,
    CreateEmployeeRequest,
    CreateJobFunctionRequest,
    CreateLoginRequest,
    DeclareShiftPreferenceRequest,
    EmployeeLoginResponse,
    EmployeeResponse,
    JobFunctionResponse,
    RegisterUnavailabilityRequest,
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


def _get_assign_job_functions() -> AssignJobFunctionsUseCase:
    _nao_conectado("staff_assign_job_functions")


def _get_change_workload_profile() -> ChangeWorkloadProfileUseCase:
    _nao_conectado("staff_change_workload_profile")


def _get_declare_shift_preference() -> DeclareShiftPreferenceUseCase:
    _nao_conectado("staff_declare_shift_preference")


def _get_register_unavailability() -> RegisterUnavailabilityUseCase:
    _nao_conectado("staff_register_unavailability")


def _get_remove_unavailability() -> RemoveUnavailabilityUseCase:
    _nao_conectado("staff_remove_unavailability")


def _get_deactivate_employee() -> DeactivateEmployeeUseCase:
    _nao_conectado("staff_deactivate_employee")


def _get_reactivate_employee() -> ReactivateEmployeeUseCase:
    _nao_conectado("staff_reactivate_employee")


def _get_copy_employee_to_unit() -> CopyEmployeeToUnitUseCase:
    _nao_conectado("staff_copy_employee_to_unit")


def _get_create_login_for_employee() -> CreateLoginForEmployeeUseCase:
    _nao_conectado("staff_create_login_for_employee")


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
        CreateJobFunctionCommand(actor=actor, tenant_id=scope.tenant_id, name=payload.name)
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
    results = use_case.execute(ListJobFunctionsQuery(actor=actor, tenant_id=scope.tenant_id))
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
            actor=actor,
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
            actor=actor,
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
            actor=actor,
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
            actor=actor,
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
            actor=actor,
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
            actor=actor,
            tenant_id=scope.tenant_id,
            unit_id=UnitId(unidade),
            employee_id=EmployeeId(funcionario),
        )
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Perfil do funcionário — substituição (`PUT`) e acréscimo (`POST`)
#
# `PUT` onde a operação é **idempotente por substituição**: `assign_job_functions`
# troca o conjunto inteiro (o command diz literalmente "não é acréscimo") e
# `declare_shift_preference` com `null` **limpa**. `POST` onde há acréscimo de
# item: `register_unavailability`.
# ---------------------------------------------------------------------------


@router.put(
    "/units/{unit_id}/employees/{employee_id}/job-functions",
    response_model=EmployeeResponse,
)
def assign_job_functions(  # noqa: PLR0913
    # Ver `rename_employee`: a aridade é estrutural (dois ids de path, o corpo e
    # as três dependências que o FastAPI resolve).
    unit_id: str,
    employee_id: str,
    payload: AssignJobFunctionsRequest,
    actor: CurrentActor,
    guard: StaffAccessGuard,
    use_case: Annotated[AssignJobFunctionsUseCase, Depends(_get_assign_job_functions)],
) -> EmployeeResponse:
    """**Substitui** o conjunto de funções do funcionário — não acrescenta."""
    unidade = validate_identifier(unit_id, entity=_UNIT)
    funcionario = validate_identifier(employee_id, entity=_EMPLOYEE)
    job_function_ids = _job_function_ids(payload.job_function_ids)
    scope = guard.authorize(actor, MANAGE_STAFF_IN_UNIT_ACCESS.permission, unit_id=unidade)
    result = use_case.execute(
        AssignJobFunctionsCommand(
            actor=actor,
            tenant_id=scope.tenant_id,
            unit_id=UnitId(unidade),
            employee_id=EmployeeId(funcionario),
            job_function_ids=job_function_ids,
        )
    )
    return EmployeeResponse.from_result(result)


@router.put(
    "/units/{unit_id}/employees/{employee_id}/workload-profile",
    response_model=EmployeeResponse,
)
def change_workload_profile(  # noqa: PLR0913
    unit_id: str,
    employee_id: str,
    payload: ChangeWorkloadProfileRequest,
    actor: CurrentActor,
    guard: StaffAccessGuard,
    use_case: Annotated[ChangeWorkloadProfileUseCase, Depends(_get_change_workload_profile)],
) -> EmployeeResponse:
    """Troca o perfil de jornada (fixa ou sob demanda)."""
    unidade = validate_identifier(unit_id, entity=_UNIT)
    funcionario = validate_identifier(employee_id, entity=_EMPLOYEE)
    scope = guard.authorize(actor, MANAGE_STAFF_IN_UNIT_ACCESS.permission, unit_id=unidade)
    result = use_case.execute(
        ChangeWorkloadProfileCommand(
            actor=actor,
            tenant_id=scope.tenant_id,
            unit_id=UnitId(unidade),
            employee_id=EmployeeId(funcionario),
            workload_profile=to_workload_profile(payload.workload_profile),
        )
    )
    return EmployeeResponse.from_result(result)


@router.put(
    "/units/{unit_id}/employees/{employee_id}/shift-preference",
    response_model=EmployeeResponse,
)
def declare_shift_preference(  # noqa: PLR0913
    unit_id: str,
    employee_id: str,
    payload: DeclareShiftPreferenceRequest,
    actor: CurrentActor,
    guard: StaffAccessGuard,
    use_case: Annotated[DeclareShiftPreferenceUseCase, Depends(_get_declare_shift_preference)],
) -> EmployeeResponse:
    """Declara ou **limpa** a preferência de turno.

    `{"shift_preference": null}` limpa; corpo `{}` recebe 422, porque o campo não
    tem default — com default, o cliente que esquecesse o campo apagaria um dado
    sem pedir.
    """
    unidade = validate_identifier(unit_id, entity=_UNIT)
    funcionario = validate_identifier(employee_id, entity=_EMPLOYEE)
    scope = guard.authorize(actor, MANAGE_STAFF_IN_UNIT_ACCESS.permission, unit_id=unidade)
    result = use_case.execute(
        DeclareShiftPreferenceCommand(
            actor=actor,
            tenant_id=scope.tenant_id,
            unit_id=UnitId(unidade),
            employee_id=EmployeeId(funcionario),
            shift_preference=_to_shift_preference(payload.shift_preference),
        )
    )
    return EmployeeResponse.from_result(result)


@router.post(
    "/units/{unit_id}/employees/{employee_id}/unavailabilities",
    response_model=EmployeeResponse,
)
def register_unavailability(  # noqa: PLR0913
    unit_id: str,
    employee_id: str,
    payload: RegisterUnavailabilityRequest,
    actor: CurrentActor,
    guard: StaffAccessGuard,
    use_case: Annotated[RegisterUnavailabilityUseCase, Depends(_get_register_unavailability)],
) -> EmployeeResponse:
    """Acrescenta um período de indisponibilidade — **200, não 201**.

    O período não é recurso endereçável: não ganha URL própria, e um 201 sem
    `Location` prometeria uma que não existe. A resposta é o funcionário
    resultante, como em toda escrita.
    """
    unidade = validate_identifier(unit_id, entity=_UNIT)
    funcionario = validate_identifier(employee_id, entity=_EMPLOYEE)
    scope = guard.authorize(actor, MANAGE_STAFF_IN_UNIT_ACCESS.permission, unit_id=unidade)
    result = use_case.execute(
        RegisterUnavailabilityCommand(
            actor=actor,
            tenant_id=scope.tenant_id,
            unit_id=UnitId(unidade),
            employee_id=EmployeeId(funcionario),
            period=UnavailabilityPeriod(start=payload.start, end=payload.end),
        )
    )
    return EmployeeResponse.from_result(result)


@router.delete(
    "/units/{unit_id}/employees/{employee_id}/unavailabilities",
    response_model=EmployeeResponse,
)
def remove_unavailability(  # noqa: PLR0913
    unit_id: str,
    employee_id: str,
    start: datetime,
    end: datetime,
    actor: CurrentActor,
    guard: StaffAccessGuard,
    use_case: Annotated[RemoveUnavailabilityUseCase, Depends(_get_remove_unavailability)],
) -> EmployeeResponse:
    """Remove um período **por igualdade de valor**, não por id.

    `UnavailabilityPeriod` é value object e não tem identidade própria: quem o
    remove reapresenta o valor. Daí os query params — eles expressam isso sem
    exigir corpo num `DELETE`. Período inexistente responde **422**
    (`UnavailabilityNotFoundError`), e não 404: o período é um valor **dentro**
    do agregado, e o funcionário existe e foi encontrado.
    """
    unidade = validate_identifier(unit_id, entity=_UNIT)
    funcionario = validate_identifier(employee_id, entity=_EMPLOYEE)
    scope = guard.authorize(actor, MANAGE_STAFF_IN_UNIT_ACCESS.permission, unit_id=unidade)
    result = use_case.execute(
        RemoveUnavailabilityCommand(
            actor=actor,
            tenant_id=scope.tenant_id,
            unit_id=UnitId(unidade),
            employee_id=EmployeeId(funcionario),
            period=UnavailabilityPeriod(start=start, end=end),
        )
    )
    return EmployeeResponse.from_result(result)


# ---------------------------------------------------------------------------
# Ciclo de vida e cópia
#
# `termination` e `rehire` são **sub-recursos `POST`** porque são as duas
# transições nomeadas do ciclo de vida (ADR 3.2.0006), não edição de campo. Um
# `PATCH {"active": false}` faria a transição parecer atribuição de atributo — a
# leitura que o ADR 3.2.0007 recusa, e que apagaria a diferença entre "desligar"
# e "corrigir um booleano".
# ---------------------------------------------------------------------------


@router.post(
    "/units/{unit_id}/employees/{employee_id}/termination",
    response_model=EmployeeResponse,
)
def deactivate_employee(
    unit_id: str,
    employee_id: str,
    actor: CurrentActor,
    guard: StaffAccessGuard,
    use_case: Annotated[DeactivateEmployeeUseCase, Depends(_get_deactivate_employee)],
) -> EmployeeResponse:
    """Desliga o funcionário — o registro **sobrevive** (ADR 3.2.0006)."""
    unidade = validate_identifier(unit_id, entity=_UNIT)
    funcionario = validate_identifier(employee_id, entity=_EMPLOYEE)
    scope = guard.authorize(actor, MANAGE_STAFF_IN_UNIT_ACCESS.permission, unit_id=unidade)
    result = use_case.execute(
        DeactivateEmployeeCommand(
            actor=actor,
            tenant_id=scope.tenant_id,
            unit_id=UnitId(unidade),
            employee_id=EmployeeId(funcionario),
        )
    )
    return EmployeeResponse.from_result(result)


@router.post(
    "/units/{unit_id}/employees/{employee_id}/rehire",
    response_model=EmployeeResponse,
)
def reactivate_employee(
    unit_id: str,
    employee_id: str,
    actor: CurrentActor,
    guard: StaffAccessGuard,
    use_case: Annotated[ReactivateEmployeeUseCase, Depends(_get_reactivate_employee)],
) -> EmployeeResponse:
    """Recontrata o funcionário, devolvendo-o à listagem default."""
    unidade = validate_identifier(unit_id, entity=_UNIT)
    funcionario = validate_identifier(employee_id, entity=_EMPLOYEE)
    scope = guard.authorize(actor, MANAGE_STAFF_IN_UNIT_ACCESS.permission, unit_id=unidade)
    result = use_case.execute(
        ReactivateEmployeeCommand(
            actor=actor,
            tenant_id=scope.tenant_id,
            unit_id=UnitId(unidade),
            employee_id=EmployeeId(funcionario),
        )
    )
    return EmployeeResponse.from_result(result)


@router.post(
    "/units/{unit_id}/employees/{employee_id}/copies",
    response_model=EmployeeResponse,
    status_code=status.HTTP_201_CREATED,
)
def copy_employee_to_unit(  # noqa: PLR0913
    unit_id: str,
    employee_id: str,
    payload: CopyEmployeeRequest,
    actor: CurrentActor,
    guard: StaffAccessGuard,
    use_case: Annotated[CopyEmployeeToUnitUseCase, Depends(_get_copy_employee_to_unit)],
) -> EmployeeResponse:
    """Copia o registro para **outra** unidade do mesmo restaurante.

    **Duas chamadas ao guard, com alvos distintos, e a duplicação é L-AG4
    aplicada — não uma otimização esquecida.** A origem (`unit_id` do path) e o
    destino (`target_unit_id` do corpo) são dois alvos: reusar o escopo da origem
    para alcançar o destino é escalada de escopo, e é assim que uma cópia vira
    exfiltração para uma unidade que o ator não enxerga.

    **A orientação é fixa e é o que CA34 trava:** `unit_id` do command é a
    **origem** (de onde se lê) e `target_unit_id` é o **destino** (onde a cópia
    cai). Inverter os dois sobrevive a todo critério que só olha status —
    autorizar as duas unidades e gravar na errada continua respondendo 201.

    `target_unit_id` passa pelo **validador de identificador antes de qualquer
    autorização**: ele é o segundo alvo, e vai para `units.find_by_id` **dentro
    de identity**, onde o byte NUL vira `DataError` e 500.

    As três recusas do destino — outro tenant, inexistente, não visível —
    produzem o **mesmo** status e o **mesmo** corpo, por desenho: quem não
    enxerga a unidade não pode distinguir "não existe" de "existe e não é sua".
    """
    unidade = validate_identifier(unit_id, entity=_UNIT)
    funcionario = validate_identifier(employee_id, entity=_EMPLOYEE)
    destino = validate_identifier(payload.target_unit_id, entity=_UNIT)

    scope = guard.authorize(actor, MANAGE_STAFF_IN_UNIT_ACCESS.permission, unit_id=unidade)
    guard.authorize(actor, MANAGE_STAFF_IN_UNIT_ACCESS.permission, unit_id=destino)

    result = use_case.execute(
        CopyEmployeeToUnitCommand(
            actor=actor,
            tenant_id=scope.tenant_id,
            unit_id=UnitId(unidade),
            employee_id=EmployeeId(funcionario),
            target_unit_id=UnitId(destino),
        )
    )
    return EmployeeResponse.from_result(result)


# ---------------------------------------------------------------------------
# Stage 3.5 — R17: o login do funcionário
# ---------------------------------------------------------------------------
#
# A única rota de staff que exige **duas** permissões, e as duas sobre o mesmo
# alvo — a unidade do path (concept 3.5 §5.3). `manage_staff` porque altera o
# registro do funcionário; `manage_users` porque cria uma conta em identity, e
# esta rota é um segundo caminho de entrada para "criar conta" que não passa por
# `/users/invitations` (finding da 2.4). A ordem das duas é contrato: a de staff
# primeiro, e a de identity **não acontece** quando a primeira nega — CA10 assere
# a sequência e a ausência com o dublê que registra chamadas.
#
# O `email` **não** passa por `validate_identifier` (concept §5.7): não é
# identificador de staff, é vocabulário de identity, que o valida atrás do
# gateway; a recusa volta traduzida (L-IG2) e o mapa de status a classifica.
#
# A rota **não** loga nem repete o `setup_link`: ele sai uma vez, no corpo, só no
# canal `link` — e `EmployeeLoginResponse` é o único schema que o carrega.


@router.post(
    "/units/{unit_id}/employees/{employee_id}/login",
    response_model=EmployeeLoginResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_login_for_employee(  # noqa: PLR0913
    unit_id: str,
    employee_id: str,
    payload: CreateLoginRequest,
    actor: CurrentActor,
    guard: StaffAccessGuard,
    use_case: Annotated[CreateLoginForEmployeeUseCase, Depends(_get_create_login_for_employee)],
) -> EmployeeLoginResponse:
    """Cria a conta pendente em identity e a vincula ao registro — 201 (R17)."""
    unidade = validate_identifier(unit_id, entity=_UNIT)
    funcionario = validate_identifier(employee_id, entity=_EMPLOYEE)
    scope = guard.authorize(actor, MANAGE_STAFF_IN_UNIT_ACCESS.permission, unit_id=unidade)
    guard.authorize(actor, MANAGE_USERS_IN_UNIT_ACCESS.permission, unit_id=unidade)
    result = use_case.execute(
        CreateLoginForEmployeeCommand(
            actor=actor,
            tenant_id=scope.tenant_id,
            unit_id=UnitId(unidade),
            employee_id=EmployeeId(funcionario),
            email=payload.email,
            delivery=LoginDelivery(payload.delivery),
        )
    )
    return EmployeeLoginResponse.from_result(result)
