"""Testes da hierarquia de exceções do BC staff (domain/exceptions/errors.py)."""

import pytest

from restaurant_hub.features.staff.domain.exceptions import errors as staff_errors
from restaurant_hub.features.staff.domain.exceptions.errors import (
    EmployeeAlreadyHasLoginError,
    EmptyJobFunctionsError,
    EmptyShiftPreferenceError,
    InvalidDayPeriodError,
    InvalidIdentifierError,
    InvalidNameError,
    InvalidUnavailabilityPeriodError,
    InvalidWeeklyHoursError,
    OverlappingUnavailabilityError,
    StaffError,
    TerminatedEmployeeLoginError,
    UnavailabilityNotFoundError,
)
from restaurant_hub.shared.domain.exceptions.base import DomainError

pytestmark = pytest.mark.unit


def test_staff_error_e_um_domain_error() -> None:
    # Garante que o error handler HTTP (2.4), que captura DomainError,
    # também captura qualquer erro deste bounded context.
    assert issubclass(StaffError, DomainError)


@pytest.mark.parametrize(
    "exc_type",
    [
        InvalidIdentifierError,
        InvalidNameError,
        InvalidDayPeriodError,
        InvalidWeeklyHoursError,
        EmptyShiftPreferenceError,
        EmptyJobFunctionsError,
        InvalidUnavailabilityPeriodError,
        OverlappingUnavailabilityError,
        UnavailabilityNotFoundError,
        EmployeeAlreadyHasLoginError,
        TerminatedEmployeeLoginError,
    ],
)
def test_toda_excecao_do_bc_herda_de_staff_error(exc_type: type[StaffError]) -> None:
    assert issubclass(exc_type, StaffError)


def test_nenhuma_excecao_do_modulo_escapa_de_staff_error() -> None:
    # Guarda *derivada* (não lista fixa): pega exceção nova que herde de
    # DomainError — ou de Exception puro, o engano mais provável — em vez de
    # StaffError, e que portanto escaparia da parametrização acima.
    definidas = [
        obj
        for obj in vars(staff_errors).values()
        if isinstance(obj, type) and issubclass(obj, Exception) and obj is not DomainError
    ]
    assert definidas, "o módulo de erros deve definir ao menos uma exceção"
    for exc_type in definidas:
        assert issubclass(exc_type, StaffError)


def test_identificador_invalido_cita_a_entidade() -> None:
    with pytest.raises(InvalidIdentifierError, match="identificador de funcionário"):
        raise InvalidIdentifierError("funcionário")


def test_nome_invalido_cita_a_entidade() -> None:
    with pytest.raises(InvalidNameError, match="nome de função"):
        raise InvalidNameError("função")


def test_nome_invalido_descreve_o_motivo_quando_ele_nao_e_o_default() -> None:
    """CA16 — o mesmo erro cobre dois defeitos, e a mensagem distingue qual."""
    assert str(InvalidNameError("funcionário")) == "nome de funcionário não pode ser vazio"
    assert (
        str(InvalidNameError("funcionário", reason="não pode conter o byte NUL"))
        == "nome de funcionário não pode conter o byte NUL"
    )


def test_periodo_do_dia_invalido_preserva_o_valor_na_mensagem() -> None:
    """CA19 — espelha `InvalidRoleError` de identity, inclusive no `!r`."""
    with pytest.raises(InvalidDayPeriodError) as excinfo:
        raise InvalidDayPeriodError("xpto")
    assert "período do dia inválido" in str(excinfo.value)
    assert "'xpto'" in str(excinfo.value)


def test_carga_invalida_preserva_o_valor_na_mensagem() -> None:
    with pytest.raises(InvalidWeeklyHoursError) as excinfo:
        raise InvalidWeeklyHoursError("-1")
    mensagem = str(excinfo.value)
    assert "carga semanal contratada inválida" in mensagem
    assert "'-1'" in mensagem


def test_preferencia_vazia_explica_a_invariante() -> None:
    with pytest.raises(EmptyShiftPreferenceError, match="ao menos um período"):
        raise EmptyShiftPreferenceError()


def test_funcoes_vazias_explica_a_invariante() -> None:
    with pytest.raises(EmptyJobFunctionsError, match="ao menos uma função"):
        raise EmptyJobFunctionsError()


def test_periodo_invalido_preserva_o_motivo() -> None:
    with pytest.raises(InvalidUnavailabilityPeriodError, match="início deve anteceder o fim"):
        raise InvalidUnavailabilityPeriodError("início deve anteceder o fim")


def test_sobreposicao_explica_a_invariante() -> None:
    with pytest.raises(OverlappingUnavailabilityError, match="não podem se sobrepor"):
        raise OverlappingUnavailabilityError()


def test_remocao_inexistente_explica_o_erro() -> None:
    with pytest.raises(UnavailabilityNotFoundError, match="não encontrado no registro"):
        raise UnavailabilityNotFoundError()


# ---------------------------------------------------------------------------
# Stage 3.5 — as duas guardas de login do domínio (concept 3.5 §6.1)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("exc_type", [EmployeeAlreadyHasLoginError, TerminatedEmployeeLoginError])
def test_as_guardas_de_login_sao_conflito_e_nao_ausencia(exc_type: type[StaffError]) -> None:
    """Regra do domínio, com uma raiz só (ADR 3.9.0001).

    As duas falam de um registro que **foi** encontrado e cujo estado gravado
    (já vinculado; desligado) recusa a transição — o oposto de ausência.
    """
    assert exc_type.__bases__ == (StaffError,)


def test_ja_vinculado_cita_o_registro() -> None:
    with pytest.raises(EmployeeAlreadyHasLoginError, match="já tem login vinculado: 'e-1'"):
        raise EmployeeAlreadyHasLoginError("e-1")


def test_desligado_cita_o_registro_e_a_regra() -> None:
    with pytest.raises(TerminatedEmployeeLoginError, match="desligado não pode receber login"):
        raise TerminatedEmployeeLoginError("e-1")
