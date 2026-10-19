"""Edição do funcionário: nome, jornada e preferência (Task 10).

Os três use cases espelham transições do agregado (ADR 3.2.0004) e seguem o
mesmo ciclo **carregar → transicionar → gravar**. O que esta suíte protege, além
do efeito pretendido, é o efeito **não** pretendido: a comparação campo a campo
sobre o `EmployeeResult` é o que pega uma transição que mexa em algo além do que
foi pedido.

`assert employee == employee` seria vacuoso aqui — `Employee.__eq__` compara só
por id. Por isso a comparação é sempre sobre o result (`frozen`, igualdade por
valor) ou campo a campo sobre a entidade relida.
"""

import dataclasses
from collections.abc import Callable
from datetime import datetime
from decimal import Decimal

import pytest

from restaurant_hub.features.staff.application.dtos.commands import (
    ChangeWorkloadProfileCommand,
    DeclareShiftPreferenceCommand,
    RenameEmployeeCommand,
)
from restaurant_hub.features.staff.application.dtos.results import EmployeeResult
from restaurant_hub.features.staff.application.errors import EmployeeNotFoundError
from restaurant_hub.features.staff.application.use_cases.change_workload_profile import (
    ChangeWorkloadProfileUseCase,
)
from restaurant_hub.features.staff.application.use_cases.declare_shift_preference import (
    DeclareShiftPreferenceUseCase,
)
from restaurant_hub.features.staff.application.use_cases.rename_employee import (
    RenameEmployeeUseCase,
)
from restaurant_hub.features.staff.domain.entities.employee import Employee
from restaurant_hub.features.staff.domain.entities.job_function import JobFunction
from restaurant_hub.features.staff.domain.exceptions.errors import InvalidNameError, StaffError
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
from tests.fakes.features.staff.in_memory_staff_store import StaffFakes, staff_repositories
from tests.fakes.features.staff.stub_access_guards import TEST_ACTOR, PermissiveAccessGuard

pytestmark = pytest.mark.unit

_A = TenantId("tenant-a")
_B = TenantId("tenant-b")
_U1 = UnitId("u1")
_U2 = UnitId("u2")
_F1 = JobFunctionId("f1")
_E1 = EmployeeId("e1")
_FIXA = FixedSchedule(weekly_hours=Decimal("44"))
_PREFERENCIA = ShiftPreference(periods=frozenset({DayPeriod.NIGHT}))
_PERIODO = UnavailabilityPeriod(
    start=datetime(2026, 8, 3, 8, 0),
    end=datetime(2026, 8, 3, 12, 0),
)


def _com_funcionario(*, preferencia: ShiftPreference | None = None) -> StaffFakes:
    """Registro com **todos** os campos preenchidos.

    De propósito: a comparação "nenhum outro campo mudou" só tem valor se
    houver campos para mudar. Um registro mínimo tornaria a asserção quase
    vazia.
    """
    fakes = staff_repositories()
    fakes.job_functions.add(JobFunction(id=_F1, tenant_id=_A, name="Cozinheiro"))
    fakes.employees.add(
        Employee(
            id=_E1,
            tenant_id=_A,
            unit_id=_U1,
            name="Maria",
            workload_profile=_FIXA,
            shift_preference=preferencia,
            job_function_ids=frozenset({_F1}),
            unavailabilities=(_PERIODO,),
        )
    )
    return fakes


def _result(fakes: StaffFakes) -> EmployeeResult:
    """Snapshot do registro gravado, como `EmployeeResult` (igualdade por valor)."""
    employee = fakes.employees.find_by_id(_A, _U1, _E1)
    assert employee is not None
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


def _exceto(resultado: EmployeeResult, campo: str) -> dict[str, object]:
    return {
        f.name: getattr(resultado, f.name) for f in dataclasses.fields(resultado) if f.name != campo
    }


# --- renomear ----------------------------------------------------------------


def test_renomear_troca_o_nome_verbatim_e_a_releitura_confirma() -> None:
    fakes = _com_funcionario()
    antes = _result(fakes)

    resultado = RenameEmployeeUseCase(fakes.employees, guard=PermissiveAccessGuard()).execute(
        RenameEmployeeCommand(
            actor=TEST_ACTOR, tenant_id=_A, unit_id=_U1, employee_id=_E1, name="  Joana "
        )
    )

    assert resultado.name == "  Joana "
    depois = _result(fakes)
    assert depois.name == "  Joana "
    # Nenhum OUTRO campo mudou — campo a campo, não `entidade == entidade`.
    assert _exceto(depois, "name") == _exceto(antes, "name")
    assert resultado == depois  # o result descreve o que foi gravado


def test_renomear_nao_altera_tenant_nem_unidade() -> None:
    """§5.12: a localização do registro é imutável; nenhum use case a toca."""
    fakes = _com_funcionario()
    resultado = RenameEmployeeUseCase(fakes.employees, guard=PermissiveAccessGuard()).execute(
        RenameEmployeeCommand(
            actor=TEST_ACTOR, tenant_id=_A, unit_id=_U1, employee_id=_E1, name="Joana"
        )
    )
    assert (resultado.tenant_id, resultado.unit_id) == (_A, _U1)


# --- jornada -----------------------------------------------------------------


def test_troca_de_jornada_fixa_para_sob_demanda_e_de_volta() -> None:
    fakes = _com_funcionario()
    trocar = ChangeWorkloadProfileUseCase(fakes.employees, guard=PermissiveAccessGuard())
    antes = _result(fakes)

    sob_demanda = trocar.execute(
        ChangeWorkloadProfileCommand(
            actor=TEST_ACTOR,
            tenant_id=_A,
            unit_id=_U1,
            employee_id=_E1,
            workload_profile=OnDemand(),
        )
    )
    assert sob_demanda.workload_profile == OnDemand()
    assert _result(fakes).workload_profile == OnDemand()
    assert _exceto(_result(fakes), "workload_profile") == _exceto(antes, "workload_profile")

    de_volta = trocar.execute(
        ChangeWorkloadProfileCommand(
            actor=TEST_ACTOR,
            tenant_id=_A,
            unit_id=_U1,
            employee_id=_E1,
            workload_profile=FixedSchedule(weekly_hours=Decimal("20.5")),
        )
    )
    assert de_volta.workload_profile == FixedSchedule(weekly_hours=Decimal("20.5"))
    assert _result(fakes).workload_profile == FixedSchedule(weekly_hours=Decimal("20.5"))


# --- preferência -------------------------------------------------------------


def test_declarar_preferencia_quando_nao_havia() -> None:
    fakes = _com_funcionario(preferencia=None)
    antes = _result(fakes)

    resultado = DeclareShiftPreferenceUseCase(
        fakes.employees, guard=PermissiveAccessGuard()
    ).execute(
        DeclareShiftPreferenceCommand(
            actor=TEST_ACTOR,
            tenant_id=_A,
            unit_id=_U1,
            employee_id=_E1,
            shift_preference=_PREFERENCIA,
        )
    )

    assert resultado.shift_preference == _PREFERENCIA
    depois = _result(fakes)
    assert depois.shift_preference == _PREFERENCIA
    assert _exceto(depois, "shift_preference") == _exceto(antes, "shift_preference")


def test_declarar_none_limpa_a_preferencia() -> None:
    """`None` significa **limpe**, não "não mexa" (ADR 3.2.0004).

    É a metade da semântica que um `update_employee` com campos opcionais não
    conseguiria expressar — e a que um use case desatento implementaria como
    no-op, deixando o gerente sem como remover uma preferência.
    """
    fakes = _com_funcionario(preferencia=_PREFERENCIA)
    antes = _result(fakes)

    resultado = DeclareShiftPreferenceUseCase(
        fakes.employees, guard=PermissiveAccessGuard()
    ).execute(
        DeclareShiftPreferenceCommand(
            actor=TEST_ACTOR, tenant_id=_A, unit_id=_U1, employee_id=_E1, shift_preference=None
        )
    )

    assert resultado.shift_preference is None
    depois = _result(fakes)
    assert depois.shift_preference is None
    assert _exceto(depois, "shift_preference") == _exceto(antes, "shift_preference")


def test_substituir_uma_preferencia_por_outra() -> None:
    fakes = _com_funcionario(preferencia=_PREFERENCIA)
    outra = ShiftPreference(periods=frozenset({DayPeriod.MORNING, DayPeriod.AFTERNOON}))
    resultado = DeclareShiftPreferenceUseCase(
        fakes.employees, guard=PermissiveAccessGuard()
    ).execute(
        DeclareShiftPreferenceCommand(
            actor=TEST_ACTOR, tenant_id=_A, unit_id=_U1, employee_id=_E1, shift_preference=outra
        )
    )
    assert resultado.shift_preference == outra
    assert _result(fakes).shift_preference == outra


# --- registro inexistente ou de outro tenant ---------------------------------


def _comandos_dos_tres(tenant: TenantId, employee_id: EmployeeId) -> list[object]:
    return [
        RenameEmployeeCommand(
            actor=TEST_ACTOR, tenant_id=tenant, unit_id=_U1, employee_id=employee_id, name="Joana"
        ),
        ChangeWorkloadProfileCommand(
            actor=TEST_ACTOR,
            tenant_id=tenant,
            unit_id=_U1,
            employee_id=employee_id,
            workload_profile=OnDemand(),
        ),
        DeclareShiftPreferenceCommand(
            actor=TEST_ACTOR,
            tenant_id=tenant,
            unit_id=_U1,
            employee_id=employee_id,
            shift_preference=_PREFERENCIA,
        ),
    ]


def _executar(fakes: StaffFakes, comando: object) -> object:
    if isinstance(comando, RenameEmployeeCommand):
        return RenameEmployeeUseCase(fakes.employees, guard=PermissiveAccessGuard()).execute(
            comando
        )
    if isinstance(comando, ChangeWorkloadProfileCommand):
        return ChangeWorkloadProfileUseCase(fakes.employees, guard=PermissiveAccessGuard()).execute(
            comando
        )
    assert isinstance(comando, DeclareShiftPreferenceCommand)
    return DeclareShiftPreferenceUseCase(fakes.employees, guard=PermissiveAccessGuard()).execute(
        comando
    )


@pytest.mark.parametrize("indice", range(3))
def test_os_tres_com_registro_inexistente_nao_gravam(indice: int) -> None:
    fakes = _com_funcionario()
    comando = _comandos_dos_tres(_A, EmployeeId("fantasma"))[indice]
    antes_calls = len(fakes.store.calls)

    with pytest.raises(EmployeeNotFoundError):
        _executar(fakes, comando)

    # A CONDUTA: o `update` nem é tentado. Sem isto, o teste passaria com o
    # use case sem guarda nenhuma — a lei L-E2 do port levantaria o mesmo erro.
    assert "employees.update" not in fakes.store.calls[antes_calls:]


@pytest.mark.parametrize("indice", range(3))
def test_os_tres_com_registro_de_outro_tenant_nao_gravam(indice: int) -> None:
    """Id alheio é indistinguível de inexistente (concept §5.4)."""
    fakes = _com_funcionario()
    antes = _result(fakes)
    comando = _comandos_dos_tres(_B, _E1)[indice]
    antes_calls = len(fakes.store.calls)

    with pytest.raises(EmployeeNotFoundError):
        _executar(fakes, comando)

    assert "employees.update" not in fakes.store.calls[antes_calls:]
    assert _result(fakes) == antes  # o registro do tenant A ficou intacto


def test_precedencia_registro_inexistente_vence_nome_vazio() -> None:
    """Par duplo de §5.16: as duas checagens falham; **NotFound vence**.

    Se a transição rodasse antes do carregamento, o erro seria
    `InvalidNameError` — e a resposta trataria como problema de payload o que é
    um recurso que não existe. Asserção por **tipo exato**.
    """
    fakes = _com_funcionario()
    with pytest.raises(StaffError) as excecao:
        RenameEmployeeUseCase(fakes.employees, guard=PermissiveAccessGuard()).execute(
            RenameEmployeeCommand(
                actor=TEST_ACTOR,
                tenant_id=_A,
                unit_id=_U1,
                employee_id=EmployeeId("fantasma"),
                name="",
            )
        )
    assert type(excecao.value) is EmployeeNotFoundError


def test_nome_vazio_em_registro_existente_e_erro_do_dominio_sem_gravar() -> None:
    """O contrapositivo: com o registro presente, quem recusa é o agregado."""
    fakes = _com_funcionario()
    antes = _result(fakes)
    antes_calls = len(fakes.store.calls)

    with pytest.raises(InvalidNameError):
        RenameEmployeeUseCase(fakes.employees, guard=PermissiveAccessGuard()).execute(
            RenameEmployeeCommand(
                actor=TEST_ACTOR, tenant_id=_A, unit_id=_U1, employee_id=_E1, name="   "
            )
        )

    assert "employees.update" not in fakes.store.calls[antes_calls:]
    assert _result(fakes) == antes


# --- CA11: o endereço do funcionário tem três partes (ADR 3.4.0007) ----------
#
# **O que estes testes matam.** Antes da Stage 3.4 o use case resolvia o
# registro por `(tenant_id, employee_id)`, e a unidade do path só era conferida
# contra o **ator** — nunca contra o **registro**. Um gerente da unidade A
# alcançava qualquer funcionário do mesmo restaurante pondo a própria unidade no
# endereço. Se algum use case voltar a resolver por `(tenant, id)`, o registro é
# encontrado apesar da unidade alheia e a escrita acontece.
#
# A asserção sobre `fakes.store.calls` é o que dá poder ao teste: `pytest.raises`
# sozinho não distingue "não encontrou porque a unidade não bate" de "não
# encontrou por outro motivo e nada mais foi tentado". A conduta esperada é
# **exatamente** uma chamada — o lookup — e nenhuma escrita depois dela.


def _edicoes_com_unidade_alheia() -> list[tuple[str, Callable[[StaffFakes], object]]]:
    """Um item por use case de edição — a lista **é** a superfície, não amostra."""
    return [
        (
            "rename_employee",
            lambda fakes: RenameEmployeeUseCase(
                fakes.employees, guard=PermissiveAccessGuard()
            ).execute(
                RenameEmployeeCommand(
                    actor=TEST_ACTOR, tenant_id=_A, unit_id=_U2, employee_id=_E1, name="Joana"
                )
            ),
        ),
        (
            "change_workload_profile",
            lambda fakes: ChangeWorkloadProfileUseCase(
                fakes.employees, guard=PermissiveAccessGuard()
            ).execute(
                ChangeWorkloadProfileCommand(
                    actor=TEST_ACTOR,
                    tenant_id=_A,
                    unit_id=_U2,
                    employee_id=_E1,
                    workload_profile=OnDemand(),
                )
            ),
        ),
        (
            "declare_shift_preference",
            lambda fakes: DeclareShiftPreferenceUseCase(
                fakes.employees, guard=PermissiveAccessGuard()
            ).execute(
                DeclareShiftPreferenceCommand(
                    actor=TEST_ACTOR,
                    tenant_id=_A,
                    unit_id=_U2,
                    employee_id=_E1,
                    shift_preference=None,
                )
            ),
        ),
    ]


@pytest.mark.parametrize(
    ("nome", "executar"),
    _edicoes_com_unidade_alheia(),
    ids=[nome for nome, _ in _edicoes_com_unidade_alheia()],
)
def test_ca11_edicao_com_unidade_alheia_nao_alcanca_o_registro(
    nome: str, executar: Callable[[StaffFakes], object]
) -> None:
    fakes = _com_funcionario()
    antes_estado = _result(fakes)
    antes = len(fakes.store.calls)

    with pytest.raises(StaffError) as excecao:
        executar(fakes)
    assert type(excecao.value) is EmployeeNotFoundError, nome

    assert fakes.store.calls[antes:] == ["employees.find_by_id"], nome
    assert _result(fakes) == antes_estado, nome
