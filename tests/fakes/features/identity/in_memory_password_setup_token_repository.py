"""Fake in-memory de `PasswordSetupTokenRepository`.

Como o de sessões, este fake é a **especificação executável** da tabela que o
adapter Postgres implementa — e implementa a semântica normativa ao pé da letra,
inclusive as partes contraintuitivas, que é onde os dois costumam divergir:

- `find_by_fingerprint` **não filtra** consumido nem expirado;
- `consume` é **condicional**: devolve `True` só na transição de nulo para
  preenchido. Um fake que devolvesse `True` sempre faria o teste de replay passar
  verde sobre um adapter que perde a corrida;
- `invalidate_all_for_user` respeita `purpose` quando ele é dado, e nunca
  reescreve um `consumed_at` já gravado.

`PasswordSetupToken` é `frozen`, então atualizar é `dataclasses.replace` — o mesmo
caminho que o fake de sessões usa.
"""

import dataclasses
from datetime import datetime

from restaurant_hub.features.identity.application.dtos.identifiers import SetupTokenId
from restaurant_hub.features.identity.application.dtos.setup_tokens import (
    PasswordSetupToken,
    SetupTokenPurpose,
)
from restaurant_hub.features.identity.application.ports.out.password_setup_token_repository import (
    PasswordSetupTokenRepository,
)
from restaurant_hub.features.identity.domain.value_objects.identifiers import UserId


class SetupTokenAlreadyExistsError(RuntimeError):
    """Id ou fingerprint repetido — o que a PK e o índice único rejeitam.

    Erro de fake, não de aplicação: nenhum caminho de produção reinsere um token,
    porque o valor vem de um gerador aleatório. Existe para que o fake não
    sobrescreva em silêncio o que o banco recusaria — que é como uma divergência
    fake/adapter nasce.
    """


class InMemoryPasswordSetupTokenRepository:
    """Implementação in-memory do port, honrando a semântica normativa."""

    def __init__(self) -> None:
        self.tokens: dict[SetupTokenId, PasswordSetupToken] = {}

    def add(self, token: PasswordSetupToken) -> None:
        if token.id in self.tokens:
            raise SetupTokenAlreadyExistsError(f"token já existe: {token.id!r}")
        if self.find_by_fingerprint(token.token_fingerprint) is not None:
            raise SetupTokenAlreadyExistsError("fingerprint de token já registrado")
        self.tokens[token.id] = token

    def find_by_fingerprint(self, fingerprint: str) -> PasswordSetupToken | None:
        # Sem filtro — regra 1 do port. Devolver `None` para token consumido o
        # tornaria indistinguível de um token forjado.
        for token in self.tokens.values():
            if token.token_fingerprint == fingerprint:
                return token
        return None

    def consume(self, token_id: SetupTokenId, consumed_at: datetime) -> bool:
        token = self.tokens.get(token_id)
        if token is None:
            # Token inexistente é `False`, não exceção — regra 2 do port.
            return False
        if token.consumed_at is not None:
            # Já consumido: a segunda apresentação perde. É esta linha que torna
            # o replay impossível, e não a checagem de `is_usable` do use case.
            return False
        self.tokens[token_id] = dataclasses.replace(token, consumed_at=consumed_at)
        return True

    def invalidate_all_for_user(
        self,
        user_id: UserId,
        consumed_at: datetime,
        purpose: SetupTokenPurpose | None = None,
    ) -> int:
        invalidados = 0
        for token_id, token in list(self.tokens.items()):
            if token.user_id != user_id or token.consumed_at is not None:
                continue
            if purpose is not None and token.purpose is not purpose:
                # Escopo por propósito: é o que impede que um pedido de
                # redefinição mate um convite pendente — regra 3 do port.
                continue
            self.tokens[token_id] = dataclasses.replace(token, consumed_at=consumed_at)
            invalidados += 1
        return invalidados

    def purge_expired(self, before: datetime) -> int:
        # `<=` e não `<`: `is_usable` é half-open, então em `expires_at == before`
        # o token já expirou e tem de ser expurgável.
        expirados = [
            token_id for token_id, token in self.tokens.items() if token.expires_at <= before
        ]
        for token_id in expirados:
            del self.tokens[token_id]
        return len(expirados)


_conforms: PasswordSetupTokenRepository = InMemoryPasswordSetupTokenRepository()
