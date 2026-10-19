"""Adapter Postgres de `RestaurantRepository`.

**Fronteira transacional** (ADR 2.6.0001, que supera para identity o concept
2.3 §7 Decisão 6): o repositório recebe um `Engine` e pede a conexão a
`conexao_da_unidade`. Fora de unidade de trabalho, cada método público é a própria
transação (`engine.begin()`), como desde a 2.3. Dentro de uma unidade aberta pelo
use case (`UnitOfWork.transaction()`), usa a conexão dela, num savepoint — e as
escritas de vários repositórios ficam atômicas juntas.

A skill `repository-pattern` recomenda transação controlada de fora, nunca
implícita no repositório: é o que a unidade de trabalho faz. O construtor não
mudou — a 2.3 previa "passar a aceitar uma `Connection` de fora" como mudança de
construtor, e a Stage 2.6 preferiu a conexão ambiente (ADR 2.6.0001, Alternativa
B, explica por quê). Cada método público delega a um privado que recebe
`Connection`, e é a mesma `Connection` dentro e fora da unidade.
"""

from sqlalchemy import Connection, Engine, select
from sqlalchemy.exc import IntegrityError

from restaurant_hub.features.identity.adapters.out.postgres import mappers
from restaurant_hub.features.identity.adapters.out.postgres.conexao_da_unidade import (
    para_escrita,
    para_leitura,
)
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
            with para_escrita(self._engine) as conexao:
                self._add(conexao, restaurant)
        except IntegrityError as erro:
            # `from erro` preserva a cadeia de causa: sem ela, o diagnóstico de um
            # conflito de integridade perde o SQL e a constraint originais.
            raise traduzir(erro, restaurant.id) from erro

    def find_by_id(self, restaurant_id: RestaurantId) -> Restaurant | None:
        with para_leitura(self._engine) as conexao:
            return self._find_by_id(conexao, restaurant_id)

    # ---- núcleo sobre `Connection` (a mesma dentro ou fora da unidade de trabalho) ----

    def _add(self, conexao: Connection, restaurant: Restaurant) -> None:
        conexao.execute(restaurants.insert().values(**mappers.restaurante_para_linha(restaurant)))

    def _find_by_id(self, conexao: Connection, restaurant_id: RestaurantId) -> Restaurant | None:
        linha = conexao.execute(
            select(restaurants).where(restaurants.c.id == restaurant_id)
        ).one_or_none()
        return mappers.linha_para_restaurante(linha) if linha is not None else None
