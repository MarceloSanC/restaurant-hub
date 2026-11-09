"""Adapter Postgres de `PasswordSetupTokenRepository`.

**A razão de este arquivo existir é uma linha só:** o `UPDATE` condicional de
`consume`. Todo o resto é persistência comum; aquela linha é o que transforma
"uso único" de intenção em garantia.

Quatro pontos, cada um contra um SQL "natural" que quebraria o contrato:

**1. `find_by_fingerprint` NÃO filtra.** Sem `WHERE consumed_at IS NULL`, sem
`WHERE expires_at > now()`. Um token já consumido precisa ser **encontrável**,
senão volta `None` e fica indistinguível de um token forjado — e o chamador perde
a capacidade de distinguir "replay de token real" de "chute" no log. Filtrar é
papel de `PasswordSetupToken.is_usable`.

**2. `consume` é `UPDATE ... WHERE consumed_at IS NULL`, e devolve `rowcount == 1`.**
O SQL natural seria `SELECT` para conferir e `UPDATE` para gravar. Ele passa em
**todo** teste sequencial e perde a corrida em produção: duas redenções
simultâneas do mesmo token leem `consumed_at IS NULL` antes de qualquer uma
gravar, ambas seguem, e ambas definem uma senha — a segunda sendo a do atacante.
Com o predicado dentro do `UPDATE`, o Postgres serializa as duas escritas na
mesma linha e exatamente uma afeta uma linha. É por isso que o teste de
concorrência desta Stage existe: ele é o único capaz de distinguir as duas
implementações.

**3. `invalidate_all_for_user` usa `consumed_at IS NULL`, sem termo de expiração.**
Regra 4 do port: a definição de "invalidar" é a mesma de `consume`, e não a de
`is_usable`. As duas leituras devolvem contagens diferentes para um token
expirado-e-não-consumido, e a contagem é observável.

**4. `purge_expired` usa `<=`, não `<`.** `is_usable` é half-open, então em
`expires_at == before` o token já expirou e tem de ser expurgável.

**Sobre `IntegrityError` em `add`:** sobe intacto, de propósito. Seguindo a
doutrina de `integrity_errors.py`, só constraint com significado de negócio é
traduzida — e id ou fingerprint repetido aqui não é regra de negócio, é
impossibilidade estatística (o valor vem de 256 bits de `secrets`). Traduzi-lo
para um erro de domínio o transformaria num 4xx plausível, escondendo o que só
pode ser bug ou colisão de gerador.
"""

from datetime import datetime

from sqlalchemy import Engine, delete, select, update

from restaurant_hub.features.identity.adapters.out.postgres import mappers
from restaurant_hub.features.identity.adapters.out.postgres.tables import (
    password_setup_tokens,
)
from restaurant_hub.features.identity.adapters.out.postgres.unit_connection import (
    for_read,
    for_write,
)
from restaurant_hub.features.identity.application.dtos.identifiers import SetupTokenId
from restaurant_hub.features.identity.application.dtos.setup_tokens import (
    PasswordSetupToken,
    SetupTokenPurpose,
)
from restaurant_hub.features.identity.domain.value_objects.identifiers import UserId


class PostgresPasswordSetupTokenRepository:
    """Implementação PostgreSQL do port `PasswordSetupTokenRepository`."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def add(self, token: PasswordSetupToken) -> None:
        """Insere o token. `IntegrityError` sobe intacto — ver docstring do módulo."""
        with for_write(self._engine) as connection:
            connection.execute(
                password_setup_tokens.insert().values(**mappers.setup_token_to_row(token))
            )

    def find_by_fingerprint(self, fingerprint: str) -> PasswordSetupToken | None:
        """Busca **sem filtro** de consumo ou expiração — regra 1 do módulo."""
        with for_read(self._engine) as connection:
            row = connection.execute(
                select(password_setup_tokens).where(
                    password_setup_tokens.c.token_fingerprint == fingerprint
                )
            ).one_or_none()
        return mappers.row_to_setup_token(row) if row is not None else None

    def consume(self, token_id: SetupTokenId, consumed_at: datetime) -> bool:
        """Transição condicional e atômica. `True` só se o token ainda não fora usado.

        O `WHERE consumed_at IS NULL` **dentro** do `UPDATE` é a trava inteira —
        ver regra 2 do módulo. Token inexistente também afeta zero linhas e
        devolve `False`, que é o contrato: quem consome já trata `False` como
        "token inválido".
        """
        with for_write(self._engine) as connection:
            result = connection.execute(
                update(password_setup_tokens)
                .where(
                    password_setup_tokens.c.id == token_id,
                    password_setup_tokens.c.consumed_at.is_(None),
                )
                .values(consumed_at=consumed_at)
            )
        return bool(result.rowcount == 1)

    def invalidate_all_for_user(
        self,
        user_id: UserId,
        consumed_at: datetime,
        purpose: SetupTokenPurpose | None = None,
    ) -> int:
        """Invalida os tokens **não consumidos** do usuário. Devolve quantos foram."""
        conditions = [
            password_setup_tokens.c.user_id == user_id,
            # Nunca reescreve um `consumed_at` já gravado — regra 5 do port: o
            # instante do primeiro consumo é o dado da forense.
            password_setup_tokens.c.consumed_at.is_(None),
        ]
        if purpose is not None:
            # Escopo por propósito: é o que impede que a rota **pública** de
            # redefinição mate o convite pendente de qualquer vítima, em laço.
            conditions.append(password_setup_tokens.c.purpose == purpose.value)

        with for_write(self._engine) as connection:
            result = connection.execute(
                update(password_setup_tokens).where(*conditions).values(consumed_at=consumed_at)
            )
        return int(result.rowcount)

    def purge_expired(self, before: datetime) -> int:
        """Remove os tokens já expirados. `<=` porque `is_usable` é half-open."""
        with for_write(self._engine) as connection:
            result = connection.execute(
                delete(password_setup_tokens).where(password_setup_tokens.c.expires_at <= before)
            )
        return int(result.rowcount)
