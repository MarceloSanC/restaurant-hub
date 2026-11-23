"""Testes da entidade Unit (domain/entities/unit.py)."""

import dataclasses

import pytest

from restaurant_hub.features.identity.domain.entities.unit import DEFAULT_TIMEZONE, Unit
from restaurant_hub.features.identity.domain.exceptions.errors import (
    InvalidIdentifierError,
    InvalidNameError,
    InvalidTimezoneError,
)
from restaurant_hub.features.identity.domain.value_objects.identifiers import (
    RestaurantId,
    UnitId,
)

pytestmark = pytest.mark.unit


def test_cria_unidade_valida() -> None:
    unidade = Unit(id=UnitId("u1"), restaurant_id=RestaurantId("r1"), name="Matriz")
    assert unidade.id == "u1"
    assert unidade.restaurant_id == "r1"
    assert unidade.name == "Matriz"


def test_tenant_id_e_o_restaurante_dono() -> None:
    # É o tenant_id da unidade que sustenta o isolamento row-level (ROADMAP-3).
    unidade = Unit(id=UnitId("u1"), restaurant_id=RestaurantId("r1"), name="Matriz")
    assert unidade.tenant_id == "r1"


def test_igualdade_por_identidade_ignora_demais_campos() -> None:
    antes = Unit(id=UnitId("u1"), restaurant_id=RestaurantId("r1"), name="Matriz")
    depois = Unit(id=UnitId("u1"), restaurant_id=RestaurantId("r1"), name="Filial")
    assert antes == depois


def test_ids_diferentes_nao_sao_iguais() -> None:
    assert Unit(id=UnitId("u1"), restaurant_id=RestaurantId("r1"), name="Matriz") != Unit(
        id=UnitId("u2"), restaurant_id=RestaurantId("r1"), name="Matriz"
    )


def test_hash_segue_a_identidade() -> None:
    antes = Unit(id=UnitId("u1"), restaurant_id=RestaurantId("r1"), name="Matriz")
    depois = Unit(id=UnitId("u1"), restaurant_id=RestaurantId("r1"), name="Filial")
    assert len({antes, depois}) == 1


def test_comparacao_com_outro_tipo_nao_e_igual() -> None:
    unidade = Unit(id=UnitId("u1"), restaurant_id=RestaurantId("r1"), name="Matriz")
    assert unidade != "u1"


@pytest.mark.parametrize("invalido", ["", "   "])
def test_nome_vazio_e_rejeitado(invalido: str) -> None:
    with pytest.raises(InvalidNameError, match="nome de unidade"):
        Unit(id=UnitId("u1"), restaurant_id=RestaurantId("r1"), name=invalido)


def test_entidade_e_imutavel() -> None:
    unidade = Unit(id=UnitId("u1"), restaurant_id=RestaurantId("r1"), name="Matriz")
    with pytest.raises(dataclasses.FrozenInstanceError):
        unidade.restaurant_id = RestaurantId("r2")  # type: ignore[misc]


@pytest.mark.parametrize("invalido", ["", "   "])
def test_id_vazio_e_rejeitado(invalido: str) -> None:
    with pytest.raises(InvalidIdentifierError, match="identificador de unidade"):
        Unit(id=UnitId(invalido), restaurant_id=RestaurantId("r1"), name="Matriz")


@pytest.mark.parametrize("invalido", ["", "   "])
def test_restaurante_vazio_e_rejeitado(invalido: str) -> None:
    # tenant_id vazio criaria um balde de falso isolamento.
    with pytest.raises(InvalidIdentifierError, match="restaurante da unidade"):
        Unit(id=UnitId("u1"), restaurant_id=RestaurantId(invalido), name="Matriz")


class _SempreIgual:
    """Objeto que se declara igual a qualquer coisa, para testar a reflexão."""

    def __eq__(self, other: object) -> bool:
        return True

    def __hash__(self) -> int:
        return 0


def test_eq_delega_ao_outro_operando_quando_o_tipo_e_estranho() -> None:
    unidade = Unit(id=UnitId("u1"), restaurant_id=RestaurantId("r1"), name="Matriz")
    assert unidade == _SempreIgual()
    assert _SempreIgual() == unidade


# ---------------------------------------------------------------------------
# Fuso da unidade (issue #198, ADR 4.1.0005)
# ---------------------------------------------------------------------------


def test_fuso_default_e_sao_paulo() -> None:
    unidade = Unit(id=UnitId("u1"), restaurant_id=RestaurantId("r1"), name="Matriz")
    assert unidade.timezone == "America/Sao_Paulo"
    assert DEFAULT_TIMEZONE == "America/Sao_Paulo"


@pytest.mark.parametrize("chave", ["America/Manaus", "America/Sao_Paulo", "UTC", "Europe/Lisbon"])
def test_aceita_chave_iana_e_a_guarda_como_veio(chave: str) -> None:
    unidade = Unit(id=UnitId("u1"), restaurant_id=RestaurantId("r1"), name="Matriz", timezone=chave)
    assert unidade.timezone == chave


@pytest.mark.parametrize(
    "invalida",
    [
        "",
        "   ",
        "Lua/Base",
        # Caixa errada: a chave IANA é sensível a caixa.
        "america/sao_paulo",
        # Espaço nas pontas: o Windows aceitaria pelo sistema de arquivos, o Linux não.
        "America/Sao_Paulo ",
        " America/Sao_Paulo",
        # Diretório da base, não fuso: construir o `ZoneInfo` levantaria `OSError`.
        "America",
        # Caminho absoluto, subida de diretório e byte NUL: `ValueError` no `ZoneInfo`.
        "/etc/localtime",
        "../America/Sao_Paulo",
        "America/Sao\x00_Paulo",
        # Arquivos da base que não são chave canônica.
        "posixrules",
        "right/America/Sao_Paulo",
    ],
)
def test_chave_fora_da_base_iana_e_recusada_com_erro_de_dominio(invalida: str) -> None:
    with pytest.raises(InvalidTimezoneError, match="fuso horário inválido"):
        Unit(id=UnitId("u1"), restaurant_id=RestaurantId("r1"), name="Matriz", timezone=invalida)


def test_fuso_nao_entra_na_igualdade() -> None:
    # A unidade continua igual a si mesma depois de mudar de fuso: igualdade por id.
    antes = Unit(id=UnitId("u1"), restaurant_id=RestaurantId("r1"), name="Matriz")
    depois = Unit(
        id=UnitId("u1"), restaurant_id=RestaurantId("r1"), name="Matriz", timezone="America/Manaus"
    )
    assert antes == depois
