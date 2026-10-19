"""Testes da política de função não detida — CA3, CA4, CA7, CA11, CA16."""

from datetime import timedelta
from decimal import Decimal

import pytest

from restaurant_hub.features.scheduling.domain.services.validation import (
    function_mismatch_policy,
)
from restaurant_hub.features.scheduling.domain.value_objects.identifiers import (
    AssignmentId,
    EmployeeId,
)
from restaurant_hub.features.scheduling.domain.value_objects.validation_config import (
    EnforcementMode,
    PolicyKind,
    PolicyRule,
)
from restaurant_hub.features.scheduling.domain.value_objects.violation import Violation
from tests.unit.features.scheduling.domain.services.validation.scenario import (
    ATENDENTE,
    COZINHEIRO,
    SEGUNDA,
    Turno,
    config,
    contexto,
    em,
    escala,
    fatos,
)

pytestmark = pytest.mark.unit

_POLITICA = function_mismatch_policy.FunctionMismatchPolicy()


def test_kind() -> None:
    assert _POLITICA.kind is PolicyKind.FUNCTION_MISMATCH


def test_funcao_nao_detida_viola_por_alocacao() -> None:
    avaliada = escala([Turno("ana", em(0, 8), em(0, 16), function=ATENDENTE)])

    (violacao,) = _POLITICA.evaluate(contexto(avaliada, fatos("ana")), config())

    assert violacao == Violation(
        policy=PolicyKind.FUNCTION_MISMATCH,
        mode=EnforcementMode.WARN,
        employee_id=EmployeeId("ana"),
        demand_id=None,
        operational_days=(SEGUNDA,),
        assignment_ids=frozenset({AssignmentId("s-a0")}),
        observed=Decimal(1),
        limit=Decimal(0),
    )
    assert violacao.key.assignment_ids == {AssignmentId("s-a0")}


def test_funcao_detida_entre_varias_nao_viola() -> None:
    avaliada = escala([Turno("ana", em(0, 8), em(0, 16), function=ATENDENTE)])
    multifuncao = fatos("ana", funcoes=(COZINHEIRO, ATENDENTE))

    assert _POLITICA.evaluate(contexto(avaliada, multifuncao), config()) == ()


def test_ana_aceita_como_excecao_que_ganha_a_funcao_deixa_de_violar() -> None:
    avaliada = escala(
        [Turno("ana", em(0, 8), em(0, 16), function=ATENDENTE, function_exception=True)]
    )

    antes = _POLITICA.evaluate(contexto(avaliada, fatos("ana", funcoes=(COZINHEIRO,))), config())
    depois = _POLITICA.evaluate(
        contexto(avaliada, fatos("ana", funcoes=(COZINHEIRO, ATENDENTE))), config()
    )

    assert len(antes) == 1
    assert depois == ()


def test_bruno_alocado_normalmente_que_perde_a_funcao_passa_a_violar() -> None:
    avaliada = escala([Turno("bruno", em(0, 8), em(0, 16), function=COZINHEIRO)])

    antes = _POLITICA.evaluate(contexto(avaliada, fatos("bruno", funcoes=(COZINHEIRO,))), config())
    (depois,) = _POLITICA.evaluate(
        contexto(avaliada, fatos("bruno", funcoes=(ATENDENTE,))), config()
    )

    assert antes == ()
    assert depois.employee_id == "bruno"


def test_a_marca_de_excecao_nao_e_lida() -> None:
    marcada = escala(
        [Turno("ana", em(0, 8), em(0, 16), function=ATENDENTE, function_exception=True)]
    )
    comum = escala([Turno("ana", em(0, 8), em(0, 16), function=ATENDENTE)])

    assert _POLITICA.evaluate(contexto(marcada), config()) == _POLITICA.evaluate(
        contexto(comum), config()
    )


def test_ignora_a_vizinha_e_o_inativo() -> None:
    anterior_dia = SEGUNDA - timedelta(days=7)
    anterior = escala(
        [
            Turno(
                "ana", em(0, 8, base=anterior_dia), em(0, 16, base=anterior_dia), function=ATENDENTE
            )
        ],
        schedule_id="p",
        first_day=anterior_dia,
    )
    inativo = escala([Turno("bruno", em(0, 8), em(0, 16), function=ATENDENTE)])

    assert _POLITICA.evaluate(contexto(escala([]), previous=anterior), config()) == ()
    assert _POLITICA.evaluate(contexto(inativo, fatos("bruno", ativo=False)), config()) == ()


def test_o_modo_vem_da_config() -> None:
    avaliada = escala([Turno("ana", em(0, 8), em(0, 16), function=ATENDENTE)])
    bloqueio = config(function_mismatch=PolicyRule(enabled=True, mode=EnforcementMode.BLOCK))

    (violacao,) = _POLITICA.evaluate(contexto(avaliada), bloqueio)

    assert violacao.mode is EnforcementMode.BLOCK
