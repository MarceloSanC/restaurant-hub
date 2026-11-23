"""O ponto único da regra de fim de vínculo (Stage 3.10, ADR 3.10.0001 §5; DoD da Stage).

Três camadas de prova:

1. **Estrutura (AST, CA9).** `revoke_login_sessions` e `is_employee_login` só são
   chamados em `_login_link.py`; todo use case que faz uma escrita que encerra
   vínculo (`deactivate`, `relink_login`, `unlink_login` do repositório) chama
   `end_active_link` antes, no mesmo `execute`. A escrita do port é reconhecida pelo
   argumento nomeado `expected_user_id`, que as três assinaturas exigem por nome —
   um apelido do repositório (`repo = self._employees`) não escapa, e as transições
   homônimas da entidade (`employee.deactivate()`) não são confundidas com ela.
2. **Comportamento da regra** (`end_active_link` direto), uma condição por teste.
3. **R13 sobre o ponto único e a escrita condicional**, inclusive o entrelace "vínculo
   entre a leitura e a escrita" (a ordem inversa do ADR 0.0.0010), com fakes.
"""

import ast
import pathlib
from decimal import Decimal
from typing import Final

import pytest

from restaurant_hub.features.staff.application.dtos.commands import DeactivateEmployeeCommand
from restaurant_hub.features.staff.application.ports.out.identity_gateway import LoginDelivery
from restaurant_hub.features.staff.application.use_cases._login_link import end_active_link
from restaurant_hub.features.staff.application.use_cases.deactivate_employee import (
    DeactivateEmployeeUseCase,
)
from restaurant_hub.features.staff.domain.entities.employee import Employee
from restaurant_hub.features.staff.domain.exceptions.errors import EmployeeLoginChangedError
from restaurant_hub.features.staff.domain.value_objects.identifiers import (
    EmployeeId,
    JobFunctionId,
    TenantId,
    UnitId,
    UserId,
)
from restaurant_hub.features.staff.domain.value_objects.workload_profile import FixedSchedule
from tests.fakes.features.staff.in_memory_employee_repository import InMemoryEmployeeRepository
from tests.fakes.features.staff.in_memory_identity_gateway import InMemoryIdentityGateway
from tests.fakes.features.staff.in_memory_staff_store import StaffFakes, staff_repositories
from tests.fakes.features.staff.stub_access_guards import TEST_ACTOR, PermissiveAccessGuard

pytestmark = pytest.mark.unit

_PASTA: Final = (
    pathlib.Path(__file__).resolve().parents[5]
    / "src"
    / "restaurant_hub"
    / "features"
    / "staff"
    / "application"
    / "use_cases"
)
_MODULO_DO_PONTO_UNICO: Final = "_login_link"
_CHAMADAS_EXCLUSIVAS: Final = frozenset({"revoke_login_sessions", "is_employee_login"})
_ESCRITAS_QUE_ENCERRAM: Final = frozenset({"deactivate", "relink_login", "unlink_login"})

# Os use cases que encerram vínculo ativo, transcritos — a varredura deriva o conjunto
# do código e compara. Use case novo que encerre vínculo entra aqui por decisão.
_ENCERRAM_VINCULO: Final = frozenset({"deactivate_employee"})


# --- 1. estrutura ------------------------------------------------------------


def _chamadas_por_nome(arvore: ast.AST) -> list[ast.Call]:
    return [n for n in ast.walk(arvore) if isinstance(n, ast.Call)]


def _e_escrita_que_encerra(chamada: ast.Call) -> bool:
    return (
        isinstance(chamada.func, ast.Attribute)
        and chamada.func.attr in _ESCRITAS_QUE_ENCERRAM
        and any(k.arg == "expected_user_id" for k in chamada.keywords)
    )


def _e_ponto_unico(chamada: ast.Call) -> bool:
    return isinstance(chamada.func, ast.Name) and chamada.func.id == "end_active_link"


def _violacoes_de_ordem(fonte: str) -> list[int]:
    """Linhas das escritas que encerram vínculo sem `end_active_link` antes, por função."""
    violacoes: list[int] = []
    for funcao in ast.walk(ast.parse(fonte)):
        if not isinstance(funcao, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        chamadas = _chamadas_por_nome(funcao)
        pontos = [c.lineno for c in chamadas if _e_ponto_unico(c)]
        violacoes += [
            c.lineno
            for c in chamadas
            if _e_escrita_que_encerra(c) and not any(p < c.lineno for p in pontos)
        ]
    return violacoes


def _modulos() -> dict[str, str]:
    return {a.stem: a.read_text("utf-8") for a in sorted(_PASTA.glob("*.py"))}


def test_revogacao_e_consulta_de_papel_so_no_ponto_unico() -> None:
    fora = {
        (nome, c.func.attr, c.lineno)
        for nome, fonte in _modulos().items()
        if nome != _MODULO_DO_PONTO_UNICO
        for c in _chamadas_por_nome(ast.parse(fonte))
        if isinstance(c.func, ast.Attribute) and c.func.attr in _CHAMADAS_EXCLUSIVAS
    }
    assert fora == set()


def test_o_ponto_unico_faz_as_duas_chamadas() -> None:
    """Controle: a varredura acima enxergaria as chamadas — elas existem no módulo."""
    feitas = {
        c.func.attr
        for c in _chamadas_por_nome(ast.parse(_modulos()[_MODULO_DO_PONTO_UNICO]))
        if isinstance(c.func, ast.Attribute)
    }
    assert feitas >= _CHAMADAS_EXCLUSIVAS


def test_toda_escrita_que_encerra_vinculo_vem_depois_do_ponto_unico() -> None:
    violacoes = {
        nome: linhas for nome, fonte in _modulos().items() if (linhas := _violacoes_de_ordem(fonte))
    }
    assert violacoes == {}


def test_os_use_cases_que_encerram_vinculo_sao_os_transcritos() -> None:
    derivados = {
        nome
        for nome, fonte in _modulos().items()
        if any(_e_escrita_que_encerra(c) for c in _chamadas_por_nome(ast.parse(fonte)))
    }
    assert derivados == _ENCERRAM_VINCULO


@pytest.mark.parametrize(
    "fonte",
    [
        pytest.param(
            "def execute(self, c):\n"
            "    self._employees.unlink_login(t, u, e, expected_user_id=x, expected_active=a)\n",
            id="sem-ponto-unico",
        ),
        pytest.param(
            "def execute(self, c):\n"
            "    repo = self._employees\n"
            "    repo.deactivate(t, u, e, expected_user_id=x, expected_active=a)\n"
            "    end_active_link(self._employees, self._gateway, e)\n",
            id="apelido-e-ponto-unico-depois",
        ),
    ],
)
def test_controle_a_varredura_de_ordem_reprova(fonte: str) -> None:
    assert _violacoes_de_ordem(fonte) != []


def test_controle_a_transicao_da_entidade_nao_conta_como_escrita() -> None:
    fonte = "def execute(self, c):\n    return to_result(employee.deactivate())\n"
    assert _violacoes_de_ordem(fonte) == []


# --- 2. a regra --------------------------------------------------------------

_A = TenantId("tenant-a")
_U1 = UnitId("u1")
_U2 = UnitId("u2")
_E1 = EmployeeId("e1")


def _registro(
    id_: str = "e1", *, unit_id: UnitId = _U1, user_id: UserId | None = None, active: bool = True
) -> Employee:
    return Employee(
        id=EmployeeId(id_),
        tenant_id=_A,
        unit_id=unit_id,
        name=f"Registro {id_}",
        workload_profile=FixedSchedule(weekly_hours=Decimal("44")),
        shift_preference=None,
        job_function_ids=frozenset({JobFunctionId("f1")}),
        user_id=user_id,
        active=active,
    )


def _arranjo() -> tuple[StaffFakes, InMemoryIdentityGateway, UserId]:
    fakes = staff_repositories()
    gateway = InMemoryIdentityGateway()
    login = gateway.provision_employee_login(
        email="maria@cantina.com", tenant_id=_A, unit_id=_U1, delivery=LoginDelivery.LINK
    ).user_id
    gateway.calls.clear()
    return fakes, gateway, login


def _gravar(fakes: StaffFakes, registro: Employee) -> None:
    fakes.store.employees[registro.id] = registro


def test_revoga_quando_o_registro_ativo_e_a_unica_fonte_do_login_de_funcionario() -> None:
    fakes, gateway, login = _arranjo()
    registro = _registro(user_id=login)
    _gravar(fakes, registro)

    end_active_link(fakes.employees, gateway, registro)

    assert gateway.revoked == [login]


def test_registro_desligado_nao_toca_identity() -> None:
    fakes, gateway, login = _arranjo()
    registro = _registro(user_id=login, active=False)

    end_active_link(fakes.employees, gateway, registro)

    assert gateway.calls == []


def test_registro_sem_login_nao_toca_identity() -> None:
    fakes, gateway, _ = _arranjo()

    end_active_link(fakes.employees, gateway, _registro())

    assert gateway.calls == []


def test_outro_registro_ativo_da_unidade_com_o_login_decide_sem_cruzar_a_fronteira() -> None:
    fakes, gateway, login = _arranjo()
    registro = _registro(user_id=login)
    _gravar(fakes, registro)
    _gravar(fakes, _registro("e2", user_id=login))

    end_active_link(fakes.employees, gateway, registro)

    assert gateway.calls == []


@pytest.mark.parametrize(
    "outro",
    [
        pytest.param({"unit_id": _U2}, id="outra-unidade"),
        pytest.param({"active": False}, id="desligado"),
        pytest.param({"user_id": UserId("outro-login")}, id="outro-login"),
    ],
)
def test_outro_registro_que_nao_concede_o_login_na_unidade_nao_impede(
    outro: dict[str, object],
) -> None:
    fakes, gateway, login = _arranjo()
    registro = _registro(user_id=login)
    _gravar(fakes, registro)
    _gravar(fakes, _registro("e2", **{"user_id": login, **outro}))  # type: ignore[arg-type]

    end_active_link(fakes.employees, gateway, registro)

    assert gateway.revoked == [login]


def test_login_de_outro_papel_nao_e_revogado() -> None:
    fakes, gateway, _ = _arranjo()
    gerente = UserId("login-do-gerente")
    gateway.seed_login_of_other_role(gerente, tenant_id=_A, unit_id=_U1)
    registro = _registro(user_id=gerente)
    _gravar(fakes, registro)

    end_active_link(fakes.employees, gateway, registro)

    assert gateway.revoked == []
    assert gateway.calls == [f"is_employee_login({gerente!r})"]


def test_login_desconhecido_nao_e_revogado() -> None:
    fakes, gateway, _ = _arranjo()
    registro = _registro(user_id=UserId("login-que-identity-nao-conhece"))
    _gravar(fakes, registro)

    end_active_link(fakes.employees, gateway, registro)

    assert gateway.revoked == []


def test_falha_da_consulta_de_papel_sobe_crua_sem_revogar() -> None:
    fakes, gateway, login = _arranjo()
    registro = _registro(user_id=login)
    _gravar(fakes, registro)
    falha = RuntimeError("identity fora")
    gateway.fail_role_query_with = falha

    with pytest.raises(RuntimeError) as excinfo:
        end_active_link(fakes.employees, gateway, registro)

    assert excinfo.value is falha
    assert gateway.revoked == []


# --- 3. R13 sobre o ponto único e a escrita condicional ----------------------


def _desligar(employees: InMemoryEmployeeRepository, gateway: InMemoryIdentityGateway) -> None:
    DeactivateEmployeeUseCase(employees, gateway, guard=PermissiveAccessGuard()).execute(
        DeactivateEmployeeCommand(actor=TEST_ACTOR, tenant_id=_A, unit_id=_U1, employee_id=_E1)
    )


class _VinculoEntreALeituraEAEscrita(InMemoryEmployeeRepository):
    """Um R17/R18 concorrente que comita entre a leitura do R13 e a escrita dele."""

    def __init__(self, fakes: StaffFakes, login: UserId) -> None:
        super().__init__(fakes.store)
        self._login = login

    def deactivate(
        self,
        tenant_id: TenantId,
        unit_id: UnitId,
        employee_id: EmployeeId,
        *,
        expected_user_id: UserId | None,
        expected_active: bool,
    ) -> None:
        super().link_login(tenant_id, unit_id, employee_id, self._login)
        super().deactivate(
            tenant_id,
            unit_id,
            employee_id,
            expected_user_id=expected_user_id,
            expected_active=expected_active,
        )


def test_r13_que_leu_sem_vinculo_e_recusado_por_um_vinculo_concorrente() -> None:
    """A ordem inversa do ADR 0.0.0010: o registro fica ativo **e** vinculado, nunca desligado."""
    fakes, gateway, login = _arranjo()
    _gravar(fakes, _registro())

    with pytest.raises(EmployeeLoginChangedError):
        _desligar(_VinculoEntreALeituraEAEscrita(fakes, login), gateway)

    relido = fakes.employees.find_by_id(_A, _U1, _E1)
    assert relido is not None
    assert (relido.active, relido.user_id) == (True, login)
    assert gateway.revoked == []


def test_r13_passa_ao_port_o_estado_que_leu() -> None:
    fakes, gateway, login = _arranjo()
    _gravar(fakes, _registro(user_id=login))
    vistos: list[tuple[UserId | None, bool]] = []

    class _Espiao(InMemoryEmployeeRepository):
        def deactivate(
            self,
            tenant_id: TenantId,
            unit_id: UnitId,
            employee_id: EmployeeId,
            *,
            expected_user_id: UserId | None,
            expected_active: bool,
        ) -> None:
            vistos.append((expected_user_id, expected_active))
            super().deactivate(
                tenant_id,
                unit_id,
                employee_id,
                expected_user_id=expected_user_id,
                expected_active=expected_active,
            )

    _desligar(_Espiao(fakes.store), gateway)

    assert vistos == [(login, True)]
