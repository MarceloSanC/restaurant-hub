"""Use case `copy_employee_to_unit` — o DoD de cópia do roadmap (Task 13).

Duas propriedades diferentes são travadas aqui, e a distinção importa:

1. **A cópia replica** — id novo, unidade destino, mesmo tenant, resto igual.
2. **Os dois registros são independentes** — e isto **não** se prova comparando
   campos logo após a cópia (nesse instante eles são iguais por definição). O
   teste **muta um e relê o outro pelo port**. Comparar logo após a cópia seria
   o falso verde clássico: passaria mesmo que os dois nomes apontassem para o
   mesmo objeto.
"""

from datetime import datetime
from decimal import Decimal

import pytest

from restaurant_hub.features.staff.application.dtos.commands import (
    CopyEmployeeToUnitCommand,
    DeactivateEmployeeCommand,
    RegisterUnavailabilityCommand,
    RenameEmployeeCommand,
)
from restaurant_hub.features.staff.application.dtos.results import EmployeeResult
from restaurant_hub.features.staff.application.errors import (
    EmployeeNotFoundError,
    SameUnitCopyError,
)
from restaurant_hub.features.staff.application.use_cases.copy_employee_to_unit import (
    CopyEmployeeToUnitUseCase,
)
from restaurant_hub.features.staff.application.use_cases.deactivate_employee import (
    DeactivateEmployeeUseCase,
)
from restaurant_hub.features.staff.application.use_cases.register_unavailability import (
    RegisterUnavailabilityUseCase,
)
from restaurant_hub.features.staff.application.use_cases.rename_employee import (
    RenameEmployeeUseCase,
)
from restaurant_hub.features.staff.domain.entities.employee import Employee
from restaurant_hub.features.staff.domain.entities.job_function import JobFunction
from restaurant_hub.features.staff.domain.exceptions.errors import (
    InvalidIdentifierError,
    StaffError,
)
from restaurant_hub.features.staff.domain.value_objects.identifiers import (
    EmployeeId,
    JobFunctionId,
    TenantId,
    UnitId,
    UserId,
)
from restaurant_hub.features.staff.domain.value_objects.shift_preference import (
    DayPeriod,
    ShiftPreference,
)
from restaurant_hub.features.staff.domain.value_objects.unavailability_period import (
    UnavailabilityPeriod,
)
from restaurant_hub.features.staff.domain.value_objects.workload_profile import FixedSchedule
from tests.fakes.features.staff.in_memory_identity_gateway import InMemoryIdentityGateway
from tests.fakes.features.staff.in_memory_staff_store import StaffFakes, staff_repositories
from tests.fakes.features.staff.stub_access_guards import TEST_ACTOR, PermissiveAccessGuard
from tests.fakes.shared.fake_id_generator import FakeIdGenerator

pytestmark = pytest.mark.unit

_A = TenantId("tenant-a")
_B = TenantId("tenant-b")
_U1 = UnitId("u1")
_U2 = UnitId("u2")
_E1 = EmployeeId("e1")
_F1 = JobFunctionId("f1")
_PERIODO = UnavailabilityPeriod(
    start=datetime(2026, 8, 3, 8, 0),
    end=datetime(2026, 8, 3, 12, 0),
)
_PREFERENCIA = ShiftPreference(periods=frozenset({DayPeriod.NIGHT}))


def _fakes(*, active: bool = True) -> StaffFakes:
    """Origem com o cadastro **cheio** — só assim a réplica prova alguma coisa."""
    fakes = staff_repositories()
    fakes.job_functions.add(JobFunction(id=_F1, tenant_id=_A, name="Cozinheiro"))
    fakes.employees.add(
        Employee(
            id=_E1,
            tenant_id=_A,
            unit_id=_U1,
            name="Maria",
            workload_profile=FixedSchedule(weekly_hours=Decimal("44")),
            shift_preference=_PREFERENCIA,
            job_function_ids=frozenset({_F1}),
            unavailabilities=(_PERIODO,),
            active=active,
        )
    )
    return fakes


def _result(fakes: StaffFakes, unidade: UnitId, employee_id: EmployeeId) -> EmployeeResult:
    """A releitura passa pelo endereço de três partes: a unidade é parâmetro
    porque a origem e a cópia vivem em unidades **diferentes** (ADR 3.4.0007).
    """
    employee = fakes.employees.find_by_id(_A, unidade, employee_id)
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


def _copiar(fakes: StaffFakes, gerador: FakeIdGenerator | None = None) -> CopyEmployeeToUnitUseCase:
    return CopyEmployeeToUnitUseCase(
        fakes.employees, gerador or FakeIdGenerator(), guard=PermissiveAccessGuard()
    )


# --- a cópia replica ---------------------------------------------------------


def test_copia_recebe_id_novo_unidade_destino_e_mesmo_tenant() -> None:
    fakes = _fakes()
    gerador = FakeIdGenerator()
    copia = _copiar(fakes, gerador).execute(
        CopyEmployeeToUnitCommand(
            actor=TEST_ACTOR, tenant_id=_A, unit_id=_U1, employee_id=_E1, target_unit_id=_U2
        )
    )

    assert copia.id == str(gerador.generated[0])
    assert copia.id != _E1
    assert copia.unit_id == _U2
    assert copia.tenant_id == _A


def test_copia_replica_todo_o_resto_do_cadastro() -> None:
    """A lista do ADR 3.2.0003: nome, perfil, preferência, funções, períodos."""
    fakes = _fakes()
    origem = _result(fakes, _U1, _E1)
    copia = _copiar(fakes).execute(
        CopyEmployeeToUnitCommand(
            actor=TEST_ACTOR, tenant_id=_A, unit_id=_U1, employee_id=_E1, target_unit_id=_U2
        )
    )

    assert (
        copia.name,
        copia.workload_profile,
        copia.shift_preference,
        copia.job_function_ids,
        copia.unavailabilities,
    ) == (
        origem.name,
        origem.workload_profile,
        origem.shift_preference,
        origem.job_function_ids,
        origem.unavailabilities,
    )
    # E a releitura pelo port confirma que a cópia foi de fato gravada.
    assert _result(fakes, _U2, EmployeeId(copia.id)) == copia


@pytest.mark.parametrize("active", [True, False])
def test_copia_carrega_o_estado_de_ciclo_de_vida_como_esta(active: bool) -> None:
    """Inclusive desligado (ADR 3.2.0003).

    Não cria estado inalcançável — registro inativo na unidade B já é
    alcançável por criar + desligar —, e recusar a cópia do desligado abriria
    um quarto item numa lista de exclusões que o ADR fechou em três.
    """
    fakes = _fakes(active=active)
    copia = _copiar(fakes).execute(
        CopyEmployeeToUnitCommand(
            actor=TEST_ACTOR, tenant_id=_A, unit_id=_U1, employee_id=_E1, target_unit_id=_U2
        )
    )
    assert copia.active is active


def test_a_origem_permanece_inalterada() -> None:
    """Comparação com snapshot tirado **antes** da cópia, campo a campo."""
    fakes = _fakes()
    antes = _result(fakes, _U1, _E1)
    _copiar(fakes).execute(
        CopyEmployeeToUnitCommand(
            actor=TEST_ACTOR, tenant_id=_A, unit_id=_U1, employee_id=_E1, target_unit_id=_U2
        )
    )
    assert _result(fakes, _U1, _E1) == antes


# --- independência estrutural (muta e relê) ----------------------------------


def test_editar_a_copia_nao_afeta_a_origem() -> None:
    fakes = _fakes()
    copia = _copiar(fakes).execute(
        CopyEmployeeToUnitCommand(
            actor=TEST_ACTOR, tenant_id=_A, unit_id=_U1, employee_id=_E1, target_unit_id=_U2
        )
    )
    origem_antes = _result(fakes, _U1, _E1)
    copia_id = EmployeeId(copia.id)

    RenameEmployeeUseCase(fakes.employees, guard=PermissiveAccessGuard()).execute(
        RenameEmployeeCommand(
            actor=TEST_ACTOR, tenant_id=_A, unit_id=_U2, employee_id=copia_id, name="Joana"
        )
    )
    RegisterUnavailabilityUseCase(fakes.employees, guard=PermissiveAccessGuard()).execute(
        RegisterUnavailabilityCommand(
            actor=TEST_ACTOR,
            tenant_id=_A,
            unit_id=_U2,
            employee_id=copia_id,
            period=UnavailabilityPeriod(
                start=datetime(2026, 8, 4, 8, 0), end=datetime(2026, 8, 4, 12, 0)
            ),
        )
    )
    DeactivateEmployeeUseCase(
        fakes.employees, InMemoryIdentityGateway(), guard=PermissiveAccessGuard()
    ).execute(
        DeactivateEmployeeCommand(actor=TEST_ACTOR, tenant_id=_A, unit_id=_U2, employee_id=copia_id)
    )

    assert _result(fakes, _U1, _E1) == origem_antes


def test_editar_a_origem_nao_afeta_a_copia() -> None:
    """O outro sentido — a independência não é assimétrica."""
    fakes = _fakes()
    copia = _copiar(fakes).execute(
        CopyEmployeeToUnitCommand(
            actor=TEST_ACTOR, tenant_id=_A, unit_id=_U1, employee_id=_E1, target_unit_id=_U2
        )
    )
    copia_id = EmployeeId(copia.id)
    copia_antes = _result(fakes, _U2, copia_id)

    RenameEmployeeUseCase(fakes.employees, guard=PermissiveAccessGuard()).execute(
        RenameEmployeeCommand(
            actor=TEST_ACTOR, tenant_id=_A, unit_id=_U1, employee_id=_E1, name="Joana"
        )
    )
    DeactivateEmployeeUseCase(
        fakes.employees, InMemoryIdentityGateway(), guard=PermissiveAccessGuard()
    ).execute(
        DeactivateEmployeeCommand(actor=TEST_ACTOR, tenant_id=_A, unit_id=_U1, employee_id=_E1)
    )

    assert _result(fakes, _U2, copia_id) == copia_antes


# --- recusas -----------------------------------------------------------------


def test_destino_igual_a_origem_e_recusado_sem_gravar() -> None:
    fakes = _fakes()
    antes = len(fakes.store.calls)

    with pytest.raises(SameUnitCopyError):
        _copiar(fakes).execute(
            CopyEmployeeToUnitCommand(
                actor=TEST_ACTOR, tenant_id=_A, unit_id=_U1, employee_id=_E1, target_unit_id=_U1
            )
        )

    assert "employees.add" not in fakes.store.calls[antes:]
    assert len(fakes.store.employees) == 1


@pytest.mark.parametrize("invalido", ["", "   "])
def test_unidade_destino_vazia_falha_depois_de_carregar_a_origem(invalido: str) -> None:
    """`InvalidIdentifierError` (achado F-03), com a conduta do terceiro caminho.

    Dos três lugares onde o erro é alcançável, este é o que carrega a origem
    antes de falhar. Uma unidade destino vazia passaria pela comparação com a
    unidade de origem (`"" != "u1"`) e só seria recusada na construção da
    cópia — daí a asserção ser sobre `employees.add` **não** ter acontecido.
    """
    fakes = _fakes()
    antes = len(fakes.store.calls)  # a fixture também escreve pelo port

    with pytest.raises(InvalidIdentifierError):
        _copiar(fakes).execute(
            CopyEmployeeToUnitCommand(
                actor=TEST_ACTOR,
                tenant_id=_A,
                unit_id=_U1,
                employee_id=_E1,
                target_unit_id=UnitId(invalido),
            )
        )

    conduta = fakes.store.calls[antes:]
    assert "employees.find_by_id" in conduta
    assert "employees.add" not in conduta
    assert len(fakes.store.employees) == 1


def test_origem_inexistente_e_not_found() -> None:
    fakes = _fakes()
    with pytest.raises(EmployeeNotFoundError):
        _copiar(fakes).execute(
            CopyEmployeeToUnitCommand(
                actor=TEST_ACTOR,
                tenant_id=_A,
                unit_id=_U1,
                employee_id=EmployeeId("fantasma"),
                target_unit_id=_U2,
            )
        )


def test_precedencia_origem_de_outro_tenant_vence_destino_igual() -> None:
    """Par duplo de §5.16, o mais delicado da Stage.

    A origem existe no tenant A, na unidade `u1`; o pedido vem com `tenant_id`
    do B e `target_unit_id` = `u1` — a unidade **real** da origem. Se a
    comparação de unidade viesse primeiro, a resposta seria `SameUnitCopyError`,
    que confirmaria ao tenant B **que o registro existe e em que unidade está**.

    Asserção por tipo exato, e reforçada pela conduta: nada foi gravado.
    """
    fakes = _fakes()
    antes = len(fakes.store.calls)

    with pytest.raises(StaffError) as excecao:
        _copiar(fakes).execute(
            CopyEmployeeToUnitCommand(
                actor=TEST_ACTOR, tenant_id=_B, unit_id=_U1, employee_id=_E1, target_unit_id=_U1
            )
        )
    assert type(excecao.value) is EmployeeNotFoundError

    assert "employees.add" not in fakes.store.calls[antes:]
    assert len(fakes.store.employees) == 1


# --- a cópia NÃO carrega o vínculo de login (Stage 3.5, CA04) ----------------


def test_ca04_a_copia_nao_carrega_o_vinculo_de_login() -> None:
    """A lista de exclusão do ADR 3.2.0003 ganha o seu primeiro item com conteúdo.

    Na 3.2 esta propriedade era vacuamente verdadeira (o campo não existia).
    Agora a origem **tem** login, e o clone nasce sem: a construção campo a campo
    do use case nunca nomeia `user_id`, e o default `None` faz o resto
    (ADR 3.5.0004 §5). A origem é **relida pelo port** — comparar o objeto em
    mãos seria o falso verde que o docstring deste módulo descreve.
    """
    fakes = _fakes()
    fakes.employees.link_login(_A, _U1, _E1, UserId("login-1"))

    copia = _copiar(fakes).execute(
        CopyEmployeeToUnitCommand(
            actor=TEST_ACTOR, tenant_id=_A, unit_id=_U1, employee_id=_E1, target_unit_id=_U2
        )
    )

    assert copia.user_id is None
    clone = fakes.employees.find_by_id(_A, _U2, copia.id)
    assert clone is not None and clone.user_id is None
    origem_relida = fakes.employees.find_by_id(_A, _U1, _E1)
    assert origem_relida is not None and origem_relida.user_id == UserId("login-1")


# --- limite declarado --------------------------------------------------------


def test_copiar_duas_vezes_para_o_mesmo_destino_cria_dois_registros() -> None:
    """**Comportamento fixado como decisão**, não como acidente (§5.11).

    Não há guarda porque qualquer guarda exigiria o registro guardar de **onde
    veio** — e "não vincula" é literal em workforce §3.7. A assimetria com
    `SameUnitCopyError` é essa: destino == origem é detectável sem vínculo
    (dois `unit_id` que o use case já tem em mãos); "já copiei antes" não é.

    Este teste existe para que ninguém "conserte" o comportamento sem revisitar
    o `[finding]` escalado para a 3.4 (confirmação explícita na borda).
    """
    fakes = _fakes()
    copiar = _copiar(fakes)
    comando = CopyEmployeeToUnitCommand(
        actor=TEST_ACTOR, tenant_id=_A, unit_id=_U1, employee_id=_E1, target_unit_id=_U2
    )

    primeira = copiar.execute(comando)
    segunda = copiar.execute(comando)

    assert primeira.id != segunda.id
    na_unidade_destino = fakes.employees.list_by_unit(_A, _U2, include_inactive=True)
    assert {registro.id for registro in na_unidade_destino} == {primeira.id, segunda.id}
    # Indistinguíveis entre si — nomes de funcionário não são únicos por design.
    assert {registro.name for registro in na_unidade_destino} == {"Maria"}


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


def test_ca11_copia_com_unidade_de_origem_alheia_nao_alcanca_o_registro() -> None:
    """A cópia é o caminho de **exfiltração** que o ADR 3.4.0007 nomeia.

    Com a origem lida por `(tenant, id)`, um ator da unidade B clonava para
    dentro da própria unidade o cadastro de um funcionário da A — as duas
    autorizações passavam, porque o ator via B duas vezes. Aqui o command declara
    origem `_U2` (onde o registro **não** está) e destino `_U1`, e o resultado
    tem de ser `EmployeeNotFoundError` sem nenhuma escrita.
    """
    fakes = _fakes()
    antes = len(fakes.store.calls)

    with pytest.raises(StaffError) as excecao:
        _copiar(fakes).execute(
            CopyEmployeeToUnitCommand(
                actor=TEST_ACTOR, tenant_id=_A, unit_id=_U2, employee_id=_E1, target_unit_id=_U1
            )
        )
    assert type(excecao.value) is EmployeeNotFoundError
    assert fakes.store.calls[antes:] == ["employees.find_by_id"]
