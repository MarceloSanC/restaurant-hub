"""Results — a saída de cada use case do BC staff.

Regra dura (CLAUDE.md nota 6, LAYOUT §7): use case devolve DTO, **nunca**
entidade. Por isso `EmployeeResult` carrega campos, não um `Employee`.

Os dois são `frozen`, logo têm **igualdade por valor** — e é isso que os torna o
alvo correto das asserções "nenhum outro campo mudou" do concept §11. As
entidades da 3.1 não servem para isso: `Employee.__eq__` e `JobFunction.__eq__`
comparam **só por id**, então `assert entidade == entidade` é vacuoso.

**O vínculo de login entrou na Stage 3.5** (`EmployeeResult.user_id`), e com
ele a restrição que a 3.2 deixou declarada passou a ter conteúdo: a cópia entre
unidades **não o carrega** (workforce §3.7; ADR 3.2.0003; ADR 3.5.0004 §5), e o
result é onde isso é verificável por teste. **Há um único sítio de construção
de `EmployeeResult`** — `use_cases/_results.py` —, para que um campo novo
apareça em **toda** resposta de funcionário sem depender de ninguém lembrar de
11 lugares (concept 3.5 D6; Gate 8 da issue #45).
"""

from dataclasses import dataclass, field

from restaurant_hub.features.staff.domain.value_objects.identifiers import (
    EmployeeId,
    JobFunctionId,
    TenantId,
    UnitId,
    UserId,
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
        user_id: o login em identity vinculado ao registro, ou `None` (Stage
            3.5). Default `None` — espelha `Employee.user_id` e é **seguro**
            porque nenhum use case constrói este DTO diretamente: todos passam
            por `employee_result`, que copia o campo da entidade (CA06). A
            cópia devolve `None` **por construção** (§5.2).
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
    user_id: UserId | None = None


@dataclass(frozen=True)
class EmployeeLoginResult:
    """O registro depois de vinculado **e**, só no canal `link`, o segredo (R17).

    Attributes:
        employee: o estado resultante do registro — com `user_id` preenchido —,
            pelo mesmo mapper de toda resposta de funcionário (CA06).
        setup_link: o link de definição de senha quando `delivery=LINK`; `None`
            quando foi por e-mail. `repr=False` porque é credencial bearer viva
            (ADR 3.5.0002 §3): sem isso qualquer traceback com `--showlocals`, ou
            log de debug do result, imprimiria o segredo. Sem default: o use case
            decide **explicitamente** `None` ou o link — um default `None`
            deixaria o canal `link` sair sem o segredo por omissão silenciosa.
    """

    employee: EmployeeResult
    setup_link: str | None = field(repr=False)
