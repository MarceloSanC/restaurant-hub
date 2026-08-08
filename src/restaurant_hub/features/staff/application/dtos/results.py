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
"""

from dataclasses import dataclass

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
