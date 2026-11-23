"""Issue #207 — renomear e apagar função: a ordem das checagens e a corrida, com fakes.

A propriedade "permitido sse o ator alcança onde a função vale" é medida pela cadeia
real de identity em `tests/unit/features/staff/adapters/test_job_function_reach_chain.py`.
Aqui ficam o que aquela suíte não discrimina:

- **a ordem** — a existência vem antes do alcance (404 não depende de alcance), e o
  alcance vem antes da validação do nome, da sonda de unicidade e da guarda de
  referências (quem é negado não aprende nada sobre o pedido nem sobre o uso);
- **os alvos exatos** — uma autorização por unidade, em ordem estável, ou
  `manage_tenant` para "todas";
- **a corrida** — uma alteração de unidades comitada entre a leitura e a escrita
  recusa o pedido (L-JF2/L-JF3 revisadas), em vez de renomear ou apagar a função
  numa unidade que o ator não alcança.

O guard é o `InMemoryAccessGuard`, que concede a tripla exata de cada alvo.
"""

from decimal import Decimal

import pytest

from restaurant_hub.features.staff.application.dtos.commands import (
    DeleteJobFunctionCommand,
    RenameJobFunctionCommand,
)
from restaurant_hub.features.staff.application.errors import (
    JobFunctionEnablementChangedError,
    JobFunctionNotFoundError,
)
from restaurant_hub.features.staff.application.use_cases.delete_job_function import (
    DeleteJobFunctionUseCase,
)
from restaurant_hub.features.staff.application.use_cases.rename_job_function import (
    RenameJobFunctionUseCase,
)
from restaurant_hub.features.staff.domain.entities.employee import Employee
from restaurant_hub.features.staff.domain.entities.job_function import JobFunction
from restaurant_hub.features.staff.domain.value_objects.identifiers import (
    EmployeeId,
    JobFunctionId,
    TenantId,
    UnitId,
)
from restaurant_hub.features.staff.domain.value_objects.unit_enablement import UnitEnablement
from restaurant_hub.features.staff.domain.value_objects.workload_profile import FixedSchedule
from tests.fakes.features.staff.in_memory_access_guard import InMemoryAccessGuard
from tests.fakes.features.staff.in_memory_job_function_repository import (
    InMemoryJobFunctionRepository,
)
from tests.fakes.features.staff.in_memory_staff_store import StaffFakes, staff_repositories
from tests.fakes.features.staff.stub_access_guards import TEST_ACTOR

pytestmark = pytest.mark.unit

_T = TenantId("tenant-a")
_A = UnitId("u-a")
_B = UnitId("u-b")
_C = UnitId("u-c")
_F = JobFunctionId("f1")
_JF = "manage_job_functions"
_MT = "manage_tenant"
_TODAS = UnitEnablement.everywhere()
_OPERACOES = ("renomear", "apagar")


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


def _mundo(habilitacao: UnitEnablement, *, em_uso: bool = False) -> StaffFakes:
    fakes = staff_repositories()
    fakes.job_functions.add(
        JobFunction(id=_F, tenant_id=_T, name="Cozinheiro", unit_enablement=habilitacao)
    )
    if em_uso:
        fakes.employees.add(
            Employee(
                id=EmployeeId("e1"),
                tenant_id=_T,
                unit_id=_A,
                name="Maria",
                workload_profile=FixedSchedule(weekly_hours=Decimal("44")),
                shift_preference=None,
                job_function_ids=frozenset({_F}),
            )
        )
    return fakes


def _executar(  # noqa: PLR0913 — operação, mundo, guard e os três eixos que um teste degrada
    operacao: str,
    fakes: StaffFakes,
    guard: InMemoryAccessGuard,
    *,
    funcao: JobFunctionId = _F,
    nome: str = "Chef",
    job_functions: InMemoryJobFunctionRepository | None = None,
) -> None:
    repositorio = job_functions or fakes.job_functions
    if operacao == "renomear":
        RenameJobFunctionUseCase(repositorio, guard=guard).execute(
            RenameJobFunctionCommand(
                actor=TEST_ACTOR, tenant_id=_T, job_function_id=funcao, name=nome
            )
        )
    else:
        DeleteJobFunctionUseCase(repositorio, fakes.employees, guard=guard).execute(
            DeleteJobFunctionCommand(actor=TEST_ACTOR, tenant_id=_T, job_function_id=funcao)
        )


def _intacta(fakes: StaffFakes, habilitacao: UnitEnablement) -> bool:
    funcao = fakes.job_functions.find_by_id(_T, _F)
    return (
        funcao is not None and funcao.name == "Cozinheiro" and funcao.unit_enablement == habilitacao
    )


# --- alvos exatos --------------------------------------------------------------


@pytest.mark.parametrize("operacao", _OPERACOES)
def test_cada_unidade_em_que_a_funcao_vale_e_um_alvo_em_ordem_estavel(operacao: str) -> None:
    fakes = _mundo(_so(_C, _A))
    guard = _guard(_A, _B, _C)

    _executar(operacao, fakes, guard)

    assert guard.calls == [
        f"authorize({_JF},{_T},None)",
        f"authorize({_JF},{_T},{_A})",
        f"authorize({_JF},{_T},{_C})",
    ]


@pytest.mark.parametrize("operacao", _OPERACOES)
def test_funcao_em_todas_as_unidades_pede_manage_tenant_e_nenhuma_unidade(operacao: str) -> None:
    fakes = _mundo(_TODAS)
    guard = _guard(restaurante=True)

    _executar(operacao, fakes, guard)

    assert guard.calls == [f"authorize({_JF},{_T},None)", f"authorize({_MT},{_T},None)"]


@pytest.mark.parametrize("operacao", _OPERACOES)
def test_deter_todas_as_unidades_nomeadas_nao_basta_para_funcao_em_todas(operacao: str) -> None:
    """ "Todas" inclui unidades futuras: alcançar as de hoje não é alcançar o restaurante."""
    fakes = _mundo(_TODAS)
    guard = _guard(_A, _B, _C)

    with pytest.raises(type(guard.authorization_error)) as excinfo:
        _executar(operacao, fakes, guard)

    assert excinfo.value is guard.authorization_error
    assert _intacta(fakes, _TODAS)


@pytest.mark.parametrize("operacao", _OPERACOES)
def test_alcancar_so_parte_das_unidades_e_negado_sem_efeito(operacao: str) -> None:
    """Basta **uma** unidade fora do alcance: a que o ator alcança não absolve a outra."""
    fakes = _mundo(_so(_A, _B))
    guard = _guard(_A)
    antes = len(fakes.store.calls)

    with pytest.raises(type(guard.authorization_error)):
        _executar(operacao, fakes, guard)

    assert fakes.store.calls[antes:] == ["job_functions.find_by_id"]
    assert _intacta(fakes, _so(_A, _B))


# --- ordem ---------------------------------------------------------------------


@pytest.mark.parametrize("operacao", _OPERACOES)
def test_funcao_inexistente_e_not_found_antes_de_qualquer_alvo_de_unidade(operacao: str) -> None:
    fakes = _mundo(_so(_B))
    guard = _guard()  # nenhuma unidade: se o alcance viesse antes, negaria

    with pytest.raises(JobFunctionNotFoundError):
        _executar(operacao, fakes, guard, funcao=JobFunctionId("nao-existe"))

    assert guard.calls == [f"authorize({_JF},{_T},None)"]


def test_renomear_sem_alcance_nega_antes_de_validar_o_nome() -> None:
    """Quem não alcança a função não aprende a forma do pedido: o nome inválido é negado."""
    fakes = _mundo(_so(_B))
    guard = _guard(_A)

    with pytest.raises(type(guard.authorization_error)):
        _executar("renomear", fakes, guard, nome="")

    assert "job_functions.find_by_name" not in fakes.store.calls


def test_apagar_sem_alcance_nega_antes_da_guarda_de_referencias() -> None:
    """Negado com a função em uso: a resposta é a recusa, não `JobFunctionInUseError`."""
    fakes = _mundo(_so(_B), em_uso=True)
    guard = _guard(_A)

    with pytest.raises(type(guard.authorization_error)):
        _executar("apagar", fakes, guard)

    assert "employees.exists_by_job_function" not in fakes.store.calls
    assert _intacta(fakes, _so(_B))


# --- corrida -------------------------------------------------------------------


class _LeituraSeguidaDeAlteracaoDeUnidades(InMemoryJobFunctionRepository):
    """Fake cujo primeiro `find_by_id` é seguido de uma alteração de unidades comitada."""

    def __init__(self, fakes: StaffFakes, intercalada: UnitEnablement) -> None:
        super().__init__(fakes.store)
        self._intercalada: UnitEnablement | None = intercalada

    def find_by_id(self, tenant_id: TenantId, job_function_id: JobFunctionId) -> JobFunction | None:
        lida = super().find_by_id(tenant_id, job_function_id)
        if self._intercalada is not None and lida is not None:
            InMemoryJobFunctionRepository(self._store).update_enablement(
                lida.with_enablement(self._intercalada), expected=lida.unit_enablement
            )
            self._intercalada = None
        return lida


@pytest.mark.parametrize("operacao", _OPERACOES)
def test_gerente_de_a_que_leu_antes_do_alargamento_nao_age_em_b(operacao: str) -> None:
    """O cenário da issue: `{A}`; o dono alarga para `{A, B}`; o gerente de A renomeia/apaga.

    O gerente foi autorizado contra `{A}`, que leu. Sem a escrita condicional, o nome
    mudaria — ou a função sumiria — também em B, que ele não alcança.
    """
    fakes = _mundo(_so(_A))
    guard = _guard(_A)
    corrida = _LeituraSeguidaDeAlteracaoDeUnidades(fakes, _so(_A, _B))

    with pytest.raises(JobFunctionEnablementChangedError):
        _executar(operacao, fakes, guard, job_functions=corrida)

    assert _intacta(fakes, _so(_A, _B))


@pytest.mark.parametrize("operacao", _OPERACOES)
def test_sem_corrida_a_habilitacao_lida_e_a_condicao_e_a_escrita_passa(operacao: str) -> None:
    """Controle: a condição não é sempre-falsa."""
    fakes = _mundo(_so(_A))

    _executar(operacao, fakes, _guard(_A))

    funcao = fakes.job_functions.find_by_id(_T, _F)
    if operacao == "renomear":
        assert funcao is not None
        assert funcao.name == "Chef"
    else:
        assert funcao is None
