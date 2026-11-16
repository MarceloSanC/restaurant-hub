"""Mappers e codec da trilha de scheduling — sem banco (CA05, CA12 e CA13, metade unit).

A fidelidade é comparada por **projeção** (`support.project`): as entidades são iguais por
id, e uma igualdade de entidade não veria um intervalo perdido. O codec da trilha é
conferido por **igualdade e tipo** campo a campo — `Decimal("22.33") == 22.33` é falso, mas
`DemandQuantity(1) == 1` também, e um `str` no lugar de um enum passaria por `==` num
`StrEnum` —, e pelo JSON **literal** de cada tipo, que é contrato de dados (concept §5.6).
"""

import dataclasses
import typing
from datetime import UTC, date, datetime, time, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy import Table

from restaurant_hub.features.scheduling.adapters.out.postgres.mappers import (
    OPERATION_KINDS,
    change_to_row,
    row_to_change,
    row_to_settings,
    rows_to_schedule,
    schedule_to_rows,
)
from restaurant_hub.features.scheduling.adapters.out.postgres.tables import (
    LIMIT_CHECKS,
    POLICY_FIELDS,
    schedule_assignments,
    schedule_bands,
    schedule_changes,
    schedule_demands,
    schedules,
)
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
    WithdrawDemand,
)
from restaurant_hub.features.scheduling.application.ports.out.schedule_repository import (
    ScheduleChange,
)
from restaurant_hub.features.scheduling.domain.entities.schedule import Schedule
from restaurant_hub.features.scheduling.domain.exceptions.errors import (
    DuplicateShiftBandError,
    InvalidDayCutoffError,
    InvalidDemandQuantityError,
    InvalidSchedulePeriodError,
    InvalidTimeRangeError,
    InvalidWeekdayError,
)
from restaurant_hub.features.scheduling.domain.value_objects.demand_quantity import (
    DemandQuantity,
)
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
from restaurant_hub.features.scheduling.domain.value_objects.operational_calendar import (
    DayCutoff,
    OperationalCalendar,
    Weekday,
)
from restaurant_hub.features.scheduling.domain.value_objects.schedule_period import (
    SchedulePeriod,
)
from restaurant_hub.features.scheduling.domain.value_objects.time_range import TimeRange
from restaurant_hub.features.scheduling.domain.value_objects.validation_config import (
    EnforcementMode,
    PolicyKind,
    ValidationConfig,
    WorkloadDirection,
)
from restaurant_hub.features.scheduling.domain.value_objects.violation import Violation
from tests.contract.features.scheduling.support import project

pytestmark = pytest.mark.unit

_QUA = date(2026, 11, 4)  # quarta-feira
_QUANDO = datetime(2026, 11, 1, 12, 0, tzinfo=UTC)


def _faixa(dia: date, hora: int, *, horas: int = 4, intervalo: int = 0) -> TimeRange:
    inicio = datetime.combine(dia, time(hora))
    return TimeRange(start=inicio, end=inicio + timedelta(hours=horas), break_minutes=intervalo)


def _escala_rica() -> Schedule:
    """Três itens por nível fora da ordem dos ids; período ≠ 7 e calendário não-default."""
    escala = Schedule(
        id=ScheduleId("s1"),
        tenant_id=TenantId("t1"),
        unit_id=UnitId("u1"),
        period=SchedulePeriod(first_day=_QUA, days=10),
        calendar=OperationalCalendar(week_start=Weekday.WEDNESDAY, day_cutoff=DayCutoff(time(4))),
    )
    ultimo = _QUA + timedelta(days=9)
    return (
        escala.enable_band(ShiftBandId("f3"), _faixa(_QUA, 10, intervalo=30))
        .enable_band(ShiftBandId("f1"), _faixa(_QUA, 22))  # cruza a meia-noite
        .enable_band(ShiftBandId("f2"), _faixa(ultimo, 23))  # termina depois do último dia
        .declare_demand(
            ShiftDemandId("d3"), ShiftBandId("f3"), JobFunctionId("cozinheiro"), DemandQuantity(2)
        )
        .declare_demand(
            ShiftDemandId("d1"), ShiftBandId("f3"), JobFunctionId("atendente"), DemandQuantity(0)
        )
        .declare_demand(
            ShiftDemandId("d2"), ShiftBandId("f3"), JobFunctionId("caixa"), DemandQuantity(1)
        )
        .assign(AssignmentId("a3"), ShiftDemandId("d3"), EmployeeId("ana"), function_exception=True)
        .assign(
            AssignmentId("a1"), ShiftDemandId("d3"), EmployeeId("bia"), counts_toward_workload=False
        )
        .assign(AssignmentId("a2"), ShiftDemandId("d3"), EmployeeId("caio"))
        .declare_allocation_break(AssignmentId("a1"), 0)
        .declare_allocation_break(AssignmentId("a2"), 15)
    )


def _ns(linha: dict[str, Any]) -> SimpleNamespace:
    return SimpleNamespace(**linha)


def _reidratar(escala: Schedule, *, invertida: bool = True) -> Schedule:
    """Ida e volta pelas linhas, com as filhas na ordem **inversa** — a ordem vem de `position`."""
    linhas = schedule_to_rows(escala)

    def ordem(itens: tuple[dict[str, Any], ...]) -> list[SimpleNamespace]:
        return [_ns(item) for item in (reversed(itens) if invertida else itens)]

    return rows_to_schedule(
        _ns(linhas.root), ordem(linhas.bands), ordem(linhas.demands), ordem(linhas.assignments)
    )


# ---------------------------------------------------------------------------
# Agregado ↔ linhas (CA12, metade unit)
# ---------------------------------------------------------------------------


def _colunas(tabela: Table) -> set[str]:
    return {coluna.name for coluna in tabela.columns}


def test_as_linhas_tem_exatamente_as_colunas_das_tabelas() -> None:
    linhas = schedule_to_rows(_escala_rica())
    assert set(linhas.root) == _colunas(schedules)
    for linha in linhas.bands:
        assert set(linha) == _colunas(schedule_bands)
    for linha in linhas.demands:
        assert set(linha) == _colunas(schedule_demands)
    for linha in linhas.assignments:
        assert set(linha) == _colunas(schedule_assignments)


def test_toda_filha_carrega_o_endereco_e_a_escala() -> None:
    """O cerco: tenant, unidade e escala em toda linha de filha."""
    linhas = schedule_to_rows(_escala_rica())
    for linha in (*linhas.bands, *linhas.demands, *linhas.assignments):
        assert (linha["tenant_id"], linha["unit_id"], linha["schedule_id"]) == ("t1", "u1", "s1")


def test_position_e_a_posicao_na_tupla_do_pai() -> None:
    linhas = schedule_to_rows(_escala_rica())
    assert [(b["id"], b["position"]) for b in linhas.bands] == [("f3", 0), ("f1", 1), ("f2", 2)]
    assert [(d["id"], d["band_id"], d["position"]) for d in linhas.demands] == [
        ("d3", "f3", 0),
        ("d1", "f3", 1),
        ("d2", "f3", 2),
    ]
    assert [(a["id"], a["demand_id"], a["position"]) for a in linhas.assignments] == [
        ("a3", "d3", 0),
        ("a1", "d3", 1),
        ("a2", "d3", 2),
    ]


def test_valores_da_raiz_e_tipos_das_colunas() -> None:
    raiz = schedule_to_rows(_escala_rica()).root
    assert raiz == {
        "id": "s1",
        "tenant_id": "t1",
        "unit_id": "u1",
        "first_day": _QUA,
        "days": 10,
        "week_start": "wednesday",
        "day_cutoff": time(4),
        "version": _escala_rica().version,
    }
    assert type(raiz["week_start"]) is str


@pytest.mark.parametrize("invertida", [True, False])
def test_ida_e_volta_preserva_conteudo_e_ordem_nos_tres_niveis(invertida: bool) -> None:
    escala = _escala_rica()
    lida = _reidratar(escala, invertida=invertida)
    assert project(lida) == project(escala)
    assert type(lida.calendar.week_start) is Weekday
    (_, _, alocacao) = lida.locate_assignment(AssignmentId("a1"))
    assert alocacao.break_minutes == 0
    (_, _, herda) = lida.locate_assignment(AssignmentId("a3"))
    assert herda.break_minutes is None


def test_escala_sem_faixas_volta_sem_faixas() -> None:
    vazia = Schedule(
        id=ScheduleId("s0"),
        tenant_id=TenantId("t1"),
        unit_id=UnitId("u1"),
        period=SchedulePeriod(first_day=date(2026, 11, 2)),
        calendar=OperationalCalendar.default(),
    )
    assert project(_reidratar(vazia)) == project(vazia)


def _linhas_corrompidas(
    tabela: str, **alteracao: object
) -> tuple[SimpleNamespace, list[SimpleNamespace], list[SimpleNamespace], list[SimpleNamespace]]:
    linhas = schedule_to_rows(_escala_rica())
    raiz = dict(linhas.root)
    faixas = [dict(b) for b in linhas.bands]
    demandas = [dict(d) for d in linhas.demands]
    alocacoes = [dict(a) for a in linhas.assignments]
    alvo = {"schedules": [raiz], "bands": faixas, "demands": demandas, "assignments": alocacoes}
    alvo[tabela][0].update(alteracao)
    return (
        _ns(raiz),
        [_ns(b) for b in faixas],
        [_ns(d) for d in demandas],
        [_ns(a) for a in alocacoes],
    )


@pytest.mark.parametrize(
    ("tabela", "alteracao", "erro"),
    [
        ("schedules", {"week_start": "segunda"}, InvalidWeekdayError),
        ("schedules", {"day_cutoff": time(4, 0, 30)}, InvalidDayCutoffError),
        ("schedules", {"week_start": "monday"}, InvalidSchedulePeriodError),  # desalinhado
        ("bands", {"end_at": datetime.combine(_QUA, time(10))}, InvalidTimeRangeError),
        (
            "bands",  # mesmo (início, fim) da f1: o schema não vê, o agregado recusa
            {"start_at": datetime.combine(_QUA, time(22)), "end_at": datetime(2026, 11, 5, 2)},
            DuplicateShiftBandError,
        ),
        ("demands", {"quantity": -1}, InvalidDemandQuantityError),
    ],
    ids=[
        "dia-da-semana",
        "corte-com-segundos",
        "desalinhado",
        "faixa-vazia",
        "faixa-repetida",
        "quantidade",
    ],
)
def test_linha_corrompida_levanta_a_excecao_de_dominio_ao_ser_lida(
    tabela: str, alteracao: dict[str, object], erro: type[Exception]
) -> None:
    with pytest.raises(erro):
        rows_to_schedule(*_linhas_corrompidas(tabela, **alteracao))


# ---------------------------------------------------------------------------
# Configuração (CA13, metade unit)
# ---------------------------------------------------------------------------

# Limites distintos dois a dois e distintos dos defaults: coluna trocada não passa.
_LIMITES = {
    "min_rest_minutes": 601,
    "daily_cap_minutes": 602,
    "weekly_cap_minutes": 2603,
    "workload_tolerance_minutes": 4,
}


def _linha_de_configuracao(**alteracao: object) -> SimpleNamespace:
    linha: dict[str, object] = {
        "tenant_id": "t1",
        "week_start": "sunday",
        "day_cutoff": time(3, 30),
        "workload_direction": "both",
        **_LIMITES,
    }
    for policy in POLICY_FIELDS:
        linha[f"{policy}_enabled"] = True
        linha[f"{policy}_mode"] = "warn"
    linha.update(alteracao)
    return SimpleNamespace(**linha)


def test_configuracao_lida_campo_a_campo() -> None:
    lida = row_to_settings(_linha_de_configuracao())
    assert lida.calendar == OperationalCalendar(
        week_start=Weekday.SUNDAY, day_cutoff=DayCutoff(time(3, 30))
    )
    assert type(lida.calendar.week_start) is Weekday
    validacao = lida.validation
    assert {name: getattr(validacao, name) for name, _ in LIMIT_CHECKS} == _LIMITES
    assert validacao.workload_direction is WorkloadDirection.BOTH
    for policy in POLICY_FIELDS:
        regra = getattr(validacao, policy)
        assert (regra.enabled, regra.mode) == (True, EnforcementMode.WARN)
        assert regra.mode is EnforcementMode.WARN


@pytest.mark.parametrize("politica", POLICY_FIELDS)
def test_cada_politica_le_as_proprias_colunas(politica: str) -> None:
    """Só ela difere das demais, na habilitação e no modo: coluna trocada reprova."""
    lida = row_to_settings(
        _linha_de_configuracao(**{f"{politica}_enabled": False, f"{politica}_mode": "block"})
    )
    for policy in POLICY_FIELDS:
        regra = getattr(lida.validation, policy)
        esperado = (
            (False, EnforcementMode.BLOCK) if policy == politica else (True, EnforcementMode.WARN)
        )
        assert (regra.enabled, regra.mode) == esperado, policy


def test_as_politicas_e_os_limites_cobrem_validation_config_inteira() -> None:
    campos = {f.name for f in dataclasses.fields(ValidationConfig)}
    assert campos == {*POLICY_FIELDS, *(name for name, _ in LIMIT_CHECKS), "workload_direction"}


def test_corte_com_segundos_levanta_ao_ser_lido() -> None:
    """A `CHECK` não expressa minuto inteiro; o construtor de `DayCutoff` barra."""
    with pytest.raises(InvalidDayCutoffError):
        row_to_settings(_linha_de_configuracao(day_cutoff=time(3, 30, 15)))


def test_valor_desconhecido_levanta_ao_ser_lido() -> None:
    with pytest.raises(InvalidWeekdayError):
        row_to_settings(_linha_de_configuracao(week_start="domingo"))
    with pytest.raises(ValueError, match="BLOCK"):
        row_to_settings(_linha_de_configuracao(overlap_mode="BLOCK"))


# ---------------------------------------------------------------------------
# Codec da trilha (CA05, metade unit)
# ---------------------------------------------------------------------------

_INICIO = datetime(2026, 11, 2, 10)
_FIM = datetime(2026, 11, 2, 14)

# Um exemplar de cada operação, com valores não-default, e o JSON literal de §5.6.
_EXEMPLARES: tuple[tuple[ScheduleOperation, dict[str, object]], ...] = (
    (
        EnableBand(ShiftBandId("f1"), TimeRange(start=_INICIO, end=_FIM, break_minutes=30)),
        {
            "kind": "enable_band",
            "band_id": "f1",
            "start": "2026-11-02T10:00:00",
            "end": "2026-11-02T14:00:00",
            "break_minutes": 30,
        },
    ),
    (
        RescheduleBand(ShiftBandId("f1"), _INICIO + timedelta(hours=1), _FIM + timedelta(hours=1)),
        {
            "kind": "reschedule_band",
            "band_id": "f1",
            "start": "2026-11-02T11:00:00",
            "end": "2026-11-02T15:00:00",
        },
    ),
    (
        RedeclareBandBreak(ShiftBandId("f1"), 45),
        {"kind": "redeclare_band_break", "band_id": "f1", "break_minutes": 45},
    ),
    (DisableBand(ShiftBandId("f2")), {"kind": "disable_band", "band_id": "f2"}),
    (
        DeclareDemand(
            ShiftDemandId("d1"), ShiftBandId("f1"), JobFunctionId("cozinheiro"), DemandQuantity(0)
        ),
        {
            "kind": "declare_demand",
            "demand_id": "d1",
            "band_id": "f1",
            "job_function_id": "cozinheiro",
            "quantity": 0,
        },
    ),
    (
        ChangeDemandQuantity(ShiftDemandId("d1"), DemandQuantity(3)),
        {"kind": "change_demand_quantity", "demand_id": "d1", "quantity": 3},
    ),
    (WithdrawDemand(ShiftDemandId("d9")), {"kind": "withdraw_demand", "demand_id": "d9"}),
    (
        AssignEmployee(
            AssignmentId("a1"), ShiftDemandId("d1"), EmployeeId("ana"), counts_toward_workload=False
        ),
        {
            "kind": "assign_employee",
            "assignment_id": "a1",
            "demand_id": "d1",
            "employee_id": "ana",
            "counts_toward_workload": False,
            "function_exception": None,
        },
    ),
    (UnassignEmployee(AssignmentId("a9")), {"kind": "unassign_employee", "assignment_id": "a9"}),
    (
        DeclareWorkloadCounting(AssignmentId("a1"), counts=False),
        {"kind": "declare_workload_counting", "assignment_id": "a1", "counts": False},
    ),
    (
        DeclareAllocationBreak(AssignmentId("a1"), None),
        {"kind": "declare_allocation_break", "assignment_id": "a1", "break_minutes": None},
    ),
    (
        DeclareAllocationBreak(AssignmentId("a1"), 0),
        {"kind": "declare_allocation_break", "assignment_id": "a1", "break_minutes": 0},
    ),
)

_SOBRE_COBERTURA = Violation(
    policy=PolicyKind.OVER_COVERAGE,
    mode=EnforcementMode.WARN,
    employee_id=None,
    demand_id=ShiftDemandId("d1"),
    operational_days=(date(2026, 11, 2),),
    assignment_ids=frozenset({AssignmentId("a2"), AssignmentId("a1")}),
    observed=Decimal("3"),
    limit=Decimal("2"),
)
_CARGA = Violation(
    policy=PolicyKind.WORKLOAD,
    mode=EnforcementMode.BLOCK,
    employee_id=EmployeeId("ana"),
    demand_id=None,
    operational_days=(date(2026, 11, 2), date(2026, 11, 3), date(2026, 11, 8)),
    assignment_ids=frozenset(),
    observed=Decimal("22.33"),
    limit=Decimal("40"),
)
_JSON_SOBRE_COBERTURA = {
    "policy": "over_coverage",
    "mode": "warn",
    "employee_id": None,
    "demand_id": "d1",
    "operational_days": ["2026-11-02"],
    "assignment_ids": ["a1", "a2"],
    "observed": "3",
    "limit": "2",
}
_JSON_CARGA = {
    "policy": "workload",
    "mode": "block",
    "employee_id": "ana",
    "demand_id": None,
    "operational_days": ["2026-11-02", "2026-11-03", "2026-11-08"],
    "assignment_ids": [],
    "observed": "22.33",
    "limit": "40",
}


def _escala_vazia() -> Schedule:
    return Schedule(
        id=ScheduleId("s1"),
        tenant_id=TenantId("t1"),
        unit_id=UnitId("u1"),
        period=SchedulePeriod(first_day=date(2026, 11, 2)),
        calendar=OperationalCalendar.default(),
        version=4,
    )


def _mudanca(
    operacoes: tuple[ScheduleOperation, ...] = (), aceites: tuple[Violation, ...] = ()
) -> ScheduleChange:
    return ScheduleChange(
        author_user_id="user-ger",
        occurred_at=_QUANDO,
        previous_version=3,
        operations=operacoes,
        acknowledged=aceites,
    )


def _campos(valor: object) -> list[tuple[str, object, type]]:
    """Campo a campo, com o tipo — `==` sozinho aceitaria `str` no lugar de `StrEnum`."""
    assert dataclasses.is_dataclass(valor)
    return [
        (campo.name, getattr(valor, campo.name), type(getattr(valor, campo.name)))
        for campo in dataclasses.fields(valor)
    ]


def test_o_mapa_de_kind_cobre_a_uniao_de_operacoes_e_os_literais_sao_os_de_5_6() -> None:
    assert set(OPERATION_KINDS) == set(typing.get_args(ScheduleOperation))
    assert {kind for _, json in _EXEMPLARES for kind in [json["kind"]]} == set(
        OPERATION_KINDS.values()
    )


@pytest.mark.parametrize(("operacao", "json"), _EXEMPLARES, ids=lambda v: type(v).__name__)
def test_cada_operacao_grava_o_json_literal_de_5_6(
    operacao: ScheduleOperation, json: dict[str, object]
) -> None:
    linha = change_to_row(_escala_vazia(), _mudanca((operacao,)), seq=1)
    assert linha["operations"] == [json]


@pytest.mark.parametrize(("operacao", "json"), _EXEMPLARES, ids=lambda v: type(v).__name__)
def test_cada_operacao_volta_com_igualdade_e_tipo(
    operacao: ScheduleOperation, json: dict[str, object]
) -> None:
    linha = change_to_row(_escala_vazia(), _mudanca((operacao,)), seq=1)
    (lida,) = row_to_change(_ns(linha)).operations
    assert type(lida) is type(operacao)
    assert _campos(lida) == _campos(operacao)
    # E o literal fixo de §5.6, lido de volta, dá a mesma operação.
    (do_literal,) = row_to_change(_ns({**linha, "operations": [json]})).operations
    assert _campos(do_literal) == _campos(operacao)


def test_violacoes_gravam_o_json_literal_e_voltam_com_igualdade_e_tipo() -> None:
    linha = change_to_row(_escala_vazia(), _mudanca(aceites=(_SOBRE_COBERTURA, _CARGA)), seq=1)
    assert linha["acknowledged"] == [_JSON_SOBRE_COBERTURA, _JSON_CARGA]
    lidas = row_to_change(_ns(linha)).acknowledged
    assert lidas == (_SOBRE_COBERTURA, _CARGA)
    for lida, original in zip(lidas, (_SOBRE_COBERTURA, _CARGA), strict=True):
        assert _campos(lida) == _campos(original)
        assert all(type(a) is str for a in lida.assignment_ids)
        assert all(type(d) is date for d in lida.operational_days)
    assert lidas[1].observed.as_tuple() == Decimal("22.33").as_tuple()


def test_a_linha_da_trilha_carrega_seq_autor_instante_e_as_duas_versoes() -> None:
    linha = change_to_row(_escala_vazia(), _mudanca(), seq=7)
    assert set(linha) == {coluna.name for coluna in schedule_changes.columns}
    assert {k: v for k, v in linha.items() if k not in {"operations", "acknowledged"}} == {
        "schedule_id": "s1",
        "seq": 7,
        "author_user_id": "user-ger",
        "occurred_at": _QUANDO,
        "previous_version": 3,
        "resulting_version": 4,
    }
    assert (linha["operations"], linha["acknowledged"]) == ([], [])


def test_criacao_tem_versao_anterior_nula() -> None:
    criacao = dataclasses.replace(_mudanca(), previous_version=None)
    assert change_to_row(_escala_vazia(), criacao, seq=1)["previous_version"] is None


def test_a_mudanca_volta_igual_com_o_instante_em_utc() -> None:
    mudanca = _mudanca(tuple(op for op, _ in _EXEMPLARES), (_CARGA,))
    linha = change_to_row(_escala_vazia(), mudanca, seq=1)
    em_sao_paulo = linha["occurred_at"].astimezone(timezone(timedelta(hours=-3)))
    lida = row_to_change(_ns({**linha, "occurred_at": em_sao_paulo}))
    assert lida == mudanca
    assert lida.occurred_at.tzinfo is UTC


def test_o_leitor_ignora_chave_desconhecida_e_recusa_kind_desconhecido() -> None:
    linha = change_to_row(_escala_vazia(), _mudanca((DisableBand(ShiftBandId("f2")),)), seq=1)
    linha["operations"][0]["motivo"] = "chave do futuro"
    linha["acknowledged"] = [{**_JSON_CARGA, "severidade": 9}]
    lida = row_to_change(_ns(linha))
    assert lida.operations == (DisableBand(ShiftBandId("f2")),)
    assert lida.acknowledged == (_CARGA,)
    with pytest.raises(ValueError, match="teleport_band"):
        row_to_change(_ns({**linha, "operations": [{"kind": "teleport_band"}]}))


# --- a marca `function_exception` de `assign_employee` (CA05 c) -------------------------


def _escala_com_alocacoes() -> Schedule:
    base = _escala_vazia()
    return (
        base.enable_band(ShiftBandId("f1"), _faixa(base.period.first_day, 10))
        .declare_demand(
            ShiftDemandId("d1"), ShiftBandId("f1"), JobFunctionId("cozinheiro"), DemandQuantity(3)
        )
        .assign(AssignmentId("a1"), ShiftDemandId("d1"), EmployeeId("ana"), function_exception=True)
        .assign(AssignmentId("a2"), ShiftDemandId("d1"), EmployeeId("bia"))
    )


def _aloca(aid: str, empregado: str) -> AssignEmployee:
    return AssignEmployee(AssignmentId(aid), ShiftDemandId("d1"), EmployeeId(empregado))


def _marcas(escala: Schedule, operacoes: tuple[ScheduleOperation, ...]) -> list[object]:
    linha = change_to_row(escala, _mudanca(operacoes), seq=2)
    return [
        item["function_exception"]
        for item in linha["operations"]
        if item["kind"] == "assign_employee"
    ]


def test_assign_employee_grava_a_marca_da_escala() -> None:
    """`true` e `false` lidos da escala gravada; `null` quando a alocação não está nela."""
    escala = _escala_com_alocacoes()
    operacoes = (_aloca("a1", "ana"), _aloca("a2", "bia"), _aloca("a3", "caio"))
    assert _marcas(escala, operacoes) == [True, False, None]


def test_alocar_desalocar_e_alocar_de_novo_marca_so_o_ultimo() -> None:
    escala = _escala_com_alocacoes()
    operacoes = (_aloca("a1", "dani"), UnassignEmployee(AssignmentId("a1")), _aloca("a1", "ana"))
    assert _marcas(escala, operacoes) == [None, True]


def test_alocacao_desfeita_no_fim_do_lote_fica_sem_marca() -> None:
    escala = _escala_com_alocacoes()
    operacoes = (_aloca("a1", "ana"), UnassignEmployee(AssignmentId("a1")))
    assert _marcas(escala, operacoes) == [None]


def test_o_leitor_ignora_a_marca_ao_remontar_a_operacao() -> None:
    escala = _escala_com_alocacoes()
    linha = change_to_row(escala, _mudanca((_aloca("a1", "ana"),)), seq=2)
    assert linha["operations"][0]["function_exception"] is True
    assert row_to_change(_ns(linha)).operations == (_aloca("a1", "ana"),)
