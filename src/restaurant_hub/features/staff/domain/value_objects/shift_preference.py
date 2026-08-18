"""Value objects de preferência de turno — `DayPeriod` e `ShiftPreference`.

`DayPeriod` co-locado aqui (decisão registrada no technical §7): só existe como
elemento de `ShiftPreference` nesta Stage. A semântica "None = sem preferência"
vive no `Employee` (o campo é `ShiftPreference | None`), não aqui: preferência
**declarada** nunca é vazia (ADR 3.1.0004).
"""

from dataclasses import dataclass
from enum import StrEnum

from restaurant_hub.features.staff.domain.exceptions.errors import (
    EmptyShiftPreferenceError,
    InvalidDayPeriodError,
)


class DayPeriod(StrEnum):
    """Períodos nomeados do dia — conjunto fechado (kickoff #6).

    Vocabulário PT da língua ubíqua (workforce §2): `MORNING` = manhã,
    `AFTERNOON` = tarde, `NIGHT` = noite, `OVERNIGHT` = **madrugada** (glosa
    fixada para mitigar a ambiguidade do nome EN — concept §10). As fronteiras
    horárias de cada período são do scheduling (workforce §3.5), não de staff.
    """

    MORNING = "morning"
    AFTERNOON = "afternoon"
    NIGHT = "night"
    OVERNIGHT = "overnight"

    @classmethod
    def from_string(cls, value: str) -> "DayPeriod":
        """Converte texto em `DayPeriod`, com erro de domínio se for desconhecido.

        Idêntico em forma ao `Role.from_string` de identity (ADR 3.4.0003 §3): a
        causa original é preservada com `from exc`, para que o rastro do
        `ValueError` do enum sobreviva para depuração nas camadas de fora.
        """
        try:
            return cls(value)
        except ValueError as exc:
            raise InvalidDayPeriodError(value) from exc


@dataclass(frozen=True)
class ShiftPreference:
    """Preferência de turno declarada — subconjunto não-vazio dos períodos.

    Attributes:
        periods: períodos preferidos; qualquer subconjunto de 1 a 4 períodos
            é válido, conjunto vazio é rejeitado (ADR 3.1.0004).
    """

    periods: frozenset[DayPeriod]

    def __post_init__(self) -> None:
        if not self.periods:
            raise EmptyShiftPreferenceError()
