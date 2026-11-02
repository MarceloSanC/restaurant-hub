"""Testes da raiz de aplicação (shared/application/errors.py, ADR 3.9.0001)."""

import pytest

from restaurant_hub.shared.application.errors import ApplicationError
from restaurant_hub.shared.domain.exceptions.base import DomainError

pytestmark = pytest.mark.unit


def test_application_error_e_exception() -> None:
    assert issubclass(ApplicationError, Exception)


def test_application_error_nao_e_erro_de_dominio() -> None:
    """As duas raízes são disjuntas — é o que distingue, pelo tipo, as duas falhas.

    Se `ApplicationError` herdasse de `DomainError`, uma credencial inválida voltaria
    a ser "violação de regra de negócio" — exatamente o que a Stage 3.9 desfaz — e
    a rede genérica de `DomainError` responderia por ela em silêncio.
    """
    assert not issubclass(ApplicationError, DomainError)
    assert not issubclass(DomainError, ApplicationError)


def test_mensagem_preservada_ao_levantar() -> None:
    with pytest.raises(ApplicationError, match="recurso 42 inexistente"):
        raise ApplicationError("recurso 42 inexistente")
