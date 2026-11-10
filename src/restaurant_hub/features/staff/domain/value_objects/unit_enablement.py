"""Value object UnitEnablement — onde uma função de trabalho vale (Stage 3.11).

A função continua pertencendo ao **restaurante** (ADR 3.11.0001 §1); este VO diz
em quais unidades dele ela está habilitada. Duas formas, e só duas:

- **todas as unidades** — inclusive as que forem criadas depois. É um valor
  próprio, e não a lista das unidades de hoje: staff não conhece as unidades do
  restaurante (elas vivem em identity, sem FK entre BCs — ADR 3.3.0002), e é esta
  forma que as funções anteriores à Stage recebem na migration;
- **um conjunto não-vazio** de unidades, por id opaco.

Vazio é recusado (ADR 3.11.0001 §2): uma função habilitada em nenhum lugar não
apareceria em listagem de unidade alguma e ainda ocuparia o nome no restaurante.
Quem não quer mais a função a apaga (ADR 3.2.0005).
"""

from dataclasses import dataclass

from restaurant_hub.features.staff.domain.exceptions.errors import InvalidUnitEnablementError
from restaurant_hub.features.staff.domain.value_objects.identifiers import UnitId


@dataclass(frozen=True)
class UnitEnablement:
    """Habilitação de uma função: todas as unidades **ou** um conjunto não-vazio.

    Attributes:
        all_units: verdadeiro quando a função vale em toda unidade do restaurante.
        unit_ids: as unidades em que a função vale; **vazio exatamente quando**
            `all_units` é verdadeiro.
    """

    all_units: bool
    unit_ids: frozenset[UnitId]

    def __post_init__(self) -> None:
        # As invariantes moram aqui, e não só nas fábricas, para valerem também na
        # reidratação da persistência (ADR 3.4.0003, precedente).
        if self.all_units and self.unit_ids:
            raise InvalidUnitEnablementError("'todas as unidades' não nomeia unidades")
        if not self.all_units and not self.unit_ids:
            raise InvalidUnitEnablementError("exige ao menos uma unidade")
        if any(not unit_id.strip() for unit_id in self.unit_ids):
            raise InvalidUnitEnablementError("identificador de unidade vazio")

    @classmethod
    def everywhere(cls) -> "UnitEnablement":
        """Todas as unidades do restaurante, presentes e futuras."""
        return cls(all_units=True, unit_ids=frozenset())

    @classmethod
    def only(cls, unit_ids: frozenset[UnitId]) -> "UnitEnablement":
        """Só as unidades dadas; conjunto vazio é recusado."""
        return cls(all_units=False, unit_ids=unit_ids)

    def covers(self, unit_id: UnitId) -> bool:
        """Diz se a função vale na unidade."""
        return self.all_units or unit_id in self.unit_ids
