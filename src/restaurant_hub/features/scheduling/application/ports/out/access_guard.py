"""Port de saída: autenticação e autorização de acesso, ditas no **vocabulário de scheduling**.

O padrão do ADR 3.7.0001 (staff) reaplicado com port próprio (ADR 4.3.0002): todo use
case recebe este port por construtor e autoriza o alvo do próprio command **antes de
qualquer outra instrução**. Nenhum módulo de scheduling importa identity nem staff
(contrato `bc-independence`); quem traduz este vocabulário para o de identity é o adapter
`adapters/out/identity/local_access_guard.py`, sobre a fachada de acesso de identity (ADR
4.5.0003, na forma do ADR 0.0.0016).

**Duas operações desde a Stage 4.5** (ADR 4.5.0003 §Decision 1; nota datada no ADR
4.3.0002): `authenticate`, que a borda HTTP usa antes de tudo, e `authorize`, que a borda e
os use cases usam. Os use cases não autenticam — o ator chega no command, já autenticado.

**As entradas são `str` nua; a saída carrega os `NewType` de scheduling** — o que
entra veio de fora; o que sai é endereço deste BC.

**A unidade é obrigatória**: toda permissão de escala que este port autoriza é por
unidade (ADR 4.1.0004 §1). **O tenant é opcional**: omitido, é o tenant do ator (ADR
0.0.0005, cláusula 3) — a borda não o conhece, e só a implementação que produziu o ator o
lê. Os use cases continuam nomeando o tenant do command. A configuração tenant-wide (Stage
4.8) estende este port com alvo "restaurante inteiro" quando nascer o consumidor.

**O escopo não é endereço** (ADR 3.7.0001 §3): o use case opera no alvo do command.
Do escopo lê-se o `tenant_id` (a borda, quando omitiu o tenant) e o `user_id` — o sujeito
autenticado, derivado do token (ADR 0.0.0005), que é o autor da trilha e o "eu" de "minha
escala" (ADR 4.3.0002 §4).

**As cinco leis** (provadas contra o fake, `tests/fakes/features/scheduling/`, e contra o
adapter):

- **L-SG1 — a recusa sai crua.** `authenticate` e `authorize` levantam quando a credencial
  não vale ou o ator não pode agir sobre o alvo, e o implementador **não traduz** a
  exceção — o tipo não é fixado aqui porque é vocabulário do outro BC, e a faixa 401/403
  fica byte-idêntica à de identity.
- **L-SG2 — alvo pedido confirmado.** Com o tenant **pedido**, o escopo devolvido tem
  exatamente o `tenant_id` e o `unit_id` pedidos, nunca vazios; ator de outro tenant ou
  sem tenant é **negado**, nunca coagido para `""`.
- **L-SG3 — uma autorização por alvo.** Autorizar uma unidade não autoriza outra, e
  uma permissão não autoriza outra.
- **L-SG4 — o sujeito vem do token.** `user_id` é o do ator autenticado, nunca vazio,
  nunca tirado do pedido.
- **L-SG5 — tenant omitido é o do ator.** Sem `tenant_id`, o escopo traz o tenant do ator
  autenticado; ator sem tenant (`platform_admin`) é **negado**, nunca coagido para `""`.
"""

from dataclasses import dataclass
from typing import Final, Protocol

from restaurant_hub.features.scheduling.domain.value_objects.identifiers import (
    TenantId,
    UnitId,
)

# Credencial **já verificada**, opaca para scheduling (ADR 3.4.0001): scheduling não
# lê papel nem vínculo do ator — tipá-lo seria começar a reimplementar a decisão.
Actor = object

# As permissões de scheduling, como **valores** (ADR 4.3.0002 §2). Os membros do enum
# de identity e o mapa de papéis entraram na Stage 4.5 (ADR 4.5.0001).
PERMISSION_VIEW_SCHEDULE: Final = "view_schedule"
PERMISSION_MANAGE_SCHEDULE: Final = "manage_schedule"
PERMISSION_VIEW_OWN_SCHEDULE: Final = "view_own_schedule"


@dataclass(frozen=True)
class AuthorizedScope:
    """O escopo que a autorização **concedeu**.

    Attributes:
        tenant_id: o restaurante autorizado — o pedido, confirmado (L-SG2), ou o do
            ator, quando o pedido o omitiu (L-SG5).
        unit_id: a unidade autorizada — a pedida, confirmada (L-SG2). Nenhuma rota a lê
            como endereço (ADR 3.6.0001): a unidade do command é a do path.
        user_id: o sujeito autenticado — id de login em identity (L-SG4).
    """

    tenant_id: TenantId
    unit_id: UnitId
    user_id: str


class AccessGuard(Protocol):
    """Autentica a credencial e autoriza o ator sobre (tenant, unidade), ou levanta."""

    def authenticate(self, request: object) -> Actor:
        """Verifica a credencial da requisição e devolve o ator (L-SG1: a recusa sai crua).

        `request` é `object` pela mesma razão que `Actor` é: a forma da requisição é do
        adapter de entrada, e scheduling não a interpreta.
        """
        ...

    def authorize(
        self,
        actor: Actor,
        permission: str,
        *,
        tenant_id: str | None = None,
        unit_id: str,
    ) -> AuthorizedScope:
        """Autoriza `actor` a exercer `permission` sobre a unidade do tenant.

        Args:
            actor: a credencial verificada, opaca.
            permission: uma das três permissões deste módulo, como valor.
            tenant_id: o restaurante alvo — confirmado contra o token, nunca a fonte.
                Ausente, é o tenant do ator (L-SG5).
            unit_id: a unidade alvo.

        Returns:
            O escopo concedido — **um por alvo** (L-SG3), com o sujeito (L-SG4).

        Raises:
            Exception: a exceção do implementador, **sem tradução** (L-SG1).
        """
        ...
