"""Testes da hierarquia de erros da camada de aplicação (concept CA13).

A invariante que estes testes protegem é de **segurança operacional**, não de
estética: se um erro desta camada escapar de `DomainError`, ele vira HTTP 500 na
Stage 2.4 em vez de um 4xx (ADR 2.2.0003). O teste percorre o módulo inteiro por
introspecção, então uma classe nova que esqueça a base certa quebra a suíte —
em vez de falhar em silêncio meses depois, na API.
"""

import inspect

import pytest

from restaurant_hub.features.identity.application import errors
from restaurant_hub.features.identity.domain.exceptions.errors import IdentityError
from restaurant_hub.shared.domain.exceptions.base import DomainError, NotFoundError

# Erros que representam "recurso inexistente" e, por isso, devem alcançar o
# handler 404 antes do 422.
_NOT_FOUND_ERRORS = (
    errors.RestaurantNotFoundError,
    errors.UnitNotFoundError,
    errors.UserNotFoundError,
)


def _application_error_classes() -> list[type[Exception]]:
    """Todas as classes de exceção declaradas em `application/errors.py`."""
    return [
        obj
        for _, obj in inspect.getmembers(errors, inspect.isclass)
        if issubclass(obj, BaseException) and obj.__module__ == errors.__name__
    ]


def test_modulo_declara_as_dez_excecoes_esperadas() -> None:
    """Guarda a lista: classe nova ou removida força revisão consciente do teste."""
    nomes = {cls.__name__ for cls in _application_error_classes()}
    assert nomes == {
        "EmailAlreadyRegisteredError",
        "InvalidCredentialsError",
        "PermissionDeniedError",
        "TenantScopeRequiredError",
        "TenantNotVisibleError",
        "UnitScopeRequiredError",
        "UnitNotVisibleError",
        "RestaurantNotFoundError",
        "UnitNotFoundError",
        "UserNotFoundError",
    }


@pytest.mark.parametrize("error_class", _application_error_classes())
def test_todo_erro_de_aplicacao_e_identity_error_e_domain_error(
    error_class: type[Exception],
) -> None:
    """Nenhum erro de negócio desta camada pode escapar para 500 na 2.4."""
    assert issubclass(error_class, IdentityError)
    assert issubclass(error_class, DomainError)


@pytest.mark.parametrize("error_class", _NOT_FOUND_ERRORS)
def test_erros_de_nao_encontrado_alcancam_o_handler_404_antes_do_422(
    error_class: type[Exception],
) -> None:
    """A ORDEM na MRO é o que decide o status HTTP.

    O Starlette resolve o handler percorrendo `type(exc).__mro__` e parando na
    primeira classe registrada. Como `NotFoundError` (404) e `DomainError` (422)
    estão ambos registrados, `NotFoundError` precisa vir antes — caso contrário
    um recurso inexistente responderia 422.
    """
    assert issubclass(error_class, NotFoundError)
    mro = error_class.__mro__
    assert mro.index(NotFoundError) < mro.index(DomainError)


def test_mensagens_identificam_o_recurso_ou_a_regra_violada() -> None:
    """Cada erro instanciado produz mensagem útil (executa o `__init__`)."""
    assert "rest-1" in str(errors.RestaurantNotFoundError("rest-1"))
    assert "unit-1" in str(errors.UnitNotFoundError("unit-1"))
    assert "user-1" in str(errors.UserNotFoundError("user-1"))
    assert "dono@x.com" in str(errors.EmailAlreadyRegisteredError("dono@x.com"))

    permission_denied = str(errors.PermissionDeniedError("employee", "manage_users"))
    assert "employee" in permission_denied
    assert "manage_users" in permission_denied

    assert "manager" in str(errors.TenantScopeRequiredError("manager"))
    assert "manager" in str(errors.UnitScopeRequiredError("manager"))

    tenant_not_visible = str(errors.TenantNotVisibleError("rest-a", "rest-b"))
    assert "rest-a" in tenant_not_visible
    assert "rest-b" in tenant_not_visible

    unit_not_visible = str(errors.UnitNotVisibleError("user-1", "unit-9"))
    assert "user-1" in unit_not_visible
    assert "unit-9" in unit_not_visible


def test_credencial_invalida_nao_revela_qual_lado_falhou() -> None:
    """E-mail inexistente e senha errada precisam ser indistinguíveis.

    A mensagem não pode citar e-mail, senha nem "usuário": qualquer uma dessas
    pistas transforma a resposta num oráculo de enumeração de contas
    (concept §5.14).
    """
    mensagem = str(errors.InvalidCredentialsError()).lower()
    assert mensagem == "credenciais inválidas"
    for pista in ("e-mail", "email", "senha", "usuário", "password"):
        assert pista not in mensagem
