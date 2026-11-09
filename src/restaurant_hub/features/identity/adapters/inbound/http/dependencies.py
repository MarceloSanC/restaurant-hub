"""Guard de autenticação e composição de autorização do boundary HTTP.

**Este módulo não decide acesso.** Ele faz três coisas, todas legitimamente do
adapter, e nenhuma delas é política:

1. **Extrai e verifica a credencial** — lê o header `Authorization: Bearer` e
   delega a verificação ao `TokenIssuer`. Nenhuma criptografia acontece aqui.
2. **Declara o requisito** — diz *qual permissão* a ação exige e *qual é o alvo*
   (tenant, unidade). `AuthorizeActionCommand` recebe esses campos como entrada,
   então alguém tem de fornecê-los; declarar o requisito não é decidi-lo.
3. **Delega a decisão** a `AuthorizeActionUseCase`, por `authorize_at_boundary`,
   que traduz duas exceções (issue #47: a tradução saiu daqui para a application
   quando a fachada de acesso passou a precisar dela também).

A regra de acesso — quais permissões cada papel tem, quem faz bypass de escopo,
como a visibilidade de unidade funciona — vive em `Role`, `User` e no use case.
Não há tabela de papéis neste arquivo, e há teste que verifica isso (ADR 2.2.0002,
ADR 2.4.0003).

**As duas traduções de exceção fecham vazamento de informação** (concept §6):

- `UserNotFoundError` só pode se referir ao **ator** (é o único usuário do
  command), e um token cujo sujeito sumiu é credencial inválida, não recurso
  ausente → `InvalidAccessTokenError` (401).
- `UnitNotFoundError` vinda daqui vira `UnitNotVisibleError` (403). Sem isso, um
  ator itera `unit_id` e lê a resposta: 404 = "não existe em lugar nenhum", 403 =
  "existe, em algum tenant". `UnitRepository.find_by_id` não filtra por tenant —
  por desenho, porque quem casa tenant e vínculo é o domínio — então a unidade de
  outro tenant é encontrada e só depois recusada. Para quem não enxerga a unidade,
  "não existe" e "existe e não é sua" precisam ser a mesma resposta.

**O ator autenticado fica anotado na requisição** (issue #26): o handler de
erros registra no log a causa de cada 401/403, e "quem tentou" é metade do
diagnóstico. A anotação é só o **sujeito** do token já verificado — nunca o
token — e só existe depois de `decode_access_token` aceitar a credencial.
"""

from dataclasses import dataclass

from fastapi import Request

from restaurant_hub.features.identity.application.dtos.commands import (
    AuthorizeActionCommand,
)
from restaurant_hub.features.identity.application.dtos.results import AuthorizedActor
from restaurant_hub.features.identity.application.dtos.tokens import AccessTokenClaims
from restaurant_hub.features.identity.application.errors import InvalidAccessTokenError
from restaurant_hub.features.identity.application.facade import AccessPrincipal
from restaurant_hub.features.identity.application.ports.out.token_issuer import TokenIssuer
from restaurant_hub.features.identity.application.use_cases.authorize_action import (
    AuthorizeActionUseCase,
    authorize_at_boundary,
)
from restaurant_hub.features.identity.domain.value_objects.identifiers import (
    RestaurantId,
    UnitId,
)
from restaurant_hub.features.identity.domain.value_objects.permission import Permission
from restaurant_hub.features.identity.domain.value_objects.role import Role

_BEARER_SCHEME = "bearer"

# Atributo de `request.state` onde o guard anota o sujeito do token aceito.
# `request.state` vive no `scope` ASGI, então o handler de exceção enxerga a
# anotação feita pela dependência, mesmo recebendo outro objeto `Request`.
_ACTOR_STATE_ATTR = "identity_actor_id"


def authenticated_actor_id(request: Request) -> str | None:
    """Sujeito do token aceito nesta requisição, ou `None` se ninguém autenticou.

    `None` é o caso de todo 401 que nasce **antes** da verificação (header
    ausente, esquema errado, token inválido) e o de toda rota pública, como o
    login — onde o "ator" seria o e-mail digitado, que não entra no log.
    """
    value = getattr(request.state, _ACTOR_STATE_ATTR, None)
    return value if isinstance(value, str) else None


def extract_bearer_token(request: Request) -> str:
    """Extrai o token do header `Authorization`.

    Header ausente, esquema diferente de `Bearer` ou token vazio produzem a
    **mesma** exceção do token malformado ou expirado: o cliente não deve
    conseguir distinguir "você esqueceu o header" de "seu token não vale"
    (concept §5 regra 10).
    """
    header = request.headers.get("Authorization")
    if header is None:
        raise InvalidAccessTokenError()

    parts = header.split(maxsplit=1)
    expected = 2
    if len(parts) != expected or parts[0].lower() != _BEARER_SCHEME:
        raise InvalidAccessTokenError()

    # Sem checagem extra de "token vazio": `split(maxsplit=1)` descarta o espaço
    # em branco à direita, então `"Bearer   "` produz UMA parte e já cai no `if`
    # acima. Um `if not parts[1].strip()` aqui seria inalcançável — e código
    # morto dentro de um guard de segurança é ruído que esconde o que importa.
    # Verificado empiricamente, inclusive com tab,  e espaços unicode.
    return parts[1].strip()


def required_permissions_for_role(target_role: Role) -> frozenset[Permission]:
    """Permissões exigidas para **criar** um usuário do papel `target_role`.

    "Não se concede o que não se detém" (concept §5 regra 4): quem cria precisa
    de `manage_users` **e** de tudo o que o papel criado passa a ter. Sem isso um
    `manager` (que tem `manage_users`) criaria um `owner` (que tem
    `manage_tenant`) e escalaria privilégio numa requisição.

    **O conjunto é derivado do mapa de papéis da 2.1**, não de uma tabela nova.
    Duas fontes de verdade sobre o que cada papel pode divergiriam, e a divergência
    apareceria como escalada silenciosa.
    """
    return frozenset({Permission.MANAGE_USERS}) | target_role.permissions


@dataclass(frozen=True)
class AuthenticatedActor:
    """Ator autenticado — quem é, antes de qualquer pergunta sobre o que pode."""

    claims: AccessTokenClaims


class IdentityGuard:
    """Autentica pelo Bearer e delega a autorização ao use case."""

    def __init__(
        self,
        token_issuer: TokenIssuer,
        authorize_action: AuthorizeActionUseCase,
    ) -> None:
        self._token_issuer = token_issuer
        self._authorize_action = authorize_action

    def authenticate(self, request: Request) -> AuthenticatedActor:
        """Verifica o Bearer e devolve as claims. Não consulta o banco.

        Anota o sujeito na requisição **depois** da verificação: um token
        recusado não deixa rastro de ator, e o log não atribui a tentativa a
        quem o token forjado alega ser.
        """
        token = extract_bearer_token(request)
        claims = self._token_issuer.decode_access_token(token)
        setattr(request.state, _ACTOR_STATE_ATTR, claims.subject)
        return AuthenticatedActor(claims=claims)

    def authenticate_principal(self, request: object) -> AccessPrincipal:
        """`authenticate`, publicado para outro BC em primitivos (issue #47).

        É o que o `AccessGuard` de staff recebe por injeção — o
        `composition_root` o conecta — para autenticar sem conhecer HTTP nem
        este módulo: extração do Bearer, verificação e anotação do ator para o
        log (#26) continuam **aqui**, numa cópia só, e a faixa 401 das rotas de
        staff segue byte-idêntica à de identity (L-AG1).

        `request` é `object` porque é assim que o port de staff o declara.
        Qualquer coisa que não seja uma requisição HTTP não tem credencial a
        verificar, e falha **fechado**, com o mesmo 401 de um header ausente.
        """
        if not isinstance(request, Request):
            raise InvalidAccessTokenError()
        claims = self.authenticate(request).claims
        return AccessPrincipal(user_id=claims.subject, tenant_id=claims.tenant_id)

    def authorize(
        self,
        actor: AuthenticatedActor,
        permission: Permission,
        *,
        tenant_id: RestaurantId | None = None,
        unit_id: UnitId | None = None,
    ) -> AuthorizedActor:
        """Delega a decisão de acesso e traduz as duas exceções de vazamento."""
        command = AuthorizeActionCommand(
            actor_id=actor.claims.subject,
            permission=permission,
            tenant_id=tenant_id,
            unit_id=unit_id,
        )
        # As duas traduções de vazamento moram em `authorize_at_boundary` desde
        # a issue #47: a fachada de acesso que staff consome as aplica também, e
        # uma regra de vazamento não pode ter duas cópias (ADR 0.0.0016).
        return authorize_at_boundary(self._authorize_action, command)

    def authorize_all(
        self,
        actor: AuthenticatedActor,
        permissions: frozenset[Permission],
        *,
        tenant_id: RestaurantId | None = None,
        unit_ids: tuple[UnitId, ...] = (),
    ) -> AuthorizedActor:
        """Autoriza **cada** permissão exigida contra **cada** unidade requisitada.

        Com `unit_ids` vazio, autoriza uma vez com `unit_id=None` — e um ator
        escopado por unidade é negado por `UnitScopeRequiredError`, porque omitir
        a unidade não pode ser caminho de escalada (ADR 2.2.0002).

        **Autorizar por unidade antes de chamar o use case de criação é o que
        mantém seguras as faixas 404/422.** Sem isto, `CreateUserUseCase` seria
        alcançado com unidades não-visíveis e responderia `UnitNotFoundError`
        (404) para inexistente e `CrossTenantError` (422) para unidade de outro
        tenant — reabrindo, com dois status falantes, o mesmo oráculo que a
        tradução de `UnitNotFoundError` fecha.

        Devolve o `AuthorizedActor` da primeira checagem; todas validam o mesmo
        ator, então qualquer uma serve para ler o tenant dele.
        """
        targets: tuple[UnitId | None, ...] = unit_ids or (None,)
        # `sorted` para que a ordem das checagens — e portanto qual erro o cliente
        # vê quando falha em mais de uma — seja determinística entre execuções.
        # Sem isso, a mensagem de erro dependeria da ordem de iteração de um
        # frozenset, e um teste de precedência ficaria intermitente.
        results = [
            self.authorize(actor, permission, tenant_id=tenant_id, unit_id=unit_id)
            for permission in sorted(permissions)
            for unit_id in targets
        ]
        return results[0]
