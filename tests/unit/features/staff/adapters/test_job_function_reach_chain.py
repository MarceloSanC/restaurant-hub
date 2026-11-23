"""Issue #207 — renomear e apagar função exigem alcance sobre onde ela vale, pela cadeia real.

A propriedade, e não um representante (memória do projeto: "teste trava o caso, não a
propriedade"): para **todo** papel de identity, **toda** habilitação gravada da função
e **todo** conjunto de unidades de que o ator é membro, renomear e apagar são
permitidos **se e somente se** o ator detém o catálogo e alcança todas as unidades em
que a função vale — e, quando ela vale em todas, detém `manage_tenant`. Negado, nada
muda: o nome fica, a função fica.

**O oráculo sai dos enums de identity, não do código sob teste.** `Role` e o seu mapa de
permissões dizem quem detém `manage_job_functions` e `manage_tenant`; `User` diz quem
dispensa o vínculo por unidade. A expectativa é montada com esses fatos e a regra do
ADR 0.0.0023; o lado medido é a cadeia de produção — `LocalAccessGuard` →
`IdentityAccessFacade` → `AuthorizeActionUseCase` sobre os repositórios de identity em
memória (a montagem de `test_application_authorization_chain.py`) — sob os use cases
de staff com os fakes dos repositórios.

O domínio tem a contagem asserida: uma derivação que esvaziasse (um enum renomeado, um
filtro errado) deixaria qualquer `all(...)` verde.
"""

import datetime
import itertools
from typing import Final

import pytest
from fastapi import Request
from starlette.datastructures import Headers

from restaurant_hub.features.identity.application.dtos.identifiers import (
    PasswordHash,
    SessionId,
)
from restaurant_hub.features.identity.application.dtos.tokens import AccessTokenClaims
from restaurant_hub.features.identity.application.errors import IdentityApplicationError
from restaurant_hub.features.identity.domain.entities.user import User
from restaurant_hub.features.identity.domain.exceptions.errors import IdentityError
from restaurant_hub.features.identity.domain.value_objects.email import Email
from restaurant_hub.features.identity.domain.value_objects.identifiers import (
    RestaurantId,
    UserId,
)
from restaurant_hub.features.identity.domain.value_objects.identifiers import (
    UnitId as IdentityUnitId,
)
from restaurant_hub.features.identity.domain.value_objects.permission import Permission
from restaurant_hub.features.identity.domain.value_objects.role import Role
from restaurant_hub.features.identity.domain.value_objects.unit_membership import (
    UnitMembership,
)
from restaurant_hub.features.staff.application.dtos.commands import (
    DeleteJobFunctionCommand,
    RenameJobFunctionCommand,
)
from restaurant_hub.features.staff.application.use_cases.delete_job_function import (
    DeleteJobFunctionUseCase,
)
from restaurant_hub.features.staff.application.use_cases.rename_job_function import (
    RenameJobFunctionUseCase,
)
from restaurant_hub.features.staff.domain.entities.job_function import JobFunction
from restaurant_hub.features.staff.domain.value_objects.identifiers import (
    JobFunctionId,
    TenantId,
    UnitId,
)
from restaurant_hub.features.staff.domain.value_objects.unit_enablement import UnitEnablement
from tests.fakes.features.staff.in_memory_staff_store import StaffFakes, staff_repositories
from tests.unit.features.staff.adapters.test_application_authorization_chain import (
    Identidade,
    _identidade,
)

pytestmark = pytest.mark.unit

# O mundo de `_identidade()`: `tenant-a` com as unidades `u1` e `u2`.
_TENANT: Final = "tenant-a"
_UNIDADES: Final = ("u1", "u2")
_F: Final = JobFunctionId("f1")
# Todas, {u1}, {u2} e {u1, u2}: a contagem transcrita contra a derivação.
_HABILITACOES_ESPERADAS: Final = 4
_HASH_QUALQUER: Final = PasswordHash("hashed::x")

# --- o domínio, derivado dos enums ---------------------------------------------

_PAPEIS: Final = tuple(Role)


def _bypassa_unidade(papel: Role) -> bool:
    """O fato de identity, perguntado à entidade — não transcrito."""
    tenant = None if papel is Role.PLATFORM_ADMIN else RestaurantId(_TENANT)
    return User(
        id=UserId("sonda"), email=Email("s@x.com"), role=papel, tenant_id=tenant
    ).bypasses_unit_scope()


def _subconjuntos(itens: tuple[str, ...]) -> list[frozenset[str]]:
    return [
        frozenset(combinacao)
        for tamanho in range(len(itens) + 1)
        for combinacao in itertools.combinations(itens, tamanho)
    ]


# A habilitação gravada: todas as unidades, ou cada subconjunto não-vazio.
_HABILITACOES: Final[tuple[frozenset[str] | None, ...]] = (
    None,
    *(conjunto for conjunto in _subconjuntos(_UNIDADES) if conjunto),
)


def _vinculos_possiveis(papel: Role) -> list[frozenset[str]]:
    """Todo conjunto de vínculos que o papel pode ter (quem dispensa a unidade, nenhum)."""
    return [frozenset()] if _bypassa_unidade(papel) else _subconjuntos(_UNIDADES)


def _rotulo(unidades: frozenset[str] | None) -> str:
    return "todas" if unidades is None else ("+".join(sorted(unidades)) or "nenhuma")


_CASOS = [
    pytest.param(
        papel,
        habilitacao,
        vinculos,
        id=f"{papel.value}-hab={_rotulo(habilitacao)}-vinc={_rotulo(vinculos)}",
    )
    for papel in _PAPEIS
    for habilitacao in _HABILITACOES
    for vinculos in _vinculos_possiveis(papel)
]


def _permitido(papel: Role, habilitacao: frozenset[str] | None, vinculos: frozenset[str]) -> bool:
    """O oráculo do ADR 0.0.0023, sobre os fatos de identity."""
    if Permission.MANAGE_JOB_FUNCTIONS not in papel.permissions:
        return False
    if habilitacao is None:
        return Permission.MANAGE_TENANT in papel.permissions
    return _bypassa_unidade(papel) or habilitacao <= vinculos


# --- montagem ------------------------------------------------------------------


def _ator(identidade: Identidade, papel: Role, vinculos: frozenset[str]) -> object:
    """Usuário gravado em identity, com os vínculos dados, e o ator que o guard devolve."""
    tenant = None if papel is Role.PLATFORM_ADMIN else RestaurantId(_TENANT)
    user_id = UserId(f"{papel.value}-ator")
    identidade.users.add(
        User(id=user_id, email=Email(f"{user_id}@x.com"), role=papel, tenant_id=tenant),
        _HASH_QUALQUER,
        [UnitMembership(user_id=user_id, unit_id=IdentityUnitId(u)) for u in sorted(vinculos)],
    )
    token = identidade.tokens.issue_access_token(
        AccessTokenClaims(
            subject=user_id,
            role=papel,
            tenant_id=tenant,
            session_id=SessionId(f"sessao-{user_id}"),
            expires_at=datetime.datetime(2030, 1, 1, tzinfo=datetime.UTC),
        )
    )
    request = Request(
        {
            "type": "http",
            "method": "PATCH",
            "path": "/api/v1/job-functions/f1",
            "headers": Headers({"Authorization": f"Bearer {token}"}).raw,
        }
    )
    return identidade.guard.authenticate(request)


def _semear(habilitacao: frozenset[str] | None) -> StaffFakes:
    fakes = staff_repositories()
    enablement = (
        UnitEnablement.everywhere()
        if habilitacao is None
        else UnitEnablement.only(frozenset(UnitId(u) for u in habilitacao))
    )
    fakes.job_functions.add(
        JobFunction(
            id=_F, tenant_id=TenantId(_TENANT), name="Cozinheiro", unit_enablement=enablement
        )
    )
    return fakes


def _gravada(fakes: StaffFakes) -> JobFunction | None:
    return fakes.job_functions.find_by_id(TenantId(_TENANT), _F)


def _renomear(fakes: StaffFakes, identidade: Identidade, ator: object) -> None:
    RenameJobFunctionUseCase(fakes.job_functions, guard=identidade.guard).execute(
        RenameJobFunctionCommand(
            actor=ator, tenant_id=TenantId(_TENANT), job_function_id=_F, name="Chef"
        )
    )


def _apagar(fakes: StaffFakes, identidade: Identidade, ator: object) -> None:
    DeleteJobFunctionUseCase(fakes.job_functions, fakes.employees, guard=identidade.guard).execute(
        DeleteJobFunctionCommand(actor=ator, tenant_id=TenantId(_TENANT), job_function_id=_F)
    )


# --- guardas do domínio --------------------------------------------------------


def test_o_dominio_da_propriedade_nao_esta_vazio_e_tem_os_dois_lados() -> None:
    """Sem papel, sem habilitação ou sem um dos dois veredictos, a propriedade é vácua."""
    assert len(_PAPEIS) == len(Role) > 0
    assert len(_HABILITACOES) == _HABILITACOES_ESPERADAS
    veredictos = [_permitido(*caso.values) for caso in _CASOS]  # type: ignore[arg-type]
    assert any(veredictos) and not all(veredictos)
    # Os dois lados aparecem para um papel escopado por unidade com o catálogo —
    # é nele que a regra da issue morde.
    escopados = [
        p
        for p in _PAPEIS
        if Permission.MANAGE_JOB_FUNCTIONS in p.permissions and not _bypassa_unidade(p)
    ]
    assert escopados, "nenhum papel escopado detém o catálogo — a issue não teria o que medir"
    # "Todas" exige `manage_tenant`: algum papel com o catálogo não a detém.
    assert any(Permission.MANAGE_TENANT not in p.permissions for p in escopados)


# --- a propriedade ------------------------------------------------------------


@pytest.mark.parametrize(("papel", "habilitacao", "vinculos"), _CASOS)
def test_issue_207_renomear_e_permitido_sse_o_ator_alcanca_onde_a_funcao_vale(
    papel: Role, habilitacao: frozenset[str] | None, vinculos: frozenset[str]
) -> None:
    identidade = _identidade()
    ator = _ator(identidade, papel, vinculos)
    fakes = _semear(habilitacao)

    if _permitido(papel, habilitacao, vinculos):
        _renomear(fakes, identidade, ator)
        gravada = _gravada(fakes)
        assert gravada is not None
        assert gravada.name == "Chef"
        return

    with pytest.raises((IdentityError, IdentityApplicationError)):
        _renomear(fakes, identidade, ator)
    gravada = _gravada(fakes)
    assert gravada is not None
    assert gravada.name == "Cozinheiro"
    assert not [c for c in fakes.store.calls if c.startswith("job_functions.update")]


@pytest.mark.parametrize(("papel", "habilitacao", "vinculos"), _CASOS)
def test_issue_207_apagar_e_permitido_sse_o_ator_alcanca_onde_a_funcao_vale(
    papel: Role, habilitacao: frozenset[str] | None, vinculos: frozenset[str]
) -> None:
    identidade = _identidade()
    ator = _ator(identidade, papel, vinculos)
    fakes = _semear(habilitacao)

    if _permitido(papel, habilitacao, vinculos):
        _apagar(fakes, identidade, ator)
        assert _gravada(fakes) is None
        return

    with pytest.raises((IdentityError, IdentityApplicationError)):
        _apagar(fakes, identidade, ator)
    assert _gravada(fakes) is not None
    assert "job_functions.delete" not in fakes.store.calls
    # Negado antes da guarda de referências: quem não alcança não aprende se está em uso.
    assert "employees.exists_by_job_function" not in fakes.store.calls


def test_o_caso_da_issue_gerente_de_a_nao_renomeia_nem_apaga_funcao_so_de_b() -> None:
    """O representante nomeado, para quem lê: `manager` membro de u1, função só em u2."""
    assert not _permitido(Role.MANAGER, frozenset({"u2"}), frozenset({"u1"}))
    assert _permitido(Role.MANAGER, frozenset({"u1"}), frozenset({"u1"}))
    assert not _permitido(Role.MANAGER, None, frozenset(_UNIDADES))
    assert _permitido(Role.OWNER, None, frozenset())
