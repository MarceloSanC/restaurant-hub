"""Use case: substituir as unidades de uma função (Stage 3.11, CA7).

O guard é o `InMemoryAccessGuard` — concede a tripla exata de cada alvo —, porque
a regra sob teste é **de alcance**: quem pode mudar o quê (ADR 3.11.0001 §5). Um
"gerente de A" é o conjunto de concessões que o papel tem em produção: o catálogo
no tenant e na unidade A, sem `manage_tenant`.

Todo efeito é conferido **relendo pelo port**, e toda recusa confere que a escrita
nem foi tentada (`store.calls`) — o result é o que o use case diz ter feito.
"""

from decimal import Decimal

import pytest

from restaurant_hub.features.staff.application.dtos.commands import SetJobFunctionUnitsCommand
from restaurant_hub.features.staff.application.errors import (
    JobFunctionInUseError,
    JobFunctionNotFoundError,
)
from restaurant_hub.features.staff.application.use_cases.set_job_function_units import (
    SetJobFunctionUnitsUseCase,
)
from restaurant_hub.features.staff.domain.entities.employee import Employee
from restaurant_hub.features.staff.domain.entities.job_function import JobFunction
from restaurant_hub.features.staff.domain.exceptions.errors import InvalidUnitEnablementError
from restaurant_hub.features.staff.domain.value_objects.identifiers import (
    EmployeeId,
    JobFunctionId,
    TenantId,
    UnitId,
)
from restaurant_hub.features.staff.domain.value_objects.unit_enablement import UnitEnablement
from restaurant_hub.features.staff.domain.value_objects.workload_profile import FixedSchedule
from tests.fakes.features.staff.in_memory_access_guard import InMemoryAccessGuard
from tests.fakes.features.staff.in_memory_staff_store import StaffFakes, staff_repositories
from tests.fakes.features.staff.stub_access_guards import TEST_ACTOR

pytestmark = pytest.mark.unit

_T = TenantId("tenant-a")
_OUTRO = TenantId("tenant-b")
_A = UnitId("u-a")
_B = UnitId("u-b")
_C = UnitId("u-c")
_F = JobFunctionId("f1")
_JF = "manage_job_functions"
_MT = "manage_tenant"
_TODAS = UnitEnablement.everywhere()


def _so(*unidades: UnitId) -> UnitEnablement:
    return UnitEnablement.only(frozenset(unidades))


def _guard(*unidades: UnitId, restaurante: bool = False) -> InMemoryAccessGuard:
    """Catálogo no tenant e nas unidades dadas; `manage_tenant` só com `restaurante`."""
    guard = InMemoryAccessGuard(credential=TEST_ACTOR)
    guard.grant(_JF, tenant_id=_T)
    for unidade in unidades:
        guard.grant(_JF, tenant_id=_T, unit_id=unidade)
    if restaurante:
        guard.grant(_MT, tenant_id=_T)
    return guard


def _mundo(habilitacao: UnitEnablement) -> StaffFakes:
    fakes = staff_repositories()
    fakes.job_functions.add(
        JobFunction(id=_F, tenant_id=_T, name="Cozinheiro", unit_enablement=habilitacao)
    )
    return fakes


def _com_registro(fakes: StaffFakes, unidade: UnitId, *, id_: str, active: bool = True) -> None:
    fakes.employees.add(
        Employee(
            id=EmployeeId(id_),
            tenant_id=_T,
            unit_id=unidade,
            name="Maria",
            workload_profile=FixedSchedule(weekly_hours=Decimal("44")),
            shift_preference=None,
            job_function_ids=frozenset({_F}),
            active=active,
        )
    )


def _executar(
    fakes: StaffFakes,
    guard: InMemoryAccessGuard,
    unidades: frozenset[UnitId] | None,
    *,
    tenant: TenantId = _T,
    funcao: JobFunctionId = _F,
) -> object:
    return SetJobFunctionUnitsUseCase(fakes.job_functions, fakes.employees, guard=guard).execute(
        SetJobFunctionUnitsCommand(
            actor=TEST_ACTOR, tenant_id=tenant, job_function_id=funcao, unit_ids=unidades
        )
    )


def _gravada(fakes: StaffFakes) -> UnitEnablement:
    funcao = fakes.job_functions.find_by_id(_T, _F)
    assert funcao is not None
    return funcao.unit_enablement


def _escritas(fakes: StaffFakes, desde: int) -> list[str]:
    return [c for c in fakes.store.calls[desde:] if c.startswith("job_functions.update")]


# --- alcance: só o que muda ---------------------------------------------------


def test_ca7_gerente_de_a_habilita_em_a_uma_funcao_que_vale_so_em_b() -> None:
    """O caminho que a unicidade do nome exige: só **A** é autorizada, não B."""
    fakes = _mundo(_so(_B))
    guard = _guard(_A)

    resultado = _executar(fakes, guard, frozenset({_A, _B}))

    assert _gravada(fakes) == _so(_A, _B)
    assert resultado.unit_ids == (_A, _B)  # type: ignore[attr-defined]
    assert resultado.all_units is False  # type: ignore[attr-defined]
    assert guard.calls == [f"authorize({_JF},{_T},None)", f"authorize({_JF},{_T},{_A})"]


def test_ca7_remover_unidade_que_o_ator_nao_enxerga_e_negado_sem_escrita() -> None:
    """O gerente de A não tira a função de B — nem "trocando" B por A."""
    fakes = _mundo(_so(_B))
    guard = _guard(_A)
    antes = len(fakes.store.calls)

    with pytest.raises(type(guard.authorization_error)) as excinfo:
        _executar(fakes, guard, frozenset({_A}))

    assert excinfo.value is guard.authorization_error  # crua (L-AG2)
    assert _gravada(fakes) == _so(_B)
    assert _escritas(fakes, antes) == []


def test_as_unidades_que_mudam_sao_autorizadas_em_ordem_estavel() -> None:
    """Acrescentadas e removidas num só passo, em ordem `sorted`; a que fica não é alvo."""
    fakes = _mundo(_so(_A, _C))
    guard = _guard(_A, _B, _C)

    _executar(fakes, guard, frozenset({_A, _B}))

    assert guard.calls == [
        f"authorize({_JF},{_T},None)",
        f"authorize({_JF},{_T},{_B})",
        f"authorize({_JF},{_T},{_C})",
    ]
    assert _gravada(fakes) == _so(_A, _B)


def test_habilitacao_igual_a_gravada_nao_pede_alcance_alem_do_tenant() -> None:
    fakes = _mundo(_so(_B))
    guard = _guard()

    _executar(fakes, guard, frozenset({_B}))

    assert guard.calls == [f"authorize({_JF},{_T},None)"]
    assert _gravada(fakes) == _so(_B)


def test_todas_para_todas_nao_pede_manage_tenant() -> None:
    """R5 — reenviar "todas" para quem já vale em todas não muda nada: só o tenant."""
    fakes = _mundo(_TODAS)
    guard = _guard()

    _executar(fakes, guard, None)

    assert guard.calls == [f"authorize({_JF},{_T},None)"]
    assert _gravada(fakes) == _TODAS


@pytest.mark.parametrize(
    ("antes", "pedido"),
    [(_TODAS, frozenset({_A})), (_so(_A), None)],
    ids=["de-todas", "para-todas"],
)
def test_ca7_passar_de_ou_para_todas_sem_manage_tenant_e_negado(
    antes: UnitEnablement, pedido: frozenset[UnitId] | None
) -> None:
    """Deter o catálogo em todas as unidades nomeadas não basta: o alvo é o restaurante."""
    fakes = _mundo(antes)
    guard = _guard(_A, _B, _C)
    inicio = len(fakes.store.calls)

    with pytest.raises(type(guard.authorization_error)):
        _executar(fakes, guard, pedido)

    assert guard.calls == [f"authorize({_JF},{_T},None)", f"authorize({_MT},{_T},None)"]
    assert _gravada(fakes) == antes
    assert _escritas(fakes, inicio) == []


@pytest.mark.parametrize(
    ("antes", "pedido", "depois"),
    [(_TODAS, frozenset({_A}), _so(_A)), (_so(_A), None, _TODAS)],
    ids=["de-todas", "para-todas"],
)
def test_quem_alcanca_o_restaurante_passa_de_e_para_todas(
    antes: UnitEnablement, pedido: frozenset[UnitId] | None, depois: UnitEnablement
) -> None:
    """Com `manage_tenant`, nenhuma unidade precisa ser autorizada uma a uma."""
    fakes = _mundo(antes)
    guard = _guard(restaurante=True)

    resultado = _executar(fakes, guard, pedido)

    assert _gravada(fakes) == depois
    assert resultado.all_units is depois.all_units  # type: ignore[attr-defined]
    assert guard.calls == [f"authorize({_JF},{_T},None)", f"authorize({_MT},{_T},None)"]


# --- existência antes do alcance ---------------------------------------------


def test_ca7_funcao_inexistente_e_not_found_antes_de_qualquer_autorizacao_de_unidade() -> None:
    fakes = _mundo(_so(_B))
    guard = _guard()  # nenhuma unidade concedida: se fosse consultada, negaria

    with pytest.raises(JobFunctionNotFoundError):
        _executar(fakes, guard, frozenset({_A}), funcao=JobFunctionId("nao-existe"))

    assert guard.calls == [f"authorize({_JF},{_T},None)"]


def test_funcao_de_outro_tenant_e_not_found() -> None:
    """Id alheio é indistinguível de inexistente (concept 3.2 §5.4)."""
    fakes = _mundo(_so(_B))
    guard = InMemoryAccessGuard(credential=TEST_ACTOR)
    guard.grant(_JF, tenant_id=_OUTRO)
    guard.grant(_MT, tenant_id=_OUTRO)

    with pytest.raises(JobFunctionNotFoundError):
        _executar(fakes, guard, None, tenant=_OUTRO)

    assert _gravada(fakes) == _so(_B)


# --- validação local e guarda -------------------------------------------------


def test_conjunto_vazio_e_recusado_pelo_dominio_sem_escrita() -> None:
    fakes = _mundo(_so(_A))
    guard = _guard(_A)
    antes = len(fakes.store.calls)

    with pytest.raises(InvalidUnitEnablementError):
        _executar(fakes, guard, frozenset())

    assert _gravada(fakes) == _so(_A)
    assert _escritas(fakes, antes) == []
    assert "employees.list_units_referencing_job_function" not in fakes.store.calls[antes:]


@pytest.mark.parametrize("ativo", [True, False], ids=["ativo", "desligado"])
def test_ca7_estreitar_com_registro_detendo_a_funcao_na_unidade_removida_e_recusado(
    ativo: bool,
) -> None:
    """ADR 3.11.0002 — o desligado conta: o registro sobrevive e ainda aponta para a função."""
    fakes = _mundo(_so(_A, _B))
    _com_registro(fakes, _B, id_="e-b", active=ativo)
    guard = _guard(_A, _B)
    antes = len(fakes.store.calls)

    with pytest.raises(JobFunctionInUseError):
        _executar(fakes, guard, frozenset({_A}))

    assert _gravada(fakes) == _so(_A, _B)
    assert _escritas(fakes, antes) == []


def test_estreitar_de_todas_com_registro_fora_do_conjunto_novo_e_recusado() -> None:
    fakes = _mundo(_TODAS)
    _com_registro(fakes, _C, id_="e-c")

    with pytest.raises(JobFunctionInUseError):
        _executar(fakes, _guard(restaurante=True), frozenset({_A, _B}))

    assert _gravada(fakes) == _TODAS


def test_estreitar_quando_os_registros_estao_so_nas_unidades_que_ficam_e_aceito() -> None:
    fakes = _mundo(_so(_A, _B))
    _com_registro(fakes, _A, id_="e-a")

    _executar(fakes, _guard(_A, _B), frozenset({_A}))

    assert _gravada(fakes) == _so(_A)


@pytest.mark.parametrize("saindo", [_A, _C], ids=["sai-a-menor", "sai-a-maior"])
def test_estreitar_com_registros_numa_unidade_que_fica_e_noutra_que_sai_e_recusado(
    saindo: UnitId,
) -> None:
    """Basta **uma** unidade removida com registro: a que fica não absolve a que sai.

    Com registros em B (fica) e na que sai, a guarda que olhasse só uma unidade, ou
    que recusasse só quando todas as unidades com registro saíssem, aceitaria.
    """
    fakes = _mundo(_so(_A, _B, _C))
    _com_registro(fakes, _B, id_="e-b")
    _com_registro(fakes, saindo, id_="e-x")
    antes = len(fakes.store.calls)

    with pytest.raises(JobFunctionInUseError):
        _executar(fakes, _guard(_A, _B, _C), frozenset({_A, _B, _C} - {saindo}))

    assert _gravada(fakes) == _so(_A, _B, _C)
    assert _escritas(fakes, antes) == []


def test_alargar_para_todas_nao_consulta_referencias() -> None:
    """ "Todas" cobre qualquer unidade — a guarda não tem o que recusar."""
    fakes = _mundo(_so(_A))
    _com_registro(fakes, _A, id_="e-a")
    antes = len(fakes.store.calls)

    _executar(fakes, _guard(restaurante=True), None)

    assert "employees.list_units_referencing_job_function" not in fakes.store.calls[antes:]
    assert _gravada(fakes) == _TODAS


def test_a_escrita_e_so_da_habilitacao_e_o_nome_fica() -> None:
    """L-JF7 — `update_enablement`, nunca `update`: renomear é outra escrita."""
    fakes = _mundo(_so(_A))
    antes = len(fakes.store.calls)

    resultado = _executar(fakes, _guard(_A, _B), frozenset({_A, _B}))

    assert _escritas(fakes, antes) == ["job_functions.update_enablement"]
    assert resultado.name == "Cozinheiro"  # type: ignore[attr-defined]
    funcao = fakes.job_functions.find_by_id(_T, _F)
    assert funcao is not None
    assert funcao.name == "Cozinheiro"


def test_alcance_vem_antes_da_validacao_local_conjunto_vazio_sem_alcance_e_negado() -> None:
    """R8 — quem não alcança o que mudaria não aprende nem a forma do pedido.

    A função vale em todas as unidades e o ator não detém `manage_tenant`: o
    conjunto vazio, que o domínio recusaria, é **negado pelo guard antes** — com a
    ordem trocada, a resposta seria `InvalidUnitEnablementError` (Checkpoint C).
    """
    fakes = _mundo(_TODAS)
    guard = _guard(_A)

    with pytest.raises(type(guard.authorization_error)) as excinfo:
        _executar(fakes, guard, frozenset())

    assert excinfo.value is guard.authorization_error
    assert guard.calls[-1] == f"authorize({_MT},{_T},None)"


@pytest.mark.parametrize("pedido", [frozenset({_A}), frozenset({_A, _B})], ids=["igual", "alarga"])
def test_registro_ja_fora_da_habilitacao_nao_trava_mudanca_que_nao_tira_a_unidade_dele(
    pedido: frozenset[UnitId],
) -> None:
    """A guarda pergunta pelo que a mudança **tira**, não por toda unidade descoberta.

    O registro em C detém a função habilitada só em A — o estado que a corrida
    declarada no ADR 3.11.0002 pode deixar. Repetir a habilitação ou alargá-la para
    B não remove C (C já não era coberta), então nenhum dos dois é recusado.
    """
    fakes = _mundo(_so(_A))
    _com_registro(fakes, _C, id_="e-c")

    _executar(fakes, _guard(_A, _B), pedido)

    assert _gravada(fakes) == UnitEnablement.only(pedido)
