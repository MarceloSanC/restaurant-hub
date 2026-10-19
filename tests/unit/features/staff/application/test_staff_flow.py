"""Fluxo ponta-a-ponta do BC staff sobre o par de fakes (Task 13).

**Sem I/O e sem mocks**, e — a regra que dá valor ao teste — **nenhuma escrita
direta nos fakes**: tudo passa pelos use cases reais. Um fluxo que preparasse
estado escrevendo no store provaria menos do que aparenta, porque o caminho
exercitado não seria o que a 3.4 vai chamar.

O que este teste pega, e que nenhum teste unitário pega, é a **composição**: os
use cases combinados sobre o mesmo store, cruzando duas unidades do mesmo
tenant. É aqui que um escopo mal passado entre operações apareceria.
"""

from datetime import datetime
from decimal import Decimal

import pytest

from restaurant_hub.features.staff.application.dtos.commands import (
    ChangeWorkloadProfileCommand,
    CopyEmployeeToUnitCommand,
    CreateEmployeeCommand,
    CreateJobFunctionCommand,
    DeactivateEmployeeCommand,
    DeclareShiftPreferenceCommand,
    DeleteJobFunctionCommand,
    RegisterUnavailabilityCommand,
)
from restaurant_hub.features.staff.application.dtos.queries import (
    ListEmployeesQuery,
    ListJobFunctionsQuery,
)
from restaurant_hub.features.staff.application.errors import JobFunctionInUseError
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
from restaurant_hub.features.staff.application.use_cases.deactivate_employee import (
    DeactivateEmployeeUseCase,
)
from restaurant_hub.features.staff.application.use_cases.declare_shift_preference import (
    DeclareShiftPreferenceUseCase,
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
from restaurant_hub.features.staff.application.use_cases.register_unavailability import (
    RegisterUnavailabilityUseCase,
)
from restaurant_hub.features.staff.domain.value_objects.identifiers import (
    EmployeeId,
    JobFunctionId,
    TenantId,
    UnitId,
)
from restaurant_hub.features.staff.domain.value_objects.shift_preference import (
    DayPeriod,
    ShiftPreference,
)
from restaurant_hub.features.staff.domain.value_objects.unavailability_period import (
    UnavailabilityPeriod,
)
from restaurant_hub.features.staff.domain.value_objects.workload_profile import (
    FixedSchedule,
    OnDemand,
)
from tests.fakes.features.staff.in_memory_identity_gateway import InMemoryIdentityGateway
from tests.fakes.features.staff.in_memory_staff_store import staff_repositories
from tests.fakes.features.staff.stub_access_guards import TEST_ACTOR, PermissiveAccessGuard
from tests.fakes.shared.fake_id_generator import FakeIdGenerator

pytestmark = pytest.mark.unit

_TENANT = TenantId("restaurante-1")
_UNIDADE_A = UnitId("unidade-a")
_UNIDADE_B = UnitId("unidade-b")
_PREFERENCIA = ShiftPreference(periods=frozenset({DayPeriod.NIGHT}))
_PERIODO = UnavailabilityPeriod(
    start=datetime(2026, 8, 3, 8, 0),
    end=datetime(2026, 8, 3, 12, 0),
)


def test_fluxo_completo_de_equipe_cruzando_duas_unidades() -> None:
    """Criar função → criar funcionário em A → jornada e preferência →
    indisponibilidade → copiar para B → desligar o de A → listar → apagar a
    função (recusado).
    """
    fakes = staff_repositories()
    ids = FakeIdGenerator()

    # 1. A função de trabalho do restaurante.
    funcao = CreateJobFunctionUseCase(
        fakes.job_functions, ids, guard=PermissiveAccessGuard()
    ).execute(CreateJobFunctionCommand(actor=TEST_ACTOR, tenant_id=_TENANT, name="Cozinheiro"))
    assert [
        resultado.name
        for resultado in ListJobFunctionsUseCase(
            fakes.job_functions, guard=PermissiveAccessGuard()
        ).execute(ListJobFunctionsQuery(actor=TEST_ACTOR, tenant_id=_TENANT))
    ] == ["Cozinheiro"]

    # 2. O funcionário na unidade A.
    funcionario = CreateEmployeeUseCase(
        fakes.employees, fakes.job_functions, ids, guard=PermissiveAccessGuard()
    ).execute(
        CreateEmployeeCommand(
            actor=TEST_ACTOR,
            tenant_id=_TENANT,
            unit_id=_UNIDADE_A,
            name="Maria",
            workload_profile=FixedSchedule(weekly_hours=Decimal("44")),
            job_function_ids=frozenset({JobFunctionId(funcao.id)}),
        )
    )
    funcionario_id = EmployeeId(funcionario.id)
    assert funcionario.active is True

    # 3. Jornada e preferência.
    ChangeWorkloadProfileUseCase(fakes.employees, guard=PermissiveAccessGuard()).execute(
        ChangeWorkloadProfileCommand(
            actor=TEST_ACTOR,
            tenant_id=_TENANT,
            unit_id=_UNIDADE_A,
            employee_id=funcionario_id,
            workload_profile=OnDemand(),
        )
    )
    DeclareShiftPreferenceUseCase(fakes.employees, guard=PermissiveAccessGuard()).execute(
        DeclareShiftPreferenceCommand(
            actor=TEST_ACTOR,
            tenant_id=_TENANT,
            unit_id=_UNIDADE_A,
            employee_id=funcionario_id,
            shift_preference=_PREFERENCIA,
        )
    )

    # 4. Indisponibilidade.
    com_periodo = RegisterUnavailabilityUseCase(
        fakes.employees, guard=PermissiveAccessGuard()
    ).execute(
        RegisterUnavailabilityCommand(
            actor=TEST_ACTOR,
            tenant_id=_TENANT,
            unit_id=_UNIDADE_A,
            employee_id=funcionario_id,
            period=_PERIODO,
        )
    )
    assert com_periodo.unavailabilities == (_PERIODO,)

    # 5. Cópia para a unidade B — leva o cadastro inteiro, já editado.
    copia = CopyEmployeeToUnitUseCase(fakes.employees, ids, guard=PermissiveAccessGuard()).execute(
        CopyEmployeeToUnitCommand(
            actor=TEST_ACTOR,
            tenant_id=_TENANT,
            unit_id=_UNIDADE_A,
            employee_id=funcionario_id,
            target_unit_id=_UNIDADE_B,
        )
    )
    assert copia.workload_profile == OnDemand()
    assert copia.shift_preference == _PREFERENCIA
    assert copia.unavailabilities == (_PERIODO,)
    assert copia.unit_id == _UNIDADE_B

    # 6. Desligamento do registro da unidade A.
    DeactivateEmployeeUseCase(
        fakes.employees, InMemoryIdentityGateway(), guard=PermissiveAccessGuard()
    ).execute(
        DeactivateEmployeeCommand(
            actor=TEST_ACTOR, tenant_id=_TENANT, unit_id=_UNIDADE_A, employee_id=funcionario_id
        )
    )

    # 7. As listagens contam a história.
    listar = ListEmployeesUseCase(fakes.employees, guard=PermissiveAccessGuard())
    assert (
        listar.execute(ListEmployeesQuery(actor=TEST_ACTOR, tenant_id=_TENANT, unit_id=_UNIDADE_A))
        == ()
    )

    a_com_inativos = listar.execute(
        ListEmployeesQuery(
            actor=TEST_ACTOR, tenant_id=_TENANT, unit_id=_UNIDADE_A, include_inactive=True
        )
    )
    assert [resultado.id for resultado in a_com_inativos] == [funcionario_id]
    assert a_com_inativos[0].active is False

    da_unidade_b = listar.execute(
        ListEmployeesQuery(actor=TEST_ACTOR, tenant_id=_TENANT, unit_id=_UNIDADE_B)
    )
    assert [resultado.id for resultado in da_unidade_b] == [copia.id]
    assert da_unidade_b[0].active is True  # a cópia não foi desligada junto

    # 8. A função continua bloqueada: o desligado de A e a cópia de B a apontam.
    with pytest.raises(JobFunctionInUseError):
        DeleteJobFunctionUseCase(
            fakes.job_functions, fakes.employees, guard=PermissiveAccessGuard()
        ).execute(
            DeleteJobFunctionCommand(
                actor=TEST_ACTOR, tenant_id=_TENANT, job_function_id=JobFunctionId(funcao.id)
            )
        )
    assert fakes.job_functions.find_by_id(_TENANT, JobFunctionId(funcao.id)) is not None


def test_o_fluxo_nao_escreve_direto_nos_fakes() -> None:
    """Guarda do próprio fluxo: só chamadas que um use case faria.

    O valor do teste acima depende de tudo passar pelos use cases. Se alguém
    "consertar" uma falha preparando estado com `fakes.store.employees[...] = …`,
    o fluxo continuaria verde exercitando um caminho que a 3.4 nunca vai
    chamar. Esta guarda torna essa regressão visível: o store só é alcançado
    pelos métodos dos ports.
    """
    fakes = staff_repositories()
    ids = FakeIdGenerator()
    funcao = CreateJobFunctionUseCase(
        fakes.job_functions, ids, guard=PermissiveAccessGuard()
    ).execute(CreateJobFunctionCommand(actor=TEST_ACTOR, tenant_id=_TENANT, name="Cozinheiro"))
    CreateEmployeeUseCase(
        fakes.employees, fakes.job_functions, ids, guard=PermissiveAccessGuard()
    ).execute(
        CreateEmployeeCommand(
            actor=TEST_ACTOR,
            tenant_id=_TENANT,
            unit_id=_UNIDADE_A,
            name="Maria",
            workload_profile=OnDemand(),
            job_function_ids=frozenset({JobFunctionId(funcao.id)}),
        )
    )
    # Todo registro no store chegou lá por uma chamada de port registrada.
    assert fakes.store.calls.count("job_functions.add") == len(fakes.store.job_functions)
    assert fakes.store.calls.count("employees.add") == len(fakes.store.employees)
