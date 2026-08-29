"""Fake in-memory de `AccessGuard` — a **segunda implementação** das quatro leis.

Entregável de primeira classe, não andaime. O ADR 3.4.0001 §Implementation notes
diz por quê: *"a port law that only the production implementation satisfies is
not a law, it is a description"*. As leis L-AG1…L-AG4 só têm poder de refutação
se existir um segundo obrigado — e é este módulo. `make typecheck` é
`mypy src/ tests/fakes/`, então a linha `_conforms` no fim do arquivo põe a
conformidade fake↔`Protocol` sob gate, e não sob vigilância de revisão.

**As exceções são sentinelas, e a identidade delas é o teste.** L-AG1 e L-AG2
exigem que a exceção **saia crua**; `pytest.raises(TipoX)` sozinho não prova
isso — um implementador que capturasse e relançasse `TipoX(...)` novo passaria.
Por isso o fake guarda **instâncias** (`credential_error`, `authorization_error`)
e levanta exatamente elas: a suíte assere `excinfo.value is guard.<sentinela>`,
que só é verdade se ninguém tocou no objeto no caminho.

**O registro de chamadas carrega o alvo**, ao contrário do `record()` do
`InMemoryStaffStore` — que grava só `"<visão>.<método>"`. A diferença é exigida
pela lei que ele serve: L-AG4 fala de *"uma chamada por alvo"*, e um registro que
guardasse apenas `"authorize"` não distinguiria duas autorizações do mesmo alvo
de duas de alvos diferentes, que é exatamente a distinção em jogo.

**A ordem das guardas de `authorize` é deliberada**, e espelha a do tradutor de
produção: ator (L-AG2) → tenant do ator (L-AG3) → **resolução do tenant ausente**
→ concessão do alvo (L-AG2). Pôr a checagem de tenant **depois** da concessão
tornaria L-AG3 dependente de o alvo não estar concedido — e a suíte prova o
contrário, autorizando um alvo concedido com um ator sem tenant e exigindo a
recusa mesmo assim.

**O tenant ausente é resolvido aqui pela mesma regra que o tradutor de produção
usa** (ADR 0.0.0005): `tenant_id=None` significa *"o tenant do próprio ator"*, e
a resolução acontece **antes** da consulta a `grants`, de modo que uma concessão
feita com o tenant nomeado seja alcançada pela chamada que o omite. Uma lei
honrada só pela implementação de produção não é lei — e cobrar as duas com
conjuntos de valores diferentes é o sinal de alerta mais forte da família *"lei
universal, representante estreito"*, que foi como a Stage 3.4 vazou duas
mutações. Por isso o eixo `tenant nomeado x tenant omitido` existe nas **duas**
suítes de lei, comparável linha a linha.

**O registro em `calls` guarda o pedido como veio, não o alvo resolvido.** L-AG4
fala de *"uma chamada por alvo"*, e a chamada é o que o chamador fez: registrar o
valor resolvido esconderia a diferença entre nomear e omitir, que é justamente a
propriedade que esta resolução introduz.
"""

from dataclasses import dataclass, field

from restaurant_hub.features.staff.application.ports.out.access_guard import (
    AccessGuard,
    AuthorizedScope,
)
from restaurant_hub.features.staff.domain.value_objects.identifiers import (
    TenantId,
    UnitId,
)


class FakeCredentialRejected(Exception):
    """Sentinela de L-AG1 — o que este fake levanta quando não há credencial.

    Tipo **próprio do fake**, e não um erro de identity: staff não conhece o
    vocabulário de erro do outro bounded context, e o port declara de propósito
    que o tipo da exceção não é fixado (ver `access_guard.py`). Um fake que
    levantasse o erro de identity provaria menos, não mais — testaria que os
    dois lados combinaram um tipo, quando a lei é sobre **não traduzir**.
    """


class FakeAuthorizationRejected(Exception):
    """Sentinela de L-AG2 e da recusa de L-AG3, pela mesma razão."""


@dataclass(frozen=True)
class FakeActor:
    """Credencial já verificada, na forma mínima que as leis exigem.

    Só dois campos, e a pobreza é o ponto: staff trata o ator como opaco
    (`Actor = object`), então tudo o que o fake precisa é de algo que
    `authenticate` devolva e `authorize` reconheça — mais o tenant, porque é
    dele que L-AG3 fala.

    Attributes:
        id: identidade do ator, usada só para legibilidade das falhas.
        tenant_id: o restaurante do ator. `None` reproduz o único caso real
            hoje — `platform_admin`, que não tem tenant —, e é o gatilho de
            L-AG3. É também o valor que `authorize` resolve quando a chamada
            **omite** o tenant alvo (ADR 0.0.0005).
    """

    id: str
    tenant_id: str | None


@dataclass
class InMemoryAccessGuard:
    """Guard configurável: uma credencial, um mapa de concessões, um registro.

    Attributes:
        credential: o ator que `authenticate` devolve. `None` ⇒ não há
            credencial válida, e L-AG1 dispara.
        grants: alvos autorizados, como `(permission, tenant_id, unit_id)` —
            a tripla **exata** do alvo, já com o tenant resolvido (é o mesmo
            valor com que a decisão consulta o mapa). Um alvo concedido não
            concede nenhum outro, que é a forma de L-AG4 no mapa.
        calls: registro das chamadas recebidas, **com o alvo** (ver docstring do
            módulo).
        credential_error: a sentinela de L-AG1, levantada por identidade.
        authorization_error: a sentinela de L-AG2/L-AG3, idem.
    """

    credential: FakeActor | None = None
    grants: set[tuple[str, str | None, str | None]] = field(default_factory=set)
    calls: list[str] = field(default_factory=list)
    credential_error: Exception = field(default_factory=FakeCredentialRejected)
    authorization_error: Exception = field(default_factory=FakeAuthorizationRejected)

    def record(self, call: str) -> None:
        """Registra uma chamada recebida."""
        self.calls.append(call)

    def grant(
        self,
        permission: str,
        *,
        tenant_id: str | None = None,
        unit_id: str | None = None,
    ) -> None:
        """Concede **um** alvo. Chamar de novo com outro alvo concede o outro."""
        self.grants.add((permission, tenant_id, unit_id))

    def authenticate(self, request: object) -> FakeActor:
        """L-AG1 — devolve o ator, ou levanta a sentinela **crua**."""
        self.record("authenticate")
        if self.credential is None:
            raise self.credential_error
        return self.credential

    def authorize(
        self,
        actor: object,
        permission: str,
        *,
        tenant_id: str | None = None,
        unit_id: str | None = None,
    ) -> AuthorizedScope:
        """Autoriza **este** alvo, ou levanta a sentinela crua.

        L-AG4 é imposta pela forma: a decisão consulta a tripla exata do pedido,
        então o escopo devolvido para `(perm, t1, u1)` não diz nada sobre
        `(perm, t1, u2)` — e a chamada seguinte tem de acontecer, aparecendo em
        `calls`.

        **`tenant_id` ausente é resolvido para o tenant do ator** antes da
        consulta ao mapa (ADR 0.0.0005) — ver o docstring do módulo.
        """
        self.record(f"authorize({permission},{tenant_id},{unit_id})")

        # L-AG2 — ator que este guard não emitiu não age. Cobre `None` e
        # qualquer objeto forjado, que é o que `Actor = object` deixa passar
        # pelo type-checker.
        if not isinstance(actor, FakeActor) or actor is not self.credential:
            raise self.authorization_error

        # L-AG3 — **antes** da concessão, de propósito: ator sem tenant é negado
        # mesmo com o alvo concedido. Nada aqui constrói `TenantId("")`.
        if not actor.tenant_id:
            raise self.authorization_error

        # ADR 0.0.0005 — a ausência significa "o tenant do próprio ator", e a
        # resolução acontece **antes** da consulta ao mapa: sem isto, uma
        # concessão feita com o tenant nomeado ficaria inalcançável pela chamada
        # que o omite, e o fake obedeceria a um contrato diferente do que o
        # tradutor de produção obedece. Só a ausência carrega significado — um
        # `""` explícito segue como alvo próprio, e não é reescrito.
        target_tenant_id = tenant_id if tenant_id is not None else actor.tenant_id

        # L-AG2 — o alvo pedido precisa estar concedido, ele e não outro.
        if (permission, target_tenant_id, unit_id) not in self.grants:
            raise self.authorization_error

        return AuthorizedScope(
            tenant_id=TenantId(actor.tenant_id),
            unit_id=UnitId(unit_id) if unit_id is not None else None,
        )


_conforms: AccessGuard = InMemoryAccessGuard()
