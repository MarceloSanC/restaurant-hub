"""Testes do value object Pagination (shared/domain/value_objects/pagination.py)."""

import dataclasses

import pytest

from restaurant_hub.shared.domain.value_objects.pagination import MAX_PAGE_SIZE, Pagination

pytestmark = pytest.mark.unit

DEFAULT_PAGE_SIZE = 20
CUSTOM_PAGE_SIZE = 37


def test_valores_default() -> None:
    pagination = Pagination()
    assert pagination.page == 1
    assert pagination.page_size == DEFAULT_PAGE_SIZE


def test_offset_da_primeira_pagina_e_zero() -> None:
    assert Pagination(page=1, page_size=DEFAULT_PAGE_SIZE).offset == 0


def test_offset_calcula_deslocamento_sql() -> None:
    page = 3
    expected_offset = (page - 1) * DEFAULT_PAGE_SIZE
    assert Pagination(page=page, page_size=DEFAULT_PAGE_SIZE).offset == expected_offset


def test_limit_e_alias_de_page_size() -> None:
    pagination = Pagination(page=2, page_size=CUSTOM_PAGE_SIZE)
    assert pagination.limit == CUSTOM_PAGE_SIZE
    assert pagination.limit == pagination.page_size


def test_page_zero_rejeitada() -> None:
    with pytest.raises(ValueError, match="page deve ser >= 1"):
        Pagination(page=0)


def test_page_negativa_rejeitada() -> None:
    with pytest.raises(ValueError, match="page deve ser >= 1"):
        Pagination(page=-5)


def test_page_size_zero_rejeitado() -> None:
    with pytest.raises(ValueError, match="page_size deve estar entre 1 e"):
        Pagination(page_size=0)


def test_page_size_acima_do_maximo_rejeitado() -> None:
    with pytest.raises(ValueError, match="page_size deve estar entre 1 e"):
        Pagination(page_size=MAX_PAGE_SIZE + 1)


def test_limites_validos_aceitos() -> None:
    assert Pagination(page=1, page_size=1).offset == 0
    assert Pagination(page=1, page_size=MAX_PAGE_SIZE).limit == MAX_PAGE_SIZE


def test_value_object_e_congelado() -> None:
    pagination = Pagination()
    with pytest.raises(dataclasses.FrozenInstanceError):
        pagination.page = 2  # type: ignore[misc]
