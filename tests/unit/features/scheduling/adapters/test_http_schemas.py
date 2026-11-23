"""Schemas e conversores da borda de scheduling (Stage 4.5, concept §4.2 e §6).

Cobre: a forma dos requests (união por `op`, `extra="forbid"` nas variantes, inteiros e
booleanos estritos, teto do lote), a ausência de tenant e de usuário nos requests (CA9), os
conversores de operação e de aceite com cada recusa da §6 (id, UUID, quantidade, decimal,
política, instante extremo, offset) e as respostas (instantes sem offset, decimais em texto,
`key` de aceite).
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Any

import pytest
from pydantic import BaseModel, TypeAdapter, ValidationError

from restaurant_hub.features.scheduling.adapters.inbound.http import schemas
from restaurant_hub.features.scheduling.adapters.inbound.http.schemas import (
    MAX_BATCH,
    MAX_QUANTITY,
    AcknowledgementPayload,
    EvaluateScheduleRequest,
    OperationPayload,
    PublishScheduleRequest,
    ViolationResponse,
    check_acknowledgement_identifiers,
    check_operation_identifiers,
    to_acknowledgement,
    to_operation,
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
    UnassignEmployee,
    WithdrawDemand,
)
from restaurant_hub.features.scheduling.application.errors import InvalidScheduleRequestError
from restaurant_hub.features.scheduling.domain.exceptions.errors import (
    InvalidDemandQuantityError,
    InvalidIdentifierError,
    InvalidTimeRangeError,
)
from restaurant_hub.features.scheduling.domain.value_objects.identifiers import (
    AssignmentId,
    EmployeeId,
    ShiftDemandId,
)
from restaurant_hub.features.scheduling.domain.value_objects.validation_config import (
    EnforcementMode,
    PolicyKind,
)
from restaurant_hub.features.scheduling.domain.value_objects.violation import Violation

pytestmark = pytest.mark.unit

_B, _D, _A = (
    "11111111-1111-4111-8111-111111111111",
    "22222222-2222-4222-8222-222222222222",
    "33333333-3333-4333-8333-333333333333",
)
_OPERACAO: TypeAdapter[Any] = TypeAdapter(OperationPayload)

# Uma operação válida de cada tipo — o domínio do teste de totalidade abaixo.
OPERACOES_VALIDAS: dict[str, dict[str, object]] = {
    "enable_band": {
        "op": "enable_band",
        "band_id": _B,
        "start": "2026-12-07T08:00:00",
        "end": "2026-12-07T16:00:00",
        "break_minutes": 60,
    },
    "reschedule_band": {
        "op": "reschedule_band",
        "band_id": "f1",
        "start": "2026-12-07T09:00:00",
        "end": "2026-12-07T16:00:00",
    },
    "redeclare_band_break": {"op": "redeclare_band_break", "band_id": "f1", "break_minutes": 30},
    "disable_band": {"op": "disable_band", "band_id": "f1"},
    "declare_demand": {
        "op": "declare_demand",
        "demand_id": _D,
        "band_id": _B,
        "job_function_id": "cook",
        "quantity": 2,
    },
    "change_demand_quantity": {"op": "change_demand_quantity", "demand_id": "d1", "quantity": 3},
    "withdraw_demand": {"op": "withdraw_demand", "demand_id": "d1"},
    "assign_employee": {
        "op": "assign_employee",
        "assignment_id": _A,
        "demand_id": _D,
        "employee_id": "emp-1",
        "counts_toward_workload": False,
    },
    "unassign_employee": {"op": "unassign_employee", "assignment_id": "a1"},
    "declare_workload_counting": {
        "op": "declare_workload_counting",
        "assignment_id": "a1",
        "counts": False,
    },
    "declare_allocation_break": {
        "op": "declare_allocation_break",
        "assignment_id": "a1",
        "break_minutes": 15,
    },
}

_DTO_POR_OP = {
    "enable_band": EnableBand,
    "reschedule_band": RescheduleBand,
    "redeclare_band_break": RedeclareBandBreak,
    "disable_band": DisableBand,
    "declare_demand": DeclareDemand,
    "change_demand_quantity": ChangeDemandQuantity,
    "withdraw_demand": WithdrawDemand,
    "assign_employee": AssignEmployee,
    "unassign_employee": UnassignEmployee,
    "declare_workload_counting": DeclareWorkloadCounting,
    "declare_allocation_break": DeclareAllocationBreak,
}


def _op(nome: str, **mudancas: object) -> Any:  # noqa: ANN401 — a variante da união
    return _OPERACAO.validate_python({**OPERACOES_VALIDAS[nome], **mudancas})


def test_ha_uma_operacao_valida_por_variante_da_uniao() -> None:
    """Totalidade: cada `op` da união tem caso feliz aqui e DTO correspondente."""
    variantes = {
        m.model_fields["op"].annotation.__args__[0]  # type: ignore[union-attr]
        for m in schemas.OperationPayload.__origin__.__args__  # type: ignore[attr-defined]
    }
    assert variantes == set(OPERACOES_VALIDAS) == set(_DTO_POR_OP)


@pytest.mark.parametrize("nome", sorted(OPERACOES_VALIDAS))
def test_cada_operacao_valida_vira_o_dto_da_4_3(nome: str) -> None:
    op = _op(nome)
    check_operation_identifiers([op])
    dto = to_operation(op)
    assert type(dto) is _DTO_POR_OP[nome]
    # Campo a campo: o que o cliente mandou é o que o DTO carrega (Checkpoint C, bloco 04–06 —
    # um valor fixo no conversor descartaria a escolha do cliente sem reprovar o tipo).
    for campo, valor in OPERACOES_VALIDAS[nome].items():
        if campo in {"op", "start", "end", "break_minutes", "quantity"} and nome in {
            "enable_band",
            "declare_demand",
            "change_demand_quantity",
        }:
            continue
        if campo == "op":
            continue
        assert getattr(dto, campo) == (
            datetime.fromisoformat(valor) if campo in {"start", "end"} else valor
        ), (nome, campo)


def test_intervalo_nulo_da_alocacao_volta_a_herdar() -> None:
    dto = to_operation(_op("declare_allocation_break", break_minutes=None))
    assert dto.break_minutes is None  # type: ignore[union-attr]


@pytest.mark.parametrize("nome", ["declare_demand", "change_demand_quantity"])
def test_a_quantidade_do_cliente_chega_ao_dto(nome: str) -> None:
    dto = to_operation(_op(nome, quantity=7))
    assert dto.quantity.value == 7  # type: ignore[union-attr]  # noqa: PLR2004


def test_enable_band_carrega_o_time_range_com_o_intervalo() -> None:
    dto = to_operation(_op("enable_band"))
    assert isinstance(dto, EnableBand)
    assert (dto.time_range.start, dto.time_range.end, dto.time_range.break_minutes) == (
        datetime(2026, 12, 7, 8),
        datetime(2026, 12, 7, 16),
        60,
    )


@pytest.mark.parametrize("nome", sorted(OPERACOES_VALIDAS))
def test_campo_a_mais_numa_operacao_e_recusado_pelo_schema(nome: str) -> None:
    with pytest.raises(ValidationError):
        _op(nome, tenant_id="t2")


@pytest.mark.parametrize(
    ("nome", "campo", "valor"),
    [
        ("declare_demand", "quantity", True),
        ("declare_demand", "quantity", 1.0),
        ("change_demand_quantity", "quantity", "2"),
        ("redeclare_band_break", "break_minutes", False),
        ("declare_workload_counting", "counts", 0),
        ("assign_employee", "counts_toward_workload", "true"),
    ],
)
def test_inteiros_e_booleanos_sao_estritos(nome: str, campo: str, valor: object) -> None:
    with pytest.raises(ValidationError):
        _op(nome, **{campo: valor})


def test_op_desconhecida_e_recusada_pelo_schema() -> None:
    with pytest.raises(ValidationError):
        _OPERACAO.validate_python({"op": "delete_schedule"})


@pytest.mark.parametrize("modelo", [EvaluateScheduleRequest, PublishScheduleRequest])
def test_o_lote_acima_de_500_e_recusado(modelo: type[BaseModel]) -> None:
    op = OPERACOES_VALIDAS["disable_band"]
    modelo.model_validate({"expected_version": 1, "operations": [op] * MAX_BATCH})
    with pytest.raises(ValidationError):
        modelo.model_validate({"expected_version": 1, "operations": [op] * (MAX_BATCH + 1)})


def _aceite(**mudancas: object) -> dict[str, object]:
    base: dict[str, object] = {
        "key": {
            "policy": "over_coverage",
            "employee_id": None,
            "demand_id": "d1",
            "operational_days": ["2026-12-08", "2026-12-07"],
            "assignment_ids": ["a2", "a1"],
        },
        "observed": "3",
        "limit": "2",
    }
    return {**base, **mudancas}


def test_os_aceites_acima_de_500_sao_recusados() -> None:
    PublishScheduleRequest.model_validate(
        {"expected_version": 1, "operations": [], "acknowledgements": [_aceite()] * MAX_BATCH}
    )
    with pytest.raises(ValidationError):
        PublishScheduleRequest.model_validate(
            {
                "expected_version": 1,
                "operations": [],
                "acknowledgements": [_aceite()] * (MAX_BATCH + 1),
            }
        )


# --- CA9: nenhum request carrega tenant nem usuário --------------------------------------

_PROIBIDOS = {"tenant_id", "tenant", "restaurant_id", "restaurant", "user_id", "actor_id"}


def _modelos_de_request() -> list[type[BaseModel]]:
    return [
        valor
        for nome, valor in vars(schemas).items()
        if isinstance(valor, type)
        and issubclass(valor, BaseModel)
        and valor.__module__ == schemas.__name__
        and (nome.endswith(("Request", "Operation", "Payload")))
    ]


def test_ca9_nenhum_request_tem_tenant_ou_usuario() -> None:
    modelos = _modelos_de_request()
    assert len(modelos) >= 14  # noqa: PLR2004 — 3 requests + 11 operações + 2 de aceite
    culpados = {m.__name__: set(m.model_fields) & _PROIBIDOS for m in modelos}
    assert {k: v for k, v in culpados.items() if v} == {}


# --- identificadores, antes de autorizar --------------------------------------------------


@pytest.mark.parametrize(
    ("nome", "campo"),
    [
        ("enable_band", "band_id"),
        ("declare_demand", "demand_id"),
        ("assign_employee", "assignment_id"),
    ],
)
@pytest.mark.parametrize("valor", ["f1", "", "\x00", "11111111-1111-4111-8111-11111111111A"])
def test_id_de_criacao_fora_do_uuid_canonico_e_recusado(nome: str, campo: str, valor: str) -> None:
    with pytest.raises(InvalidIdentifierError):
        check_operation_identifiers([_op(nome, **{campo: valor})])


@pytest.mark.parametrize(
    ("nome", "campo"),
    [
        ("declare_demand", "band_id"),
        ("declare_demand", "job_function_id"),
        ("assign_employee", "demand_id"),
        ("assign_employee", "employee_id"),
        ("reschedule_band", "band_id"),
        ("redeclare_band_break", "band_id"),
        ("disable_band", "band_id"),
        ("change_demand_quantity", "demand_id"),
        ("withdraw_demand", "demand_id"),
        ("unassign_employee", "assignment_id"),
        ("declare_workload_counting", "assignment_id"),
        ("declare_allocation_break", "assignment_id"),
    ],
)
@pytest.mark.parametrize("valor", ["", "  ", "x\x00"], ids=["vazio", "espaco", "nul"])
def test_id_de_referencia_vazio_espaco_ou_nul_e_recusado(nome: str, campo: str, valor: str) -> None:
    with pytest.raises(InvalidIdentifierError):
        check_operation_identifiers([_op(nome, **{campo: valor})])


@pytest.mark.parametrize(
    ("campo", "valor"),
    [("employee_id", "\x00"), ("demand_id", " "), ("assignment_ids", ["a1", ""])],
)
def test_id_da_key_do_aceite_e_validado(campo: str, valor: object) -> None:
    corpo = _aceite()
    corpo["key"] = {**corpo["key"], campo: valor}  # type: ignore[dict-item]
    with pytest.raises(InvalidIdentifierError):
        check_acknowledgement_identifiers([AcknowledgementPayload.model_validate(corpo)])


# --- valores, depois de autorizar ---------------------------------------------------------


@pytest.mark.parametrize("nome", ["declare_demand", "change_demand_quantity"])
def test_quantidade_acima_do_integer_e_recusada_e_o_teto_passa(nome: str) -> None:
    assert to_operation(_op(nome, quantity=MAX_QUANTITY)) is not None
    with pytest.raises(InvalidScheduleRequestError, match="quantidade"):
        to_operation(_op(nome, quantity=MAX_QUANTITY + 1))


def test_quantidade_negativa_e_do_dominio() -> None:
    with pytest.raises(InvalidDemandQuantityError):
        to_operation(_op("declare_demand", quantity=-1))


@pytest.mark.parametrize("nome", ["enable_band", "reschedule_band"])
@pytest.mark.parametrize("campo", ["start", "end"])
def test_instante_extremo_e_recusado(nome: str, campo: str) -> None:
    with pytest.raises(InvalidScheduleRequestError, match=campo):
        to_operation(_op(nome, **{campo: "0001-01-01T03:00:00"}))


def test_offset_no_limite_da_faixa_e_recusado_pelo_dominio() -> None:
    """D-TIME — valor com `Z` é parseado tz-aware e recusado, nunca convertido."""
    with pytest.raises(InvalidTimeRangeError):
        to_operation(_op("enable_band", start="2026-12-07T08:00:00Z"))


def test_aceite_vira_o_dto_com_a_key_como_ecoada() -> None:
    dto = to_acknowledgement(AcknowledgementPayload.model_validate(_aceite()))
    assert dto.key.policy is PolicyKind.OVER_COVERAGE
    assert dto.key.employee_id is None
    assert dto.key.demand_id == "d1"
    # A borda não reordena os dias (a key compara tupla ordenada).
    assert dto.key.operational_days == (date(2026, 12, 8), date(2026, 12, 7))
    assert dto.key.assignment_ids == frozenset({"a1", "a2"})
    assert (dto.observed, dto.limit) == (Decimal(3), Decimal(2))


@pytest.mark.parametrize(
    ("campo", "valor", "trecho"),
    [
        ("observed", "abc", "observed"),
        ("observed", "NaN", "observed"),
        ("limit", "Infinity", "limit"),
        ("limit", "", "limit"),
        ("observed", "40,5", "observed"),
        ("observed", "1E+1000000", "observed"),
        ("limit", "-9E+999999", "limit"),
        ("observed", "1E+16", "observed"),
        ("limit", "1E-13", "limit"),
    ],
)
def test_medida_malformada_e_422_de_scheduling(campo: str, valor: str, trecho: str) -> None:
    with pytest.raises(InvalidScheduleRequestError, match=trecho):
        to_acknowledgement(AcknowledgementPayload.model_validate(_aceite(**{campo: valor})))


def test_politica_desconhecida_e_422_de_scheduling() -> None:
    corpo = _aceite()
    corpo["key"] = {**corpo["key"], "policy": "overtime"}  # type: ignore[dict-item]
    with pytest.raises(InvalidScheduleRequestError, match="overtime"):
        to_acknowledgement(AcknowledgementPayload.model_validate(corpo))


# --- respostas ----------------------------------------------------------------------------


def _violacao(policy: PolicyKind = PolicyKind.WORKLOAD) -> Violation:
    return Violation(
        policy=policy,
        mode=EnforcementMode.WARN,
        employee_id=EmployeeId("emp-1"),
        demand_id=None,
        operational_days=(date(2026, 12, 7),),
        assignment_ids=frozenset({AssignmentId("a2"), AssignmentId("a1")}),
        observed=Decimal("6.6E+2"),
        limit=Decimal("600"),
    )


def test_violacao_na_resposta_tem_medida_em_texto_e_a_key_de_aceite() -> None:
    corpo = ViolationResponse.from_violation(_violacao()).model_dump(mode="json")
    assert corpo["observed"] == "660"
    assert corpo["limit"] == "600"
    assert corpo["assignment_ids"] == ["a1", "a2"]
    # Política agregada: a key não carrega as alocações (ADR 4.2.0002).
    assert corpo["key"] == {
        "policy": "workload",
        "employee_id": "emp-1",
        "demand_id": None,
        "operational_days": ["2026-12-07"],
        "assignment_ids": [],
    }


def test_a_key_da_resposta_volta_como_aceite_que_cobre_a_violacao() -> None:
    """Ida e volta: o que a resposta mostra é o que o aceite precisa ecoar."""
    violacao = _violacao(PolicyKind.OVER_COVERAGE)
    violacao = Violation(
        policy=violacao.policy,
        mode=violacao.mode,
        employee_id=None,
        demand_id=ShiftDemandId("d1"),
        operational_days=violacao.operational_days,
        assignment_ids=violacao.assignment_ids,
        observed=violacao.observed,
        limit=violacao.limit,
    )
    resposta = ViolationResponse.from_violation(violacao).model_dump(mode="json")
    aceite = to_acknowledgement(
        AcknowledgementPayload.model_validate(
            {"key": resposta["key"], "observed": resposta["observed"], "limit": resposta["limit"]}
        )
    )
    assert aceite.key == violacao.key
    assert (aceite.observed, aceite.limit) == (violacao.observed, violacao.limit)


def test_instante_da_resposta_sai_sem_offset() -> None:
    resposta = schemas.MyShiftResponse(
        schedule_id="s",
        band_id="b",
        assignment_id="a",
        employee_id="e",
        operational_day=date(2026, 12, 7),
        start=datetime(2026, 12, 7, 8),
        end=datetime(2026, 12, 7, 16),
        job_function_id="cook",
        job_function_name=None,
        worked_minutes=480,
    ).model_dump(mode="json")
    assert (resposta["start"], resposta["end"]) == ("2026-12-07T08:00:00", "2026-12-07T16:00:00")
    assert datetime.fromisoformat(resposta["start"]).tzinfo is None
