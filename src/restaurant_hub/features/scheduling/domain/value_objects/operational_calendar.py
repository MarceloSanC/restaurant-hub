"""Value objects do calendário operacional — `Weekday`, `DayCutoff` e `OperationalCalendar`.

Co-locados num módulo só (concept §7, precedente de `DayPeriod` dentro de
`shift_preference.py` na 3.1): `Weekday` e `DayCutoff` só existem como partes do
calendário operacional do restaurante.

**Nenhum default de campo aqui.** O dia de início da semana e o horário de corte
são defaults de **configuração** de tenant (ADR 4.1.0002 §1/§2), não regra: vivem
num único sítio nomeado, `OperationalCalendar.default()`, e nunca como valor
default de campo de dataclass (concept §7 "Defaults do calendário num único
sítio").
"""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from enum import StrEnum

from restaurant_hub.features.scheduling.domain.exceptions.errors import (
    InvalidDayCutoffError,
    InvalidSchedulePeriodError,
    InvalidWeekdayError,
)
from restaurant_hub.features.scheduling.domain.value_objects.schedule_period import (
    SchedulePeriod,
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


@dataclass(frozen=True)
class OperationalCalendar:
    """As duas configurações de calendário do restaurante, e a produção de períodos.

    Fotografado na criação da escala (ADR 4.1.0009): a raiz carrega o calendário
    com que foi criada, e `is_aligned` é o que torna `week_start` dado vivo dentro
    do agregado (concept §5.2).

    Attributes:
        week_start: dia da semana em que começa o período.
        day_cutoff: horário de corte do dia operacional.
    """

    week_start: Weekday
    day_cutoff: DayCutoff

    @classmethod
    def default(cls) -> "OperationalCalendar":
        """Segunda-feira e corte às 05:00 — o **único** sítio desses dois valores.

        São defaults de configuração, sem força de regra (ADR 4.1.0002 §1/§2): a
        4.4 os persiste por restaurante e a 4.5 os edita.
        """
        return cls(week_start=Weekday.MONDAY, day_cutoff=DayCutoff(at=time(5, 0)))

    def operational_day_of(self, instant: datetime) -> date:
        """Dia operacional que contém `instant` — delega ao corte."""
        return self.day_cutoff.operational_day_of(instant)

    def period_starting_on(self, first_day: date, days: int = 7) -> SchedulePeriod:
        """Período de `days` dias a partir de `first_day`, alinhado ao `week_start`.

        `first_day` que não cai no `week_start` é recusado. A contagem de dias é
        validada pelo próprio `SchedulePeriod`; o alinhamento, por `is_aligned` —
        o mesmo predicado que o `Schedule.__post_init__` usa, para que fábrica e
        reidratação apliquem uma lei só.
        """
        period = SchedulePeriod(first_day=first_day, days=days)
        if not self.is_aligned(period):
            raise InvalidSchedulePeriodError("desalinhado")
        return period

    def is_aligned(self, period: SchedulePeriod) -> bool:
        """Se o primeiro dia do período cai no `week_start` deste calendário."""
        return Weekday.from_date(period.first_day) == self.week_start
