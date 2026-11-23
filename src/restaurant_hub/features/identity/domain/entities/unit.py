"""Entidade Unit — unidade (filial) de um restaurante.

Raiz de agregado própria: referencia o restaurante **por id** (`restaurant_id`),
nunca por referência de objeto (ADR 2.1.0001). O `restaurant_id` é o `tenant_id`
da unidade — é ele que sustenta o isolamento row-level (ROADMAP-3).

Igualdade por **identidade**.

**O fuso é da unidade** (ADR 4.1.0005, issue #198): `timezone` é uma chave IANA
(`America/Sao_Paulo`, `America/Manaus`), com default `America/Sao_Paulo`. É
configuração da unidade, não dado de escala: scheduling, ponto e hub o leem do
dono, identity, e convertem horário de parede em instante do lado deles.

**A chave é validada na entrada, não na reidratação** (auditoria do PR #232).
Quem cria a unidade passa por `Unit.create`, que recusa chave fora da base IANA
com `InvalidTimezoneError`. O construtor não consulta a base. Pertencer à base
não é propriedade do estado gravado: depende do `tzdata` e do sistema de
arquivos do processo que lê. Um release do IANA que remova um nome (o
`US/Pacific-New` saiu na 2020b) ou um processo com outra base mudariam o
resultado sem nenhuma escrita. Se o construtor validasse, essa linha passaria a
levantar no `find_by_id`, inclusive dentro do `AuthorizeActionUseCase`, antes da
checagem de tenant. Toda rota que autoriza pela unidade responderia 422, com a
chave no corpo, mesmo a quem é de outro tenant. A autorização não lê o fuso, e
quem converte horário de parede em instante é o consumidor (ADR 4.1.0005
§Decision 3), que trata a chave que não carrega no ponto de uso.
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
    não é recusa de chave. O pacote `tzdata`, dependência declarada do projeto,
    garante a base mesmo onde o sistema não tem uma; onde tem, o conjunto também
    inclui as chaves do sistema.
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
            Validada por `create`, não pelo construtor (docstring do módulo).
    """

    id: UnitId
    restaurant_id: RestaurantId
    name: str
    timezone: str = DEFAULT_TIMEZONE

    @classmethod
    def create(
        cls,
        *,
        id: UnitId,
        restaurant_id: RestaurantId,
        name: str,
        timezone: str = DEFAULT_TIMEZONE,
    ) -> "Unit":
        """Unidade nova, com o fuso conferido contra a base IANA do processo.

        É o caminho de quem cria (ou, no futuro, altera) a unidade. A
        reidratação usa o construtor, que não consulta a base.

        Raises:
            InvalidTimezoneError: `timezone` não é chave IANA conhecida.
            InvalidIdentifierError, InvalidNameError: as do construtor.
        """
        if timezone not in _iana_keys():
            raise InvalidTimezoneError(timezone)
        return cls(id=id, restaurant_id=restaurant_id, name=name, timezone=timezone)

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise InvalidIdentifierError("unidade")
        if not self.restaurant_id.strip():
            raise InvalidIdentifierError("restaurante da unidade")
        if not self.name.strip():
            raise InvalidNameError("unidade")

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
