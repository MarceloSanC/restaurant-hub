"""Value object SchedulePeriod — intervalo contíguo de dias operacionais.

O período da escala é uma sequência de `days` dias operacionais a partir de
`first_day` (ADR 4.1.0002 §1). Na v1 são 7, produzidos pelo calendário
(`OperationalCalendar.period_starting_on`); `days == 7` é o default, **não**
invariante — quinzena/mês ficam como evolução aditiva.

**Teto 31** (concept §7 "Teto declarado"): o maior mês civil, logo o maior
período que essa evolução precisa admitir; limita também o agregado que a 4.4
carrega inteiro. O alinhamento ao dia de início é lei do calendário
(`OperationalCalendar.is_aligned`), não deste VO — aqui não há `week_start`.
"""

from dataclasses import dataclass
from datetime import date, timedelta

from restaurant_hub.features.scheduling.domain.exceptions.errors import (
    InvalidSchedulePeriodError,
)

_MINIMO_DE_DIAS = 1
_MAXIMO_DE_DIAS = 31


@dataclass(frozen=True)
class SchedulePeriod:
    """Período da escala — `days` dias operacionais contíguos a partir de `first_day`.

    Attributes:
        first_day: primeiro dia operacional do período.
        days: quantidade de dias operacionais; `1 <= days <= 31`.
    """

    first_day: date
    days: int = 7

    def __post_init__(self) -> None:
        if not _MINIMO_DE_DIAS <= self.days <= _MAXIMO_DE_DIAS:
            raise InvalidSchedulePeriodError(
                f"o período deve ter de {_MINIMO_DE_DIAS} a {_MAXIMO_DE_DIAS} dias "
                f"(recebido: {self.days})"
            )

    @property
    def last_day(self) -> date:
        """Último dia operacional do período (`first_day + (days - 1)`)."""
        return self.first_day + timedelta(days=self.days - 1)

    @property
    def operational_days(self) -> tuple[date, ...]:
        """Os `days` dias operacionais do período, em ordem."""
        return tuple(self.first_day + timedelta(days=indice) for indice in range(self.days))

    def contains(self, operational_day: date) -> bool:
        """Se o dia operacional pertence ao período (bordas inclusivas)."""
        return self.first_day <= operational_day <= self.last_day
