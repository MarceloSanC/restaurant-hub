"""Value objects do perfil de jornada — `FixedSchedule`, `OnDemand` e a união `WorkloadProfile`.

Os dois perfis do workforce (§3.3) como VOs frozen; a união de tipos torna o
estado inválido irrepresentável: "sob demanda com carga" ou "fixa sem carga"
não compilam, e "exatamente um perfil" é garantia **estática** do mypy strict
sobre `WorkloadProfile`, não checagem de runtime (concept §11).
"""

from dataclasses import dataclass
from decimal import Decimal

from restaurant_hub.features.staff.domain.exceptions.errors import InvalidWeeklyHoursError


@dataclass(frozen=True)
class FixedSchedule:
    """Jornada fixa — UMA carga semanal contratada, em horas.

    Attributes:
        weekly_hours: carga semanal positiva e finita; fracionária é aceita
            (ex.: ``Decimal("22.5")``). Teto de horas NÃO é dado de staff.
    """

    weekly_hours: Decimal

    def __post_init__(self) -> None:
        # is_finite() ANTES da comparação: cobre NaN, sNaN e ±Infinity —
        # comparar NaN com 0 levantaria decimal.InvalidOperation.
        if not self.weekly_hours.is_finite() or self.weekly_hours <= 0:
            raise InvalidWeeklyHoursError(self.weekly_hours)


@dataclass(frozen=True)
class OnDemand:
    """Jornada sob demanda — sem dados.

    Não carrega carga contratada nem valor monetário (kickoff #11; workforce
    §3.3b): a classificação "conta ou não para a carga" pertence à alocação
    (Step 4), e dinheiro não é dado de staff v1.
    """


WorkloadProfile = FixedSchedule | OnDemand
