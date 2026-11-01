"""Dois dublês **declaradamente infiéis** do `AccessGuard` — para os use cases (Stage 3.7).

**Não são implementações das leis.** A segunda implementação de L-AG1..L-AG4 é o
`InMemoryAccessGuard` (Stage 3.4), e só ela roda na suíte de lei. Os dois daqui
existem para medir **os use cases**, não o port, e cada um descumpre o contrato do
port de um jeito escolhido — é a mesma forma do `AdversarialAccessGuard` da 3.6,
cuja infidelidade é o instrumento:

- `DenyingAccessGuard` nega **tudo**. É o "SempreNega" da issue #49: com ele, todo
  use case tem de levantar e não produzir efeito nenhum (concept 3.7 CA03).
- `PermissiveAccessGuard` concede tudo o que **nomeia** o tenant, e devolve um
  escopo **que não é o pedido** — tenant e unidade que nenhum teste semeia. Usado
  nas suítes de regra de negócio dos use cases, ele deixa essas suítes medindo o
  que já mediam (regra de negócio, não acesso) e, de carona, faz qualquer leitura
  do `AuthorizedScope` desviar a escrita para um endereço inexistente — que a
  releitura pelo port denuncia (concept 3.7 R4/CA07). Um escopo fiel tornaria
  *"o use case usou o command"* e *"o use case usou o escopo"* o mesmo objeto.

**Os dois registram o pedido como veio** — `(permission, tenant_id, unit_id)` —,
porque é a sequência exata de alvos que CA05 trava. Registrar strings como o
`InMemoryAccessGuard` faz obrigaria cada asserção a reformatar o alvo. **O ator vai
num registro à parte, `actors`, por identidade**: sem ele, um use case que
autorizasse `None` (ou qualquer objeto) no lugar de `command.actor` passaria por
toda a suíte de application — o permissivo concede sem olhar o ator (Checkpoint C
da 3.7).

**`PermissiveAccessGuard` recusa `tenant_id=None`.** Todo use case de staff
**nomeia** o tenant do command (concept 3.7 R3); a ausência significa "o tenant do
ator" (ADR 0.0.0005), que é o que a **borda** pede, nunca a application. Recusar é
o que faz uma mutação que omita o tenant reprovar mesmo nas suítes que não
olham a sequência de chamadas.

O texto do port *"um fake que não resolva o tenant do ator não cumpre este port"*
vale para implementações; nenhum destes se apresenta como uma.
"""

from dataclasses import dataclass, field
from typing import Final

from restaurant_hub.features.staff.application.ports.out.access_guard import (
    AccessGuard,
    AuthorizedScope,
)
from restaurant_hub.features.staff.domain.value_objects.identifiers import (
    TenantId,
    UnitId,
)
from tests.fakes.features.staff.in_memory_access_guard import FakeActor

# O ator que as suítes de regra de negócio passam em todo command. É um
# `FakeActor` — e não um `object()` nu — para que a mesma suíte possa trocar o
# guard por um `InMemoryAccessGuard(credential=TEST_ACTOR)` sem trocar o ator.
TEST_ACTOR: Final = FakeActor(id="test-actor", tenant_id="tenant-a")

# O endereço que o `PermissiveAccessGuard` devolve, e que **nenhum** teste semeia.
# Se um use case o ler em vez do command, o efeito vai parar aqui.
INFIDEL_TENANT: Final = TenantId("tenant-que-o-escopo-inventou")
INFIDEL_UNIT: Final = UnitId("unidade-que-o-escopo-inventou")

AuthorizeCall = tuple[str, str | None, str | None]


class StubAuthorizationDenied(Exception):
    """Sentinela dos dois dublês — levantada **por identidade** (L-AG2: sai crua)."""


@dataclass
class DenyingAccessGuard:
    """Nega toda autorização, sempre com **a mesma** instância de exceção.

    Attributes:
        calls: os pedidos recebidos, como vieram.
        denial: a instância levantada — `pytest.raises(...).value is guard.denial`
            só é verdade se ninguém no caminho capturou e relançou outra.
    """

    calls: list[AuthorizeCall] = field(default_factory=list)
    actors: list[object] = field(default_factory=list)
    denial: Exception = field(default_factory=StubAuthorizationDenied)

    def authenticate(self, request: object) -> FakeActor:
        """Não é o que se mede aqui: devolve o ator de teste."""
        return TEST_ACTOR

    def authorize(
        self,
        actor: object,
        permission: str,
        *,
        tenant_id: str | None = None,
        unit_id: str | None = None,
    ) -> AuthorizedScope:
        """Registra o pedido e nega."""
        self.calls.append((permission, tenant_id, unit_id))
        self.actors.append(actor)
        raise self.denial


@dataclass
class PermissiveAccessGuard:
    """Concede todo pedido que nomeia o tenant, e devolve um escopo **infiel**.

    Attributes:
        calls: os pedidos recebidos, como vieram — a sequência que CA05 trava.
        denial: o que levanta quando o pedido **omite** o tenant.
    """

    calls: list[AuthorizeCall] = field(default_factory=list)
    actors: list[object] = field(default_factory=list)
    denial: Exception = field(default_factory=StubAuthorizationDenied)

    def authenticate(self, request: object) -> FakeActor:
        """Não é o que se mede aqui: devolve o ator de teste."""
        return TEST_ACTOR

    def authorize(
        self,
        actor: object,
        permission: str,
        *,
        tenant_id: str | None = None,
        unit_id: str | None = None,
    ) -> AuthorizedScope:
        """Registra o pedido; concede se o tenant foi nomeado, com escopo inventado."""
        self.calls.append((permission, tenant_id, unit_id))
        self.actors.append(actor)
        if tenant_id is None:
            raise self.denial
        return AuthorizedScope(tenant_id=INFIDEL_TENANT, unit_id=INFIDEL_UNIT)


_conforms_denying: AccessGuard = DenyingAccessGuard()
_conforms_permissive: AccessGuard = PermissiveAccessGuard()
