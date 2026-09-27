"""Value object DemandQuantity — quantas pessoas uma função pede numa faixa.

VO e não `int` cru (concept §7): sem ele a recusa do negativo se espalharia por
`declare_demand`, `change_demand_quantity` e pela reidratação da 4.4.

`0` é estado válido — "faixa habilitada sem demanda dessa função" — e **N é
alvo, não teto** (ADR 4.1.0003 (g)): alocados acima de N é situação de política
da 4.2, nunca recusa estrutural. Só o negativo é recusado.
"""

from dataclasses import dataclass

from restaurant_hub.features.scheduling.domain.exceptions.errors import (
    InvalidDemandQuantityError,
)


@dataclass(frozen=True)
class DemandQuantity:
    """Quantidade-alvo de pessoas de uma função numa faixa.

    Attributes:
        value: quantidade-alvo; `>= 0`.
    """

    value: int

    def __post_init__(self) -> None:
        if self.value < 0:
            raise InvalidDemandQuantityError(self.value)
