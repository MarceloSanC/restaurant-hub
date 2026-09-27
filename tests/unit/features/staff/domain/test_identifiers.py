"""Testes dos identificadores tipados do BC staff (value_objects/identifiers.py)."""

import pytest

from restaurant_hub.features.staff.domain.value_objects.identifiers import (
    EmployeeId,
    JobFunctionId,
    TenantId,
    UnitId,
    UserId,
)

pytestmark = pytest.mark.unit


def test_ids_devolvem_o_proprio_valor() -> None:
    # NewType é identidade só em tempo de type-check; em runtime devolve o argumento.
    assert EmployeeId("e1") == "e1"
    assert JobFunctionId("f1") == "f1"
    assert TenantId("t1") == "t1"
    assert UnitId("u1") == "u1"
    assert UserId("login-1") == "login-1"


def test_nomes_dos_newtypes_batem_com_os_identificadores() -> None:
    # Um typo no argumento do NewType (ex.: "EmployeeID") não quebra nada em
    # runtime, mas degrada silenciosamente toda mensagem futura do mypy.
    assert EmployeeId.__name__ == "EmployeeId"
    assert JobFunctionId.__name__ == "JobFunctionId"
    assert TenantId.__name__ == "TenantId"
    assert UnitId.__name__ == "UnitId"
    assert UserId.__name__ == "UserId"
