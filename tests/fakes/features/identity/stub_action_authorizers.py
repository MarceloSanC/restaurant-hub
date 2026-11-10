"""Dublês do `ActionAuthorizer` — **declarados infiéis**, fora de qualquer suíte de lei.

A implementação do port é uma só: `AuthorizeActionUseCase` (ADR 2.7.0001 §Decision 2).
Estes dois não se apresentam como implementação; existem para as suítes dos use
cases de identity que agem por um ator (Stage 2.7), como `stub_access_guards.py` de
staff (Stage 3.7):

- `DenyingActionAuthorizer` — nega **todo** pedido com **a mesma instância**
  sentinela, para que o teste confira por `is` que foi a recusa do autorizador, e
  não outra exceção qualquer, que interrompeu o use case. A sentinela **não** é
  `UserNotFoundError` nem `UnitNotFoundError`: essas duas `authorize_at_boundary`
  traduz, e o `is` falharia pela razão errada.
- `RecordingActionAuthorizer` — concede tudo, registra cada pedido na ordem em
  que chegou e devolve um `AuthorizedActor` **infiel** (ator, tenant e unidade que
  nenhum teste semeia). Um use case que lesse o escopo devolvido em vez do command
  (concept 2.7 R4) escreveria num endereço inexistente e reprovaria a releitura.
"""

from restaurant_hub.features.identity.application.dtos.commands import (
    AuthorizeActionCommand,
)
from restaurant_hub.features.identity.application.dtos.results import AuthorizedActor
from restaurant_hub.features.identity.application.ports.out.action_authorizer import (
    ActionAuthorizer,
)
from restaurant_hub.features.identity.domain.value_objects.identifiers import (
    RestaurantId,
    UnitId,
    UserId,
)
from restaurant_hub.features.identity.domain.value_objects.role import Role

# O ator que as suítes de regra de negócio passam no command: com o autorizador que
# registra, ele só precisa existir; quem confere o ator é a suíte de autorização.
TEST_ACTOR_ID = UserId("ator-de-teste")

INFIDEL_ACTOR = UserId("ator-infiel-que-nenhum-teste-semeia")
INFIDEL_TENANT = RestaurantId("tenant-infiel-que-nenhum-teste-semeia")
INFIDEL_UNIT = UnitId("unidade-infiel-que-nenhum-teste-semeia")


class AuthorizationDenied(Exception):
    """Sentinela do `DenyingActionAuthorizer`."""


class DenyingActionAuthorizer:
    """Nega todo pedido, sempre com a mesma instância, e registra o que foi pedido."""

    def __init__(self) -> None:
        self.denial = AuthorizationDenied("negado pelo dublê")
        self.calls: list[AuthorizeActionCommand] = []

    def execute(self, command: AuthorizeActionCommand) -> AuthorizedActor:
        self.calls.append(command)
        raise self.denial


class RecordingActionAuthorizer:
    """Concede todo pedido, registra-o e devolve um escopo infiel."""

    def __init__(self) -> None:
        self.calls: list[AuthorizeActionCommand] = []

    def execute(self, command: AuthorizeActionCommand) -> AuthorizedActor:
        self.calls.append(command)
        return AuthorizedActor(
            user_id=INFIDEL_ACTOR,
            role=Role.OWNER,
            actor_tenant_id=INFIDEL_TENANT,
            scope_tenant_id=INFIDEL_TENANT,
            scope_unit_id=INFIDEL_UNIT,
        )


_conforms_denying: ActionAuthorizer = DenyingActionAuthorizer()
_conforms_recording: ActionAuthorizer = RecordingActionAuthorizer()
