"""Use cases de indisponibilidade: registrar e remover (Task 11).

A não-sobreposição é consistência do **agregado** (workforce §3.6), imposta pelo
`Employee` na revalidação. O que estes use cases acrescentam é o ciclo
carregar → transicionar → gravar, e o que a suíte trava é que uma transição
recusada **não chega ao port**.

O caso adjacente (fim == início) tem teste próprio porque é a fronteira exata da
semântica semi-aberta `[início, fim)` (ADR 3.1.0001): é o valor em que um `<=`
trocado por `<` deixaria de rejeitar — ou passaria a rejeitar — sem que nenhum
outro caso percebesse.
"""

from collections.abc import Callable
from datetime import datetime
from decimal import Decimal

import pytest

from restaurant_hub.features.staff.application.dtos.commands import (
    RegisterUnavailabilityCommand,
    RemoveUnavailabilityCommand,
)
from restaurant_hub.features.staff.application.errors import (
    EmployeeNotFoundError,
    StaffApplicationError,
)
from restaurant_hub.features.staff.application.use_cases.register_unavailability import (
    RegisterUnavailabilityUseCase,
)
from restaurant_hub.features.staff.application.use_cases.remove_unavailability import (
    RemoveUnavailabilityUseCase,
)
from restaurant_hub.features.staff.domain.entities.employee import Employee
from restaurant_hub.features.staff.domain.entities.job_function import JobFunction
from restaurant_hub.features.staff.domain.exceptions.errors import (
    OverlappingUnavailabilityError,
    StaffError,
    UnavailabilityNotFoundError,
)
from restaurant_hub.features.staff.domain.value_objects.identifiers import (
    EmployeeId,
    JobFunctionId,
    TenantId,
    UnitId,
)
from restaurant_hub.features.staff.domain.value_objects.unavailability_period import (
    UnavailabilityPeriod,
)
from restaurant_hub.features.staff.domain.value_objects.workload_profile import FixedSchedule
from tests.fakes.features.staff.in_memory_staff_store import StaffFakes, staff_repositories
from tests.fakes.features.staff.stub_access_guards import TEST_ACTOR, PermissiveAccessGuard

pytestmark = pytest.mark.unit

_A = TenantId("tenant-a")
_B = TenantId("tenant-b")
_U1 = UnitId("u1")
_U2 = UnitId("u2")
_E1 = EmployeeId("e1")
_F1 = JobFunctionId("f1")


def _periodo(inicio: int, fim: int) -> UnavailabilityPeriod:
    return UnavailabilityPeriod(
        start=datetime(2026, 8, 3, inicio, 0),
        end=datetime(2026, 8, 3, fim, 0),
    )


def _fakes(*periodos: UnavailabilityPeriod) -> StaffFakes:
    fakes = staff_repositories()
    fakes.job_functions.add(JobFunction(id=_F1, tenant_id=_A, name="Cozinheiro"))
    fakes.employees.add(
        Employee(
            id=_E1,
            tenant_id=_A,
            unit_id=_U1,
            name="Maria",
            workload_profile=FixedSchedule(weekly_hours=Decimal("44")),
            shift_preference=None,
            job_function_ids=frozenset({_F1}),
            unavailabilities=periodos,
        )
    )
    return fakes


def _gravados(fakes: StaffFakes) -> tuple[UnavailabilityPeriod, ...]:
    employee = fakes.employees.find_by_id(_A, _U1, _E1)
    assert employee is not None
    return employee.unavailabilities


def _registrar(fakes: StaffFakes) -> RegisterUnavailabilityUseCase:
    return RegisterUnavailabilityUseCase(fakes.employees, guard=PermissiveAccessGuard())


def _remover(fakes: StaffFakes) -> RemoveUnavailabilityUseCase:
    return RemoveUnavailabilityUseCase(fakes.employees, guard=PermissiveAccessGuard())


# --- registrar ---------------------------------------------------------------


def test_registrar_acrescenta_o_periodo() -> None:
    fakes = _fakes()
    resultado = _registrar(fakes).execute(
        RegisterUnavailabilityCommand(
            actor=TEST_ACTOR, tenant_id=_A, unit_id=_U1, employee_id=_E1, period=_periodo(8, 12)
        )
    )
    assert resultado.unavailabilities == (_periodo(8, 12),)
    assert _gravados(fakes) == (_periodo(8, 12),)


def test_registrar_acrescenta_sem_apagar_os_existentes() -> None:
    fakes = _fakes(_periodo(8, 12))
    _registrar(fakes).execute(
        RegisterUnavailabilityCommand(
            actor=TEST_ACTOR, tenant_id=_A, unit_id=_U1, employee_id=_E1, period=_periodo(14, 16)
        )
    )
    assert _gravados(fakes) == (_periodo(8, 12), _periodo(14, 16))


def test_periodo_sobreposto_e_recusado_e_nada_e_gravado() -> None:
    fakes = _fakes(_periodo(8, 12))
    antes = len(fakes.store.calls)

    with pytest.raises(OverlappingUnavailabilityError):
        _registrar(fakes).execute(
            RegisterUnavailabilityCommand(
                actor=TEST_ACTOR,
                tenant_id=_A,
                unit_id=_U1,
                employee_id=_E1,
                period=_periodo(10, 14),
            )
        )

    assert "employees.update" not in fakes.store.calls[antes:]
    assert _gravados(fakes) == (_periodo(8, 12),)  # coleção antiga


def test_periodo_adjacente_e_aceito() -> None:
    """Fronteira exata da semântica semi-aberta: fim == início **não** conflita."""
    fakes = _fakes(_periodo(8, 12))
    _registrar(fakes).execute(
        RegisterUnavailabilityCommand(
            actor=TEST_ACTOR, tenant_id=_A, unit_id=_U1, employee_id=_E1, period=_periodo(12, 14)
        )
    )
    assert _gravados(fakes) == (_periodo(8, 12), _periodo(12, 14))


def test_registrar_em_registro_inexistente_e_not_found() -> None:
    fakes = _fakes()
    with pytest.raises(EmployeeNotFoundError):
        _registrar(fakes).execute(
            RegisterUnavailabilityCommand(
                actor=TEST_ACTOR,
                tenant_id=_A,
                unit_id=_U1,
                employee_id=EmployeeId("fantasma"),
                period=_periodo(8, 12),
            )
        )


def test_registrar_em_registro_de_outro_tenant_e_not_found() -> None:
    fakes = _fakes()
    with pytest.raises(EmployeeNotFoundError):
        _registrar(fakes).execute(
            RegisterUnavailabilityCommand(
                actor=TEST_ACTOR, tenant_id=_B, unit_id=_U1, employee_id=_E1, period=_periodo(8, 12)
            )
        )
    assert _gravados(fakes) == ()


def test_precedencia_registro_inexistente_vence_periodo_sobreposto() -> None:
    """Par duplo de §5.16, asserido por tipo exato."""
    fakes = _fakes(_periodo(8, 12))
    with pytest.raises((StaffError, StaffApplicationError)) as excecao:
        _registrar(fakes).execute(
            RegisterUnavailabilityCommand(
                actor=TEST_ACTOR,
                tenant_id=_A,
                unit_id=_U1,
                employee_id=EmployeeId("fantasma"),
                period=_periodo(10, 14),
            )
        )
    assert type(excecao.value) is EmployeeNotFoundError


# --- remover -----------------------------------------------------------------


def test_remover_tira_o_periodo_por_valor() -> None:
    """O período não tem identidade: quem o remove reapresenta o **valor**."""
    fakes = _fakes(_periodo(8, 12), _periodo(14, 16))
    resultado = _remover(fakes).execute(
        RemoveUnavailabilityCommand(
            actor=TEST_ACTOR, tenant_id=_A, unit_id=_U1, employee_id=_E1, period=_periodo(8, 12)
        )
    )
    assert resultado.unavailabilities == (_periodo(14, 16),)
    assert _gravados(fakes) == (_periodo(14, 16),)


def test_remover_periodo_ausente_e_erro_e_nada_e_gravado() -> None:
    fakes = _fakes(_periodo(8, 12))
    antes = len(fakes.store.calls)

    with pytest.raises(UnavailabilityNotFoundError):
        _remover(fakes).execute(
            RemoveUnavailabilityCommand(
                actor=TEST_ACTOR,
                tenant_id=_A,
                unit_id=_U1,
                employee_id=_E1,
                period=_periodo(14, 16),
            )
        )

    assert "employees.update" not in fakes.store.calls[antes:]
    assert _gravados(fakes) == (_periodo(8, 12),)


def test_remover_de_registro_inexistente_e_not_found() -> None:
    fakes = _fakes(_periodo(8, 12))
    with pytest.raises(EmployeeNotFoundError):
        _remover(fakes).execute(
            RemoveUnavailabilityCommand(
                actor=TEST_ACTOR,
                tenant_id=_A,
                unit_id=_U1,
                employee_id=EmployeeId("fantasma"),
                period=_periodo(8, 12),
            )
        )


def test_remover_de_registro_de_outro_tenant_e_not_found() -> None:
    fakes = _fakes(_periodo(8, 12))
    with pytest.raises(EmployeeNotFoundError):
        _remover(fakes).execute(
            RemoveUnavailabilityCommand(
                actor=TEST_ACTOR, tenant_id=_B, unit_id=_U1, employee_id=_E1, period=_periodo(8, 12)
            )
        )
    assert _gravados(fakes) == (_periodo(8, 12),)


def test_precedencia_registro_inexistente_vence_periodo_ausente() -> None:
    """Par duplo de §5.16, asserido por tipo exato.

    Importa porque os dois erros têm **status HTTP diferentes** na 3.4:
    `EmployeeNotFoundError` é 404 e `UnavailabilityNotFoundError` é 422
    (concept §4). Trocar a ordem trocaria a resposta da API.
    """
    fakes = _fakes(_periodo(8, 12))
    with pytest.raises((StaffError, StaffApplicationError)) as excecao:
        _remover(fakes).execute(
            RemoveUnavailabilityCommand(
                actor=TEST_ACTOR,
                tenant_id=_A,
                unit_id=_U1,
                employee_id=EmployeeId("fantasma"),
                period=_periodo(14, 16),
            )
        )
    assert type(excecao.value) is EmployeeNotFoundError


def test_ciclo_registrar_e_remover_volta_ao_estado_inicial() -> None:
    fakes = _fakes()
    _registrar(fakes).execute(
        RegisterUnavailabilityCommand(
            actor=TEST_ACTOR, tenant_id=_A, unit_id=_U1, employee_id=_E1, period=_periodo(8, 12)
        )
    )
    _remover(fakes).execute(
        RemoveUnavailabilityCommand(
            actor=TEST_ACTOR, tenant_id=_A, unit_id=_U1, employee_id=_E1, period=_periodo(8, 12)
        )
    )
    assert _gravados(fakes) == ()


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


def _movimentos_com_unidade_alheia() -> list[tuple[str, Callable[[StaffFakes], object]]]:
    return [
        (
            "register_unavailability",
            lambda fakes: _registrar(fakes).execute(
                RegisterUnavailabilityCommand(
                    actor=TEST_ACTOR,
                    tenant_id=_A,
                    unit_id=_U2,
                    employee_id=_E1,
                    period=_periodo(8, 12),
                )
            ),
        ),
        (
            "remove_unavailability",
            lambda fakes: _remover(fakes).execute(
                RemoveUnavailabilityCommand(
                    actor=TEST_ACTOR,
                    tenant_id=_A,
                    unit_id=_U2,
                    employee_id=_E1,
                    period=_periodo(8, 12),
                )
            ),
        ),
    ]


@pytest.mark.parametrize(
    ("nome", "executar"),
    _movimentos_com_unidade_alheia(),
    ids=[nome for nome, _ in _movimentos_com_unidade_alheia()],
)
def test_ca11_movimento_com_unidade_alheia_nao_alcanca_o_registro(
    nome: str, executar: Callable[[StaffFakes], object]
) -> None:
    fakes = _fakes(_periodo(8, 12))
    antes = len(fakes.store.calls)

    with pytest.raises((StaffError, StaffApplicationError)) as excecao:
        executar(fakes)
    assert type(excecao.value) is EmployeeNotFoundError, nome

    assert fakes.store.calls[antes:] == ["employees.find_by_id"], nome
    assert _gravados(fakes) == (_periodo(8, 12),), nome
