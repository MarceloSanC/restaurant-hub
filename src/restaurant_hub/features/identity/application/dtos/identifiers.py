"""Identificadores tipados que nascem na camada de aplicação.

`PasswordHash` existe para que o type-checker separe o hash da senha em claro:
as duas são `str` em runtime, e trocá-las é o tipo de engano que só aparece em
produção. `NewType` dá a distinção estática com custo zero de runtime — o mesmo
recurso que a 2.1 usou para `RestaurantId`/`UnitId`/`UserId`.

`SessionId` fica aqui, e não no domínio, porque a sessão de refresh é um conceito
desta camada (ADR 2.2.0001).
"""

from typing import NewType

PasswordHash = NewType("PasswordHash", str)
SessionId = NewType("SessionId", str)
