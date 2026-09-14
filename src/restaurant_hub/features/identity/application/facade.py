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
3. **Não autoriza.** Nenhum use case de identity autoriza hoje (#49); quem chama
   responde pela autorização na sua própria borda — para staff, R17 exige
   `manage_staff` **e** `manage_users` (concept 3.5 §5.3). A fachada é,
   assumidamente, um segundo caminho de entrada para "criar conta" que não passa
   por `required_permissions_for_role`; o gateway fecha a brecha fixando o papel
   como valor (`"employee"`, L-IG1), e o pino em `test_http_dependencies.py`
   trava que `employee` exige exatamente `manage_users`.

A fachada é montada **uma vez**, no `composition_root`, sobre os mesmos três use
cases que servem as rotas de identity — um grafo, não dois.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field

from restaurant_hub.features.identity.application.dtos.commands import (
    ProvisionAccountCommand,
    RevokeAllSessionsCommand,
    SendInvitationCommand,
)
from restaurant_hub.features.identity.application.errors import EmailAlreadyRegisteredError
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
from restaurant_hub.features.identity.domain.value_objects.role import Role

__all__ = [
    "EmailAlreadyRegisteredError",
    "IdentityFacade",
    "InvalidEmailError",
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
    """As três operações que um consumidor de identity pode pedir nesta Stage."""

    def __init__(
        self,
        provision_account: ProvisionAccountUseCase,
        send_invitation: SendInvitationUseCase,
        revoke_all_sessions: RevokeAllSessionsUseCase,
    ) -> None:
        self._provision_account = provision_account
        self._send_invitation = send_invitation
        self._revoke_all_sessions = revoke_all_sessions

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
        resultado = self._provision_account.execute(
            ProvisionAccountCommand(
                email=Email(email),
                role=Role.from_string(role),
                tenant_id=RestaurantId(tenant_id),
                unit_ids=tuple(UnitId(unit_id) for unit_id in unit_ids),
                handed_over=handed_over,
            )
        )
        return ProvisionedAccount(user_id=resultado.user.id, setup_link=resultado.setup_link)

    def send_invitation(self, *, email: str, setup_link: str) -> None:
        """Envia o convite com o link já emitido; a falha do sender sobe."""
        self._send_invitation.execute(
            SendInvitationCommand(email=Email(email), setup_link=setup_link)
        )

    def revoke_all_sessions(self, user_id: str) -> None:
        """Corta todas as sessões vivas do usuário; id desconhecido não levanta."""
        self._revoke_all_sessions.execute(RevokeAllSessionsCommand(user_id=UserId(user_id)))
