"""Entidade Unit — unidade (filial) de um restaurante.

Raiz de agregado própria: referencia o restaurante **por id** (`restaurant_id`),
nunca por referência de objeto (ADR 2.1.0001). O `restaurant_id` é o `tenant_id`
da unidade — é ele que sustenta o isolamento row-level (ROADMAP-3).

Igualdade por **identidade**.

**O fuso é da unidade** (ADR 4.1.0005, issue #198): `timezone` é uma chave IANA
(`America/Sao_Paulo`, `America/Manaus`), com default `America/Sao_Paulo`. É
configuração da unidade, não dado de escala: scheduling, ponto e hub o leem do
dono, identity, e convertem horário de parede em instante do lado deles.
"""

from dataclasses import dataclass
from functools import cache
from typing import Final
from zoneinfo import available_timezones

from restaurant_hub.features.identity.domain.exceptions.errors import (
    InvalidIdentifierError,
    InvalidNameError,
    InvalidTimezoneError,
)
from restaurant_hub.features.identity.domain.value_objects.identifiers import (
    RestaurantId,
    UnitId,
)

DEFAULT_TIMEZONE: Final = "America/Sao_Paulo"
"""Fuso de toda unidade que não declara outro (ADR 4.1.0005 §Decision 1)."""


@cache
def _iana_keys() -> frozenset[str]:
    """As chaves IANA que o `zoneinfo` conhece neste processo, lidas uma vez.

    Pertencimento ao conjunto, e não "o `ZoneInfo(key)` construiu?": construir
    depende do sistema de arquivos. No Windows, `ZoneInfo("America/Sao_Paulo ")`
    (espaço no fim) é aceito, porque o sistema de arquivos ignora o espaço, e no
    Linux é recusado; `ZoneInfo("America")` (um diretório) levanta `OSError`, que
    não é recusa de chave. O conjunto é o mesmo nos dois, porque a base vem do
    pacote `tzdata`, dependência declarada do projeto.
    """
    return frozenset(available_timezones())


@dataclass(frozen=True, eq=False)
class Unit:
    """Unidade de um restaurante.

    Attributes:
        id: identidade da unidade.
        restaurant_id: restaurante dono da unidade — também o seu `tenant_id`.
        name: nome da unidade (não vazio).
        timezone: chave IANA do fuso da unidade; default `America/Sao_Paulo`.
    """

    id: UnitId
    restaurant_id: RestaurantId
    name: str
    timezone: str = DEFAULT_TIMEZONE

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise InvalidIdentifierError("unidade")
        if not self.restaurant_id.strip():
            raise InvalidIdentifierError("restaurante da unidade")
        if not self.name.strip():
            raise InvalidNameError("unidade")
        if self.timezone not in _iana_keys():
            raise InvalidTimezoneError(self.timezone)

    @property
    def tenant_id(self) -> RestaurantId:
        """Tenant da unidade — o restaurante a que ela pertence."""
        return self.restaurant_id

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Unit):
            return NotImplemented
        return self.id == other.id

    def __hash__(self) -> int:
        return hash(self.id)
