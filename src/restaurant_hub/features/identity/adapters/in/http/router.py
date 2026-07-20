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

from fastapi import APIRouter, Depends, Response, status

from restaurant_hub.features.identity.application.dtos.commands import (
    AuthenticateUserCommand,
    RefreshSessionCommand,
    RevokeSessionCommand,
)
from restaurant_hub.features.identity.application.dtos.results import (
    AuthenticationResult,
)
from restaurant_hub.features.identity.application.use_cases.authenticate_user import (
    AuthenticateUserUseCase,
)
from restaurant_hub.features.identity.application.use_cases.refresh_session import (
    RefreshSessionUseCase,
)
from restaurant_hub.features.identity.application.use_cases.revoke_session import (
    RevokeSessionUseCase,
)
from restaurant_hub.features.identity.domain.value_objects.email import Email

from .dependencies import IdentityGuard
from .schemas import (
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    TokenResponse,
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


def _get_guard() -> IdentityGuard:
    _nao_conectado("identity_guard")


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
