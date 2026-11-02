"""Port de saída: autorização de acesso, dita no **vocabulário de scheduling**.

O padrão do ADR 3.7.0001 (staff) reaplicado com port próprio (ADR 4.3.0002): todo use
case recebe este port por construtor e autoriza o alvo do próprio command **antes de
qualquer outra instrução**. Nenhum módulo de scheduling importa identity nem staff
(contrato `bc-independence`); quem traduz este vocabulário para o de identity é o
composition root (Stage 4.4/4.5).

**Só `authorize`.** A autenticação é da borda (4.5) e não tem consumidor aqui.

**As entradas são `str` nua; a saída carrega os `NewType` de scheduling** — o que
entra veio de fora; o que sai é endereço deste BC.

**Os dois alvos são obrigatórios**: toda permissão de scheduling é por unidade (ADR
4.1.0004 §1, "all unit-scoped"). Não há caminho "tenant inteiro" a omitir.

**O escopo não é endereço** (ADR 3.7.0001 §3): o use case opera no alvo do command.
Do escopo lê-se só o `user_id` — o sujeito autenticado, derivado do token (ADR
0.0.0005), que é o autor da trilha e o "eu" de "minha escala" (ADR 4.3.0002 §4).

**As quatro leis** (provadas contra o fake, `tests/fakes/features/scheduling/`):

- **L-SG1 — a recusa sai crua.** `authorize` levanta quando o ator não pode agir
  sobre o alvo, e o implementador **não traduz** a exceção — o tipo não é fixado aqui
  porque é vocabulário do outro BC.
- **L-SG2 — alvo confirmado.** O escopo devolvido tem exatamente o `tenant_id` e o
  `unit_id` pedidos, nunca vazios; ator de outro tenant ou sem tenant é **negado**,
  nunca coagido para `""`.
- **L-SG3 — uma autorização por alvo.** Autorizar uma unidade não autoriza outra, e
  uma permissão não autoriza outra.
- **L-SG4 — o sujeito vem do token.** `user_id` é o do ator autenticado, nunca vazio,
  nunca tirado do pedido.
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

# As permissões de scheduling, como **valores** (ADR 4.3.0002 §2). O membro do enum
# de identity e o mapa de papéis são da Stage 4.5 (ADR 4.1.0004).
PERMISSION_VIEW_SCHEDULE: Final = "view_schedule"
PERMISSION_MANAGE_SCHEDULE: Final = "manage_schedule"
PERMISSION_VIEW_OWN_SCHEDULE: Final = "view_own_schedule"


@dataclass(frozen=True)
class AuthorizedScope:
    """O escopo que a autorização **concedeu**.

    Attributes:
        tenant_id: o restaurante autorizado — o pedido, confirmado (L-SG2).
        unit_id: a unidade autorizada — a pedida, confirmada (L-SG2).
        user_id: o sujeito autenticado — id de login em identity (L-SG4). É o único
            campo que um use case lê.
    """

    tenant_id: TenantId
    unit_id: UnitId
    user_id: str


class AccessGuard(Protocol):
    """Autoriza o ator a exercer uma permissão sobre (tenant, unidade), ou levanta."""

    def authorize(
        self,
        actor: Actor,
        permission: str,
        *,
        tenant_id: str,
        unit_id: str,
    ) -> AuthorizedScope:
        """Autoriza `actor` a exercer `permission` sobre a unidade do tenant.

        Args:
            actor: a credencial verificada, opaca.
            permission: uma das três permissões deste módulo, como valor.
            tenant_id: o restaurante alvo — confirmado contra o token, nunca a fonte.
            unit_id: a unidade alvo.

        Returns:
            O escopo concedido — **um por alvo** (L-SG3), com o sujeito (L-SG4).

        Raises:
            Exception: a exceção do implementador, **sem tradução** (L-SG1).
        """
        ...
