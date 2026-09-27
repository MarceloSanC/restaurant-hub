"""Value objects do calendário operacional — `Weekday` e `DayCutoff`.

Co-locados num módulo só (concept §7, precedente de `DayPeriod` dentro de
`shift_preference.py` na 3.1): só existem como partes do calendário operacional
do restaurante.

**Nenhum default de campo aqui.** O dia de início da semana e o horário de corte
são defaults de **configuração** de tenant (ADR 4.1.0002 §1/§2), não regra: vivem
num único sítio nomeado do calendário, e nunca como valor default de campo de
dataclass (concept §7 "Defaults do calendário num único sítio").
"""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from enum import StrEnum

from restaurant_hub.features.scheduling.domain.exceptions.errors import (
    InvalidDayCutoffError,
    InvalidWeekdayError,
)

_UM_DIA = timedelta(days=1)


class Weekday(StrEnum):
    """Os 7 dias da semana — conjunto fechado, na ordem ISO (segunda = 1)."""

    MONDAY = "monday"
    TUESDAY = "tuesday"
    WEDNESDAY = "wednesday"
    THURSDAY = "thursday"
    FRIDAY = "friday"
    SATURDAY = "saturday"
    SUNDAY = "sunday"

    @classmethod
    def from_date(cls, day: date) -> "Weekday":
        """Dia da semana de uma data, via `isoweekday()` (1 = segunda … 7 = domingo).

        Depende da ordem de declaração dos membros, que é a ordem ISO. A lista é
        anotada porque o mypy do hook de pre-commit infere `tuple(cls)` de um
        `StrEnum` como tupla de `str` (versão diferente da do `make check` — issue #7).
        """
        membros: list[Weekday] = [*cls]
        return membros[day.isoweekday() - 1]

    @classmethod
    def from_string(cls, value: str) -> "Weekday":
        """Converte texto em `Weekday`, com erro de domínio se for desconhecido.

        Idêntico em forma a `DayPeriod.from_string` de staff (ADR 3.4.0003 §3): a
        causa original é preservada com `from exc`.
        """
        try:
            return cls(value)
        except ValueError as exc:
            raise InvalidWeekdayError(value) from exc


@dataclass(frozen=True)
class DayCutoff:
    """Horário de corte do dia operacional.

    O dia operacional de um instante é o dia civil do instante, **salvo** se o
    instante vier antes do corte — aí é o dia civil anterior. `at` **não tem
    teto** (decisão do sponsor de 2026-09-27, Q5; ADR 4.1.0002 §2): um corte
    tardio é configuração, não defeito.

    Attributes:
        at: horário de corte — `time` ingênuo, de minuto inteiro.
    """

    at: time

    def __post_init__(self) -> None:
        if self.at.tzinfo is not None:
            raise InvalidDayCutoffError("horário deve ser ingênuo (sem tzinfo)")
        if self.at.second != 0 or self.at.microsecond != 0:
            raise InvalidDayCutoffError(
                "horário deve ser de minuto inteiro (segundo e microssegundo zero)"
            )

    def operational_day_of(self, instant: datetime) -> date:
        """Dia operacional que contém `instant`.

        Exatamente no corte o instante já pertence ao dia civil (o corte é o
        **início** do dia operacional). Cruzar a meia-noite civil não é caso
        especial (ADR 4.1.0002 §2; ADR 4.1.0008).
        """
        if instant.time() < self.at:
            return instant.date() - _UM_DIA
        return instant.date()
