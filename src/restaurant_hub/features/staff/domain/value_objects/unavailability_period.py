"""Value object UnavailabilityPeriod — intervalo de indisponibilidade semi-aberto.

Intervalo data-hora `[start, end)` (ADR 3.1.0001, decisão i) com instantes
**ingênuos** (sem tzinfo): wall-clock no fuso da unidade do registro
(ADR 3.1.0005) — correção de fuso não pode deslocar o que o gerente declarou;
a conversão para instante absoluto é de quem conhece o fuso
(scheduling/adapters). Tz-aware é rejeitado na construção, o que torna toda
comparação naive vs. naive segura por construção.

Frozen ⇒ igualdade por valor e hashável — a remoção por valor no `Employee`
(`remove_unavailability`, Task 07) depende disso.
"""

from dataclasses import dataclass
from datetime import datetime

from restaurant_hub.features.staff.domain.exceptions.errors import (
    InvalidUnavailabilityPeriodError,
)


@dataclass(frozen=True)
class UnavailabilityPeriod:
    """Período de indisponibilidade `[start, end)` de um funcionário.

    Attributes:
        start: início (inclusivo) — datetime ingênuo, wall-clock da unidade.
        end: fim (exclusivo) — datetime ingênuo; `start < end`.
    """

    start: datetime
    end: datetime

    def __post_init__(self) -> None:
        # Tz-aware ANTES de comparar: garante que start < end só roda naive vs. naive.
        if self.start.tzinfo is not None or self.end.tzinfo is not None:
            raise InvalidUnavailabilityPeriodError(
                "instantes devem ser ingênuos (wall-clock do fuso da unidade, sem tzinfo)"
            )
        if self.start >= self.end:
            raise InvalidUnavailabilityPeriodError("início deve anteceder o fim")

    def overlaps(self, other: "UnavailabilityPeriod") -> bool:
        """Sobreposição na semântica semi-aberta `[start, end)`.

        Sobrepõem sse `início_A < fim_B` e `início_B < fim_A` — adjacentes
        (fim de um == início do outro) **não** conflitam (ADR 3.1.0001).
        """
        return self.start < other.end and other.start < self.end
