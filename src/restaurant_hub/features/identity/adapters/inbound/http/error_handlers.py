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

**A causa que o corpo esconde vai para o log** (issue #26). As faixas 401/403
devolvem corpo constante, e o que as distingue — "token expirado", "papel sem
permissão", "unidade de outro tenant" — só sobrevive no servidor: cada resposta
dessas faixas grava um `warning` com o status, a rota, o ator (quando o guard o
autenticou) e a cadeia de causas. O que entra e o que fica de fora está em
`describe_suppressed_cause`.
"""

import logging
from typing import Final

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from restaurant_hub.features.identity.adapters.inbound.http.dependencies import (
    authenticated_actor_id,
)
from restaurant_hub.features.identity.application.errors import (
    EmailAlreadyRegisteredError,
    InvalidAccessTokenError,
    InvalidCredentialsError,
    InvalidRefreshTokenError,
    InvalidSetupTokenError,
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

_log = logging.getLogger(__name__)

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
# A mensagem específica não se perde: ela continua na exceção, e o handler a
# grava no log do servidor (`_registrar_causa_suprimida`), onde é diagnóstico e
# não oráculo.
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
    # 401 numa rota **pública** que não usa Bearer, e a escolha é deliberada:
    # `InvalidRefreshTokenError` já viaja no corpo e também é 401 (ADR 2.4.0001),
    # e a faixa 401 é a única com **corpo constante** — que é justamente a
    # propriedade de que este erro precisa, de graça. O `WWW-Authenticate: Bearer`
    # que a faixa anexa fica semanticamente impreciso; exceptuá-lo criaria uma
    # SEGUNDA forma de 401 no BC, e a diferença entre as duas seria observável.
    # Um cabeçalho impreciso não é um oráculo; duas faixas 401 distinguíveis são.
    InvalidSetupTokenError: HTTP_UNAUTHORIZED,
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


# Faixas cujo corpo esconde a causa — e por isso são as que a registram no log.
_FAIXAS_SUPRIMIDAS: Final = frozenset({HTTP_UNAUTHORIZED, HTTP_FORBIDDEN})

# Teto da cadeia de causas percorrida. As cadeias reais têm até dois elos
# (`UnitNotVisibleError` <- `UnitNotFoundError`); o teto só impede que uma
# cadeia patológica transforme uma linha de log em um laço.
_ELOS_MAXIMOS: Final = 5


def _neutralizar(texto: str) -> str:
    """Escapa caractere não imprimível — CR/LF incluídos — antes de ir ao log.

    As mensagens deste BC já interpolam valores com `!r`, mas a garantia contra
    injeção de linha de log (CWE-117) não pode depender de cada `__init__`
    lembrar disso.
    """
    return "".join(
        c if c.isprintable() else c.encode("unicode_escape").decode("ascii") for c in texto
    )


def _descrever_elo(exc: BaseException) -> str:
    """Um elo da cadeia: classe e mensagem se for do BC, só a classe se não for.

    **A mensagem só entra para `IdentityError`.** As mensagens deste BC são
    escritas sabendo que acabam em log — nenhuma interpola senha, token, hash ou
    link (`InvalidSetupTokenError` e `SessionFingerprintAlreadyExistsError`
    documentam a regra) e `InvalidCredentialsError` não cita o e-mail tentado.
    Exceção de fora — PyJWT, `ValueError` do parse de uma claim — não passou por
    essa revisão, e a mensagem dela pode ecoar o que o cliente mandou. Dela fica
    só o nome qualificado da classe, que já basta para separar "expirado" de
    "assinatura inválida".
    """
    if isinstance(exc, IdentityError):
        return f"{type(exc).__name__}: {exc}"
    classe = type(exc)
    if classe.__module__ == "builtins":
        return classe.__qualname__
    return f"{classe.__module__}.{classe.__qualname__}"


def _proximo_elo(exc: BaseException) -> BaseException | None:
    """A causa explícita (`from`), ou o contexto implícito se não foi suprimido."""
    if exc.__cause__ is not None:
        return exc.__cause__
    if exc.__suppress_context__:
        return None
    return exc.__context__


def describe_suppressed_cause(exc: IdentityError) -> str:
    """Cadeia de causas da exceção, do elo mais externo ao mais interno.

    Ex.: `"InvalidAccessTokenError: token de acesso inválido <-
    jwt.exceptions.ExpiredSignatureError"`. É o que distingue, no log, as causas
    que o corpo constante iguala.
    """
    elos: list[str] = []
    vistos: set[int] = set()
    atual: BaseException | None = exc
    while atual is not None and id(atual) not in vistos and len(elos) < _ELOS_MAXIMOS:
        vistos.add(id(atual))
        elos.append(_descrever_elo(atual))
        atual = _proximo_elo(atual)
    return _neutralizar(" <- ".join(elos))


def _rota(request: Request) -> str:
    """O **molde** da rota (`/restaurants/{restaurant_id}/units`), não o path cru.

    O molde agrupa as ocorrências da mesma rota e não carrega o que o cliente
    escreveu; o path cru só entra se o roteamento não chegou a casar uma rota.
    """
    molde = getattr(request.scope.get("route"), "path", None)
    return molde if isinstance(molde, str) else request.url.path


def _registrar_causa_suprimida(request: Request, exc: IdentityError, status: int) -> None:
    """Grava a causa de um 401/403 — o que o corpo constante não diz ao cliente.

    Fica **de fora**: o token, o header `Authorization`, a senha, o e-mail do
    login e o link de definição de senha — nenhum deles é lido aqui. O ator é o
    sujeito do token **já verificado** (`authenticated_actor_id`), e falta nos
    401 que nascem antes da verificação.
    """
    ator = authenticated_actor_id(request)
    rota = _neutralizar(_rota(request))
    metodo = _neutralizar(request.method)
    causa = describe_suppressed_cause(exc)
    _log.warning(
        "resposta %d com causa suprimida: %s %s ator=%s causa=%s",
        status,
        metodo,
        rota,
        ator if ator is not None else "-",
        causa,
        extra={
            "auth_status": status,
            "auth_method": metodo,
            "auth_route": rota,
            "auth_actor": ator,
            "auth_cause": causa,
        },
    )


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
        status = resolve_status(exc)
        if status in _FAIXAS_SUPRIMIDAS:
            _registrar_causa_suprimida(request, exc, status)
        return build_error_response(exc)
