"""CA14 da Stage 3.7 — a confirmação do tenant pela **cadeia real** de identity.

A suíte de propriedade (`test_use_cases_authorize.py`) prova que todo use case de
staff **pede** ao guard o alvo do próprio command, com o tenant nomeado. Ela não
prova que alguém **recusa** um tenant alheio: os dois dublês de lá não confirmam
nada, e o `InMemoryAccessGuard` consulta só o mapa de concessões que o teste
montou. A recusa é de identity — passo 2 (RBAC) e passo 3 (`_assert_tenant_scope`)
de `AuthorizeActionUseCase`, mais L-AG3 no adapter de staff —, e uma implementação do port
que cumprisse as quatro leis e não confirmasse o tenant nomeado deixaria passar
exatamente o command que a issue #49 descreve (Checkpoint A da 3.7, achado 1).

Por isso aqui a cadeia é a de **produção**, inteira, sem banco — e, desde a issue
#47, com as duas metades do guard: o ator nasce de um Bearer **assinado** passado
por `LocalAccessGuard.authenticate` → `IdentityGuard.authenticate_principal`, e a
recusa vem de `LocalAccessGuard.authorize` → `IdentityAccessFacade` →
`authorize_at_boundary` → `AuthorizeActionUseCase`, sobre os repositórios de
identity em memória. O mundo tem dois restaurantes: `tenant-a`,
dono dos registros de staff que os cenários endereçam (unidades `u1` e `u2`), e
`tenant-x`, de onde vêm os atores. Para **todo** cenário x **todo** papel, um ator
de `tenant-x` (ou o `platform_admin`, sem tenant) executando o command de
`tenant-a` é recusado com a exceção de identity e **nenhum efeito**; o controle
positivo é o `owner` de `tenant-a` executando o mesmo command.

Custo aceito, não evitado (ADR 3.7.0001, alternativa G): 17 x 5 casos — a
comparação é redundante pelo caminho HTTP e é a única linha para qualquer outro.
"""

import dataclasses
import datetime
from typing import Final

import pytest
from fastapi import Request
from starlette.datastructures import Headers

from restaurant_hub.features.identity.adapters.inbound.http.dependencies import IdentityGuard
from restaurant_hub.features.identity.application.dtos.identifiers import (
    PasswordHash,
    SessionId,
)
from restaurant_hub.features.identity.application.dtos.tokens import AccessTokenClaims
from restaurant_hub.features.identity.application.errors import (
    PermissionDeniedError,
    TenantNotVisibleError,
)
from restaurant_hub.features.identity.application.facade import IdentityAccessFacade
from restaurant_hub.features.identity.application.use_cases.authorize_action import (
    AuthorizeActionUseCase,
)
from restaurant_hub.features.identity.domain.entities.unit import Unit
from restaurant_hub.features.identity.domain.entities.user import User
from restaurant_hub.features.identity.domain.value_objects.email import Email
from restaurant_hub.features.identity.domain.value_objects.identifiers import (
    RestaurantId,
    UnitId,
    UserId,
)
from restaurant_hub.features.identity.domain.value_objects.role import Role
from restaurant_hub.features.identity.domain.value_objects.unit_membership import (
    UnitMembership,
)
from restaurant_hub.features.staff.adapters.out.identity.local_access_guard import (
    LocalAccessGuard,
)
from restaurant_hub.features.staff.application.ports.out.access_guard import AccessGuard
from tests.fakes.features.identity.fake_token_issuer import FakeTokenIssuer
from tests.fakes.features.identity.in_memory_unit_repository import InMemoryUnitRepository
from tests.fakes.features.identity.in_memory_user_repository import InMemoryUserRepository
from tests.unit.features.staff.application.test_use_cases_authorize import (
    CENARIOS,
    Montagem,
    _montar,
)

pytestmark = pytest.mark.unit

# O tenant dos registros de staff — o mesmo valor que os cenários endereçam.
_VITIMA: Final = RestaurantId("tenant-a")
_ATACANTE: Final = RestaurantId("tenant-x")
_U1: Final = UnitId("u1")
_U2: Final = UnitId("u2")
_X1: Final = UnitId("x1")
_HASH: Final = PasswordHash("hashed::x")

# Os papéis que chegam de fora do tenant-alvo, com **a checagem que os para** —
# assertada pelo tipo exato, para que a recusa não passe por um motivo qualquer
# (Checkpoint C do bloco 07). `owner`/`manager`/`hr` detêm as permissões de staff
# e passam o passo 2: quem os recusa é o passo 3, a **confirmação do tenant
# nomeado** — o que este arquivo existe para provar. `employee` não detém
# permissão nenhuma e `platform_admin` só `manage_platform`: param no passo 2
# (RBAC), antes do tenant, e ficam aqui como as outras duas portas de entrada.
_PAPEIS_DE_FORA: Final = {
    Role.OWNER: TenantNotVisibleError,
    Role.MANAGER: TenantNotVisibleError,
    Role.HR: TenantNotVisibleError,
    Role.EMPLOYEE: PermissionDeniedError,
    Role.PLATFORM_ADMIN: PermissionDeniedError,
}


@dataclasses.dataclass
class Identidade:
    """O lado de identity do mundo: unidades, usuários e o guard de produção."""

    users: InMemoryUserRepository
    units: InMemoryUnitRepository
    guard: AccessGuard
    tokens: FakeTokenIssuer


def _identidade() -> Identidade:
    users = InMemoryUserRepository()
    units = InMemoryUnitRepository()
    units.add(Unit(id=_U1, restaurant_id=_VITIMA, name="Centro"))
    units.add(Unit(id=_U2, restaurant_id=_VITIMA, name="Praia"))
    units.add(Unit(id=_X1, restaurant_id=_ATACANTE, name="Outra"))
    tokens = FakeTokenIssuer()
    authorize_action = AuthorizeActionUseCase(users=users, units=units)
    # A montagem do `composition_root`, sem o resto do grafo: o mesmo use case
    # sob a fachada e sob o guard HTTP que autentica.
    guard = LocalAccessGuard(
        access=IdentityAccessFacade(authorize_action=authorize_action),
        authenticate_request=IdentityGuard(tokens, authorize_action).authenticate_principal,
    )
    return Identidade(users=users, units=units, guard=guard, tokens=tokens)


def _ator(identidade: Identidade, papel: Role, tenant: RestaurantId | None) -> object:
    """Um usuário **gravado** em identity e o ator que o guard real devolve para o seu token.

    `manager`/`hr`/`employee` são membros de uma unidade do **próprio** tenant —
    para que a recusa de `manager`/`hr` seja pelo tenant e não por falta de vínculo,
    o que o teste assere pelo tipo exato (`TenantNotVisibleError`).
    """
    tenant_do_papel = None if papel is Role.PLATFORM_ADMIN else tenant
    user_id = UserId(f"{papel.value}-{tenant_do_papel or 'plataforma'}")
    unidade = _U1 if tenant_do_papel == _VITIMA else _X1
    vinculos = (
        [UnitMembership(user_id=user_id, unit_id=unidade)]
        if papel in (Role.MANAGER, Role.HR, Role.EMPLOYEE)
        else []
    )
    identidade.users.add(
        User(
            id=user_id,
            email=Email(f"{user_id}@x.com"),
            role=papel,
            tenant_id=tenant_do_papel,
        ),
        _HASH,
        vinculos,
    )
    token = identidade.tokens.issue_access_token(
        AccessTokenClaims(
            subject=user_id,
            role=papel,
            tenant_id=tenant_do_papel,
            session_id=SessionId(f"sessao-{user_id}"),
            expires_at=datetime.datetime(2030, 1, 1, tzinfo=datetime.UTC),
        )
    )
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/staff",
            "headers": Headers({"Authorization": f"Bearer {token}"}).raw,
        }
    )
    return identidade.guard.authenticate(request)


def _executar(montagem: Montagem, nome: str, ator: object) -> object:
    command = dataclasses.replace(CENARIOS[nome].command, actor=ator)  # type: ignore[type-var]
    return montagem.use_case.execute(command)


@pytest.mark.parametrize("papel", list(_PAPEIS_DE_FORA), ids=lambda papel: papel.value)
@pytest.mark.parametrize("nome", sorted(CENARIOS))
def test_ca14_ator_de_outro_tenant_e_recusado_por_identity_sem_efeito(
    nome: str, papel: Role
) -> None:
    identidade = _identidade()
    ator = _ator(identidade, papel, _ATACANTE)
    montagem = _montar(CENARIOS[nome].classe, identidade.guard)
    chamadas_ao_store = len(montagem.fakes.store.calls)

    with pytest.raises(_PAPEIS_DE_FORA[papel]) as excinfo:
        _executar(montagem, nome, ator)

    assert type(excinfo.value) is _PAPEIS_DE_FORA[papel]

    assert montagem.fakes.store.calls[chamadas_ao_store:] == []
    assert montagem.gateway.calls == []
    assert montagem.ids.generated == []


@pytest.mark.parametrize("nome", sorted(CENARIOS))
def test_ca14_controle_positivo_o_dono_do_tenant_executa_o_mesmo_command(nome: str) -> None:
    """Sem isto, a recusa acima passaria com uma cadeia que recusasse **tudo**."""
    identidade = _identidade()
    dono = _ator(identidade, Role.OWNER, _VITIMA)
    montagem = _montar(CENARIOS[nome].classe, identidade.guard)

    resultado = _executar(montagem, nome, dono)

    CENARIOS[nome].no_endereco_do_command(montagem, resultado)


@pytest.mark.parametrize("ator_invalido", [None, object()], ids=["none", "objeto-qualquer"])
@pytest.mark.parametrize("nome", sorted(CENARIOS))
def test_ator_que_nao_e_ator_falha_fechado_sem_efeito(nome: str, ator_invalido: object) -> None:
    """Concept 3.7 §6 — `actor=None` (ou um objeto qualquer) vindo de um driver não-HTTP.

    `Actor = object`, então o command constrói. Quem recusa é a cadeia de produção.
    Até a issue #47 a recusa era o `AttributeError` de `actor.claims.subject` —
    **fail-closed, mas não tipado** (finding da §7 da 3.7). Desde a #47 o ator é
    o `AccessPrincipal` da fachada, e `LocalAccessGuard.authorize` recusa
    qualquer outro com um `TypeError` que nomeia o tipo recebido, **antes** de
    chegar a identity. O teste trava as duas metades: que recusa, e que nada
    acontece antes. Uma mudança que passasse a aceitar `None` como "ator
    anônimo" reprova aqui.
    """
    identidade = _identidade()
    montagem = _montar(CENARIOS[nome].classe, identidade.guard)
    chamadas_ao_store = len(montagem.fakes.store.calls)

    with pytest.raises(TypeError, match="ator não autenticado por este guard"):
        _executar(montagem, nome, ator_invalido)

    assert montagem.fakes.store.calls[chamadas_ao_store:] == []
    assert montagem.gateway.calls == []
    assert montagem.ids.generated == []
