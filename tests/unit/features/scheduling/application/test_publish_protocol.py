"""Protocolo de publicação (`_publish.py`) — concept 4.3 §5.5 a §5.10 e §5.21.

CA04 (1ª falha recusa), CA08 (aceite e medida), CA09 (sobre-cobertura), CA10
(pré-existente), CA11 (alocar), CA12 (no-op), CA14 (D3), CA19 (instante de fora), CA20
(erros crus), CA22 (ids de criação).
"""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from restaurant_hub.features.scheduling.application.dtos.commands import (
    AssignEmployee,
    ChangeDemandQuantity,
    DeclareAllocationBreak,
    DeclareDemand,
    DeclareWorkloadCounting,
    DisableBand,
    EnableBand,
    RedeclareBandBreak,
    RescheduleBand,
    ScheduleOperation,
    UnassignEmployee,
    ViolationAcknowledgement,
    WithdrawDemand,
)
from restaurant_hub.features.scheduling.application.errors import (
    IdentifierInUseError,
    InactiveAllocationsInUseError,
    InactiveStaffMemberError,
    JobFunctionNotFoundError,
    StaffMemberNotFoundError,
)
from restaurant_hub.features.scheduling.application.use_cases._inputs import StaffView
from restaurant_hub.features.scheduling.application.use_cases._publish import (
    apply_operations,
    check_creation_ids,
    introduced,
    split_acknowledged,
)
from restaurant_hub.features.scheduling.domain.entities.schedule import Schedule
from restaurant_hub.features.scheduling.domain.exceptions.errors import (
    DuplicateEntityIdError,
    InvalidTimeRangeError,
    ShiftBandInUseError,
    ShiftDemandInUseError,
    ShiftDemandNotFoundError,
)
from restaurant_hub.features.scheduling.domain.value_objects.demand_quantity import (
    DemandQuantity,
)
from restaurant_hub.features.scheduling.domain.value_objects.identifiers import (
    AssignmentId,
    EmployeeId,
    JobFunctionId,
    ShiftBandId,
    ShiftDemandId,
)
from restaurant_hub.features.scheduling.domain.value_objects.time_range import TimeRange
from restaurant_hub.features.scheduling.domain.value_objects.validation_config import (
    EnforcementMode,
    PolicyKind,
)
from restaurant_hub.features.scheduling.domain.value_objects.violation import Violation
from tests.unit.features.scheduling.application.conftest import (
    COOK,
    MONDAY,
    WAITER,
    at,
    member,
    schedule,
)

pytestmark = pytest.mark.unit

_F1, _D1 = ShiftBandId("f1"), ShiftDemandId("d1")


def _view(*membros: object) -> StaffView:
    return StaffView(
        members={m.employee_id: m for m in membros},  # type: ignore[attr-defined]
        function_names={COOK: "Cozinheiro", WAITER: "Atendente"},
    )


_VIEW = _view(member("ana"), member("bia", functions=(WAITER,)), member("caio", active=False))


def _base() -> Schedule:
    return (
        schedule()
        .enable_band(_F1, TimeRange(start=at(MONDAY, 10), end=at(MONDAY, 16)))
        .declare_demand(_D1, _F1, COOK, DemandQuantity(2))
    )


# --- CA11 — alocar ----------------------------------------------------------------------


def test_ca11_alocar_registro_ausente_recusa() -> None:
    with pytest.raises(StaffMemberNotFoundError):
        apply_operations(
            _base(), (AssignEmployee(AssignmentId("a1"), _D1, EmployeeId("zé")),), _VIEW
        )


def test_ca11_alocar_desligado_recusa() -> None:
    with pytest.raises(InactiveStaffMemberError):
        apply_operations(
            _base(), (AssignEmployee(AssignmentId("a1"), _D1, EmployeeId("caio")),), _VIEW
        )


@pytest.mark.parametrize(("registro", "excecao"), [("ana", False), ("bia", True)])
def test_ca11_marca_de_excecao_nasce_pela_nao_detencao(registro: str, excecao: bool) -> None:
    lote = apply_operations(
        _base(), (AssignEmployee(AssignmentId("a1"), _D1, EmployeeId(registro), False),), _VIEW
    )
    _, _, alocacao = lote.schedule.locate_assignment(AssignmentId("a1"))
    assert alocacao.function_exception is excecao
    assert alocacao.counts_toward_workload is False


def test_ca11_demanda_de_funcao_fora_do_catalogo_recusa() -> None:
    with pytest.raises(JobFunctionNotFoundError):
        apply_operations(
            _base(),
            (DeclareDemand(ShiftDemandId("d2"), _F1, JobFunctionId("x"), DemandQuantity(1)),),
            _VIEW,
        )


# --- CA04/CA20 — lote atômico e erros crus ---------------------------------------------


def test_ca04_ca20_a_primeira_falha_sobe_crua_e_interrompe() -> None:
    lote: tuple[ScheduleOperation, ...] = (
        AssignEmployee(AssignmentId("a1"), _D1, EmployeeId("ana")),
        AssignEmployee(AssignmentId("a2"), ShiftDemandId("nao-existe"), EmployeeId("ana")),
        AssignEmployee(AssignmentId("a3"), _D1, EmployeeId("zé")),
    )
    with pytest.raises(ShiftDemandNotFoundError) as excinfo:
        apply_operations(_base(), lote, _VIEW)
    assert type(excinfo.value) is ShiftDemandNotFoundError


def test_ca22_id_repetido_no_proprio_lote_e_a_recusa_do_dominio() -> None:
    lote = (
        AssignEmployee(AssignmentId("a1"), _D1, EmployeeId("ana")),
        UnassignEmployee(AssignmentId("a1")),
        EnableBand(_F1, TimeRange(start=at(MONDAY, 18), end=at(MONDAY, 20))),
    )
    with pytest.raises(DuplicateEntityIdError):
        apply_operations(_base(), lote, _VIEW)


# --- CA12 — no-op e efetivas -----------------------------------------------------------


def test_ca12_as_cinco_idempotentes_nao_sao_efetivas() -> None:
    base = _base().assign(AssignmentId("a1"), _D1, EmployeeId("ana"))
    lote: tuple[ScheduleOperation, ...] = (
        RescheduleBand(_F1, at(MONDAY, 10), at(MONDAY, 16)),
        RedeclareBandBreak(_F1, 0),
        ChangeDemandQuantity(_D1, DemandQuantity(2)),
        DeclareWorkloadCounting(AssignmentId("a1"), True),
        DeclareAllocationBreak(AssignmentId("a1"), None),
    )
    resultado = apply_operations(base, lote, _VIEW)
    assert resultado.schedule is base
    assert resultado.effective == ()


def test_ca12_lote_misto_so_lista_as_efetivas_e_a_versao_conta_so_elas() -> None:
    base = _base()
    efetiva = ChangeDemandQuantity(_D1, DemandQuantity(3))
    lote = (ChangeDemandQuantity(_D1, DemandQuantity(2)), efetiva, RedeclareBandBreak(_F1, 0))
    resultado = apply_operations(base, lote, _VIEW)
    assert resultado.effective == (efetiva,)
    assert resultado.schedule.version == base.version + 1


# --- CA19 — instante de fora do domínio ------------------------------------------------


@pytest.mark.parametrize(
    "inicio",
    [at(MONDAY, 11).replace(tzinfo=UTC), at(MONDAY, 11).replace(second=30)],
    ids=["tz-aware", "com-segundos"],
)
def test_ca19_limites_de_reagendamento_validados_antes_do_dia_operacional(inicio: datetime) -> None:
    with pytest.raises(InvalidTimeRangeError):
        apply_operations(_base(), (RescheduleBand(_F1, inicio, at(MONDAY, 17)),), _VIEW)


# --- CA14 — D3 ---------------------------------------------------------------------------


def _com_desligado() -> Schedule:
    return _base().assign(AssignmentId("a-caio"), _D1, EmployeeId("caio"))


@pytest.mark.parametrize(
    "operacao", [DisableBand(_F1), WithdrawDemand(_D1)], ids=["faixa", "demanda"]
)
def test_ca14_presa_so_por_desligado_recusa_com_contagem_e_ids(operacao: ScheduleOperation) -> None:
    with pytest.raises(InactiveAllocationsInUseError) as excinfo:
        apply_operations(_com_desligado(), (operacao,), _VIEW)
    assert excinfo.value.assignment_ids == (AssignmentId("a-caio"),)
    assert excinfo.value.count == 1
    assert "caio" not in str(excinfo.value)


@pytest.mark.parametrize(
    "operacao", [DisableBand(_F1), WithdrawDemand(_D1)], ids=["faixa", "demanda"]
)
def test_ca14_desalocar_no_mesmo_lote_destrava(operacao: ScheduleOperation) -> None:
    resultado = apply_operations(
        _com_desligado(), (UnassignEmployee(AssignmentId("a-caio")), operacao), _VIEW
    )
    assert resultado.effective[-1] == operacao


@pytest.mark.parametrize(
    ("operacao", "erro"),
    [(DisableBand(_F1), ShiftBandInUseError), (WithdrawDemand(_D1), ShiftDemandInUseError)],
    ids=["faixa", "demanda"],
)
def test_ca14_com_alocacao_de_ativo_a_recusa_e_a_do_dominio(
    operacao: ScheduleOperation, erro: type[Exception]
) -> None:
    escala = _com_desligado().assign(AssignmentId("a-ana"), _D1, EmployeeId("ana"))
    with pytest.raises(erro):
        apply_operations(escala, (operacao,), _VIEW)


def test_ca14_faixa_sem_alocacao_e_desabilitada_normalmente() -> None:
    resultado = apply_operations(_base(), (DisableBand(_F1),), _VIEW)
    assert resultado.schedule.bands == ()


# --- CA22 — ids de criação ---------------------------------------------------------------


@pytest.mark.parametrize(
    "operacao",
    [
        EnableBand(_F1, TimeRange(start=at(MONDAY, 18), end=at(MONDAY, 20))),
        DeclareDemand(_D1, _F1, WAITER, DemandQuantity(1)),
        AssignEmployee(AssignmentId("a1"), _D1, EmployeeId("ana")),
    ],
    ids=["faixa", "demanda", "alocacao"],
)
def test_ca22_id_de_criacao_ja_usado_na_escala_recusa(operacao: ScheduleOperation) -> None:
    escala = _base().assign(AssignmentId("a1"), _D1, EmployeeId("ana"))
    with pytest.raises(IdentifierInUseError):
        check_creation_ids((escala,), (operacao,))


def test_ca22_id_de_criacao_ja_usado_numa_vizinha_recusa_e_tipos_distintos_nao_colidem() -> None:
    vizinha = schedule("s0", MONDAY - timedelta(days=7)).enable_band(
        ShiftBandId("g1"),
        TimeRange(start=at(MONDAY - timedelta(days=7), 9), end=at(MONDAY - timedelta(days=7), 12)),
    )
    with pytest.raises(IdentifierInUseError) as excinfo:
        check_creation_ids(
            (_base(), vizinha),
            (EnableBand(ShiftBandId("g1"), TimeRange(start=at(MONDAY, 18), end=at(MONDAY, 20))),),
        )
    assert (excinfo.value.id_type, excinfo.value.value) == ("ShiftBandId", "g1")
    check_creation_ids(
        (_base(),), (DeclareDemand(ShiftDemandId("f1"), _F1, WAITER, DemandQuantity(1)),)
    )


# --- CA08/CA09/CA10 — introduzidas e aceite ----------------------------------------------

_DIA = (date(2026, 11, 2),)


def _v(  # noqa: PLR0913
    policy: PolicyKind,
    observed: str,
    limit: str,
    *,
    employee: str | None = "ana",
    demand: str | None = None,
    assignments: tuple[str, ...] = (),
    mode: EnforcementMode = EnforcementMode.WARN,
) -> Violation:
    return Violation(
        policy=policy,
        mode=mode,
        employee_id=EmployeeId(employee) if employee else None,
        demand_id=ShiftDemandId(demand) if demand else None,
        operational_days=_DIA,
        assignment_ids=frozenset(AssignmentId(a) for a in assignments),
        observed=Decimal(observed),
        limit=Decimal(limit),
    )


def test_ca10_pre_existente_com_mesma_medida_nao_e_introduzida() -> None:
    bloqueante = _v(
        PolicyKind.UNAVAILABILITY, "60", "0", assignments=("a1",), mode=EnforcementMode.BLOCK
    )
    assert introduced((bloqueante,), (bloqueante,)) == ()


def test_ca08_chave_nova_e_introduzida() -> None:
    nova = _v(PolicyKind.DAILY_CAP, "600", "480")
    assert introduced((), (nova,)) == (nova,)


def test_ca08_medida_que_cresce_e_introduzida_e_a_que_melhora_nao() -> None:
    antes = _v(PolicyKind.WEEKLY_CAP, "2700", "2640")
    pior = _v(PolicyKind.WEEKLY_CAP, "2760", "2640")
    melhor = _v(PolicyKind.WEEKLY_CAP, "2650", "2640")
    assert introduced((antes,), (pior,)) == (pior,)
    assert introduced((antes,), (melhor,)) == ()


def test_ca08_carga_both_que_troca_subcarga_por_sobrecarga_e_introduzida() -> None:
    subcarga = _v(PolicyKind.WORKLOAD, "1800", "2400")
    sobrecarga = _v(PolicyKind.WORKLOAD, "2760", "2400")  # |360| < |600|, mas trocou de sinal
    assert introduced((subcarga,), (sobrecarga,)) == (sobrecarga,)


def test_ca08_aceite_cobre_a_medida_vista_e_nao_a_pior() -> None:
    vista = _v(PolicyKind.WEEKLY_CAP, "2760", "2640")
    aceite = ViolationAcknowledgement(key=vista.key, observed=vista.observed, limit=vista.limit)
    assert split_acknowledged((vista,), (aceite,)) == ((vista,), ())
    pior = _v(PolicyKind.WEEKLY_CAP, "2820", "2640")
    assert split_acknowledged((pior,), (aceite,)) == ((), (pior,))
    melhor = _v(PolicyKind.WEEKLY_CAP, "2700", "2640")
    assert split_acknowledged((melhor,), (aceite,)) == ((melhor,), ())


def test_ca08_aceite_reenviado_depois_de_reduzir_n_nao_cobre() -> None:
    vista = _v(
        PolicyKind.OVER_COVERAGE, "3", "2", employee=None, demand="d1", assignments=("a", "b", "c")
    )
    aceite = ViolationAcknowledgement(key=vista.key, observed=Decimal(3), limit=Decimal(2))
    apos_reduzir = _v(
        PolicyKind.OVER_COVERAGE, "3", "1", employee=None, demand="d1", assignments=("a", "b", "c")
    )
    assert split_acknowledged((apos_reduzir,), (aceite,)) == ((), (apos_reduzir,))


def test_ca08_aceite_de_subcarga_nao_cobre_sobrecarga_nem_chave_diferente() -> None:
    sobrecarga = _v(PolicyKind.WORKLOAD, "2760", "2400")
    aceite_subcarga = ViolationAcknowledgement(
        key=sobrecarga.key, observed=Decimal(1800), limit=Decimal(2400)
    )
    outra = _v(PolicyKind.WORKLOAD, "2760", "2400", employee="bia")
    aceite_alheio = ViolationAcknowledgement(
        key=outra.key, observed=Decimal(9999), limit=Decimal(0)
    )
    assert split_acknowledged((sobrecarga,), (aceite_subcarga, aceite_alheio)) == (
        (),
        (sobrecarga,),
    )


def _sobre(n: str, *alocacoes: str) -> Violation:
    return _v(
        PolicyKind.OVER_COVERAGE,
        str(len(alocacoes)),
        n,
        employee=None,
        demand="d1",
        assignments=alocacoes,
    )


def test_ca09_desalocar_excedente_sem_chegar_a_n_nao_e_introduzida() -> None:
    assert introduced((_sobre("1", "a", "b", "c"),), (_sobre("1", "a", "b"),)) == ()


def test_ca09_aumentar_o_excedente_ou_trocar_a_alocacao_e_introduzida() -> None:
    antes = _sobre("1", "a", "b")
    mais = _sobre("1", "a", "b", "c")
    troca = _sobre("1", "a", "c")
    reduz_n = _sobre("0", "a", "b")
    assert introduced((antes,), (mais,)) == (mais,)
    assert introduced((antes,), (troca,)) == (troca,)
    assert introduced((antes,), (reduz_n,)) == (reduz_n,)
    assert introduced((), (antes,)) == (antes,)


def test_ca09_sobre_cobertura_de_outra_demanda_nao_conta_como_antes() -> None:
    outra = _v(
        PolicyKind.OVER_COVERAGE, "2", "1", employee=None, demand="d9", assignments=("x", "y")
    )
    agora = _sobre("1", "a", "b")
    assert introduced((outra,), (agora,)) == (agora,)
