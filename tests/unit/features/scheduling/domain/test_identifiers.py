"""Testes dos identificadores tipados do BC scheduling (value_objects/identifiers.py).

Ponto de partida da varredura de CA22: aqui se afirma que os **8** nomes existem
no módulo e que são `NewType` sobre `str`; a recusa de vazio/só-whitespace é
imposta nas entidades (Tasks 05 a 08), que é onde CA22 fecha.

**As asserções são laços sobre a tupla, não `parametrize`.** Um `NewType` não tem
tipo estático nomeável que sirva de anotação de parâmetro, e `Any` num parâmetro é
proibido pelo ruff (ANN401) neste repositório; a tupla anotada no escopo do módulo
mantém a varredura derivada sem abrir a exceção de lint. É também a forma do
precedente (`tests/unit/features/staff/domain/test_identifiers.py`).
"""

from typing import Any

import pytest

from restaurant_hub.features.scheduling.domain.value_objects import identifiers
from restaurant_hub.features.scheduling.domain.value_objects.identifiers import (
    AssignmentId,
    EmployeeId,
    JobFunctionId,
    ScheduleId,
    ShiftBandId,
    ShiftDemandId,
    TenantId,
    UnitId,
)

pytestmark = pytest.mark.unit

_TOTAL_DE_IDENTIFICADORES = 8

# Os 8 identificadores próprios do BC (concept §4, §7). A lista é **explícita** e
# `test_o_modulo_define_exatamente_os_oito_identificadores` a cobra contra
# `vars(identifiers)` — o par de `tests/unit/test_status_map.py`: derivada sozinha
# ela concordaria com um módulo vazio; escrita à mão, ela envelhece.
_IDENTIFICADORES: tuple[Any, ...] = (
    ScheduleId,
    ShiftBandId,
    ShiftDemandId,
    AssignmentId,
    TenantId,
    UnitId,
    EmployeeId,
    JobFunctionId,
)


def test_ids_devolvem_o_proprio_valor() -> None:
    # NewType é identidade só em tempo de type-check; em runtime devolve o argumento.
    for tipo in _IDENTIFICADORES:
        assert tipo("x1") == "x1", tipo


def test_nomes_dos_newtypes_batem_com_os_identificadores() -> None:
    # Um typo no argumento do NewType (ex.: "ScheduleID") não quebra nada em
    # runtime, mas degrada silenciosamente toda mensagem futura do mypy. A
    # asserção compara o nome declarado com o nome ligado no módulo.
    for tipo in _IDENTIFICADORES:
        assert getattr(identifiers, tipo.__name__, None) is tipo, tipo.__name__


def test_o_modulo_define_exatamente_os_oito_identificadores() -> None:
    """Varredura derivada: o módulo não tem identificador fora da lista de CA22.

    Sem ela, um nono `NewType` — ou um identificador **importado** de outro BC,
    que é a violação que `test_bc_independence.py` mede do outro lado — entraria
    sem asserção nenhuma, e os dois laços acima seguiriam verdes.
    """
    no_modulo = {
        nome
        for nome, valor in vars(identifiers).items()
        if not nome.startswith("_") and getattr(valor, "__supertype__", None) is str
    }

    assert no_modulo == {tipo.__name__ for tipo in _IDENTIFICADORES}
    assert len(_IDENTIFICADORES) == _TOTAL_DE_IDENTIFICADORES


def test_os_identificadores_sao_newtypes_sobre_str() -> None:
    """`NewType` sobre `str`, não alias nem subclasse.

    `ScheduleId = str` passaria na asserção de passthrough acima — o valor
    voltaria igual —, e apagaria toda a distinção de tipo que é a razão do
    módulo: o mypy deixaria de reclamar de um `ShiftDemandId` passado onde se
    espera um `AssignmentId`.
    """
    for tipo in _IDENTIFICADORES:
        assert tipo.__supertype__ is str, tipo.__name__
