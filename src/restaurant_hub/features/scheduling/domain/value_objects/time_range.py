"""Value object TimeRange — a faixa/turno como par de instantes ingênuos.

Intervalo **semi-aberto** `[start, end)` de instantes **ingênuos** (wall-clock da
unidade, ADR 4.1.0005) de **minuto inteiro**, com o intervalo de refeição
declarado em minutos (ADR 4.1.0007). As datas vivem dentro do valor: a faixa que
cruza a meia-noite civil é um intervalo só, sem caso especial.

**Sítio único de horas.** `worked_minutes` é a **única** expressão aritmética de
horas do BC (ADR 4.1.0002 §3; ADR 4.1.0011): as políticas que somam (4.2) e o
hub (Step 8) chegam aqui, via `Schedule.worked_minutes_of`. Minutos inteiros,
nunca `float`/`Decimal` (ADR 4.1.0007 §3).

Frozen ⇒ igualdade por valor, **inclusive** o `break_minutes`; a chave de
unicidade da faixa dentro do agregado é `hours_key`, que **não** o inclui.
"""

import dataclasses
from dataclasses import dataclass
from datetime import datetime, timedelta

from restaurant_hub.features.scheduling.domain.exceptions.errors import (
    InvalidTimeRangeError,
)

_ONE_MINUTE = timedelta(minutes=1)
_MAX_DURATION = timedelta(hours=24)


@dataclass(frozen=True)
class TimeRange:
    """Faixa `[start, end)` com intervalo declarado.

    Attributes:
        start: início (inclusivo) — datetime ingênuo, minuto inteiro.
        end: fim (exclusivo) — datetime ingênuo, minuto inteiro;
            `start < end` e `end - start <= 24h`.
        break_minutes: intervalo declarado da faixa, em minutos;
            `0 <= break_minutes < nominal_minutes`.
    """

    start: datetime
    end: datetime
    break_minutes: int = 0

    def __post_init__(self) -> None:
        # Tz-aware ANTES de comparar: garante que start < end só roda naive vs. naive
        # (precedente unavailability_period.py).
        if self.start.tzinfo is not None or self.end.tzinfo is not None:
            raise InvalidTimeRangeError(
                "instantes devem ser ingênuos (wall-clock do fuso da unidade, sem tzinfo)"
            )
        for instant in (self.start, self.end):
            if instant.second != 0 or instant.microsecond != 0:
                raise InvalidTimeRangeError(
                    "instantes devem ser de minuto inteiro (segundo e microssegundo zero)"
                )
        if self.start >= self.end:
            raise InvalidTimeRangeError("início deve anteceder o fim")
        if self.end - self.start > _MAX_DURATION:
            raise InvalidTimeRangeError("duração nominal não pode passar de 24h")
        # nominal_minutes só é lido depois de o par ser válido: antes disso a
        # checagem do intervalo rodaria sobre duração negativa.
        if self.break_minutes < 0:
            raise InvalidTimeRangeError("intervalo não pode ser negativo")
        if self.break_minutes >= self.nominal_minutes:
            raise InvalidTimeRangeError("intervalo deve ser menor que a duração nominal")

    @property
    def nominal_minutes(self) -> int:
        """Duração de relógio da faixa, em minutos inteiros (`end - start`)."""
        return (self.end - self.start) // _ONE_MINUTE

    def worked_minutes(self, break_minutes: int | None = None) -> int:
        """Minutos trabalhados — `horas(a)`, o sítio único da aritmética de horas.

        Sem argumento, desconta o intervalo da própria faixa; com argumento,
        desconta o **intervalo efetivo** da alocação (ADR 4.1.0011). Os limites
        do intervalo da alocação são impostos por quem o conhece junto com a
        faixa (`ShiftBand`), não aqui: este método é só a expressão.
        """
        deducted_break = self.break_minutes if break_minutes is None else break_minutes
        return self.nominal_minutes - deducted_break

    @property
    def hours_key(self) -> tuple[datetime, datetime]:
        """Chave de unicidade da faixa no agregado — `(start, end)`, sem o intervalo.

        Duas faixas de mesmo par e intervalos diferentes seriam ambiguidade, não
        variação (ADR 4.1.0011): a chave as iguala mesmo sendo valores distintos.
        """
        return (self.start, self.end)

    def overlaps(self, other: "TimeRange") -> bool:
        """Sobreposição na semântica semi-aberta `[start, end)`.

        Sobrepõem sse `início_A < fim_B` e `início_B < fim_A` — adjacentes
        (fim de um == início do outro) **não** se sobrepõem (ADR 4.1.0007 §5).
        """
        return self.start < other.end and other.start < self.end

    def with_break(self, break_minutes: int) -> "TimeRange":
        """Mesma faixa com outro intervalo declarado (revalidado na construção)."""
        return dataclasses.replace(self, break_minutes=break_minutes)

    def with_bounds(self, start: datetime, end: datetime) -> "TimeRange":
        """Outra faixa de relógio **com o mesmo intervalo** (revalidada).

        Preservar `break_minutes` é o que torna "reagendar não muda o intervalo"
        estrutural, e não uma checagem (ADR 4.1.0011; restrição 3 de
        `reschedule_band`). Encurtar abaixo do intervalo é recusado pela própria
        invariante do intervalo.
        """
        return dataclasses.replace(self, start=start, end=end)
