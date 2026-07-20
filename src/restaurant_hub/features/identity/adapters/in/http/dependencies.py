"""Guard de autenticação e composição de autorização do boundary HTTP.

**Este módulo não decide acesso.** Ele faz três coisas, todas legitimamente do
adapter, e nenhuma delas é política:

1. **Extrai e verifica a credencial** — lê o header `Authorization: Bearer` e
   delega a verificação ao `TokenIssuer`. Nenhuma criptografia acontece aqui.
2. **Declara o requisito** — diz *qual permissão* a ação exige e *qual é o alvo*
   (tenant, unidade). `AuthorizeActionCommand` recebe esses campos como entrada,
   então alguém tem de fornecê-los; declarar o requisito não é decidi-lo.
3. **Delega a decisão** a `AuthorizeActionUseCase`, e traduz duas exceções.

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
"""

from dataclasses import dataclass

from fastapi import Request

from restaurant_hub.features.identity.application.dtos.commands import (
    AuthorizeActionCommand,
)
from restaurant_hub.features.identity.application.dtos.results import AuthorizedActor
from restaurant_hub.features.identity.application.dtos.tokens import AccessTokenClaims
from restaurant_hub.features.identity.application.errors import (
    InvalidAccessTokenError,
    UnitNotFoundError,
    UnitNotVisibleError,
    UserNotFoundError,
)
from restaurant_hub.features.identity.application.ports.out.token_issuer import TokenIssuer
from restaurant_hub.features.identity.application.use_cases.authorize_action import (
    AuthorizeActionUseCase,
)
from restaurant_hub.features.identity.domain.value_objects.identifiers import (
    RestaurantId,
    UnitId,
)
from restaurant_hub.features.identity.domain.value_objects.permission import Permission
from restaurant_hub.features.identity.domain.value_objects.role import Role

_ESQUEMA_BEARER = "bearer"


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

    partes = header.split(maxsplit=1)
    esperado = 2
    if len(partes) != esperado or partes[0].lower() != _ESQUEMA_BEARER:
        raise InvalidAccessTokenError()

    token = partes[1].strip()
    if not token:
        raise InvalidAccessTokenError()
    return token


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
        """Verifica o Bearer e devolve as claims. Não consulta o banco."""
        token = extract_bearer_token(request)
        return AuthenticatedActor(claims=self._token_issuer.decode_access_token(token))

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
        try:
            return self._authorize_action.execute(command)
        except UserNotFoundError as exc:
            # O ator do token sumiu. Credencial inválida, não recurso ausente.
            raise InvalidAccessTokenError() from exc
        except UnitNotFoundError as exc:
            # Indistinguível de "existe e você não enxerga" — ver docstring do
            # módulo. É o fechamento do oráculo de enumeração cross-tenant.
            #
            # A mensagem construída aqui nunca chega ao cliente: a faixa 403 tem
            # corpo constante (error_handlers). Ela existe para o log.
            raise UnitNotVisibleError(actor.claims.subject, unit_id or "<sem unidade>") from exc

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
        alvos: tuple[UnitId | None, ...] = unit_ids or (None,)
        # `sorted` para que a ordem das checagens — e portanto qual erro o cliente
        # vê quando falha em mais de uma — seja determinística entre execuções.
        # Sem isso, a mensagem de erro dependeria da ordem de iteração de um
        # frozenset, e um teste de precedência ficaria intermitente.
        resultados = [
            self.authorize(actor, permission, tenant_id=tenant_id, unit_id=unit_id)
            for permission in sorted(permissions)
            for unit_id in alvos
        ]
        return resultados[0]
