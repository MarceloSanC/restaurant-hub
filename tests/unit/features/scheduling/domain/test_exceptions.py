"""Testes da hierarquia de exceções do BC scheduling (domain/exceptions/errors.py).

**CA17 (4.1) e CA14 (4.2) são uma totalidade, não um representante.** O mapa de
erros do concept 4.1 §6 tem 21 linhas para 20 exceções, e a Stage 4.1 nasceu com as
20 completas para que nenhuma Task posterior tivesse de crescer esta varredura; a
Stage 4.2 acrescentou as 2 da validação (concept 4.2 §6) na sua Task 01. Por isso
há **três** asserções sobre o conjunto, e não uma: a parametrizada (cada uma das 22
herda da raiz), a derivada de `vars` (nenhuma exceção do módulo escapa da raiz) e a
de igualdade (o módulo define **exatamente** as 22 + a raiz). A terceira é a que
pega a exceção criada aqui e esquecida no concept §6 — o inverso do que as duas
primeiras pegam.
"""

import pytest

from restaurant_hub.features.scheduling.domain.exceptions import errors as scheduling_errors
from restaurant_hub.features.scheduling.domain.exceptions.errors import (
    AssignmentNotFoundError,
    DuplicateAssignmentError,
    DuplicateAssignmentInBandError,
    DuplicateEntityIdError,
    DuplicateShiftBandError,
    DuplicateShiftDemandError,
    InvalidAssignmentBreakError,
    InvalidDayCutoffError,
    InvalidDemandQuantityError,
    InvalidEvaluationInputError,
    InvalidIdentifierError,
    InvalidSchedulePeriodError,
    InvalidScheduleVersionError,
    InvalidTimeRangeError,
    InvalidValidationConfigError,
    InvalidWeekdayError,
    SchedulingError,
    ShiftBandDayChangeError,
    ShiftBandInUseError,
    ShiftBandNotFoundError,
    ShiftDemandInUseError,
    ShiftDemandNotFoundError,
    TimeRangeOutsidePeriodError,
)
from restaurant_hub.shared.domain.exceptions.base import DomainError

pytestmark = pytest.mark.unit

_TOTAL_DE_EXCECOES = 22

# As 20 subclasses declaradas no concept 4.1 §4, na ordem em que ele as lista,
# seguidas das 2 do concept 4.2 §4.
_AS_DO_BC: tuple[type[SchedulingError], ...] = (
    InvalidIdentifierError,
    InvalidTimeRangeError,
    InvalidWeekdayError,
    InvalidDayCutoffError,
    InvalidSchedulePeriodError,
    InvalidDemandQuantityError,
    InvalidScheduleVersionError,
    InvalidAssignmentBreakError,
    DuplicateEntityIdError,
    DuplicateShiftBandError,
    ShiftBandNotFoundError,
    ShiftBandInUseError,
    ShiftBandDayChangeError,
    TimeRangeOutsidePeriodError,
    DuplicateShiftDemandError,
    ShiftDemandNotFoundError,
    ShiftDemandInUseError,
    DuplicateAssignmentError,
    DuplicateAssignmentInBandError,
    AssignmentNotFoundError,
    InvalidValidationConfigError,
    InvalidEvaluationInputError,
)

# As que recebem valor de contexto, com o argumento e o trecho que a mensagem
# tem de preservar. A tabela é pareada com o construtor: uma exceção que passe a
# receber contexto e não entre aqui cai na asserção de exaustividade abaixo.
_COM_CONTEXTO: tuple[tuple[type[SchedulingError], object, str], ...] = (
    (InvalidIdentifierError, "escala", "identificador de escala"),
    (InvalidTimeRangeError, "início deve anteceder o fim", "início deve anteceder o fim"),
    (InvalidWeekdayError, "xpto", "'xpto'"),
    (InvalidDayCutoffError, "não pode ser tz-aware", "não pode ser tz-aware"),
    (InvalidSchedulePeriodError, "desalinhado", "desalinhado"),
    (InvalidDemandQuantityError, -1, "-1"),
    (InvalidScheduleVersionError, 0, "0"),
    (InvalidAssignmentBreakError, "não pode ser negativo", "não pode ser negativo"),
    (DuplicateEntityIdError, "ShiftDemandId", "ShiftDemandId"),
    (InvalidValidationConfigError, "min_rest_minutes", "min_rest_minutes"),
    (InvalidEvaluationInputError, "sem fatos", "sem fatos"),
)

# As que não carregam contexto: a mensagem é a invariante inteira.
_SEM_CONTEXTO: tuple[tuple[type[SchedulingError], str], ...] = (
    (DuplicateShiftBandError, "par (início, fim)"),
    (ShiftBandNotFoundError, "faixa não encontrada"),
    (ShiftBandInUseError, "alocação pendente"),
    (ShiftBandDayChangeError, "dia operacional"),
    (TimeRangeOutsidePeriodError, "fora dos dias operacionais"),
    (DuplicateShiftDemandError, "já tem demanda dessa função"),
    (ShiftDemandNotFoundError, "demanda não encontrada"),
    (ShiftDemandInUseError, "não pode ser retirada"),
    (DuplicateAssignmentError, "vaga desta demanda"),
    (DuplicateAssignmentInBandError, "mesma faixa"),
    (AssignmentNotFoundError, "alocação não encontrada"),
)


def _excecoes_definidas_no_modulo() -> set[type[Exception]]:
    """As classes de exceção **definidas** aqui — não as importadas.

    O filtro por `__module__` é o que exclui `DomainError`, que o módulo importa
    para herdar dele. A alternativa do precedente de identity/staff
    (`obj is not DomainError`) bastava para um módulo com um import; aqui a
    asserção é de **igualdade** de conjunto, e um import futuro qualquer a
    reprovaria por um motivo que não é o dela.
    """
    return {
        obj
        for obj in vars(scheduling_errors).values()
        if isinstance(obj, type)
        and issubclass(obj, Exception)
        and obj.__module__ == scheduling_errors.__name__
    }


def test_scheduling_error_e_um_domain_error() -> None:
    # Garante que o error handler HTTP, que captura DomainError, também captura
    # qualquer erro deste bounded context. O mapa de status é da 4.5.
    assert issubclass(SchedulingError, DomainError)


def test_a_raiz_do_bc_herda_de_domain_error_diretamente() -> None:
    """`_raiz_de_erro` de `tests/unit/test_status_map.py` exige **exatamente uma**.

    Uma subclasse que herdasse de `DomainError` direto (o engano mais provável
    num módulo de 23 classes) daria duas raízes e reprovaria a varredura de
    repositório — aqui a propriedade é afirmada no nível do BC, onde o defeito
    nasce.
    """
    raizes = [obj for obj in _excecoes_definidas_no_modulo() if DomainError in obj.__bases__]

    assert raizes == [SchedulingError]


@pytest.mark.parametrize("exc_type", _AS_DO_BC)
def test_toda_excecao_do_bc_herda_de_scheduling_error(exc_type: type[SchedulingError]) -> None:
    assert issubclass(exc_type, SchedulingError)


def test_nenhuma_excecao_do_modulo_escapa_de_scheduling_error() -> None:
    # Guarda *derivada* (não lista fixa): pega exceção nova que herde de
    # DomainError — ou de Exception puro, o engano mais provável — em vez de
    # SchedulingError, e que portanto escaparia da parametrização acima.
    definidas = _excecoes_definidas_no_modulo()
    assert definidas, "o módulo de erros deve definir ao menos uma exceção"
    for exc_type in definidas:
        assert issubclass(exc_type, SchedulingError)


def test_o_conjunto_publico_do_modulo_e_exatamente_as_do_bc_mais_a_raiz() -> None:
    """CA17/CA14 — o conjunto é **23**, e a igualdade fecha os dois quantificadores.

    A varredura acima pega a exceção do módulo que escapa da raiz; esta pega a
    exceção que **existe** no módulo e não está no mapa de erros do concept §6 —
    e também a que sai da lista do concept sem sair do código. Sem a igualdade, a
    24ª exceção entraria herdando corretamente de `SchedulingError`, sem linha na
    §6, e nada reprovaria.
    """
    esperado = {SchedulingError, *_AS_DO_BC}

    assert _excecoes_definidas_no_modulo() == esperado
    assert len(_AS_DO_BC) == _TOTAL_DE_EXCECOES


def test_toda_excecao_do_bc_aparece_numa_das_duas_tabelas_de_mensagem() -> None:
    """Anti-vácuo das tabelas de mensagem: nenhuma das 22 fica sem asserção.

    Sem esta, acrescentar a exceção à lista `_AS_DO_BC` e esquecê-la nas tabelas
    deixaria a mensagem dela sem nenhum teste — e o gate de cobertura não a
    pegaria, porque o `super().__init__` de uma linha ficaria coberto pelo import.
    """
    com_mensagem = {tipo for tipo, _, _ in _COM_CONTEXTO} | {tipo for tipo, _ in _SEM_CONTEXTO}

    assert com_mensagem == set(_AS_DO_BC)


@pytest.mark.parametrize(("exc_type", "argumento", "trecho"), _COM_CONTEXTO)
def test_a_excecao_com_contexto_preserva_o_valor_na_mensagem(
    exc_type: type[SchedulingError], argumento: object, trecho: str
) -> None:
    """A mensagem tem de dizer **qual** valor ou motivo quebrou.

    Quatro destas (`InvalidTimeRangeError`, `InvalidSchedulePeriodError`,
    `InvalidAssignmentBreakError`, `InvalidDayCutoffError`) cobrem mais de um
    cenário do concept §6, e é o `reason` que impede a mensagem de descrever o
    defeito errado a quem recebe a recusa.
    """
    with pytest.raises(exc_type) as excinfo:
        raise exc_type(argumento)  # type: ignore[call-arg]

    assert trecho in str(excinfo.value)


@pytest.mark.parametrize(("exc_type", "trecho"), _SEM_CONTEXTO)
def test_a_excecao_sem_contexto_explica_a_invariante(
    exc_type: type[SchedulingError], trecho: str
) -> None:
    # `in` e não `match=`: o trecho é texto literal, e o `match` do pytest é
    # **regex** — o parêntese de "par (início, fim)" reprovaria por sintaxe, não
    # por conteúdo.
    with pytest.raises(exc_type) as excinfo:
        raise exc_type()  # type: ignore[call-arg]

    assert trecho in str(excinfo.value)


def test_as_duas_duplicidades_de_alocacao_sao_mensagens_distintas() -> None:
    """§6 as declara **disjuntas por nível**, e a mensagem tem de distingui-las.

    Mesma demanda é `DuplicateAssignmentError`; outra demanda da **mesma faixa**
    é `DuplicateAssignmentInBandError` (invariante 23). Duas exceções com a mesma
    prosa tornariam a distinção invisível para quem lê a recusa, e a segunda
    pareceria redundante na primeira revisão que a encontrasse.
    """
    assert str(DuplicateAssignmentError()) != str(DuplicateAssignmentInBandError())
