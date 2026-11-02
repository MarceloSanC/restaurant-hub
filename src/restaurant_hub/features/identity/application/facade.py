"""Fachada de identity — o *Open Host Service* in-process para outros bounded contexts.

**É o único módulo de identity que outro BC pode importar** (LAYOUT §3, ADR
3.5.0001 §1 e §4): o contrato `bc-independence` do import-linter nomeia
exatamente um par, `staff.adapters.out.identity.* -> identity.application.facade`,
e qualquer outro import de identity a partir de staff continua reprovando. Uma
segunda aresta entra por decisão — um segundo par nomeado —, nunca por deriva.

Três propriedades definem a fachada:

1. **Assinaturas em primitivos** (`str`, `Sequence[str]`, `bool`). A conversão
   para value object (`Email(...)`, `Role.from_string(...)`, `RestaurantId`,
   `UnitId`) acontece **aqui dentro**, para que o consumidor nunca precise
   nomear um tipo de identity — é o que mantém a varredura AST de
   `test_bc_independence.py` (nenhum módulo de staff nomeia `Role`/`Permission`)
   verdadeira com a aresta aberta.
2. **Não traduz exceção nenhuma.** As de identity sobem como são; quem traduz é o
   gateway do consumidor, no vocabulário do próprio BC (L-IG2 de staff). Para
   que o consumidor não precise de um segundo módulo de identity só para
   nomear o que vai capturar, este módulo **re-exporta** as duas exceções que
   um consumidor é esperado a traduzir: `EmailAlreadyRegisteredError` e
   `InvalidEmailError`.
3. **Não autoriza as próprias operações.** Nenhum use case de identity autoriza
   hoje (#49); quem chama
   responde pela autorização na sua própria borda — para staff, R17 exige
   `manage_staff` **e** `manage_users` (concept 3.5 §5.3). A fachada é,
   assumidamente, um segundo caminho de entrada para "criar conta" que não passa
   por `required_permissions_for_role`; o gateway fecha a brecha fixando o papel
   como valor (`"employee"`, L-IG1), e o pino em `test_http_dependencies.py`
   trava que `employee` exige exatamente `manage_users`.

**A fachada de acesso (`IdentityAccessFacade`, issue #47, ADR 0.0.0016)** é a
segunda classe deste módulo, e a propriedade 3 não a contradiz: ela não autoriza
as **suas** chamadas, ela **expõe** a decisão de acesso de identity — a mesma que
o guard HTTP toma — em primitivos, para que o `AccessGuard` de staff seja
implementado em `staff/adapters/out/identity/` em vez de no `composition_root`.
Mora neste módulo, e não num segundo, para que a aresta continue sendo **um** par
nomeado no `.importlinter`. O que ela **não** faz é autenticar a requisição:
extrair o Bearer e anotar o ator para o log (#26) são do adapter HTTP de
identity, que publica `AccessPrincipal` — o tipo daqui — por
`IdentityGuard.authenticate_principal`.

A fachada é montada **uma vez**, no `composition_root`, sobre os **mesmos
repositórios, `EmailSender` e `Clock`** que servem as rotas de identity — um
grafo, não dois. Os três primeiros use cases por baixo dela nasceram na Stage
3.5; o quarto, `GetAccountRoleUseCase`, na 3.8 (ADR 3.8.0001 §3) — o único de
leitura. Todos têm a fachada como único consumidor (ADR 3.5.0001 §Consequences).
"""

from collections.abc import Sequence
from dataclasses import dataclass, field

from restaurant_hub.features.identity.application.dtos.commands import (
    AuthorizeActionCommand,
    GetAccountRoleCommand,
    ProvisionAccountCommand,
    RevokeAllSessionsCommand,
    SendInvitationCommand,
)
from restaurant_hub.features.identity.application.errors import (
    EmailAlreadyRegisteredError,
    PermissionDeniedError,
)
from restaurant_hub.features.identity.application.use_cases.authorize_action import (
    AuthorizeActionUseCase,
    authorize_at_boundary,
)
from restaurant_hub.features.identity.application.use_cases.get_account_role import (
    GetAccountRoleUseCase,
)
from restaurant_hub.features.identity.application.use_cases.provision_account import (
    ProvisionAccountUseCase,
)
from restaurant_hub.features.identity.application.use_cases.revoke_all_sessions import (
    RevokeAllSessionsUseCase,
)
from restaurant_hub.features.identity.application.use_cases.send_invitation import (
    SendInvitationUseCase,
)
from restaurant_hub.features.identity.domain.exceptions.errors import InvalidEmailError
from restaurant_hub.features.identity.domain.value_objects.email import Email
from restaurant_hub.features.identity.domain.value_objects.identifiers import (
    RestaurantId,
    UnitId,
    UserId,
)
from restaurant_hub.features.identity.domain.value_objects.permission import Permission
from restaurant_hub.features.identity.domain.value_objects.role import Role

__all__ = [
    "AccessGrant",
    "AccessPrincipal",
    "EmailAlreadyRegisteredError",
    "IdentityAccessFacade",
    "IdentityFacade",
    "InvalidEmailError",
    "PermissionDeniedError",
    "ProvisionedAccount",
]


@dataclass(frozen=True)
class ProvisionedAccount:
    """O que a fachada devolve ao consumidor: o id da conta e o link que a ativa.

    Primitivos, não `UserResult`: o consumidor não conhece os DTOs de identity.
    `repr=False` no link pelo mesmo motivo de `ProvisionedAccountResult` — é
    credencial bearer viva e atravessa dois BCs antes de chegar a quem a exibe.
    """

    user_id: str
    setup_link: str = field(repr=False)


class IdentityFacade:
    """As quatro operações que um consumidor de identity pode pedir."""

    def __init__(
        self,
        provision_account: ProvisionAccountUseCase,
        send_invitation: SendInvitationUseCase,
        revoke_all_sessions: RevokeAllSessionsUseCase,
        get_account_role: GetAccountRoleUseCase,
    ) -> None:
        self._provision_account = provision_account
        self._send_invitation = send_invitation
        self._revoke_all_sessions = revoke_all_sessions
        self._get_account_role = get_account_role

    def provision_account(
        self,
        *,
        email: str,
        role: str,
        tenant_id: str,
        unit_ids: Sequence[str],
        handed_over: bool,
    ) -> ProvisionedAccount:
        """Cria a conta pendente e devolve o link.

        Raises:
            InvalidEmailError: `email` malformado (inclusive byte NUL).
            InvalidRoleError: `role` desconhecido.
            EmailAlreadyRegisteredError: e-mail já usado em qualquer tenant.
            RestaurantNotFoundError, UnitNotFoundError, CrossTenantError,
            PlatformAdminMembershipError: como no use case — sem tradução.
        """
        result = self._provision_account.execute(
            ProvisionAccountCommand(
                email=Email(email),
                role=Role.from_string(role),
                tenant_id=RestaurantId(tenant_id),
                unit_ids=tuple(UnitId(unit_id) for unit_id in unit_ids),
                handed_over=handed_over,
            )
        )
        return ProvisionedAccount(user_id=result.user.id, setup_link=result.setup_link)

    def send_invitation(self, *, email: str, setup_link: str) -> None:
        """Envia o convite com o link já emitido; a falha do sender sobe."""
        self._send_invitation.execute(
            SendInvitationCommand(email=Email(email), setup_link=setup_link)
        )

    def revoke_all_sessions(self, user_id: str) -> None:
        """Corta todas as sessões vivas do usuário; id desconhecido não levanta."""
        self._revoke_all_sessions.execute(RevokeAllSessionsCommand(user_id=UserId(user_id)))

    def account_role(self, user_id: str) -> str | None:
        """O papel da conta em texto (`Role.value`), ou `None` se ela não existe.

        Só leitura (Stage 3.8, ADR 3.8.0001 §3). Devolve o **valor** do papel,
        não o `Role`: o consumidor não nomeia tipos de identity (propriedade 1).
        A falha do repositório sobe como é (propriedade 2).
        """
        result = self._get_account_role.execute(GetAccountRoleCommand(user_id=UserId(user_id)))
        return None if result is None else result.role.value


@dataclass(frozen=True)
class AccessPrincipal:
    """Quem a credencial verificada diz ser — em primitivos (issue #47).

    É o que o adapter HTTP de identity publica para outro BC depois de verificar
    o Bearer (`IdentityGuard.authenticate_principal`), e o que volta a esta
    fachada em `IdentityAccessFacade.authorize`. Só os dois campos que a decisão
    de acesso de um consumidor usa: o sujeito, que identity reconsulta no banco,
    e o tenant do token, que resolve o alvo omitido (ADR 0.0.0005, cláusula 3).

    Attributes:
        user_id: o sujeito do token aceito.
        tenant_id: o tenant do token; `None` para `platform_admin`.
    """

    user_id: str
    tenant_id: str | None


@dataclass(frozen=True)
class AccessGrant:
    """O que a decisão de acesso concedeu — campos de `AuthorizedActor`, em texto.

    Attributes:
        role: o papel do ator (`Role.value`), para a mensagem de uma negação
            que o consumidor imponha por conta própria (L-AG3 de staff).
        actor_tenant_id: o tenant do **ator**, lido do banco; `None` para
            `platform_admin`. Não é o alvo pedido.
        scope_unit_id: a unidade alvo aprovada; `None` quando o pedido não
            nomeou unidade.
    """

    role: str
    actor_tenant_id: str | None
    scope_unit_id: str | None


class IdentityAccessFacade:
    """A decisão de acesso de identity, exposta a outro BC em primitivos (#47)."""

    def __init__(self, authorize_action: AuthorizeActionUseCase) -> None:
        self._authorize_action = authorize_action

    def authorize(
        self,
        principal: AccessPrincipal,
        permission: str,
        *,
        tenant_id: str | None,
        unit_id: str | None,
    ) -> AccessGrant:
        """Decide se `principal` pode exercer `permission` sobre o alvo, ou levanta.

        `tenant_id` e `unit_id` chegam **como o chamador os pediu** — `None` é
        "não declarei". A resolução do tenant omitido é do chamador, que é quem
        conhece o significado da omissão no seu contrato; a fachada não a faz
        para não decidir por ele.

        Raises:
            ValueError: `permission` não é um nome do vocabulário de identity —
                defeito de programação do chamador, não decisão de acesso, e por
                isso não é mascarado como 403.
            InvalidAccessTokenError, UnitNotVisibleError: os dois oráculos
                fechados por `authorize_at_boundary`.
            PermissionDeniedError, TenantScopeRequiredError,
            TenantNotVisibleError, UnitScopeRequiredError: como no use case —
                sem tradução.
        """
        authorized = authorize_at_boundary(
            self._authorize_action,
            AuthorizeActionCommand(
                actor_id=UserId(principal.user_id),
                permission=Permission(permission),
                tenant_id=RestaurantId(tenant_id) if tenant_id is not None else None,
                unit_id=UnitId(unit_id) if unit_id is not None else None,
            ),
        )
        return AccessGrant(
            role=authorized.role.value,
            actor_tenant_id=authorized.actor_tenant_id,
            scope_unit_id=authorized.scope_unit_id,
        )
