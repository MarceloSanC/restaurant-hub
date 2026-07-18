"""Testes da hierarquia de exceções do BC identity (domain/exceptions/errors.py)."""

import pytest

from restaurant_hub.features.identity.domain.exceptions.errors import (
    CrossTenantError,
    IdentityError,
    InvalidEmailError,
    InvalidRoleError,
    MissingTenantError,
    PlatformAdminMembershipError,
    PlatformAdminTenantError,
)
from restaurant_hub.shared.domain.exceptions.base import DomainError

pytestmark = pytest.mark.unit


def test_identity_error_e_um_domain_error() -> None:
    # Garante que o error handler HTTP (2.4), que captura DomainError,
    # também captura qualquer erro deste bounded context.
    assert issubclass(IdentityError, DomainError)


@pytest.mark.parametrize(
    "exc_type",
    [
        InvalidEmailError,
        InvalidRoleError,
        MissingTenantError,
        PlatformAdminTenantError,
        PlatformAdminMembershipError,
        CrossTenantError,
    ],
)
def test_toda_excecao_do_bc_herda_de_identity_error(exc_type: type[IdentityError]) -> None:
    assert issubclass(exc_type, IdentityError)


def test_email_invalido_preserva_o_valor_na_mensagem() -> None:
    with pytest.raises(InvalidEmailError, match="e-mail inválido"):
        raise InvalidEmailError("sem-arroba")


def test_papel_invalido_preserva_o_valor_na_mensagem() -> None:
    with pytest.raises(InvalidRoleError, match="chef"):
        raise InvalidRoleError("chef")


def test_missing_tenant_cita_o_papel() -> None:
    with pytest.raises(MissingTenantError, match="employee"):
        raise MissingTenantError("employee")


def test_platform_admin_tenant_error_explica_a_invariante() -> None:
    with pytest.raises(PlatformAdminTenantError, match="platform_admin"):
        raise PlatformAdminTenantError()


def test_platform_admin_membership_error_explica_a_invariante() -> None:
    with pytest.raises(PlatformAdminMembershipError, match="unidade"):
        raise PlatformAdminMembershipError()


def test_cross_tenant_error_cita_os_dois_tenants() -> None:
    with pytest.raises(CrossTenantError, match="isolamento de tenant"):
        raise CrossTenantError("r1", "r2")
