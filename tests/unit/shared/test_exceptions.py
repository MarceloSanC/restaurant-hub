"""Testes da hierarquia base de exceções (shared/domain/exceptions/base.py)."""

import pytest

from restaurant_hub.shared.domain.exceptions import base
from restaurant_hub.shared.domain.exceptions.base import DomainError, NotFoundError

pytestmark = pytest.mark.unit


def test_not_found_e_erro_de_dominio() -> None:
    assert issubclass(NotFoundError, DomainError)


def test_a_hierarquia_tem_exatamente_duas_classes() -> None:
    """`ApplicationError` saiu na #45, e a contagem é o que impede o retorno.

    Ela viveu seis Stages sem subclasse e sem `raise`, fora da hierarquia de
    `DomainError` — logo, sem handler: levantá-la produziria 500. Uma terceira
    classe base aqui é decisão de arquitetura, não conveniência de quem precisa
    de um erro novo; esta asserção obriga a discussão a acontecer.
    """
    do_modulo = {
        nome
        for nome, valor in vars(base).items()
        if isinstance(valor, type)
        and issubclass(valor, Exception)
        and valor.__module__ == base.__name__
    }

    assert do_modulo == {"DomainError", "NotFoundError"}


def test_domain_error_e_exception() -> None:
    assert issubclass(DomainError, Exception)


def test_mensagem_preservada_ao_levantar() -> None:
    with pytest.raises(NotFoundError, match="pedido 42 nao encontrado"):
        raise NotFoundError("pedido 42 nao encontrado")
