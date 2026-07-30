"""Testes da entidade Employee (domain/entities/employee.py)."""

import dataclasses
from datetime import datetime
from decimal import Decimal

import pytest

from restaurant_hub.features.staff.domain.entities.employee import Employee
from restaurant_hub.features.staff.domain.exceptions.errors import (
    EmptyJobFunctionsError,
    InvalidIdentifierError,
    InvalidNameError,
    OverlappingUnavailabilityError,
    UnavailabilityNotFoundError,
)
from restaurant_hub.features.staff.domain.value_objects.identifiers import (
    EmployeeId,
    JobFunctionId,
    TenantId,
    UnitId,
)
from restaurant_hub.features.staff.domain.value_objects.shift_preference import (
    DayPeriod,
    ShiftPreference,
)
from restaurant_hub.features.staff.domain.value_objects.unavailability_period import (
    UnavailabilityPeriod,
)
from restaurant_hub.features.staff.domain.value_objects.workload_profile import (
    FixedSchedule,
    OnDemand,
)

pytestmark = pytest.mark.unit

_FIXA = FixedSchedule(weekly_hours=Decimal("44"))
_PREFERENCIA = ShiftPreference(periods=frozenset({DayPeriod.NIGHT}))


def _periodo(start_hour: int, end_hour: int) -> UnavailabilityPeriod:
    return UnavailabilityPeriod(
        start=datetime(2026, 8, 3, start_hour, 0),
        end=datetime(2026, 8, 3, end_hour, 0),
    )


_BASE = Employee(
    id=EmployeeId("e1"),
    tenant_id=TenantId("t1"),
    unit_id=UnitId("u1"),
    name="Maria",
    workload_profile=_FIXA,
    shift_preference=None,
    job_function_ids=frozenset({JobFunctionId("f1")}),
)


def _funcionario(**overrides: object) -> Employee:
    # dataclasses.replace chama o construtor real: cada override passa pelo
    # __post_init__ como uma construção direta passaria.
    return dataclasses.replace(_BASE, **overrides)


# --- construção válida -------------------------------------------------------


def test_cria_funcionario_valido_com_jornada_fixa() -> None:
    funcionario = _funcionario(workload_profile=_FIXA)
    assert funcionario.workload_profile == _FIXA
    assert funcionario.shift_preference is None
    assert funcionario.unavailabilities == ()


def test_cria_funcionario_valido_sob_demanda() -> None:
    funcionario = _funcionario(workload_profile=OnDemand())
    assert funcionario.workload_profile == OnDemand()


def test_jornada_fixa_pode_declarar_preferencia() -> None:
    # ADR 3.1.0004: preferência vale para ambos os perfis.
    funcionario = _funcionario(workload_profile=_FIXA, shift_preference=_PREFERENCIA)
    assert funcionario.shift_preference == _PREFERENCIA


def test_sob_demanda_pode_declarar_preferencia() -> None:
    funcionario = _funcionario(workload_profile=OnDemand(), shift_preference=_PREFERENCIA)
    assert funcionario.shift_preference == _PREFERENCIA


# --- identificadores e nome --------------------------------------------------


@pytest.mark.parametrize("invalido", ["", "   "])
def test_id_vazio_e_rejeitado(invalido: str) -> None:
    with pytest.raises(InvalidIdentifierError, match="identificador de funcionário"):
        _funcionario(id=invalido)


@pytest.mark.parametrize("invalido", ["", "   "])
def test_tenant_vazio_e_rejeitado(invalido: str) -> None:
    with pytest.raises(InvalidIdentifierError, match="identificador de tenant do funcionário"):
        _funcionario(tenant_id=invalido)


@pytest.mark.parametrize("invalido", ["", "   "])
def test_unidade_vazia_e_rejeitada(invalido: str) -> None:
    with pytest.raises(InvalidIdentifierError, match="identificador de unidade do funcionário"):
        _funcionario(unit_id=invalido)


@pytest.mark.parametrize("invalido", ["", "   "])
def test_nome_vazio_e_rejeitado_na_construcao(invalido: str) -> None:
    with pytest.raises(InvalidNameError, match="nome de funcionário"):
        _funcionario(name=invalido)


@pytest.mark.parametrize("invalido", ["", "   "])
def test_nome_vazio_e_rejeitado_no_rename(invalido: str) -> None:
    with pytest.raises(InvalidNameError, match="nome de funcionário"):
        _funcionario().rename(invalido)


def test_nome_e_preservado_verbatim_na_construcao() -> None:
    # ADR 3.1.0002: sem trim/case silenciosos.
    assert _funcionario(name="  Cozinheiro ").name == "  Cozinheiro "


def test_nome_e_preservado_verbatim_no_rename() -> None:
    renomeado = _funcionario().rename("  João ")
    assert renomeado.name == "  João "


# --- conjunto de funções (ADR 3.1.0006) --------------------------------------


def test_conjunto_de_funcoes_vazio_e_rejeitado_na_construcao() -> None:
    with pytest.raises(EmptyJobFunctionsError, match="ao menos uma função"):
        _funcionario(job_function_ids=frozenset())


def test_conjunto_de_funcoes_vazio_e_rejeitado_no_assign() -> None:
    with pytest.raises(EmptyJobFunctionsError, match="ao menos uma função"):
        _funcionario().assign_job_functions(frozenset())


def test_uma_funcao_e_aceita() -> None:
    funcionario = _funcionario(job_function_ids=frozenset({JobFunctionId("f1")}))
    assert funcionario.job_function_ids == frozenset({JobFunctionId("f1")})


def test_varias_funcoes_sao_aceitas() -> None:
    varias = frozenset({JobFunctionId("f1"), JobFunctionId("f2"), JobFunctionId("f3")})
    assert _funcionario(job_function_ids=varias).job_function_ids == varias


def test_assign_substitui_o_conjunto_devolvendo_nova_instancia() -> None:
    original = _funcionario()
    novas = frozenset({JobFunctionId("f2"), JobFunctionId("f3")})
    atualizado = original.assign_job_functions(novas)
    assert atualizado.job_function_ids == novas
    assert original.job_function_ids == frozenset({JobFunctionId("f1")})  # original imutado


# --- indisponibilidades ------------------------------------------------------


def test_construcao_com_colecao_inicial_sobreposta_e_rejeitada() -> None:
    # Caminho de reidratação (mapper da 3.3): estado sobreposto é irrepresentável.
    with pytest.raises(OverlappingUnavailabilityError):
        _funcionario(unavailabilities=(_periodo(8, 12), _periodo(10, 14)))


def test_construcao_com_periodos_adjacentes_e_aceita() -> None:
    # Semântica semi-aberta [start, end): fim == início não conflita.
    funcionario = _funcionario(unavailabilities=(_periodo(8, 12), _periodo(12, 14)))
    assert funcionario.unavailabilities == (_periodo(8, 12), _periodo(12, 14))


def test_add_rejeita_sobreposicao_parcial() -> None:
    funcionario = _funcionario(unavailabilities=(_periodo(8, 12),))
    with pytest.raises(OverlappingUnavailabilityError):
        funcionario.add_unavailability(_periodo(10, 14))


def test_add_rejeita_continencia_total() -> None:
    funcionario = _funcionario(unavailabilities=(_periodo(8, 16),))
    with pytest.raises(OverlappingUnavailabilityError):
        funcionario.add_unavailability(_periodo(10, 12))


def test_add_aceita_adjacente_devolvendo_nova_instancia() -> None:
    original = _funcionario(unavailabilities=(_periodo(8, 12),))
    atualizado = original.add_unavailability(_periodo(12, 14))
    assert atualizado.unavailabilities == (_periodo(8, 12), _periodo(12, 14))
    assert original.unavailabilities == (_periodo(8, 12),)  # original imutado


def test_remove_por_valor_devolvendo_nova_instancia() -> None:
    original = _funcionario(unavailabilities=(_periodo(8, 12), _periodo(14, 16)))
    atualizado = original.remove_unavailability(_periodo(8, 12))
    assert atualizado.unavailabilities == (_periodo(14, 16),)
    assert original.unavailabilities == (_periodo(8, 12), _periodo(14, 16))  # original imutado


def test_remove_de_periodo_inexistente_e_erro() -> None:
    with pytest.raises(UnavailabilityNotFoundError, match="não encontrado"):
        _funcionario(unavailabilities=(_periodo(8, 12),)).remove_unavailability(_periodo(14, 16))


# --- preferência e perfil ----------------------------------------------------


def test_declara_preferencia_quando_nao_havia() -> None:
    original = _funcionario(shift_preference=None)
    atualizado = original.declare_shift_preference(_PREFERENCIA)
    assert atualizado.shift_preference == _PREFERENCIA
    assert original.shift_preference is None  # original imutado


def test_substitui_preferencia_existente_por_outra() -> None:
    outra = ShiftPreference(periods=frozenset({DayPeriod.MORNING, DayPeriod.AFTERNOON}))
    atualizado = _funcionario(shift_preference=_PREFERENCIA).declare_shift_preference(outra)
    assert atualizado.shift_preference == outra


def test_declarar_none_limpa_a_preferencia() -> None:
    atualizado = _funcionario(shift_preference=_PREFERENCIA).declare_shift_preference(None)
    assert atualizado.shift_preference is None


def test_troca_perfil_de_fixa_para_sob_demanda_e_volta() -> None:
    fixa = _funcionario(workload_profile=_FIXA)
    sob_demanda = fixa.change_workload_profile(OnDemand())
    assert sob_demanda.workload_profile == OnDemand()
    assert fixa.workload_profile == _FIXA  # original imutado
    de_volta = sob_demanda.change_workload_profile(FixedSchedule(weekly_hours=Decimal("20.5")))
    assert de_volta.workload_profile == FixedSchedule(weekly_hours=Decimal("20.5"))


# --- identidade e imutabilidade ----------------------------------------------


def test_entidade_e_imutavel() -> None:
    with pytest.raises(dataclasses.FrozenInstanceError):
        _funcionario().name = "Outro"  # type: ignore[misc]


def test_igualdade_por_identidade_ignora_demais_campos() -> None:
    assert _funcionario(name="Maria") == _funcionario(name="Joana")


def test_ids_diferentes_nao_sao_iguais() -> None:
    assert _funcionario(id="e1") != _funcionario(id="e2")


def test_hash_segue_a_identidade() -> None:
    assert len({_funcionario(name="Maria"), _funcionario(name="Joana")}) == 1


def test_comparacao_com_outro_tipo_nao_e_igual() -> None:
    assert _funcionario() != "e1"


class _SempreIgual:
    """Objeto que se declara igual a qualquer coisa, para testar a reflexão."""

    def __eq__(self, other: object) -> bool:
        return True

    def __hash__(self) -> int:
        return 0


def test_eq_delega_ao_outro_operando_quando_o_tipo_e_estranho() -> None:
    # __eq__ devolve NotImplemented para tipo alheio: o outro operando decide.
    assert _funcionario() == _SempreIgual()
    assert _SempreIgual() == _funcionario()
