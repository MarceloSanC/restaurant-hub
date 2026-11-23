"""O ponto único da regra de fim de vínculo (Stage 3.10, ADR 3.10.0001 §5; DoD da Stage).

Três camadas de prova:

1. **Estrutura (AST, CA9).** `revoke_login_sessions` e `is_employee_login` só são
   chamados em `_login_link.py`, e ali só dentro de `end_active_link`; todo use case
   que faz uma escrita que encerra vínculo (`deactivate`, `relink_login`,
   `unlink_login` do repositório) chama `end_active_link` antes, no mesmo `execute`.
   A escrita do port é reconhecida pelo argumento nomeado `expected_user_id`, que
   as três assinaturas exigem por nome — um apelido do repositório
   (`repo = self._employees`) não escapa, e as transições
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

from restaurant_hub.features.staff.application.dtos.commands import (
    DeactivateEmployeeCommand,
    RelinkLoginCommand,
    UnlinkLoginCommand,
)
from restaurant_hub.features.staff.application.ports.out.identity_gateway import LoginDelivery
from restaurant_hub.features.staff.application.use_cases._login_link import end_active_link
from restaurant_hub.features.staff.application.use_cases.deactivate_employee import (
    DeactivateEmployeeUseCase,
)
from restaurant_hub.features.staff.application.use_cases.relink_login import RelinkLoginUseCase
from restaurant_hub.features.staff.application.use_cases.unlink_login import UnlinkLoginUseCase
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
# As transições da entidade que encerram vínculo: um use case que as aplicasse e
# gravasse por outro caminho (`update(employee.deactivate())`) também encerraria o
# vínculo ativo — contam, com qualquer receptor (Checkpoint C, bloco T05–T07, F1).
_TRANSICOES_QUE_ENCERRAM: Final = frozenset(
    {"deactivate", "deactivate_as_read", "relink_login", "unlink_login"}
)

# Os use cases que encerram vínculo ativo, transcritos — a varredura deriva o conjunto
# do código e compara. Use case novo que encerre vínculo entra aqui por decisão.
_ENCERRAM_VINCULO: Final = frozenset({"relink_login", "unlink_login", "deactivate_employee"})


# --- 1. estrutura ------------------------------------------------------------


def _chamadas_por_nome(arvore: ast.AST) -> list[ast.Call]:
    return [n for n in ast.walk(arvore) if isinstance(n, ast.Call)]


def _e_escrita_que_encerra(chamada: ast.Call) -> bool:
    return (
        isinstance(chamada.func, ast.Attribute)
        and chamada.func.attr in _ESCRITAS_QUE_ENCERRAM
        and any(k.arg == "expected_user_id" for k in chamada.keywords)
    )


def _encerra_vinculo(chamada: ast.Call) -> bool:
    """Escrita do port **ou** transição da entidade que encerra vínculo."""
    return _e_escrita_que_encerra(chamada) or (
        isinstance(chamada.func, ast.Attribute) and chamada.func.attr in _TRANSICOES_QUE_ENCERRAM
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
            if _encerra_vinculo(c) and not any(p < c.lineno for p in pontos)
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


def _e_end_active_link(nome: str) -> bool:
    """O ponto único — e as cópias dele que o mutmut escreve no módulo mutado.

    O job `mutation` do `audit-gate.yml` roda a suíte sobre `mutants/`, onde cada função
    de `_login_link.py` vira um trampolim mais as cópias `x_end_active_link__mutmut_*`
    (a original e uma por mutante). Elas são o mesmo ponto único; sem aceitá-las, a
    varredura reprovaria a própria corrida de mutação.
    """
    return nome == "end_active_link" or nome.startswith("x_end_active_link__mutmut_")


def _chamadas_exclusivas_fora_de_end_active_link(fonte: str) -> set[tuple[str, int]]:
    """As chamadas exclusivas que não estão no corpo de `end_active_link`."""
    arvore = ast.parse(fonte)
    dentro = {
        id(c)
        for funcao in arvore.body
        if isinstance(funcao, ast.FunctionDef) and _e_end_active_link(funcao.name)
        for c in _chamadas_por_nome(funcao)
    }
    return {
        (c.func.attr, c.lineno)
        for c in _chamadas_por_nome(arvore)
        if isinstance(c.func, ast.Attribute)
        and c.func.attr in _CHAMADAS_EXCLUSIVAS
        and id(c) not in dentro
    }


def test_no_modulo_do_ponto_unico_so_end_active_link_revoga() -> None:
    """Dentro do módulo permitido, só `end_active_link` revoga: o ponto é único.

    Uma segunda função de `_login_link.py` que revogasse passaria pela varredura acima
    (o módulo é o permitido). Até a issue #243 ela ficaria também invisível à regra
    10, que lia uma tabela de auxiliares escrita à mão — o ponto cego que a auditoria
    do PR #230 mediu. Desde a #243 a regra deriva os auxiliares que escrevem e a
    contaria; este teste continua cobrando o que é dele, o ponto único (ADR 3.8.0001
    decisão 5).
    """
    assert _chamadas_exclusivas_fora_de_end_active_link(_modulos()[_MODULO_DO_PONTO_UNICO]) == set()


def test_controle_outra_funcao_do_modulo_que_revoga_reprova() -> None:
    fonte = (
        "def end_active_link(gateway, employee):\n"
        "    gateway.revoke_login_sessions(employee.user_id)\n"
        "def cut(gateway, user_id):\n"
        "    gateway.revoke_login_sessions(user_id)\n"
    )
    assert _chamadas_exclusivas_fora_de_end_active_link(fonte) == {("revoke_login_sessions", 4)}


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
        if nome != _MODULO_DO_PONTO_UNICO
        and any(_encerra_vinculo(c) for c in _chamadas_por_nome(ast.parse(fonte)))
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
            "    end_active_link(self._gateway, e)\n",
            id="apelido-e-ponto-unico-depois",
        ),
    ],
)
def test_controle_a_varredura_de_ordem_reprova(fonte: str) -> None:
    assert _violacoes_de_ordem(fonte) != []


def test_controle_a_transicao_da_entidade_sem_ponto_unico_reprova() -> None:
    """`update(employee.deactivate())` desligaria um vinculado sem a regra (F1)."""
    fonte = "def execute(self, c):\n    self._employees.update(employee.deactivate())\n"
    assert _violacoes_de_ordem(fonte) != []


def test_controle_a_transicao_depois_do_ponto_unico_passa() -> None:
    fonte = (
        "def execute(self, c):\n"
        "    end_active_link(self._gateway, employee)\n"
        "    return to_result(employee.deactivate())\n"
    )
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

    end_active_link(gateway, registro)

    assert gateway.revoked == [login]


def test_registro_desligado_nao_toca_identity() -> None:
    _, gateway, login = _arranjo()
    registro = _registro(user_id=login, active=False)

    end_active_link(gateway, registro)

    assert gateway.calls == []


def test_registro_sem_login_nao_toca_identity() -> None:
    _, gateway, _ = _arranjo()

    end_active_link(gateway, _registro())

    assert gateway.calls == []


@pytest.mark.parametrize(
    "outro",
    [
        pytest.param({}, id="ativo-da-unidade-com-o-login"),
        pytest.param({"unit_id": _U2}, id="outra-unidade"),
        pytest.param({"active": False}, id="desligado"),
        pytest.param({"user_id": UserId("outro-login")}, id="outro-login"),
    ],
)
def test_outro_registro_nao_e_lido_e_o_vinculo_ativo_revoga(outro: dict[str, object]) -> None:
    """A regra não lê a unidade (issue #241, ADR 0.0.0025 §4): fail-closed.

    O primeiro caso — outro registro **ativo da mesma unidade** com o mesmo login —
    é o estado que o índice `uq_employees_tenant_unit_user` recusa; aqui ele é gravado
    direto no store só para travar que, se existisse, a regra revogaria em vez de
    deixar as sessões vivas. Os outros três nunca impediram a revogação.
    """
    fakes, gateway, login = _arranjo()
    registro = _registro(user_id=login)
    _gravar(fakes, registro)
    _gravar(fakes, _registro("e2", **{"user_id": login, **outro}))  # type: ignore[arg-type]
    antes = len(fakes.store.calls)

    end_active_link(gateway, registro)

    assert gateway.revoked == [login]
    assert fakes.store.calls[antes:] == [], "a regra leu o repositório"


def test_login_de_outro_papel_nao_e_revogado() -> None:
    fakes, gateway, _ = _arranjo()
    gerente = UserId("login-do-gerente")
    gateway.seed_login_of_other_role(gerente, tenant_id=_A, unit_id=_U1)
    registro = _registro(user_id=gerente)
    _gravar(fakes, registro)

    end_active_link(gateway, registro)

    assert gateway.revoked == []
    assert gateway.calls == [f"is_employee_login({gerente!r})"]


def test_login_desconhecido_nao_e_revogado() -> None:
    fakes, gateway, _ = _arranjo()
    registro = _registro(user_id=UserId("login-que-identity-nao-conhece"))
    _gravar(fakes, registro)

    end_active_link(gateway, registro)

    assert gateway.revoked == []


def test_falha_da_consulta_de_papel_sobe_crua_sem_revogar() -> None:
    fakes, gateway, login = _arranjo()
    registro = _registro(user_id=login)
    _gravar(fakes, registro)
    falha = RuntimeError("identity fora")
    gateway.fail_role_query_with = falha

    with pytest.raises(RuntimeError) as excinfo:
        end_active_link(gateway, registro)

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


class _RecontratacaoEntreALeituraEAEscrita(InMemoryEmployeeRepository):
    """Um R14 concorrente que recontrata o registro entre a leitura do R13 e a escrita."""

    def deactivate(
        self,
        tenant_id: TenantId,
        unit_id: UnitId,
        employee_id: EmployeeId,
        *,
        expected_user_id: UserId | None,
        expected_active: bool,
    ) -> None:
        gravado = self.find_by_id(tenant_id, unit_id, employee_id)
        assert gravado is not None
        self._store.employees[employee_id] = gravado.reactivate()
        super().deactivate(
            tenant_id,
            unit_id,
            employee_id,
            expected_user_id=expected_user_id,
            expected_active=expected_active,
        )


def test_r13_que_leu_desligado_e_recusado_por_uma_recontratacao_concorrente() -> None:
    """O motivo de `expected_active`: o vínculo voltou a ser ativo e a regra não rodou."""
    fakes, gateway, login = _arranjo()
    _gravar(fakes, _registro(user_id=login, active=False))

    with pytest.raises(EmployeeLoginChangedError):
        _desligar(_RecontratacaoEntreALeituraEAEscrita(fakes.store), gateway)

    relido = fakes.employees.find_by_id(_A, _U1, _E1)
    assert relido is not None
    assert (relido.active, relido.user_id) == (True, login)
    assert gateway.calls == []


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
    _desligar(_Espiao(fakes.store), gateway)

    assert vistos == [(login, True), (login, False)]


# --- 4. CA4: a regra, condição a condição, em cada chamador ------------------
#
# A mesma tabela de condições para R13, R19 e R20. Um chamador que reimplementasse
# a regra (ou a pulasse num caso) reprova aqui em runtime, mesmo que a varredura de
# AST acima fosse contornada. Em R19 a regra é do login **antigo**: a conta nova,
# membro da unidade, é semeada à parte.

_NOVA = UserId("conta-nova")
_EMAIL_DA_NOVA = "nova@cantina.com"


def _executar(chamador: str, employees: InMemoryEmployeeRepository, gateway: object) -> None:
    guard = PermissiveAccessGuard()
    if chamador == "deactivate_employee":
        DeactivateEmployeeUseCase(employees, gateway, guard=guard).execute(  # type: ignore[arg-type]
            DeactivateEmployeeCommand(actor=TEST_ACTOR, tenant_id=_A, unit_id=_U1, employee_id=_E1)
        )
    elif chamador == "unlink_login":
        UnlinkLoginUseCase(employees, gateway, guard=guard).execute(  # type: ignore[arg-type]
            UnlinkLoginCommand(actor=TEST_ACTOR, tenant_id=_A, unit_id=_U1, employee_id=_E1)
        )
    else:
        RelinkLoginUseCase(employees, gateway, guard=guard).execute(  # type: ignore[arg-type]
            RelinkLoginCommand(
                actor=TEST_ACTOR,
                tenant_id=_A,
                unit_id=_U1,
                employee_id=_E1,
                email=_EMAIL_DA_NOVA,
            )
        )


_CHAMADORES = sorted(_ENCERRAM_VINCULO)


def _arranjo_ca4() -> tuple[StaffFakes, InMemoryIdentityGateway, UserId]:
    fakes, gateway, login = _arranjo()
    gateway.seed_account(_NOVA, email=_EMAIL_DA_NOVA, tenant_id=_A, unit_ids=frozenset({_U1}))
    return fakes, gateway, login


@pytest.mark.parametrize("chamador", _CHAMADORES)
def test_ca4_revoga_o_login_de_funcionario_unico_da_unidade(chamador: str) -> None:
    fakes, gateway, login = _arranjo_ca4()
    _gravar(fakes, _registro(user_id=login))

    _executar(chamador, fakes.employees, gateway)

    assert gateway.revoked == [login]


@pytest.mark.parametrize("chamador", _CHAMADORES)
def test_ca4_outro_registro_ativo_da_unidade_com_o_login_nao_impede_a_revogacao(
    chamador: str,
) -> None:
    """Issue #241: o estado é recusado pelo índice da unidade (ADR 0.0.0025); gravado
    direto no store, ele não segura as sessões vivas em nenhum dos três chamadores."""
    fakes, gateway, login = _arranjo_ca4()
    _gravar(fakes, _registro(user_id=login))
    _gravar(fakes, _registro("e2", user_id=login))

    _executar(chamador, fakes.employees, gateway)

    assert gateway.revoked == [login]


@pytest.mark.parametrize("chamador", _CHAMADORES)
def test_ca4_login_de_outro_papel_nao_revoga(chamador: str) -> None:
    fakes, gateway, _ = _arranjo_ca4()
    gerente = UserId("login-do-gerente")
    gateway.seed_login_of_other_role(gerente, tenant_id=_A, unit_id=_U1)
    _gravar(fakes, _registro(user_id=gerente))

    _executar(chamador, fakes.employees, gateway)

    assert gateway.revoked == []


@pytest.mark.parametrize("chamador", _CHAMADORES)
def test_ca4_login_desconhecido_nao_revoga(chamador: str) -> None:
    fakes, gateway, _ = _arranjo_ca4()
    _gravar(fakes, _registro(user_id=UserId("login-que-identity-nao-conhece")))

    _executar(chamador, fakes.employees, gateway)

    assert gateway.revoked == []


@pytest.mark.parametrize("chamador", ["deactivate_employee", "unlink_login"])
def test_ca4_registro_desligado_nao_toca_identity(chamador: str) -> None:
    """R13 repetido e R20 de desligado. R19 recusa desligado antes (CA6)."""
    fakes, gateway, login = _arranjo_ca4()
    _gravar(fakes, _registro(user_id=login, active=False))

    _executar(chamador, fakes.employees, gateway)

    assert gateway.calls == []


def test_ca4_trocar_aplica_a_regra_ao_login_antigo_e_nao_ao_novo() -> None:
    fakes, gateway, login = _arranjo_ca4()
    _gravar(fakes, _registro(user_id=login))

    _executar("relink_login", fakes.employees, gateway)

    assert gateway.revoked == [login]
    assert f"is_employee_login({_NOVA!r})" not in gateway.calls


def test_r13_falha_da_revogacao_sobe_crua_e_o_registro_fica_ativo() -> None:
    fakes, gateway, login = _arranjo()
    _gravar(fakes, _registro(user_id=login))
    falha = RuntimeError("identity fora")
    gateway.fail_revoke_with = falha

    with pytest.raises(RuntimeError) as excinfo:
        _desligar(fakes.employees, gateway)

    assert excinfo.value is falha
    relido = fakes.employees.find_by_id(_A, _U1, _E1)
    assert relido is not None
    assert relido.active is True
