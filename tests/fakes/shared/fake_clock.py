"""Fake do port compartilhado `Clock`.

Tempo fixo e controlável. Sem isso, testar expiração de sessão exigiria dormir —
ou aceitar asserções frouxas, que é como uma regra de expiração errada passa
despercebida.
"""

from datetime import datetime, timedelta

from restaurant_hub.shared.application.ports.out.clock import Clock


class FakeClock:
    """Relógio de teste com instante fixo e avanço explícito."""

    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now

    def advance(self, delta: timedelta) -> None:
        """Avança o relógio — para exercitar expiração sem esperar de verdade."""
        self._now += delta


_conforms: Clock = FakeClock(datetime.now())
