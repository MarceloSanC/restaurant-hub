"""Adapter Postgres de `RestaurantRepository`.

**Fronteira transacional** (concept §7 Decisão 6): o repositório recebe um
`Engine` e abre a própria transação por método público, via `engine.begin()`.

A skill `repository-pattern` recomenda o oposto — transação controlada por um
unit-of-work externo, nunca implícita no repositório. O desvio é consciente e tem
uma razão concreta: os ports da 2.2 são **síncronos e sem UoW** (ADR 2.2.0004), a
camada `application` está proibida de importar SQLAlchemy (contrato
`identity-application-purity` do import-linter), e nenhum use case desta Stage
precisa de atomicidade **entre** repositórios — `UserRepository.add`, que precisa
de atomicidade, a obtém dentro de uma única chamada. Inventar um port de UoW agora
seria contrato novo sem consumidor.

Para manter a troca barata quando esse consumidor existir, cada método público só
abre a transação e delega a um privado que recebe `Connection`. Passar a aceitar
uma `Connection` de fora vira uma mudança de construtor, sem tocar na lógica nem
na forma do port.
"""

from sqlalchemy import Connection, Engine, select
from sqlalchemy.exc import IntegrityError

from restaurant_hub.features.identity.adapters.out.postgres import mappers
from restaurant_hub.features.identity.adapters.out.postgres.integrity_errors import (
    traduzir,
)
from restaurant_hub.features.identity.adapters.out.postgres.tables import restaurants
from restaurant_hub.features.identity.domain.entities.restaurant import Restaurant
from restaurant_hub.features.identity.domain.value_objects.identifiers import (
    RestaurantId,
)


class PostgresRestaurantRepository:
    """Implementação PostgreSQL do port `RestaurantRepository`."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def add(self, restaurant: Restaurant) -> None:
        """Insere um restaurante. Id já gravado levanta `RestaurantAlreadyExistsError`."""
        try:
            with self._engine.begin() as conexao:
                self._add(conexao, restaurant)
        except IntegrityError as erro:
            # `from erro` preserva a cadeia de causa: sem ela, o diagnóstico de um
            # conflito de integridade perde o SQL e a constraint originais.
            raise traduzir(erro, restaurant.id) from erro

    def find_by_id(self, restaurant_id: RestaurantId) -> Restaurant | None:
        with self._engine.connect() as conexao:
            return self._find_by_id(conexao, restaurant_id)

    # ---- núcleo sobre `Connection` (ponto de troca para um futuro UoW) ----

    def _add(self, conexao: Connection, restaurant: Restaurant) -> None:
        conexao.execute(restaurants.insert().values(**mappers.restaurante_para_linha(restaurant)))

    def _find_by_id(self, conexao: Connection, restaurant_id: RestaurantId) -> Restaurant | None:
        linha = conexao.execute(
            select(restaurants).where(restaurants.c.id == restaurant_id)
        ).one_or_none()
        return mappers.linha_para_restaurante(linha) if linha is not None else None
