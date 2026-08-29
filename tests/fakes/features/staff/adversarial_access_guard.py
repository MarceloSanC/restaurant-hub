"""Terceiro implementador do `AccessGuard` — o que **contradiz de propósito** os outros dois.

**Este módulo existe porque um dublê fiel não refuta a lei que CA15 enuncia.** A
lei da §5.4 do concept diz que a unidade que chega ao use case é a do **path**,
e "do path" é uma afirmação de **independência**: ela só tem conteúdo se a outra
fonte possível — o `AuthorizedScope` devolvido pelo guard — puder discordar.

As **duas** implementações existentes do port **ecoam** a unidade pedida:

- o tradutor de produção (`composition_root._IdentityAccessGuard`) devolve
  `scope_unit_id`, e `AuthorizeActionUseCase` o monta com
  `scope_unit_id=command.unit_id` (`authorize_action.py:113`);
- o `InMemoryAccessGuard` faz `unit_id=UnitId(unit_id) if unit_id is not None`,
  isto é, devolve literalmente o que recebeu.

Com qualquer uma das duas, *"o router usou o path"* e *"o router usou o escopo"*
são o **mesmo objeto**: a mutação `unit_id=scope.unit_id` **sobrevive**, e a
cobertura fecha em 100% sobre uma propriedade nunca exercida. É a família *"lei
universal, representante estreito"* na sua forma mais enganosa — aqui o domínio
quantificado tem, no sistema inteiro, **um único valor observável**, e o segundo
precisa ser **fabricado**.

Daí este guard. Ele é deliberadamente **infiel** ao comportamento real, e a
infidelidade é o instrumento: se o router lê o escopo em vez do path, o valor que
chega ao use case passa a ser um que **não existe em produção**, e o teste
reprova. Nenhuma outra propriedade do sistema é medida com ele.

**Os dois modos, e por que são dois** (ADR 3.6.0001 §Decision 5):

- `MODO_UNIDADE_DIVERGENTE` — devolve uma unidade **diferente** da pedida. Mata a
  mutação `unit_id=scope.unit_id` diretamente: o command carregaria o valor
  adversarial.
- `MODO_SEM_UNIDADE` — devolve `None`. Mata a variante `unit_id=scope.unit_id or
  unit_id`, que sobreviveria ao primeiro modo em qualquer rota onde o escopo
  divergente ainda fosse *truthy*, e reproduz o caso real do `owner` que faz
  bypass de escopo de unidade (o escopo volta com `None` sobre uma permissão
  unit-scoped — ver `AuthorizedScope.unit_id`).

**`_conforms` no fim do arquivo não é enfeite.** `make typecheck` é
`mypy src/ tests/fakes/`, então a linha põe a conformidade deste dublê com o
`Protocol` sob **gate**, e não sob vigilância de revisão. Foi exatamente essa
borda — dublê fora do alcance do type-checker — que produziu o blocker do
Checkpoint B da Stage 3.4 (D-3B2 do technical).
"""

from dataclasses import dataclass, field
from enum import Enum

from restaurant_hub.features.staff.application.ports.out.access_guard import (
    AccessGuard,
    AuthorizedScope,
)
from restaurant_hub.features.staff.domain.value_objects.identifiers import TenantId, UnitId

# A unidade que este guard inventa. O valor é reconhecível de propósito: se ele
# aparecer numa asserção de teste ou numa mensagem de falha, o diagnóstico é
# imediato — o router leu o escopo.
UNIDADE_ADVERSARIAL = "unit-QUE-O-CLIENTE-NAO-PEDIU"


class ModoAdversarial(Enum):
    """As duas formas de contradizer o pedido, e as duas são necessárias."""

    UNIDADE_DIVERGENTE = "unidade-divergente"
    SEM_UNIDADE = "sem-unidade"


class AdversarialAuthorizationRejected(Exception):
    """Sentinela de recusa — tipo próprio, pela mesma razão do fake sancionado.

    Staff não conhece o vocabulário de erro do outro bounded context, e o port
    declara de propósito que o tipo da exceção não é fixado.
    """


@dataclass
class AdversarialAccessGuard:
    """`AccessGuard` que devolve um escopo **discordante** do alvo pedido.

    Autoriza tudo: o que se mede com ele não é a decisão de acesso — essa já tem
    as suas leis, cobradas contra as **duas** implementações fiéis —, e sim o que
    o router faz com a **resposta**. Um guard que negasse obrigaria cada teste de
    CA15 a montar concessões, e a montagem viraria a variável que explica a falha.

    Attributes:
        tenant_id: o tenant que todo escopo devolvido carrega. Fiel de propósito:
            a lei sob teste é sobre a **unidade**, e um tenant também divergente
            faria a falha ser ambígua entre dois eixos.
        modo: qual das duas contradições aplicar.
        calls: registro das chamadas, no mesmo formato do fake sancionado, para
            que uma suíte possa trocar um pelo outro sem reescrever asserções.
    """

    tenant_id: str = "rest-1"
    modo: ModoAdversarial = ModoAdversarial.UNIDADE_DIVERGENTE
    calls: list[str] = field(default_factory=list)
    authorization_error: Exception = field(default_factory=AdversarialAuthorizationRejected)

    def authenticate(self, request: object) -> object:
        """Devolve um ator qualquer — a autenticação não é o que se mede aqui."""
        self.calls.append("authenticate")
        return ("ator-adversarial", request)

    def authorize(
        self,
        actor: object,
        permission: str,
        *,
        tenant_id: str | None = None,
        unit_id: str | None = None,
    ) -> AuthorizedScope:
        """Concede sempre, e devolve um escopo que **contradiz** o alvo pedido.

        A contradição é o ponto: `unit_id` do retorno nunca é igual ao `unit_id`
        do pedido. Um router correto ignora este campo — ele endereça o registro
        pelo **path** —, e por isso não nota diferença nenhuma.
        """
        self.calls.append(f"authorize({permission},{tenant_id},{unit_id})")

        divergente = self.modo is ModoAdversarial.UNIDADE_DIVERGENTE
        return AuthorizedScope(
            tenant_id=TenantId(self.tenant_id),
            unit_id=UnitId(UNIDADE_ADVERSARIAL) if divergente else None,
        )


_conforms: AccessGuard = AdversarialAccessGuard()
