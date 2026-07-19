"""Testes dos DTOs de comando e resultado (concept CA14).

Além da construção, o teste guarda duas propriedades que são contrato:

1. **Imutabilidade** — os DTOs atravessam camadas; um result mutável permitiria
   que o adapter alterasse a resposta depois da decisão do use case.
2. **Nenhum segredo em result** — verificado por introspecção dos campos, não
   por leitura humana, para que um campo novo com senha/hash quebre a suíte.
"""

import dataclasses
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import pytest

from restaurant_hub.features.identity.application.dtos import results
from restaurant_hub.features.identity.application.dtos.commands import (
    AuthenticateUserCommand,
    AuthorizeActionCommand,
    CreateRestaurantCommand,
    CreateUnitCommand,
    CreateUserCommand,
)
from restaurant_hub.features.identity.application.dtos.identifiers import (
    PasswordHash,
    SessionId,
)
from restaurant_hub.features.identity.application.dtos.results import (
    AuthenticationResult,
    AuthorizedActor,
    RestaurantResult,
    UnitResult,
    UserResult,
)
from restaurant_hub.features.identity.domain.value_objects.email import Email
from restaurant_hub.features.identity.domain.value_objects.identifiers import (
    RestaurantId,
    UnitId,
    UserId,
)
from restaurant_hub.features.identity.domain.value_objects.permission import Permission
from restaurant_hub.features.identity.domain.value_objects.role import Role

_RESULT_CLASSES = (
    RestaurantResult,
    UnitResult,
    UserResult,
    AuthenticationResult,
    AuthorizedActor,
)


def test_create_user_command_tem_unit_ids_vazio_por_padrao() -> None:
    """A maioria dos usuários nasce sem vínculo; exigir a lista seria ruído."""
    command = CreateUserCommand(
        email=Email("dono@x.com"),
        plain_password="s3nha",
        role=Role.OWNER,
        tenant_id=RestaurantId("rest-1"),
    )
    assert command.unit_ids == ()


def test_authorize_action_command_tem_alvo_opcional_no_tipo() -> None:
    """Opcional no tipo, obrigatório na regra — quem exige é o use case (§5.6)."""
    command = AuthorizeActionCommand(
        actor_id=UserId("user-1"),
        permission=Permission.MANAGE_USERS,
    )
    assert command.tenant_id is None
    assert command.unit_id is None


def test_commands_carregam_os_campos_declarados() -> None:
    """Construção de cada command com todos os campos preenchidos."""
    assert CreateRestaurantCommand(name="Cantina").name == "Cantina"

    unit_command = CreateUnitCommand(restaurant_id=RestaurantId("rest-1"), name="Centro")
    assert unit_command.restaurant_id == "rest-1"

    auth_command = AuthenticateUserCommand(email=Email("dono@x.com"), plain_password="s3nha")
    assert auth_command.email.value == "dono@x.com"

    authorize = AuthorizeActionCommand(
        actor_id=UserId("user-1"),
        permission=Permission.MANAGE_USERS,
        tenant_id=RestaurantId("rest-1"),
        unit_id=UnitId("unit-1"),
    )
    assert authorize.unit_id == "unit-1"


def test_results_carregam_os_campos_declarados() -> None:
    """Construção de cada result com todos os campos preenchidos."""
    now = datetime(2026, 7, 18, 12, 0, tzinfo=UTC)

    assert RestaurantResult(id=RestaurantId("rest-1"), name="Cantina").name == "Cantina"
    assert (
        UnitResult(
            id=UnitId("unit-1"), restaurant_id=RestaurantId("rest-1"), name="Centro"
        ).restaurant_id
        == "rest-1"
    )

    user_result = UserResult(
        id=UserId("user-1"),
        email=Email("dono@x.com"),
        role=Role.OWNER,
        tenant_id=RestaurantId("rest-1"),
        unit_ids=(UnitId("unit-1"),),
    )
    assert user_result.unit_ids == ("unit-1",)

    authentication = AuthenticationResult(
        access_token="access",
        refresh_token="refresh",
        access_token_expires_at=now,
        refresh_token_expires_at=now,
        user_id=UserId("user-1"),
    )
    assert authentication.refresh_token == "refresh"

    actor = AuthorizedActor(
        user_id=UserId("user-1"),
        role=Role.MANAGER,
        actor_tenant_id=RestaurantId("rest-1"),
        scope_tenant_id=RestaurantId("rest-1"),
        scope_unit_id=UnitId("unit-1"),
    )
    assert actor.scope_unit_id == "unit-1"


def test_authorized_actor_separa_tenant_do_ator_do_tenant_alvo() -> None:
    """Um platform_admin não tem tenant, mas age sobre um — os campos são distintos.

    Colapsar os dois faria a 2.4 receber `None` justamente para o papel que atua
    entre tenants, e ela teria de re-derivar o alvo do request.
    """
    actor = AuthorizedActor(
        user_id=UserId("admin-1"),
        role=Role.PLATFORM_ADMIN,
        actor_tenant_id=None,
        scope_tenant_id=RestaurantId("rest-9"),
        scope_unit_id=None,
    )
    assert actor.actor_tenant_id is None
    assert actor.scope_tenant_id == "rest-9"


def test_dtos_sao_imutaveis() -> None:
    """DTO mutável permitiria alterar a resposta depois da decisão do use case."""
    command = CreateRestaurantCommand(name="Cantina")
    with pytest.raises(FrozenInstanceError):
        command.name = "Outra"  # type: ignore[misc]

    result = RestaurantResult(id=RestaurantId("rest-1"), name="Cantina")
    with pytest.raises(FrozenInstanceError):
        result.name = "Outra"  # type: ignore[misc]


def test_nenhum_result_expoe_senha_ou_hash() -> None:
    """CA14 — por introspecção, para que um campo novo com segredo quebre a suíte."""
    proibidos = {"password", "senha", "plain_password", "password_hash", "hash"}
    for result_class in _RESULT_CLASSES:
        nomes = {campo.name for campo in dataclasses.fields(result_class)}
        assert not (nomes & proibidos), f"{result_class.__name__} expõe segredo"
        for campo in dataclasses.fields(result_class):
            assert "PasswordHash" not in str(campo.type)


def test_modulo_de_results_declara_os_cinco_esperados() -> None:
    """Guarda a lista: result novo entra conscientemente na checagem de segredo.

    O filtro por `__module__` é necessário — `vars(results)` também enxerga os VOs
    de domínio importados (`Email` é dataclass), que não são results.
    """
    declarados = {
        nome
        for nome, obj in vars(results).items()
        if dataclasses.is_dataclass(obj)
        and not nome.startswith("_")
        and obj.__module__ == results.__name__
    }
    assert declarados == {cls.__name__ for cls in _RESULT_CLASSES}


def test_identificadores_da_camada_distinguem_hash_de_senha_em_claro() -> None:
    """`PasswordHash` e `SessionId` são `NewType`: distinção estática, `str` em runtime.

    O valor de negócio está no type-check (impedir passar senha onde se espera
    hash); em runtime a checagem possível é a transparência, que é o que garante
    que persistir/serializar continue trivial.
    """
    password_hash = PasswordHash("hashed::s3nha")
    session_id = SessionId("sess-1")
    assert password_hash == "hashed::s3nha"
    assert isinstance(password_hash, str)
    assert isinstance(session_id, str)
