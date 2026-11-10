"""Adapter de saída: `IdentityGateway` implementado sobre a fachada de identity.

**A única aresta entre os dois bounded contexts** (ADR 3.5.0001). Este módulo é o
único de staff autorizado a importar identity, e importa **um** módulo dela —
`restaurant_hub.features.identity.application.facade` —, por um par nomeado no
contrato `bc-independence` do `.importlinter`. Qualquer outro import de identity,
aqui ou em qualquer outro módulo de staff, reprova `lint-imports` e
`test_bc_independence.py`.

O que o gateway faz é **tradução de vocabulário**, nas duas direções:

- **Para dentro**, fixa o que o port publica como lei. L-IG1: o papel é
  `"employee"` como **valor** — staff nunca nomeia `Role` —, e o escopo é o
  tenant e a unidade do registro (`unit_ids=(unit_id,)`). O canal vira o
  prazo: `LoginDelivery.LINK` é `handed_over=True` (o link em mãos vive
  `Settings.handover_link_ttl_hours`), `EMAIL` é o prazo do convite comum.
- **Para fora**, traduz **exatamente** as duas exceções que L-IG2 nomeia —
  `EmailAlreadyRegisteredError → LoginEmailAlreadyInUseError` e
  `InvalidEmailError → InvalidLoginEmailError` — e deixa **tudo o mais** subir
  cru, inclusive a falha do envio. É o mesmo raciocínio de L-AG1/L-AG2 do
  `AccessGuard`: uma condição que já tem handler não ganha uma segunda banda de
  erro só por ter atravessado a fronteira.

Não autoriza: a fachada não autoriza as próprias operações — identity não
autoriza na application, só na borda HTTP (ADR 0.0.0014 §4; issue #115) — e
este adapter tampouco. Quem
responde pela autorização é o use case que o chama, antes de chegar aqui (Stage
3.7, ADR 3.7.0001), e cada operação tem o seu: **provisionar e enviar o convite**
vêm de `create_login_for_employee`, que autoriza `manage_staff` **e**
`manage_users` (a rota R17 autoriza as mesmas duas antes dele); **perguntar se o
login é de funcionário e revogar as sessões** vêm de `deactivate_employee`, que
autoriza só `manage_staff` (a rota R13 também).
"""

from restaurant_hub.features.identity.application.facade import (
    EmailAlreadyRegisteredError,
    IdentityFacade,
    InvalidEmailError,
)
from restaurant_hub.features.staff.application.errors import (
    InvalidLoginEmailError,
    LoginEmailAlreadyInUseError,
)
from restaurant_hub.features.staff.application.ports.out.identity_gateway import (
    LoginDelivery,
    ProvisionedLogin,
)
from restaurant_hub.features.staff.domain.value_objects.identifiers import (
    TenantId,
    UnitId,
    UserId,
)

# L-IG1 — o papel do login de funcionário é do port, fixado como valor. Um
# literal, e não `Role.EMPLOYEE.value`: staff não conhece o enum (CA12).
_EMPLOYEE_ROLE = "employee"


class LocalIdentityGateway:
    """Implementação in-process do port, sobre `IdentityFacade`."""

    def __init__(self, facade: IdentityFacade) -> None:
        self._facade = facade

    def provision_employee_login(
        self,
        *,
        email: str,
        tenant_id: TenantId,
        unit_id: UnitId,
        delivery: LoginDelivery,
    ) -> ProvisionedLogin:
        """Cria o login pendente e devolve id e link (L-IG1, L-IG2, L-IG3).

        Raises:
            LoginEmailAlreadyInUseError: o e-mail já é login de alguém (tradução).
            InvalidLoginEmailError: o e-mail é malformado para identity (tradução).
            Exception: qualquer outra falha de identity sobe crua (L-IG2).
        """
        try:
            account = self._facade.provision_account(
                email=email,
                role=_EMPLOYEE_ROLE,
                tenant_id=str(tenant_id),
                unit_ids=(str(unit_id),),
                handed_over=delivery is LoginDelivery.LINK,
            )
        except EmailAlreadyRegisteredError as exc:
            raise LoginEmailAlreadyInUseError(email) from exc
        except InvalidEmailError as exc:
            raise InvalidLoginEmailError(email) from exc
        return ProvisionedLogin(user_id=UserId(account.user_id), setup_link=account.setup_link)

    def send_login_invitation(self, *, user_id: UserId, email: str, setup_link: str) -> None:
        """Envia o convite; a falha do envio sobe crua e na mesma instância (L-IG2)."""
        self._facade.send_invitation(email=email, setup_link=setup_link)

    def revoke_login_sessions(self, user_id: UserId) -> None:
        """Corta as sessões do login; idempotente e total (L-IG4)."""
        self._facade.revoke_all_sessions(str(user_id))

    def is_employee_login(self, user_id: UserId) -> bool:
        """Compara o papel da conta com o literal de L-IG1 (L-IG5).

        Conta desconhecida chega como `None` e responde `False`. **Sem `try`:** a
        falha da fachada sobe na mesma instância — um `except` que respondesse
        `False` faria o desligamento gravar com a sessão viva.
        """
        return self._facade.account_role(str(user_id)) == _EMPLOYEE_ROLE
