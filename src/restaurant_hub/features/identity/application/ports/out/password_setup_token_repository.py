"""Port de saída: persistência dos tokens de definição de senha (ADR 2.5.0002).

É o que torna o **uso único** real. Um token puramente assinado vale até expirar;
para que a segunda apresentação do mesmo token falhe, alguém precisa registrar
que a primeira aconteceu — e precisa registrá-lo de um jeito que duas requisições
simultâneas não consigam ambas vencer.

**Semântica normativa** — a Stage 2.5 implementa exatamente isto em Postgres, e
cada regra existe por um motivo concreto:

1. **`find_by_fingerprint` não filtra.** Devolve o token mesmo consumido ou
   expirado, pela mesma razão de `SessionRepository.find_by_fingerprint`: se
   filtrasse, um token já usado voltaria `None`, indistinguível de um token
   forjado, e o chamador perderia a capacidade de distinguir os dois cenários no
   log. Filtrar é papel do chamador, via `PasswordSetupToken.is_usable`.
2. **`consume` devolve `bool`, e o booleano É o contrato de uso único.** Devolve
   `True` **apenas** se transicionou `consumed_at` de nulo para preenchido. Um
   `consume` que devolvesse `None` empurraria a decisão para uma checagem prévia
   no use case — e duas requisições simultâneas com o mesmo token passariam ambas
   pela checagem antes de qualquer uma gravar. O adapter Postgres implementa isto
   como `UPDATE ... WHERE consumed_at IS NULL` e devolve `rowcount == 1`; um
   `SELECT` seguido de `UPDATE` passaria em todo teste sequencial e perderia a
   corrida em produção.
3. **`invalidate_all_for_user` escopa por propósito quando ele é dado.** Na
   **emissão** o escopo é obrigatório: pedir uma redefinição de senha mata as
   redefinições anteriores e **não** toca num convite pendente. Sem isso,
   qualquer pessoa na internet mataria o convite de qualquer vítima em laço, pela
   rota pública. Na **redenção** o escopo é `None` de propósito: definir uma senha
   mata **tudo** do usuário, para que um convite antigo de TTL longo não sobreviva
   à troca de senha (ADR 2.5.0003).
4. **"Invalidar" é definido por `consumed_at IS NULL`, e NÃO por `is_usable`.**
   A distinção parece pedante e não é: um usuário com um convite **expirado e não
   consumido** mais um reset vivo faz `invalidate_all_for_user` devolver `2` sob
   esta definição e `1` sob a leitura "só os que ainda valem". O número é
   observável (é o retorno do método, e a CA13 assere sobre ele), então as duas
   leituras produzem fake e adapter que discordam — e discordam **em silêncio**,
   porque o caso ambíguo é justamente o que ninguém escreve teste para.
   Fixamos a definição barata: o predicado é `consumed_at IS NULL`, o mesmo de
   `consume`, sem termo de expiração. Um token expirado já é inútil por
   `is_usable`; marcá-lo como consumido é redundante, não incorreto, e poupa a
   query de precisar do relógio.
5. **Nada reescreve um `consumed_at` já gravado.** `consume` e
   `invalidate_all_for_user` só tocam linhas com `consumed_at IS NULL` — o
   instante do primeiro consumo é o dado que a forense de um token vazado precisa.
"""

from datetime import datetime
from typing import Protocol

from restaurant_hub.features.identity.application.dtos.identifiers import SetupTokenId
from restaurant_hub.features.identity.application.dtos.setup_tokens import (
    PasswordSetupToken,
    SetupTokenPurpose,
)
from restaurant_hub.features.identity.domain.value_objects.identifiers import UserId


class PasswordSetupTokenRepository(Protocol):
    """Contrato de persistência dos tokens de definição de senha."""

    def add(self, token: PasswordSetupToken) -> None:
        """Persiste um token recém-emitido.

        **É inserção, não upsert** (ADR 2.3.0003). Guarda apenas o fingerprint —
        não existe coluna capaz de guardar o valor, então um dump deste banco não
        devolve nenhum token utilizável.

        **O fingerprint é único**, e a unicidade faz parte deste contrato, não é
        detalhe do adapter: `find_by_fingerprint` devolve **um** token, e sem o
        índice único o adapter teria de escolher entre linhas empatadas — escolha
        que o fake in-memory resolveria por ordem de inserção. Id repetido e
        fingerprint repetido levantam; nenhum caminho de produção chega aqui,
        porque o valor vem de um gerador aleatório, mas o fake e o schema
        precisam concordar sobre o que é recusado.
        """
        ...

    def find_by_fingerprint(self, fingerprint: str) -> PasswordSetupToken | None:
        """Devolve o token do fingerprint, **sem** filtrar consumido/expirado."""
        ...

    def consume(self, token_id: SetupTokenId, consumed_at: datetime) -> bool:
        """Marca o token como consumido. `True` só se ele ainda não estava.

        A transição é **condicional e atômica** — ver a regra 2 do módulo. É esta
        chamada, e não a checagem de `is_usable`, que torna o replay impossível.
        Token inexistente devolve `False`, não levanta: quem consome já trata
        `False` como "token inválido", e um erro extra criaria um segundo caminho
        para o mesmo desfecho.
        """
        ...

    def invalidate_all_for_user(
        self,
        user_id: UserId,
        consumed_at: datetime,
        purpose: SetupTokenPurpose | None = None,
    ) -> int:
        """Invalida os tokens **não consumidos** do usuário. Devolve quantos foram.

        O predicado é `consumed_at IS NULL` e **não** inclui expiração — regra 4
        do módulo, que explica por que a diferença é observável e por que a
        definição barata é a escolhida.

        Com `purpose`, restringe ao propósito dado (uso da **emissão**); sem ele,
        atinge todos (uso da **redenção**) — regra 3. Usuário sem token não
        consumido devolve `0`; não levanta.
        """
        ...

    def purge_expired(self, before: datetime) -> int:
        """Remove os tokens já expirados em `before`. Devolve quantos removeu.

        O predicado é `expires_at <= before`, **inclusive** — a mesma fronteira de
        `is_usable`, que é half-open. Um `<` aqui deixaria para trás exatamente o
        token que `is_usable` já considera expirado.

        **A política de retenção é do chamador**, como em
        `SessionRepository.purge_expired` (ADR 2.3.0004): quem quiser preservar
        histórico forense passa `now - 90d`.
        """
        ...
