"""Mapa exceção → status HTTP do BC identity (ADR 2.4.0001).

**Mora na feature, não em `shared`.** O handler genérico de
`shared/infrastructure/http/error_handlers.py` converte `DomainError` em 422 e
`NotFoundError` em 404, e continua valendo como rede de segurança; mas as classes
de identity não podem ser referenciadas de `shared`, que não importa de features
(LAYOUT §7).

**Um handler só, registrado sobre `IdentityError`.** O status é resolvido
percorrendo o `__mro__` da exceção contra o mapa abaixo. Starlette escolhe o
handler pelo primeiro tipo do MRO que estiver registrado, e como `IdentityError`
precede `NotFoundError`/`DomainError` em todas as MROs deste BC, este handler
ganha dos genéricos — o que é o desejado, porque o mapa daqui é mais específico.

**A totalidade do mapa é um teste, não uma promessa.** Um erro novo sem entrada
cairia no default 422 em silêncio, que é exatamente como um 403 vira 422 sem
ninguém notar. O teste enumera as subclasses e falha se alguma não tiver entrada
própria.
"""

from typing import Final

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from restaurant_hub.features.identity.application.errors import (
    EmailAlreadyRegisteredError,
    InvalidAccessTokenError,
    InvalidCredentialsError,
    InvalidRefreshTokenError,
    PermissionDeniedError,
    RefreshTokenReuseError,
    RestaurantAlreadyExistsError,
    RestaurantNotFoundError,
    SessionAlreadyExistsError,
    SessionFingerprintAlreadyExistsError,
    TenantNotVisibleError,
    TenantScopeRequiredError,
    UnitAlreadyExistsError,
    UnitMembershipAlreadyExistsError,
    UnitNotFoundError,
    UnitNotVisibleError,
    UnitScopeRequiredError,
    UserAlreadyExistsError,
    UserNotFoundError,
)
from restaurant_hub.features.identity.domain.exceptions.errors import (
    CrossTenantError,
    IdentityError,
    InvalidEmailError,
    InvalidIdentifierError,
    InvalidNameError,
    InvalidRoleError,
    MissingTenantError,
    PlatformAdminMembershipError,
    PlatformAdminTenantError,
)

HTTP_UNAUTHORIZED: Final = 401
HTTP_FORBIDDEN: Final = 403
HTTP_NOT_FOUND: Final = 404
HTTP_CONFLICT: Final = 409
HTTP_UNPROCESSABLE: Final = 422

# Corpos CONSTANTES das faixas 401 e 403 (concept §5 regra 10).
#
# Igualar o status não basta. O corpo default é `{"detail": str(exc)}`, e as
# mensagens deste BC carregam ids e tenants — `TenantNotVisibleError` renderiza
# "ator do tenant 'A' e alvo no tenant 'B'". Deixá-la sair reabriria pelo corpo o
# oráculo de enumeração que a conversão de `UnitNotFoundError` fecha pelo status,
# e ainda revelaria qual tenant é dono do recurso.
#
# A mensagem específica não se perde: ela continua na exceção, e vai para o log
# do servidor, onde é diagnóstico e não oráculo.
_CORPO_401: Final = {"detail": "não autenticado", "type": "unauthorized"}
_CORPO_403: Final = {"detail": "acesso negado", "type": "forbidden"}

# RFC 6750 §3 — resposta 401 de recurso protegido por Bearer anuncia o esquema.
_CABECALHOS_401: Final = {"WWW-Authenticate": "Bearer"}

IDENTITY_ERROR_STATUS: Final[dict[type[IdentityError], int]] = {
    # 401 — quem você é não foi estabelecido.
    InvalidCredentialsError: HTTP_UNAUTHORIZED,
    InvalidAccessTokenError: HTTP_UNAUTHORIZED,
    InvalidRefreshTokenError: HTTP_UNAUTHORIZED,
    RefreshTokenReuseError: HTTP_UNAUTHORIZED,
    # 401, e não 409, apesar do nome "AlreadyExists": a própria classe declara
    # que fingerprint repetido é o **sinal de reuso de refresh token**.
    # Classificá-lo como conflito de escrita registraria o oposto do que ele
    # significa e produziria, num endpoint de autenticação, um status
    # distinguível das demais falhas de credencial.
    SessionFingerprintAlreadyExistsError: HTTP_UNAUTHORIZED,
    # 403 — você é conhecido e não pode. Os dois eixos do ADR 2.2.0002 mais as
    # duas exigências de escopo, que negam por ausência (fail-closed).
    PermissionDeniedError: HTTP_FORBIDDEN,
    TenantScopeRequiredError: HTTP_FORBIDDEN,
    TenantNotVisibleError: HTTP_FORBIDDEN,
    UnitScopeRequiredError: HTTP_FORBIDDEN,
    UnitNotVisibleError: HTTP_FORBIDDEN,
    # 404 — alvo inexistente. Note que `UserNotFoundError` e `UnitNotFoundError`
    # vindos do GUARD não chegam aqui: o guard os converte antes, para 401 e 403
    # respectivamente, fechando dois vazamentos de informação (concept §6).
    RestaurantNotFoundError: HTTP_NOT_FOUND,
    UnitNotFoundError: HTTP_NOT_FOUND,
    UserNotFoundError: HTTP_NOT_FOUND,
    # 409 — conflito com estado já gravado (ADR 2.3.0003).
    EmailAlreadyRegisteredError: HTTP_CONFLICT,
    RestaurantAlreadyExistsError: HTTP_CONFLICT,
    UnitAlreadyExistsError: HTTP_CONFLICT,
    UserAlreadyExistsError: HTTP_CONFLICT,
    UnitMembershipAlreadyExistsError: HTTP_CONFLICT,
    SessionAlreadyExistsError: HTTP_CONFLICT,
    # 422 — invariante de domínio violada pelo conteúdo enviado.
    InvalidEmailError: HTTP_UNPROCESSABLE,
    InvalidRoleError: HTTP_UNPROCESSABLE,
    InvalidNameError: HTTP_UNPROCESSABLE,
    InvalidIdentifierError: HTTP_UNPROCESSABLE,
    MissingTenantError: HTTP_UNPROCESSABLE,
    PlatformAdminTenantError: HTTP_UNPROCESSABLE,
    PlatformAdminMembershipError: HTTP_UNPROCESSABLE,
    CrossTenantError: HTTP_UNPROCESSABLE,
}


def resolve_status(exc: IdentityError) -> int:
    """Status da exceção, resolvido pelo `__mro__`.

    Percorrer o MRO — em vez de olhar só `type(exc)` — faz uma subclasse futura
    herdar a classificação do pai em runtime. **Isso não relaxa a totalidade**: o
    teste continua exigindo entrada própria para cada classe concreta, e a
    herança existe só para que um erro não classificado degrade para algo
    sensato em produção em vez de virar 500.
    """
    for classe in type(exc).__mro__:
        status = IDENTITY_ERROR_STATUS.get(classe)
        if status is not None:
            return status
    return HTTP_UNPROCESSABLE


def build_error_response(exc: IdentityError) -> JSONResponse:
    """Monta a resposta, aplicando a regra de corpo constante das faixas 401/403."""
    status = resolve_status(exc)

    if status == HTTP_UNAUTHORIZED:
        return JSONResponse(status_code=status, content=_CORPO_401, headers=_CABECALHOS_401)
    if status == HTTP_FORBIDDEN:
        return JSONResponse(status_code=status, content=_CORPO_403)

    # 404, 409 e 422 mantêm `str(exc)`: a mensagem descreve um recurso que o
    # próprio cliente nomeou ou uma invariante que o payload dele violou, e as
    # checagens de escopo rodam antes, de modo que ela só fala do tenant do ator.
    # A exceção conhecida é `EmailAlreadyRegisteredError` (409), cuja unicidade é
    # global por decisão de kickoff — o sinal ali é o status, não o corpo, e o
    # corpo só ecoa o e-mail que o cliente enviou.
    return JSONResponse(
        status_code=status,
        content={"detail": str(exc), "type": "identity_error"},
    )


def register_identity_error_handlers(app: FastAPI) -> None:
    """Registra o handler único de `IdentityError` na aplicação."""

    @app.exception_handler(IdentityError)
    async def identity_error_handler(request: Request, exc: IdentityError) -> JSONResponse:
        return build_error_response(exc)
