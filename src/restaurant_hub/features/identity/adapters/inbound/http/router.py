"""Rotas HTTP do BC identity.

**Adapter fino.** Cada rota faz quatro coisas e nada mais: converte texto em value
object, declara o requisito de acesso, chama o use case, e mapeia o result para o
schema de resposta. Não há regra de negócio aqui, e não há decisão de acesso —
essa é do `AuthorizeActionUseCase`, alcançado pelo guard.

**Sobre os provedores `_get_*`.** As dependências são resolvidas por
`app.dependency_overrides`, preenchido pelo composition root: as funções abaixo
são apenas as **chaves** desse dicionário e, se alguma for chamada de verdade,
significa que o wiring não aconteceu — daí levantarem em vez de devolverem algo.
Falhar alto é melhor que servir um `None` que só quebra três camadas adiante.

**Conversão texto → value object acontece aqui**, e não no schema Pydantic: assim
um e-mail ou papel inválido levanta erro de **domínio**, que o mapa de
`error_handlers` classifica (422), em vez de virar um `RequestValidationError` do
FastAPI, que seguiria outro caminho e outro formato de corpo.
"""

from typing import Annotated, Never

from fastapi import APIRouter, Depends, Request, Response, status

from restaurant_hub.features.identity.application.dtos.commands import (
    AuthenticateUserCommand,
    CreateUnitCommand,
    CreateUserCommand,
    InviteUserCommand,
    ProvisionRestaurantCommand,
    RefreshSessionCommand,
    RequestPasswordResetCommand,
    RevokeSessionCommand,
    SetPasswordWithTokenCommand,
)
from restaurant_hub.features.identity.application.dtos.results import (
    AuthenticationResult,
    ProvisionedRestaurantResult,
    UnitResult,
    UserResult,
)
from restaurant_hub.features.identity.application.use_cases.authenticate_user import (
    AuthenticateUserUseCase,
)
from restaurant_hub.features.identity.application.use_cases.create_unit import (
    CreateUnitUseCase,
)
from restaurant_hub.features.identity.application.use_cases.create_user import (
    CreateUserUseCase,
)
from restaurant_hub.features.identity.application.use_cases.invite_user import (
    InviteUserUseCase,
)
from restaurant_hub.features.identity.application.use_cases.provision_restaurant import (
    ProvisionRestaurantUseCase,
)
from restaurant_hub.features.identity.application.use_cases.refresh_session import (
    RefreshSessionUseCase,
)
from restaurant_hub.features.identity.application.use_cases.request_password_reset import (
    RequestPasswordResetUseCase,
)
from restaurant_hub.features.identity.application.use_cases.revoke_session import (
    RevokeSessionUseCase,
)
from restaurant_hub.features.identity.application.use_cases.set_password_with_token import (
    SetPasswordWithTokenUseCase,
)
from restaurant_hub.features.identity.domain.value_objects.email import Email
from restaurant_hub.features.identity.domain.value_objects.identifiers import (
    RestaurantId,
    UnitId,
)
from restaurant_hub.features.identity.domain.value_objects.permission import Permission
from restaurant_hub.features.identity.domain.value_objects.role import Role

from .dependencies import AuthenticatedActor, IdentityGuard, required_permissions_for_role
from .schemas import (
    CreateOwnerRequest,
    CreateUnitRequest,
    CreateUserRequest,
    InviteUserRequest,
    LoginRequest,
    LogoutRequest,
    ProvisionedRestaurantResponse,
    ProvisionRestaurantRequest,
    RefreshRequest,
    RequestPasswordResetRequest,
    SetPasswordRequest,
    TokenResponse,
    UnitResponse,
    UserResponse,
)

router = APIRouter(tags=["identity"])


def _nao_conectado(nome: str) -> Never:
    raise RuntimeError(
        f"dependência {nome!r} não foi conectada pelo composition root — "
        "veja wire_dependencies() e create_app()"
    )


def _get_authenticate_user() -> AuthenticateUserUseCase:
    _nao_conectado("authenticate_user")


def _get_refresh_session() -> RefreshSessionUseCase:
    _nao_conectado("refresh_session")


def _get_revoke_session() -> RevokeSessionUseCase:
    _nao_conectado("revoke_session")


def _get_provision_restaurant() -> ProvisionRestaurantUseCase:
    _nao_conectado("provision_restaurant")


def _get_create_unit() -> CreateUnitUseCase:
    _nao_conectado("create_unit")


def _get_create_user() -> CreateUserUseCase:
    _nao_conectado("create_user")


def _get_invite_user() -> InviteUserUseCase:
    _nao_conectado("invite_user")


def _get_request_password_reset() -> RequestPasswordResetUseCase:
    _nao_conectado("request_password_reset")


def _get_set_password_with_token() -> SetPasswordWithTokenUseCase:
    _nao_conectado("set_password_with_token")


def _get_guard() -> IdentityGuard:
    _nao_conectado("identity_guard")


def _authenticated_actor(
    request: Request,
    guard: Annotated[IdentityGuard, Depends(_get_guard)],
) -> AuthenticatedActor:
    """Autenticação como **dependência**, e não como chamada no corpo da rota.

    A diferença é observável: o FastAPI resolve as dependências **antes** de
    validar o corpo da requisição. Autenticando aqui, uma requisição sem
    credencial recebe 401 mesmo que o corpo esteja malformado; autenticando
    dentro da rota, o 422 da validação do corpo chegaria primeiro — e um cliente
    sem credencial nenhuma passaria a distinguir "meu corpo tem forma válida" de
    "não tem", sondando o schema de endpoints protegidos.

    É também o que o concept §7.5 declara: `Depends`, não middleware. Com
    `Depends`, uma rota **sem** o guard é visível na assinatura da função; com
    middleware global seria preciso manter uma allowlist de rotas públicas, que
    erra por omissão e **abre** rota sem querer.
    """
    return guard.authenticate(request)


def _unit_response(resultado: UnitResult) -> UnitResponse:
    return UnitResponse(id=resultado.id, restaurant_id=resultado.restaurant_id, name=resultado.name)


def _user_response(resultado: UserResult) -> UserResponse:
    return UserResponse(
        id=resultado.id,
        email=resultado.email.value,
        role=resultado.role.value,
        tenant_id=resultado.tenant_id,
        unit_ids=list(resultado.unit_ids),
    )


def _provisioned_restaurant_response(
    resultado: ProvisionedRestaurantResult,
) -> ProvisionedRestaurantResponse:
    return ProvisionedRestaurantResponse(
        id=resultado.id, name=resultado.name, owner=_user_response(resultado.owner)
    )


def _token_response(resultado: AuthenticationResult) -> TokenResponse:
    return TokenResponse(
        access_token=resultado.access_token,
        refresh_token=resultado.refresh_token,
        access_token_expires_at=resultado.access_token_expires_at,
        refresh_token_expires_at=resultado.refresh_token_expires_at,
    )


# ---------------------------------------------------------------------------
# Autenticação — as três rotas públicas
# ---------------------------------------------------------------------------


@router.post("/auth/login", response_model=TokenResponse)
def login(
    payload: LoginRequest,
    use_case: Annotated[AuthenticateUserUseCase, Depends(_get_authenticate_user)],
) -> TokenResponse:
    """Autentica por e-mail e senha e abre uma sessão de refresh.

    Pública por definição. E-mail malformado levanta `InvalidEmailError` (422)
    antes de qualquer consulta — sem custo e sem tocar o banco.
    """
    resultado = use_case.execute(
        AuthenticateUserCommand(
            email=Email(payload.email),
            plain_password=payload.password.get_secret_value(),
        )
    )
    return _token_response(resultado)


@router.post("/auth/refresh", response_model=TokenResponse)
def refresh(
    payload: RefreshRequest,
    use_case: Annotated[RefreshSessionUseCase, Depends(_get_refresh_session)],
) -> TokenResponse:
    """Rotaciona o par de tokens.

    **Não exige access token**: a autoridade da operação é a posse do refresh —
    é justamente a rota que existe para quando o access já expirou. Reapresentar
    um refresh já rotacionado dispara a detecção de reuso e derruba as sessões do
    usuário (concept §5 regra 5).
    """
    resultado = use_case.execute(
        RefreshSessionCommand(refresh_token=payload.refresh_token.get_secret_value())
    )
    return _token_response(resultado)


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    payload: LogoutRequest,
    use_case: Annotated[RevokeSessionUseCase, Depends(_get_revoke_session)],
) -> Response:
    """Encerra a sessão do refresh apresentado.

    Devolve 204 **sempre**, inclusive para token desconhecido ou já revogado. Um
    404 aqui diria, a quem não tem credencial nenhuma, se um dado valor de
    refresh existe.
    """
    use_case.execute(RevokeSessionCommand(refresh_token=payload.refresh_token.get_secret_value()))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Tenancy — as quatro rotas de criação, todas autenticadas
# ---------------------------------------------------------------------------


@router.post(
    "/restaurants",
    response_model=ProvisionedRestaurantResponse,
    status_code=status.HTTP_201_CREATED,
)
def provision_restaurant(
    payload: ProvisionRestaurantRequest,
    ator: Annotated[AuthenticatedActor, Depends(_authenticated_actor)],
    guard: Annotated[IdentityGuard, Depends(_get_guard)],
    use_case: Annotated[ProvisionRestaurantUseCase, Depends(_get_provision_restaurant)],
) -> ProvisionedRestaurantResponse:
    """Provisiona um tenant: o restaurante **e** o seu primeiro `owner`, tudo ou nada.

    Exige `manage_platform`, isto é: **só `platform_admin`** (decisão do sponsor
    de 2026-07-19). `tenant_id=None` no comando de autorização porque esta é uma
    ação de plataforma, não de tenant — e um ator com tenant falha antes disso,
    na checagem de permissão.

    **Restaurante e dono nascem numa unidade de trabalho** (ADR 0.0.0012): antes
    eram duas chamadas, e uma falha entre elas deixava um restaurante que ninguém
    opera. Nenhum caminho da API cria restaurante sem dono.

    **É uma das duas exceções declaradas à regra "não se concede o que não se
    detém"** (a outra é `POST /restaurants/{id}/owners`): o ator emite um `owner`
    sem deter `manage_tenant` nem `manage_users` — é o que bootstrap significa.
    O papel não vem do request: é o literal `Role.OWNER` dentro do use case, e é
    isso que mantém "nenhuma rota emite `platform_admin`" (ADR 2.4.0003 §2b).
    """
    guard.authorize(ator, Permission.MANAGE_PLATFORM)

    resultado = use_case.execute(
        ProvisionRestaurantCommand(
            name=payload.name,
            owner_email=Email(payload.owner.email),
            owner_plain_password=payload.owner.password.get_secret_value(),
        )
    )
    return _provisioned_restaurant_response(resultado)


@router.post(
    "/restaurants/{restaurant_id}/owners",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_restaurant_owner(
    restaurant_id: str,
    payload: CreateOwnerRequest,
    ator: Annotated[AuthenticatedActor, Depends(_authenticated_actor)],
    guard: Annotated[IdentityGuard, Depends(_get_guard)],
    use_case: Annotated[CreateUserUseCase, Depends(_get_create_user)],
) -> UserResponse:
    """Acrescenta um `owner` a um restaurante existente — ação de **plataforma**.

    Até a issue #67 esta rota **era** o bootstrap: o restaurante nascia sozinho em
    `POST /restaurants` e o dono vinha aqui, numa segunda chamada. Hoje o
    restaurante já nasce com o dono (ADR 0.0.0012), e esta rota ficou como o
    caminho de suporte da plataforma — devolver acesso a um tenant cujos donos o
    perderam, ou dar dono a restaurante criado antes da mudança. `platform_admin`
    detém **apenas** `manage_platform` (mapa da 2.1) e não cria usuário pela rota
    de tenant (ADR 2.4.0003 §5).

    **É exceção declarada à regra "não se concede o que não se detém"**: o ator
    emite um `owner` sem deter `manage_tenant` nem `manage_users`. O que contém a
    exceção não é a regra, é o conjunto de rotas: são duas (esta e
    `POST /restaurants`), as duas exigem `manage_platform`, e nas duas o papel é o
    literal `Role.OWNER` — aqui, abaixo; lá, no use case —, nunca vindo do
    request. É isso que garante que **nenhuma rota emite `platform_admin`**.

    **O tenant vem do PATH, não do ator** (concept §5 regra 3, segunda origem):
    o ator é `platform_admin` e o seu `actor_tenant_id` é necessariamente `None`,
    então tirá-lo do ator produziria `MissingTenantError` e a rota seria
    natimorta. Um path param nomeia o recurso e é resolvido contra o banco
    (`RestaurantNotFoundError` → 404), ao contrário de um campo de corpo, que
    seria afirmação não verificada do cliente.
    """
    guard.authorize(ator, Permission.MANAGE_PLATFORM)

    resultado = use_case.execute(
        CreateUserCommand(
            email=Email(payload.email),
            plain_password=payload.password.get_secret_value(),
            role=Role.OWNER,
            tenant_id=RestaurantId(restaurant_id),
        )
    )
    return _user_response(resultado)


@router.post(
    "/restaurants/{restaurant_id}/units",
    response_model=UnitResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_unit(
    restaurant_id: str,
    payload: CreateUnitRequest,
    ator: Annotated[AuthenticatedActor, Depends(_authenticated_actor)],
    guard: Annotated[IdentityGuard, Depends(_get_guard)],
    use_case: Annotated[CreateUnitUseCase, Depends(_get_create_unit)],
) -> UnitResponse:
    """Cria uma unidade sob um restaurante — ação do `owner`.

    Exige `manage_tenant`, que só o `owner` detém: `manager`/`hr` não têm, e
    `platform_admin` também não ("acesso de plataforma não é acesso de
    restaurante"). É a decisão do sponsor: o `owner` cria e gerencia unidades.

    O `restaurant_id` do path é passado como **alvo** da autorização, de modo que
    um `owner` de outro tenant falha em `_assert_tenant_scope` antes de qualquer
    escrita.
    """
    tenant_id = RestaurantId(restaurant_id)
    guard.authorize(ator, Permission.MANAGE_TENANT, tenant_id=tenant_id)

    resultado = use_case.execute(CreateUnitCommand(restaurant_id=tenant_id, name=payload.name))
    return _unit_response(resultado)


@router.post(
    "/users",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_user(
    payload: CreateUserRequest,
    ator: Annotated[AuthenticatedActor, Depends(_authenticated_actor)],
    guard: Annotated[IdentityGuard, Depends(_get_guard)],
    use_case: Annotated[CreateUserUseCase, Depends(_get_create_user)],
) -> UserResponse:
    """Cria um usuário dentro do tenant do **ator**.

    Três defesas compõem esta rota, e nenhuma delas é opcional:

    1. **"Não se concede o que não se detém"** — o conjunto de permissões
       exigidas inclui todas as do papel alvo, derivadas do mapa da 2.1. Um
       `manager` (que tem `manage_users`) não cria um `owner` (que tem
       `manage_tenant`), e ninguém cria um `platform_admin`.
    2. **Autorização por unidade requisitada** — cada `unit_id` do corpo é
       checado. Além de impedir que um `manager` vincule alguém a uma unidade que
       não enxerga, é o que mantém seguras as faixas 404/422: sem isso o use case
       seria alcançado com unidade não-visível e responderia `UnitNotFoundError`
       (404) ou `CrossTenantError` (422), reabrindo o oráculo de enumeração.
    3. **O tenant vem do ator**, nunca do corpo — o schema sequer tem o campo.
    """
    papel_alvo = Role.from_string(payload.role)
    unit_ids = tuple(UnitId(unit_id) for unit_id in payload.unit_ids)

    autorizado = guard.authorize_all(
        ator,
        required_permissions_for_role(papel_alvo),
        tenant_id=ator.claims.tenant_id,
        unit_ids=unit_ids,
    )

    resultado = use_case.execute(
        CreateUserCommand(
            email=Email(payload.email),
            plain_password=payload.password.get_secret_value(),
            role=papel_alvo,
            tenant_id=autorizado.actor_tenant_id,
            unit_ids=unit_ids,
        )
    )
    return _user_response(resultado)


# ---------------------------------------------------------------------------
# Convite e definição de senha (Stage 2.5)
# ---------------------------------------------------------------------------


@router.post(
    "/users/invitations",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
def invite_user(
    payload: InviteUserRequest,
    ator: Annotated[AuthenticatedActor, Depends(_authenticated_actor)],
    guard: Annotated[IdentityGuard, Depends(_get_guard)],
    use_case: Annotated[InviteUserUseCase, Depends(_get_invite_user)],
) -> UserResponse:
    """Convida uma pessoa para o tenant do **ator**.

    **A autorização é literalmente a mesma de `POST /users`**, e a repetição é
    deliberada: convidar concede exatamente o mesmo acesso que criar, então
    afrouxar aqui seria criar uma porta lateral para a escalada que aquela rota
    fecha. As três defesas continuam valendo — "não se concede o que não se
    detém" via `required_permissions_for_role`, autorização por unidade
    requisitada, e tenant vindo do ator e nunca do corpo.

    A resposta é o `UserResponse` de sempre: **nenhum campo de token**. O link
    existe apenas dentro do e-mail (concept §5 regra 1).
    """
    papel_alvo = Role.from_string(payload.role)
    unit_ids = tuple(UnitId(unit_id) for unit_id in payload.unit_ids)

    autorizado = guard.authorize_all(
        ator,
        required_permissions_for_role(papel_alvo),
        tenant_id=ator.claims.tenant_id,
        unit_ids=unit_ids,
    )

    resultado = use_case.execute(
        InviteUserCommand(
            email=Email(payload.email),
            role=papel_alvo,
            tenant_id=autorizado.actor_tenant_id,
            unit_ids=unit_ids,
        )
    )
    return _user_response(resultado)


@router.post(
    "/auth/password-reset-requests",
    status_code=status.HTTP_202_ACCEPTED,
)
def request_password_reset(
    payload: RequestPasswordResetRequest,
    use_case: Annotated[RequestPasswordResetUseCase, Depends(_get_request_password_reset)],
) -> Response:
    """Pede a redefinição de senha. **Sempre 202, sempre com o mesmo corpo.**

    Pública por definição, e é justamente por isso que a resposta não pode
    depender de o e-mail existir. **202 e não 200**: o servidor aceitou o pedido
    e não afirma nada sobre o que fez com ele — que é literalmente a semântica
    desejada e a única honesta.

    O corpo é vazio, então não há campo, mensagem nem contagem que difira entre
    os dois casos. O use case tampouco levanta: qualquer falha do envio ou da
    escrita é absorvida lá dentro, porque 500 num caminho e 202 no outro seria
    enumeração de contas pelo status (concept §5 regra 8).

    E-mail malformado ainda é 422, e isso **não** fura a regra: o formato é
    conhecimento que o cliente já tem antes de perguntar, e não revela nada
    sobre a base.
    """
    use_case.execute(RequestPasswordResetCommand(email=Email(payload.email)))
    return Response(status_code=status.HTTP_202_ACCEPTED)


@router.post("/auth/password", status_code=status.HTTP_204_NO_CONTENT)
def set_password(
    payload: SetPasswordRequest,
    use_case: Annotated[SetPasswordWithTokenUseCase, Depends(_get_set_password_with_token)],
) -> Response:
    """Define a senha apresentando o token recebido por e-mail.

    **204 sem corpo — não autentica** (concept §5 regra 14). Devolver um par de
    tokens aqui transformaria o link de e-mail numa credencial de sessão: quem
    interceptasse o e-mail ganharia acesso sem nunca provar que sabe a senha.
    O cliente faz login pelo caminho normal, logo em seguida.

    O usuário alvo **não** vem do corpo: sai do registro que o servidor gravou ao
    emitir o token. Token desconhecido, expirado, já usado ou de usuário apagado
    produzem o mesmo 401 de corpo constante.
    """
    use_case.execute(
        SetPasswordWithTokenCommand(
            token=payload.token.get_secret_value(),
            plain_password=payload.password.get_secret_value(),
        )
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
