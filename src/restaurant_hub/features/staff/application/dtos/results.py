"""Results — a saída de cada use case do BC staff.

Regra dura (CLAUDE.md nota 6, LAYOUT §7): use case devolve DTO, **nunca**
entidade. Por isso `EmployeeResult` carrega campos, não um `Employee`.

Os dois são `frozen`, logo têm **igualdade por valor** — e é isso que os torna o
alvo correto das asserções "nenhum outro campo mudou" do concept §11. As
entidades da 3.1 não servem para isso: `Employee.__eq__` e `JobFunction.__eq__`
comparam **só por id**, então `assert entidade == entidade` é vacuoso.

**Nenhum campo de vínculo de login.** Hoje isso é vacuamente verdadeiro (o
campo não existe no modelo da 3.1); fica declarado como **restrição para a
3.5**, que acrescenta `user_id` ao registro: a cópia entre unidades não o
carrega (workforce §3.7; concept §5.10), e o result é onde a ausência é
verificável por teste.

**Cada result é construído num sítio só, e o sítio mora aqui** (issue #45,
Gate 8). `EmployeeResult` era montado campo a campo em **onze** use cases:
acrescentar um atributo ao registro exigia onze edições idênticas, e esquecer
uma delas não produz erro de tipo — produz um result com o campo no default,
ou um `TypeError` num só dos onze caminhos. A regra é mecânica
(`scripts/check_layout.py`, regra 8) justamente porque a disciplina não é
observável em revisão de diff: o décimo-segundo sítio parece igual aos outros
onze.

As funções ficam **junto das classes** e não num `mappers.py` à parte porque o
que a regra assere é adjacência: o result e a única forma de construí-lo são a
mesma unidade de leitura. Elas são o **único** lugar do BC que lê entidade e
escreve DTO — a fronteira que LAYOUT §7 desenha, num ponto só por agregado.
"""

from dataclasses import dataclass

from restaurant_hub.features.staff.domain.entities.employee import Employee
from restaurant_hub.features.staff.domain.entities.job_function import JobFunction
from restaurant_hub.features.staff.domain.value_objects.identifiers import (
    EmployeeId,
    JobFunctionId,
    TenantId,
    UnitId,
)
from restaurant_hub.features.staff.domain.value_objects.shift_preference import ShiftPreference
from restaurant_hub.features.staff.domain.value_objects.unavailability_period import (
    UnavailabilityPeriod,
)
from restaurant_hub.features.staff.domain.value_objects.workload_profile import WorkloadProfile


@dataclass(frozen=True)
class JobFunctionResult:
    """Função de trabalho.

    **Sem campo de estado** — a função não tem ciclo de vida (ADR 3.2.0005).
    """

    id: JobFunctionId
    tenant_id: TenantId
    name: str


@dataclass(frozen=True)
class EmployeeResult:
    """Registro de funcionário.

    Attributes:
        id: identidade do registro.
        tenant_id: restaurante dono do registro.
        unit_id: unidade do registro — **imutável** (L-E3).
        name: nome verbatim.
        workload_profile: perfil de jornada (união de tipos da 3.1). Não é
            reduzido a primitivos aqui: reduzi-lo devolveria à borda o
            discriminador que a união existe para tornar irrepresentável.
        shift_preference: `None` = sem preferência declarada.
        job_function_ids: sai como `frozenset`, **sem ordem** — a ordem não é
            dado do domínio (ADR 3.1.0006). Ordenar para exibição é do adapter
            da 3.4.
        unavailabilities: períodos do registro, sem sobreposição.
        active: estado do ciclo de vida (ADR 3.2.0006).
    """

    id: EmployeeId
    tenant_id: TenantId
    unit_id: UnitId
    name: str
    workload_profile: WorkloadProfile
    shift_preference: ShiftPreference | None
    job_function_ids: frozenset[JobFunctionId]
    unavailabilities: tuple[UnavailabilityPeriod, ...]
    active: bool


def to_job_function_result(job_function: JobFunction) -> JobFunctionResult:
    """O único sítio de construção de `JobFunctionResult` (Gate 8, issue #45)."""
    return JobFunctionResult(
        id=job_function.id,
        tenant_id=job_function.tenant_id,
        name=job_function.name,
    )


def to_employee_result(employee: Employee) -> EmployeeResult:
    """O único sítio de construção de `EmployeeResult` (Gate 8, issue #45).

    Todos os campos são copiados verbatim da entidade: a função **não** filtra,
    ordena nem deriva nada. Uma projeção que decidisse algo aqui esconderia a
    decisão de todos os onze use cases que a chamam, e é o adapter — não este
    mapeamento — que ordena `job_function_ids` para exibição (ADR 3.1.0006).
    """
    return EmployeeResult(
        id=employee.id,
        tenant_id=employee.tenant_id,
        unit_id=employee.unit_id,
        name=employee.name,
        workload_profile=employee.workload_profile,
        shift_preference=employee.shift_preference,
        job_function_ids=employee.job_function_ids,
        unavailabilities=employee.unavailabilities,
        active=employee.active,
    )
