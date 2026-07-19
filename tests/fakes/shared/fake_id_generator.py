"""Fake do port compartilhado `IdGenerator`.

Gera UUIDs previsíveis (`...0001`, `...0002`, …) para que o teste possa afirmar o
id exato produzido por um use case. Com `uuid4()` real só seria possível afirmar
"algum id", e a conversão canônica `str(uuid)` — que a Stage 2.3 vai persistir —
ficaria sem verificação.
"""

from collections.abc import Sequence
from uuid import UUID

from restaurant_hub.shared.application.ports.out.id_generator import IdGenerator


class FakeIdGenerator:
    """Gerador determinístico: sequência fixa, ou UUIDs incrementais."""

    def __init__(self, ids: Sequence[UUID] | None = None) -> None:
        self._queue = list(ids) if ids is not None else []
        self._counter = 0
        self.generated: list[UUID] = []

    def next_id(self) -> UUID:
        if self._queue:
            generated = self._queue.pop(0)
        else:
            self._counter += 1
            generated = UUID(int=self._counter)
        self.generated.append(generated)
        return generated


_conforms: IdGenerator = FakeIdGenerator()
