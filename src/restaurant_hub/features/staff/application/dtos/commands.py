"""Commands — a entrada de cada use case de escrita do BC staff.

São DTOs `frozen`: o use case recebe **dado**, não entidade. Value objects
imutáveis do domínio (`WorkloadProfile`, `ShiftPreference`,
`UnavailabilityPeriod`) trafegam aqui por licença explícita do LAYOUT §7 — são
valores puros, indistinguíveis de primitivos para o consumidor. Entidades, não:
nem `Employee` nem `JobFunction` aparecem em nenhum campo.

**Todos carregam `tenant_id`**, e os que atuam sobre um registro existente
carregam também `unit_id` e o id do registro: nenhuma operação desta camada é
expressável sem escopo (ADR 3.2.0002).

**A unidade faz parte do endereço do funcionário** (ADR 3.4.0007 §3), e a ordem
dos campos é a ordem normativa do lookup — `(tenant_id, unit_id, employee_id)`.
Nenhum deles tem default, **de propósito**: um `unit_id: UnitId | None = None`
faria o campo ser esquecível, e omitir viraria caminho de escalada — a mesma
propriedade que o ADR 3.2.0002 já comprou para o tenant. Quem não sabe a
unidade não consegue formar o pedido.

`CreateEmployeeCommand` já a carregava; as duas queries não mudam
(`ListEmployeesQuery` já a exige e `ListJobFunctionsQuery` é tenant-scoped por
desenho, porque o catálogo pertence ao restaurante).

A conversão de texto cru para VO (`FixedSchedule(...)`, `ShiftPreference(...)`,
`UnavailabilityPeriod(...)`) é do adapter que recebe a requisição (Stage 3.4):
o command já chega com o VO **construído**, e quando essa construção falha o
erro (`InvalidWeeklyHoursError`, `EmptyShiftPreferenceError`,
`InvalidUnavailabilityPeriodError`) acontece **antes** do use case — é o
terceiro bloco da §6 do concept.
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
class CreateJobFunctionCommand:
    """Criação de uma função de trabalho no restaurante.

    Não há campo de estado: a função **não tem ciclo de vida** (ADR 3.2.0005).
    """

    tenant_id: TenantId
    name: str


@dataclass(frozen=True)
class RenameJobFunctionCommand:
    """Renomeação de uma função existente.

    Renomear para o **próprio nome atual** não é conflito (concept §5.5).
    """

    tenant_id: TenantId
    job_function_id: JobFunctionId
    name: str


@dataclass(frozen=True)
class DeleteJobFunctionCommand:
    """Remoção **definitiva** de uma função — guardada por referências (§5.9)."""

    tenant_id: TenantId
    job_function_id: JobFunctionId


@dataclass(frozen=True)
class CreateEmployeeCommand:
    """Criação do registro de funcionário **numa unidade**.

    Attributes:
        tenant_id: restaurante dono do registro.
        unit_id: unidade do registro — funcionário é registro **por unidade**.
        name: nome verbatim, não-único (homônimos são legítimos).
        workload_profile: exatamente um perfil (união de tipos da 3.1).
        job_function_ids: conjunto **não-vazio**; toda id é resolvida no tenant
            antes da construção (§5.8/§5.16).
        shift_preference: `None` = **sem preferência declarada** (ADR 3.1.0004),
            que é o default de um cadastro novo.
    """

    tenant_id: TenantId
    unit_id: UnitId
    name: str
    workload_profile: WorkloadProfile
    job_function_ids: frozenset[JobFunctionId]
    shift_preference: ShiftPreference | None = None


@dataclass(frozen=True)
class RenameEmployeeCommand:
    """Renomeação do registro de funcionário (nome verbatim)."""

    tenant_id: TenantId
    unit_id: UnitId
    employee_id: EmployeeId
    name: str


@dataclass(frozen=True)
class AssignJobFunctionsCommand:
    """**Substituição** do conjunto de funções do registro — não é acréscimo.

    Conjunto vazio é rejeitado pelo domínio (`EmptyJobFunctionsError`).
    """

    tenant_id: TenantId
    unit_id: UnitId
    employee_id: EmployeeId
    job_function_ids: frozenset[JobFunctionId]


@dataclass(frozen=True)
class ChangeWorkloadProfileCommand:
    """Troca do perfil de jornada (fixa ↔ sob demanda)."""

    tenant_id: TenantId
    unit_id: UnitId
    employee_id: EmployeeId
    workload_profile: WorkloadProfile


@dataclass(frozen=True)
class DeclareShiftPreferenceCommand:
    """Declaração (ou limpeza) da preferência de turno.

    `shift_preference` **não tem default de propósito**: aqui `None` significa
    "**limpe** a preferência", não "não mexa" — é a razão de o ADR 3.2.0004 ter
    escolhido use cases granulares em vez de um update parcial, onde `None`
    teria de significar as duas coisas ao mesmo tempo.
    """

    tenant_id: TenantId
    unit_id: UnitId
    employee_id: EmployeeId
    shift_preference: ShiftPreference | None


@dataclass(frozen=True)
class RegisterUnavailabilityCommand:
    """Registro de um período de indisponibilidade.

    Sobreposição com período já registrado é rejeitada pelo agregado
    (`OverlappingUnavailabilityError`); adjacente é aceito (ADR 3.1.0001).
    """

    tenant_id: TenantId
    unit_id: UnitId
    employee_id: EmployeeId
    period: UnavailabilityPeriod


@dataclass(frozen=True)
class RemoveUnavailabilityCommand:
    """Remoção de um período **por igualdade de valor**.

    O período não tem identidade própria: quem o remove reapresenta o valor.
    """

    tenant_id: TenantId
    unit_id: UnitId
    employee_id: EmployeeId
    period: UnavailabilityPeriod


@dataclass(frozen=True)
class DeactivateEmployeeCommand:
    """Desligamento do funcionário — o registro **sobrevive** (ADR 3.2.0006)."""

    tenant_id: TenantId
    unit_id: UnitId
    employee_id: EmployeeId


@dataclass(frozen=True)
class ReactivateEmployeeCommand:
    """Recontratação do funcionário — devolve o registro à listagem default."""

    tenant_id: TenantId
    unit_id: UnitId
    employee_id: EmployeeId


@dataclass(frozen=True)
class DeleteEmployeeCommand:
    """Remoção **definitiva** do registro — para o cadastro criado por engano.

    É o irmão duro de `DeactivateEmployeeCommand`: aqui a história some. Por
    isso a operação é guardada (L-E5).
    """

    tenant_id: TenantId
    unit_id: UnitId
    employee_id: EmployeeId


@dataclass(frozen=True)
class CopyEmployeeToUnitCommand:
    """Cópia do cadastro para **outra** unidade do mesmo restaurante.

    **`unit_id` é a unidade de ORIGEM** — a que endereça o registro a ser lido;
    `target_unit_id` é o destino, onde a cópia é gravada. É o único command em
    que as duas convivem, e confundi-las produz exatamente a exfiltração
    cross-unidade que esta Stage fecha.

    Não existe cópia cross-tenant, e não há como expressá-la: o command tem um
    `tenant_id` só (concept §5.11).
    """

    tenant_id: TenantId
    unit_id: UnitId
    employee_id: EmployeeId
    target_unit_id: UnitId
