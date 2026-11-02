"""Testes da hierarquia base de exceções (shared/domain/exceptions/base.py)."""

import inspect

import pytest

from restaurant_hub.shared.domain.exceptions import base
from restaurant_hub.shared.domain.exceptions.base import DomainError

pytestmark = pytest.mark.unit


def test_o_modulo_tem_exatamente_uma_classe() -> None:
    """Uma raiz por significado, e a de domínio é a única que mora aqui.

    `ApplicationError` saiu daqui na #45 e voltou na Stage 3.9 em
    `shared/application` (ADR 3.9.0001); `NotFoundError` saiu na mesma Stage, sem
    subclasse. Uma segunda classe base aqui é decisão de arquitetura, não
    conveniência de quem precisa de um erro novo; esta asserção obriga a discussão a
    acontecer.
    """
    do_modulo = {
        nome
        for nome, valor in vars(base).items()
        if isinstance(valor, type)
        and issubclass(valor, Exception)
        and valor.__module__ == base.__name__
    }

    assert do_modulo == {"DomainError"}


def test_domain_error_e_exception() -> None:
    assert issubclass(DomainError, Exception)


def test_mensagem_preservada_ao_levantar() -> None:
    with pytest.raises(DomainError, match="regra 42 violada"):
        raise DomainError("regra 42 violada")


def test_a_raiz_de_dominio_nao_fala_de_status() -> None:
    """Concept 3.9 CA5: o módulo da raiz não define as classes pelo que viram na borda.

    A regra 11 do `check_layout.py` deixa "status" fora do vocabulário porque o domínio
    a usa legitimamente (status de escala); aqui, no módulo-raiz, a palavra não tem uso
    — era a forma como a docstring definia `NotFoundError` antes da Stage 3.9.
    """
    assert "status" not in inspect.getsource(base).lower()
