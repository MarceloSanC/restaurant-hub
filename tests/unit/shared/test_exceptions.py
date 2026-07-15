"""Testes da hierarquia base de exceções (shared/domain/exceptions/base.py)."""

import pytest

from restaurant_hub.shared.domain.exceptions.base import (
    ApplicationError,
    DomainError,
    NotFoundError,
)

pytestmark = pytest.mark.unit


def test_not_found_e_erro_de_dominio() -> None:
    assert issubclass(NotFoundError, DomainError)


def test_application_error_nao_e_erro_de_dominio() -> None:
    # ApplicationError é orquestração, não violação de regra de negócio —
    # o error handler HTTP trata as duas hierarquias de forma distinta.
    assert not issubclass(ApplicationError, DomainError)
    assert issubclass(ApplicationError, Exception)


def test_domain_error_e_exception() -> None:
    assert issubclass(DomainError, Exception)


def test_mensagem_preservada_ao_levantar() -> None:
    with pytest.raises(NotFoundError, match="pedido 42 nao encontrado"):
        raise NotFoundError("pedido 42 nao encontrado")
