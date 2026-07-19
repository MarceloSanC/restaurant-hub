"""Repositórios de restaurante e unidade contra PostgreSQL real — CA2, CA3, CA6.

O que estes testes cobrem e os unitários não: que o SQL realmente escreve e lê o
que o mapper prometeu, e que as constraints do banco disparam onde o concept diz
que disparam.
"""

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError

from restaurant_hub.features.identity.adapters.out.postgres.restaurant_repository import (
    PostgresRestaurantRepository,
)
from restaurant_hub.features.identity.adapters.out.postgres.unit_repository import (
    PostgresUnitRepository,
)
from restaurant_hub.features.identity.application.errors import (
    RestaurantAlreadyExistsError,
    UnitAlreadyExistsError,
)
from restaurant_hub.features.identity.domain.entities.restaurant import Restaurant
from restaurant_hub.features.identity.domain.entities.unit import Unit
from restaurant_hub.features.identity.domain.value_objects.identifiers import (
    RestaurantId,
    UnitId,
)

pytestmark = pytest.mark.integration


def test_restaurante_faz_round_trip_campo_a_campo(banco_limpo: Engine) -> None:
    """CA2 — comparação **campo a campo**, não por `==`.

    `Restaurant.__eq__` compara só por id, então um round-trip que corrompesse o
    `name` ainda passaria num `assert lido == gravado`. A asserção por campo é o
    que dá sentido ao teste.
    """
    repo = PostgresRestaurantRepository(banco_limpo)
    repo.add(Restaurant(id=RestaurantId("rest-1"), name="  Cantina  "))

    lido = repo.find_by_id(RestaurantId("rest-1"))

    assert lido is not None
    assert lido.id == "rest-1"
    # `name` verbatim: os espaços sobrevivem ao banco (ADR 2.3.0005), o que também
    # prova que a coluna é TEXT e não CHAR(n), que faria padding à direita.
    assert lido.name == "  Cantina  "


def test_find_by_id_de_restaurante_inexistente_devolve_none(banco_limpo: Engine) -> None:
    """CA3 — ausência é `None`, não exceção."""
    repo = PostgresRestaurantRepository(banco_limpo)
    assert repo.find_by_id(RestaurantId("nao-existe")) is None


def test_restaurante_duplicado_levanta_erro_de_dominio(banco_limpo: Engine) -> None:
    """CA6 — `add` é inserção, não upsert; a PK impõe e o adapter traduz."""
    repo = PostgresRestaurantRepository(banco_limpo)
    repo.add(Restaurant(id=RestaurantId("rest-1"), name="Cantina"))

    with pytest.raises(RestaurantAlreadyExistsError):
        repo.add(Restaurant(id=RestaurantId("rest-1"), name="Outro nome"))

    # E o primeiro valor continua lá — a tentativa falhada não sobrescreveu nada.
    lido = repo.find_by_id(RestaurantId("rest-1"))
    assert lido is not None
    assert lido.name == "Cantina"


def test_unidade_faz_round_trip_campo_a_campo(banco_limpo: Engine) -> None:
    restaurantes = PostgresRestaurantRepository(banco_limpo)
    unidades = PostgresUnitRepository(banco_limpo)
    restaurantes.add(Restaurant(id=RestaurantId("rest-1"), name="Cantina"))

    unidades.add(Unit(id=UnitId("unit-1"), restaurant_id=RestaurantId("rest-1"), name="  Centro  "))

    lida = unidades.find_by_id(UnitId("unit-1"))
    assert lida is not None
    assert lida.id == "unit-1"
    assert lida.restaurant_id == "rest-1"
    assert lida.name == "  Centro  "


def test_find_by_id_de_unidade_inexistente_devolve_none(banco_limpo: Engine) -> None:
    assert PostgresUnitRepository(banco_limpo).find_by_id(UnitId("nao-existe")) is None


def test_unidade_duplicada_levanta_erro_de_dominio(banco_limpo: Engine) -> None:
    restaurantes = PostgresRestaurantRepository(banco_limpo)
    unidades = PostgresUnitRepository(banco_limpo)
    restaurantes.add(Restaurant(id=RestaurantId("rest-1"), name="Cantina"))
    unidades.add(Unit(id=UnitId("unit-1"), restaurant_id=RestaurantId("rest-1"), name="Centro"))

    with pytest.raises(UnitAlreadyExistsError):
        unidades.add(Unit(id=UnitId("unit-1"), restaurant_id=RestaurantId("rest-1"), name="Praia"))


def test_unidade_de_restaurante_inexistente_nao_e_traduzida(banco_limpo: Engine) -> None:
    """Decisão 7 — violação de FK sobe como `IntegrityError`, de propósito.

    O use case já validou a existência do restaurante antes de chamar o
    repositório, então uma FK que estoura aqui é bug ou concorrência exótica.
    Traduzi-la para erro de negócio a esconderia atrás de um 4xx plausível.
    """
    unidades = PostgresUnitRepository(banco_limpo)

    with pytest.raises(IntegrityError):
        unidades.add(
            Unit(id=UnitId("unit-1"), restaurant_id=RestaurantId("fantasma"), name="Centro")
        )


def test_nenhum_repositorio_devolve_linha_de_outro_tenant(banco_limpo: Engine) -> None:
    """I4 na prática: unidades de tenants distintos não se confundem.

    A busca é por id (o port não recebe tenant), então o que se prova aqui é que o
    `restaurant_id` lido é o gravado — a base sobre a qual o domínio decide
    visibilidade. O cerco duro contra vínculo cross-tenant é exercitado no teste
    do repositório de usuário.
    """
    restaurantes = PostgresRestaurantRepository(banco_limpo)
    unidades = PostgresUnitRepository(banco_limpo)
    restaurantes.add(Restaurant(id=RestaurantId("rest-a"), name="A"))
    restaurantes.add(Restaurant(id=RestaurantId("rest-b"), name="B"))
    unidades.add(Unit(id=UnitId("unit-a"), restaurant_id=RestaurantId("rest-a"), name="A1"))
    unidades.add(Unit(id=UnitId("unit-b"), restaurant_id=RestaurantId("rest-b"), name="B1"))

    lida_a = unidades.find_by_id(UnitId("unit-a"))
    lida_b = unidades.find_by_id(UnitId("unit-b"))

    assert lida_a is not None and lida_a.restaurant_id == "rest-a"
    assert lida_b is not None and lida_b.restaurant_id == "rest-b"
    assert lida_a.tenant_id != lida_b.tenant_id


def test_escrita_foi_realmente_commitada(banco_limpo: Engine) -> None:
    """Prova que `engine.begin()` commitou — e não que o dado está num cache.

    Sem esta checagem por fora do repositório, um `add` que abrisse transação e
    nunca commitasse passaria em todos os outros testes desta classe, desde que a
    leitura acontecesse na mesma conexão.
    """
    PostgresRestaurantRepository(banco_limpo).add(
        Restaurant(id=RestaurantId("rest-1"), name="Cantina")
    )

    with banco_limpo.connect() as outra_conexao:
        total = outra_conexao.execute(
            text("SELECT count(*) FROM restaurants WHERE id = 'rest-1'")
        ).scalar_one()

    assert total == 1
