"""`evaluate_schedule` e `publish_schedule` (concept 4.3 §5.4 a §5.13).

CA02, CA04, CA05, CA06, CA07, CA10, CA12, CA16, CA25, CA26.
"""

import dataclasses
from datetime import timedelta
from decimal import Decimal

import pytest

from restaurant_hub.features.scheduling.application.dtos.commands import (
    AssignEmployee,
    ChangeDemandQuantity,
    DeclareDemand,
    EnableBand,
    PublishScheduleCommand,
    RedeclareBandBreak,
    ScheduleOperation,
    UnassignEmployee,
    ViolationAcknowledgement,
)
from restaurant_hub.features.scheduling.application.dtos.queries import EvaluateScheduleQuery
from restaurant_hub.features.scheduling.application.errors import (
    BlockingViolationsError,
    IdentifierInUseError,
    InactiveStaffMemberError,
    MissingStaffRecordsError,
    ScheduleNotFoundError,
    ScheduleVersionConflictError,
    UnacknowledgedViolationsError,
)
from restaurant_hub.features.scheduling.application.ports.out.schedule_config_repository import (
    SchedulingSettings,
)
from restaurant_hub.features.scheduling.application.ports.out.staff_read_port import (
    JobFunctionEntry,
    StaffMember,
)
from restaurant_hub.features.scheduling.application.use_cases.evaluate_schedule import (
    EvaluateScheduleUseCase,
)
from restaurant_hub.features.scheduling.application.use_cases.publish_schedule import (
    PublishScheduleUseCase,
)
from restaurant_hub.features.scheduling.domain.entities.schedule import Schedule
from restaurant_hub.features.scheduling.domain.value_objects.demand_quantity import (
    DemandQuantity,
)
from restaurant_hub.features.scheduling.domain.value_objects.employee_facts import (
    UnavailabilityWindow,
)
from restaurant_hub.features.scheduling.domain.value_objects.identifiers import (
    AssignmentId,
    EmployeeId,
    ScheduleId,
    ShiftBandId,
    ShiftDemandId,
    TenantId,
    UnitId,
)
from restaurant_hub.features.scheduling.domain.value_objects.operational_calendar import (
    OperationalCalendar,
)
from restaurant_hub.features.scheduling.domain.value_objects.time_range import TimeRange
from restaurant_hub.features.scheduling.domain.value_objects.validation_config import (
    EnforcementMode,
    PolicyKind,
    PolicyRule,
    ValidationConfig,
    WorkloadDirection,
)
from tests.fakes.features.scheduling.in_memory_staff_read import InMemoryStaffRead
from tests.unit.features.scheduling.application.conftest import (
    COOK,
    MONDAY,
    NOW,
    T1,
    T2,
    U1,
    U2,
    World,
    at,
    blank_change,
    member,
    schedule,
)

pytestmark = pytest.mark.unit

_S1, _F1, _D1 = ScheduleId("s1"), ShiftBandId("f1"), ShiftDemandId("d1")


def _seed(world: World, base: Schedule | None = None) -> Schedule:
    """s1: faixa f1 seg 10-16, demanda de cozinheiro N=1 com Ana alocada (a-ana)."""
    world.staff.add_member(T1, member("carla"))
    escala = base or (
        schedule("s1")
        .enable_band(_F1, TimeRange(start=at(MONDAY, 10), end=at(MONDAY, 16)))
        .declare_demand(_D1, _F1, COOK, DemandQuantity(1))
        .assign(AssignmentId("a-ana"), _D1, EmployeeId("ana"))
    )
    world.schedules.add(dataclasses.replace(escala, version=1), blank_change())
    return escala


def _evaluate(world: World) -> EvaluateScheduleUseCase:
    return EvaluateScheduleUseCase(world.schedules, world.config, world.staff, world.guard)


def _publish(world: World) -> PublishScheduleUseCase:
    return PublishScheduleUseCase(
        world.schedules, world.config, world.staff, world.clock, world.guard
    )


def _q(
    world: World, ops: tuple[ScheduleOperation, ...], version: int = 1, sid: ScheduleId = _S1
) -> EvaluateScheduleQuery:
    return EvaluateScheduleQuery(world.manager, T1, U1, sid, version, ops)


def _c(
    world: World,
    ops: tuple[ScheduleOperation, ...],
    acks: tuple[ViolationAcknowledgement, ...] = (),
    version: int = 1,
    sid: ScheduleId = _S1,
) -> PublishScheduleCommand:
    return PublishScheduleCommand(world.manager, T1, U1, sid, version, ops, acks)


_EXCEDENTE = (AssignEmployee(AssignmentId("a-carla"), _D1, EmployeeId("carla")),)
_SOBREPOSICAO: tuple[ScheduleOperation, ...] = (
    EnableBand(ShiftBandId("f2"), TimeRange(start=at(MONDAY, 14), end=at(MONDAY, 18))),
    DeclareDemand(ShiftDemandId("d2"), ShiftBandId("f2"), COOK, DemandQuantity(1)),
    AssignEmployee(AssignmentId("a-ana-2"), ShiftDemandId("d2"), EmployeeId("ana")),
)


# --- CA05 — avaliar --------------------------------------------------------------------


def test_ca05_avaliar_separa_as_introduzidas_e_nao_grava(world: World) -> None:
    _seed(world)
    resultado = _evaluate(world).execute(_q(world, _EXCEDENTE))
    assert [v.policy for v in resultado.warnings] == [PolicyKind.OVER_COVERAGE]
    assert resultado.blocking == ()
    assert resultado.schedule.summary.version == 2  # noqa: PLR2004
    assert PolicyKind.OVER_COVERAGE in {v.policy for v in resultado.schedule.violations}
    assert "save" not in world.schedules.calls


def test_ca05_avaliar_devolve_a_block_introduzida_sem_recusar(world: World) -> None:
    _seed(world)
    resultado = _evaluate(world).execute(_q(world, _SOBREPOSICAO))
    assert [v.policy for v in resultado.blocking] == [PolicyKind.OVERLAP]
    assert "save" not in world.schedules.calls


# --- CA02 — versão -----------------------------------------------------------------------


@pytest.mark.parametrize("caso", ["avaliar", "publicar"])
def test_ca02_versao_vencida_recusa_com_a_atual_sem_gravar(world: World, caso: str) -> None:
    _seed(world)
    with pytest.raises(ScheduleVersionConflictError) as excinfo:
        if caso == "avaliar":
            _evaluate(world).execute(_q(world, _EXCEDENTE, version=7))
        else:
            _publish(world).execute(_c(world, _EXCEDENTE, version=7))
    assert excinfo.value.current_version == 1
    assert "save" not in world.schedules.calls


# --- CA26 — endereço -----------------------------------------------------------------------


@pytest.mark.parametrize("caso", ["avaliar", "publicar"])
@pytest.mark.parametrize("endereco", [(T1, U2), (T2, U1)], ids=["outra-unidade", "outro-tenant"])
def test_ca26_escala_de_outra_unidade_ou_tenant_nao_e_encontrada(
    world: World, caso: str, endereco: tuple[TenantId, UnitId]
) -> None:
    _seed(world, schedule("s1", tenant=endereco[0], unit=endereco[1]))
    with pytest.raises(ScheduleNotFoundError):
        if caso == "avaliar":
            _evaluate(world).execute(_q(world, ()))
        else:
            _publish(world).execute(_c(world, ()))
    assert "save" not in world.schedules.calls


def test_ca26_config_gravada_do_tenant_vale_no_avaliador(world: World) -> None:
    _seed(world)
    silenciosa = PolicyRule(enabled=False, mode=EnforcementMode.WARN)
    config = ValidationConfig.default()
    world.config.set_settings(
        T1,
        SchedulingSettings(
            calendar=OperationalCalendar.default(),
            validation=dataclasses.replace(config, over_coverage=silenciosa),
        ),
    )
    resultado = _evaluate(world).execute(_q(world, _EXCEDENTE))
    assert resultado.warnings == ()


def test_ca26_config_de_outro_tenant_nao_e_lida(world: World) -> None:
    _seed(world)
    silenciosa = PolicyRule(enabled=False, mode=EnforcementMode.WARN)
    world.config.set_settings(
        T2,
        SchedulingSettings(
            calendar=OperationalCalendar.default(),
            validation=dataclasses.replace(ValidationConfig.default(), over_coverage=silenciosa),
        ),
    )
    resultado = _evaluate(world).execute(_q(world, _EXCEDENTE))
    assert [v.policy for v in resultado.warnings] == [PolicyKind.OVER_COVERAGE]


# --- CA06 — block --------------------------------------------------------------------------


def test_ca06_publicar_recusa_block_introduzida_sem_gravar(world: World) -> None:
    _seed(world)
    with pytest.raises(BlockingViolationsError) as excinfo:
        _publish(world).execute(_c(world, _SOBREPOSICAO))
    assert [v.policy for v in excinfo.value.violations] == [PolicyKind.OVERLAP]
    assert "save" not in world.schedules.calls


def test_ca06_todas_as_block_introduzidas_sobem_no_erro(world: World) -> None:
    _seed(world)
    # Indisponibilidade de Ana só na janela da faixa nova (16-18h; f1 termina às 16h).
    janela = UnavailabilityWindow(start=at(MONDAY, 16), end=at(MONDAY, 18))
    world.staff.add_member(T1, member("ana", unavailabilities=(janela,)), user_id="user-ana")
    with pytest.raises(BlockingViolationsError) as excinfo:
        _publish(world).execute(_c(world, _SOBREPOSICAO))
    assert {v.policy for v in excinfo.value.violations} == {
        PolicyKind.OVERLAP,
        PolicyKind.UNAVAILABILITY,
    }
    assert len(excinfo.value.violations) == 2  # noqa: PLR2004


def test_ids_de_criacao_sao_conferidos_antes_da_leitura_de_staff(world: World) -> None:
    _seed(world)
    world.staff.remove_member(T1, U1, "ana")
    reuso = (EnableBand(_F1, TimeRange(start=at(MONDAY, 18), end=at(MONDAY, 20))),)
    with pytest.raises(IdentifierInUseError):
        _evaluate(world).execute(_q(world, reuso))


def test_ca06_block_e_checado_antes_do_warn(world: World) -> None:
    _seed(world)
    with pytest.raises(BlockingViolationsError):
        _publish(world).execute(_c(world, (*_SOBREPOSICAO, *_EXCEDENTE)))


def test_ca06_function_mismatch_em_block_recusa_a_alocacao_sem_funcao(world: World) -> None:
    _seed(world)
    world.config.set_settings(
        T1,
        SchedulingSettings(
            calendar=OperationalCalendar.default(),
            validation=dataclasses.replace(
                ValidationConfig.default(),
                function_mismatch=PolicyRule(enabled=True, mode=EnforcementMode.BLOCK),
            ),
        ),
    )
    lote = (
        ChangeDemandQuantity(_D1, DemandQuantity(2)),
        AssignEmployee(AssignmentId("a-bia"), _D1, EmployeeId("bia")),
    )
    with pytest.raises(BlockingViolationsError) as excinfo:
        _publish(world).execute(_c(world, lote))
    assert [v.policy for v in excinfo.value.violations] == [PolicyKind.FUNCTION_MISMATCH]


# --- CA07 — warn e aceite -------------------------------------------------------------------


def test_ca07_warn_sem_aceite_recusa_com_as_pendentes(world: World) -> None:
    _seed(world)
    with pytest.raises(UnacknowledgedViolationsError) as excinfo:
        _publish(world).execute(_c(world, _EXCEDENTE))
    assert [v.policy for v in excinfo.value.violations] == [PolicyKind.OVER_COVERAGE]
    assert "save" not in world.schedules.calls


def test_ca07_com_o_aceite_grava_a_escala_e_a_mudanca(world: World) -> None:
    _seed(world)
    avaliado = _evaluate(world).execute(_q(world, _EXCEDENTE))
    acks = tuple(ViolationAcknowledgement(v.key, v.observed, v.limit) for v in avaliado.warnings)
    publicado = _publish(world).execute(_c(world, _EXCEDENTE, acks))
    assert publicado.summary.version == 2  # noqa: PLR2004
    _, mudanca = world.schedules.changes_of(_S1)
    assert mudanca.author_user_id == "user-ger"
    assert mudanca.occurred_at == NOW
    assert mudanca.previous_version == 1
    assert mudanca.operations == _EXCEDENTE
    assert mudanca.acknowledged == avaliado.warnings
    gravada = world.schedules.find_by_id(T1, U1, _S1)
    assert gravada is not None
    assert gravada.version == 2  # noqa: PLR2004


# --- CA10 — pré-existente --------------------------------------------------------------------


def test_ca10_block_pre_existente_de_staff_nao_trava_mudanca_alheia(world: World) -> None:
    _seed(world)
    # Férias lançadas em staff DEPOIS de Ana estar alocada (D1).
    ferias = UnavailabilityWindow(start=at(MONDAY, 0), end=at(MONDAY + timedelta(days=3), 0))
    world.staff.add_member(T1, member("ana", unavailabilities=(ferias,)), user_id="user-ana")
    publicado = _publish(world).execute(_c(world, (RedeclareBandBreak(_F1, 30),)))
    assert PolicyKind.UNAVAILABILITY in {v.policy for v in publicado.violations}
    assert world.schedules.calls.count("save") == 1


# --- CA04/CA12 — lote ----------------------------------------------------------------------


def test_ca04_block_intermediario_que_some_no_final_nao_recusa(world: World) -> None:
    _seed(world)
    lote = (*_SOBREPOSICAO, UnassignEmployee(AssignmentId("a-ana-2")))
    publicado = _publish(world).execute(_c(world, lote))
    assert PolicyKind.OVERLAP not in {v.policy for v in publicado.violations}


def test_ca04_lote_vazio_e_aceito_sem_gravar(world: World) -> None:
    _seed(world)
    publicado = _publish(world).execute(_c(world, ()))
    assert publicado.summary.version == 1
    assert "save" not in world.schedules.calls


def test_ca12_lote_so_de_no_ops_nao_grava(world: World) -> None:
    _seed(world)
    lote = (ChangeDemandQuantity(_D1, DemandQuantity(1)), RedeclareBandBreak(_F1, 0))
    _publish(world).execute(_c(world, lote))
    assert "save" not in world.schedules.calls
    assert len(world.schedules.changes_of(_S1)) == 1


def test_ca12_lote_misto_grava_so_as_efetivas_e_a_versao_conta_so_elas(world: World) -> None:
    _seed(world)
    efetiva = RedeclareBandBreak(_F1, 30)
    lote = (ChangeDemandQuantity(_D1, DemandQuantity(1)), efetiva, RedeclareBandBreak(_F1, 30))
    publicado = _publish(world).execute(_c(world, lote))
    assert publicado.summary.version == 2  # noqa: PLR2004
    assert world.schedules.changes_of(_S1)[-1].operations == (efetiva,)


# --- CA16 — registro ausente ----------------------------------------------------------------


@pytest.mark.parametrize("caso", ["avaliar", "publicar"])
def test_ca16_alocado_que_staff_nao_devolve_recusa_com_os_ids(world: World, caso: str) -> None:
    _seed(world)
    world.staff.remove_member(T1, U1, "ana")
    with pytest.raises(MissingStaffRecordsError) as excinfo:
        if caso == "avaliar":
            _evaluate(world).execute(_q(world, ()))
        else:
            _publish(world).execute(_c(world, ()))
    assert excinfo.value.assignment_ids == (AssignmentId("a-ana"),)


def test_ca16_ausente_numa_vizinha_tambem_recusa(world: World) -> None:
    _seed(world)
    anterior = MONDAY - timedelta(days=7)
    vizinha = (
        schedule("s0", anterior)
        .enable_band(ShiftBandId("g1"), TimeRange(start=at(anterior, 9), end=at(anterior, 12)))
        .declare_demand(ShiftDemandId("e1"), ShiftBandId("g1"), COOK, DemandQuantity(1))
        .assign(AssignmentId("b-ze"), ShiftDemandId("e1"), EmployeeId("ze"))
    )
    world.schedules.add(dataclasses.replace(vizinha, version=1), blank_change())
    with pytest.raises(MissingStaffRecordsError) as excinfo:
        _evaluate(world).execute(_q(world, ()))
    assert excinfo.value.assignment_ids == (AssignmentId("b-ze"),)


# --- CA25 — vizinhas e virada ---------------------------------------------------------------

_DOMINGO = MONDAY - timedelta(days=1)


def _virada(world: World) -> None:
    """A = semana anterior com Ana no domingo 18-23h; B = s1 vazia na segunda."""
    anterior = MONDAY - timedelta(days=7)
    a = (
        schedule("sA", anterior)
        .enable_band(ShiftBandId("gA"), TimeRange(start=at(_DOMINGO, 18), end=at(_DOMINGO, 23)))
        .declare_demand(ShiftDemandId("eA"), ShiftBandId("gA"), COOK, DemandQuantity(1))
        .assign(AssignmentId("b-ana"), ShiftDemandId("eA"), EmployeeId("ana"))
    )
    world.schedules.add(dataclasses.replace(a, version=1), blank_change())
    b = (
        schedule("s1")
        .enable_band(_F1, TimeRange(start=at(MONDAY, 6), end=at(MONDAY, 10)))
        .declare_demand(_D1, _F1, COOK, DemandQuantity(1))
    )
    world.schedules.add(dataclasses.replace(b, version=1), blank_change())


def test_ca25_violacao_de_fronteira_introduzida_e_perguntada_e_nao_repete_na_vizinha(
    world: World,
) -> None:
    _virada(world)
    lote = (AssignEmployee(AssignmentId("a-ana"), _D1, EmployeeId("ana")),)
    avaliado = _evaluate(world).execute(_q(world, lote))
    assert [v.policy for v in avaliado.warnings] == [PolicyKind.REST_BETWEEN_SHIFTS]
    (descanso,) = avaliado.warnings
    assert descanso.operational_days == (_DOMINGO, MONDAY)
    acks = (ViolationAcknowledgement(descanso.key, descanso.observed, descanso.limit),)
    _publish(world).execute(_c(world, lote, acks))
    # Editar a escala A depois: a mesma key está antes e depois — não é perguntada de novo.
    alheia = (RedeclareBandBreak(ShiftBandId("gA"), 30),)
    na_vizinha = _evaluate(world).execute(
        EvaluateScheduleQuery(world.manager, T1, U1, ScheduleId("sA"), 1, alheia)
    )
    assert PolicyKind.REST_BETWEEN_SHIFTS in {v.policy for v in na_vizinha.schedule.violations}
    assert na_vizinha.warnings == ()


def test_ca25_escala_nao_adjacente_nao_entra_como_vizinha(world: World) -> None:
    _seed(world)
    longe = MONDAY - timedelta(days=14)
    world.schedules.add(
        schedule("sX", longe)
        .enable_band(ShiftBandId("gX"), TimeRange(start=at(longe, 9), end=at(longe, 12)))
        .declare_demand(ShiftDemandId("eX"), ShiftBandId("gX"), COOK, DemandQuantity(1))
        .assign(AssignmentId("x-ze"), ShiftDemandId("eX"), EmployeeId("ze")),
        blank_change(),
    )
    # Se a de duas semanas atrás entrasse, o "ze" ausente recusaria.
    _evaluate(world).execute(_q(world, ()))


# --- lacunas da auditoria de testes ---------------------------------------------------------


@pytest.mark.parametrize("caso", ["avaliar", "publicar"])
def test_ca02_versao_anterior_a_gravada_recusa(world: World, caso: str) -> None:
    _seed(world)
    gravada = world.schedules.find_by_id(T1, U1, _S1)
    assert gravada is not None
    world.schedules.save(dataclasses.replace(gravada, version=2), 1, blank_change(1))
    world.schedules.calls.clear()
    with pytest.raises(ScheduleVersionConflictError) as excinfo:
        if caso == "avaliar":
            _evaluate(world).execute(_q(world, _EXCEDENTE, version=1))
        else:
            _publish(world).execute(_c(world, _EXCEDENTE, version=1))
    assert excinfo.value.current_version == 2  # noqa: PLR2004
    assert "save" not in world.schedules.calls


def test_ca10_sobre_cobertura_pre_existente_nao_pede_aceite_de_novo(world: World) -> None:
    _seed(world)
    avaliado = _evaluate(world).execute(_q(world, _EXCEDENTE))
    acks = tuple(ViolationAcknowledgement(v.key, v.observed, v.limit) for v in avaliado.warnings)
    _publish(world).execute(_c(world, _EXCEDENTE, acks))
    publicado = _publish(world).execute(_c(world, (RedeclareBandBreak(_F1, 30),), version=2))
    assert PolicyKind.OVER_COVERAGE in {v.policy for v in publicado.violations}
    assert publicado.summary.version == 3  # noqa: PLR2004


def test_ca22_id_de_criacao_usado_na_vizinha_recusa_no_use_case(world: World) -> None:
    _seed(world)
    anterior = MONDAY - timedelta(days=7)
    vizinha = schedule("s0", anterior).enable_band(
        ShiftBandId("g1"), TimeRange(start=at(anterior, 9), end=at(anterior, 12))
    )
    world.schedules.add(dataclasses.replace(vizinha, version=1), blank_change())
    reuso = (EnableBand(ShiftBandId("g1"), TimeRange(start=at(MONDAY, 18), end=at(MONDAY, 20))),)
    with pytest.raises(IdentifierInUseError):
        _evaluate(world).execute(_q(world, reuso))


def test_ca11_alocar_desligado_pelo_use_case_recusa_como_inativo(world: World) -> None:
    _seed(world)
    world.staff.add_member(T1, member("caio", active=False))
    with pytest.raises(InactiveStaffMemberError):
        _publish(world).execute(
            _c(world, (AssignEmployee(AssignmentId("a-caio"), _D1, EmployeeId("caio")),))
        )


def test_insumo_inclui_o_quadro_ativo_nao_alocado(world: World) -> None:
    _seed(world)
    world.staff.add_member(T1, member("dora", hours=Decimal("40")))
    world.config.set_settings(
        T1,
        SchedulingSettings(
            calendar=OperationalCalendar.default(),
            validation=dataclasses.replace(
                ValidationConfig.default(), workload_direction=WorkloadDirection.BOTH
            ),
        ),
    )
    resultado = _evaluate(world).execute(_q(world, ()))
    assert any(
        v.policy is PolicyKind.WORKLOAD and v.employee_id == "dora"
        for v in resultado.schedule.violations
    )


def test_ca16_varios_ausentes_vem_todos_ordenados(world: World) -> None:
    base = (
        schedule("s1")
        .enable_band(_F1, TimeRange(start=at(MONDAY, 10), end=at(MONDAY, 16)))
        .declare_demand(_D1, _F1, COOK, DemandQuantity(3))
        .assign(AssignmentId("a-2"), _D1, EmployeeId("ze"))
        .assign(AssignmentId("a-1"), _D1, EmployeeId("rui"))
        .assign(AssignmentId("a-ana"), _D1, EmployeeId("ana"))
    )
    _seed(world, base)
    with pytest.raises(MissingStaffRecordsError) as excinfo:
        _evaluate(world).execute(_q(world, ()))
    assert excinfo.value.assignment_ids == (AssignmentId("a-1"), AssignmentId("a-2"))


class _QuadroDefasado(InMemoryStaffRead):
    """O quadro ativo devolve uma cópia defasada de Ana (sem as férias)."""

    def list_active_members(self, tenant_id: TenantId, unit_id: UnitId) -> tuple[StaffMember, ...]:
        return tuple(
            dataclasses.replace(m, unavailabilities=())
            for m in super().list_active_members(tenant_id, unit_id)
        )


def test_list_members_prevalece_sobre_o_quadro_ativo(world: World) -> None:
    staff = _QuadroDefasado()
    ferias = UnavailabilityWindow(start=at(MONDAY, 0), end=at(MONDAY + timedelta(days=2), 0))
    staff.add_member(T1, member("ana", unavailabilities=(ferias,)), user_id="user-ana")
    staff.add_job_function(T1, JobFunctionEntry(COOK, "Cozinheiro"))
    world.staff = staff
    _seed(world)
    resultado = _evaluate(world).execute(_q(world, ()))
    assert PolicyKind.UNAVAILABILITY in {v.policy for v in resultado.schedule.violations}


def test_ca10_inativo_alocado_nao_gera_violacao_nem_recusa_no_publish(world: World) -> None:
    ferias = UnavailabilityWindow(start=at(MONDAY, 0), end=at(MONDAY + timedelta(days=2), 0))
    world.staff.add_member(T1, member("caio", active=False, unavailabilities=(ferias,)))
    base = (
        schedule("s1")
        .enable_band(_F1, TimeRange(start=at(MONDAY, 10), end=at(MONDAY, 16)))
        .declare_demand(_D1, _F1, COOK, DemandQuantity(1))
        .assign(AssignmentId("a-caio"), _D1, EmployeeId("caio"))
    )
    _seed(world, base)
    avaliado = _evaluate(world).execute(_q(world, (RedeclareBandBreak(_F1, 30),)))
    assert avaliado.blocking == ()
    assert avaliado.schedule.violations == ()
    publicado = _publish(world).execute(_c(world, (RedeclareBandBreak(_F1, 30),)))
    assert publicado.violations == ()
