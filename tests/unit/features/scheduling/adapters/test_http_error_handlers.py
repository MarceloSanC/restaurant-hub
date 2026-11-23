"""O mapa de erros de scheduling, par a par, e os corpos das recusas (Stage 4.5, ADR 4.5.0002).

A totalidade (toda subclasse das duas raízes tem entrada; handler nas duas raízes) é de
`tests/unit/test_status_map.py`. Aqui, o que ela não pega (ADR 3.4.0002 §3b):

- **os pares exatos**, transcritos do concept §6 — dois erros trocando de faixa dentro de
  faixas já exercitadas passariam na totalidade;
- **a lista exata dos `code`** — o `code` é contrato do cliente, e renomear uma classe o muda;
- **os corpos com estado**, atravessando o handler registrado numa app.
"""

from datetime import date
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from restaurant_hub.features.scheduling.adapters.inbound.http.error_handlers import (
    SCHEDULING_ERROR_STATUS,
    error_code,
    register_scheduling_error_handlers,
    resolve_status,
)
from restaurant_hub.features.scheduling.application import errors as app_errors
from restaurant_hub.features.scheduling.domain.exceptions import errors as dom_errors
from restaurant_hub.features.scheduling.domain.value_objects.identifiers import (
    AssignmentId,
    EmployeeId,
)
from restaurant_hub.features.scheduling.domain.value_objects.validation_config import (
    EnforcementMode,
    PolicyKind,
)
from restaurant_hub.features.scheduling.domain.value_objects.violation import Violation

pytestmark = pytest.mark.unit

# Transcrito do concept 4.5 §6 — não colhido do mapa.
_FAIXAS: dict[int, set[str]] = {
    404: {"ScheduleNotFoundError", "StaffMemberNotFoundError", "JobFunctionNotFoundError"},
    409: {
        "ScheduleVersionConflictError",
        "SchedulePeriodTakenError",
        "IdentifierInUseError",
        "InactiveStaffMemberError",
        "JobFunctionNotEnabledInUnitError",
        "InactiveAllocationsInUseError",
        "MissingStaffRecordsError",
        "ShiftBandInUseError",
        "ShiftDemandInUseError",
    },
    422: {
        "BlockingViolationsError",
        "UnacknowledgedViolationsError",
        "InvalidScheduleRequestError",
        "InvalidIdentifierError",
        "InvalidTimeRangeError",
        "InvalidWeekdayError",
        "InvalidDayCutoffError",
        "InvalidSchedulePeriodError",
        "InvalidDemandQuantityError",
        "InvalidScheduleVersionError",
        "InvalidAssignmentBreakError",
        "DuplicateEntityIdError",
        "DuplicateShiftBandError",
        "DuplicateShiftDemandError",
        "DuplicateAssignmentError",
        "DuplicateAssignmentInBandError",
        "ShiftBandNotFoundError",
        "ShiftBandDayChangeError",
        "TimeRangeOutsidePeriodError",
        "ShiftDemandNotFoundError",
        "AssignmentNotFoundError",
        "InvalidValidationConfigError",
        "InvalidEvaluationInputError",
    },
}
_TOTAL_DE_ERROS = 35


def test_as_faixas_transcritas_somam_os_35_erros_do_concept() -> None:
    nomes = [n for grupo in _FAIXAS.values() for n in grupo]
    assert len(nomes) == len(set(nomes)) == _TOTAL_DE_ERROS


@pytest.mark.parametrize(
    ("nome", "faixa"), sorted((n, f) for f, grupo in _FAIXAS.items() for n in grupo)
)
def test_par_a_par(nome: str, faixa: int) -> None:
    classe = getattr(app_errors, nome, None) or getattr(dom_errors, nome)
    assert SCHEDULING_ERROR_STATUS[classe] == faixa


def test_o_mapa_tem_exatamente_os_35_pares() -> None:
    assert {c.__name__ for c in SCHEDULING_ERROR_STATUS} == {
        n for grupo in _FAIXAS.values() for n in grupo
    }


def test_nenhuma_entrada_401_ou_403() -> None:
    """L-SG1: as faixas 401/403 são de identity, de corpo constante."""
    assert not {401, 403} & set(SCHEDULING_ERROR_STATUS.values())


# A lista exata dos `code` — contrato do cliente (ADR 4.5.0002 §Decision 4).
_CODES = {
    "ScheduleNotFoundError": "schedule_not_found",
    "StaffMemberNotFoundError": "staff_member_not_found",
    "JobFunctionNotFoundError": "job_function_not_found",
    "ScheduleVersionConflictError": "schedule_version_conflict",
    "SchedulePeriodTakenError": "schedule_period_taken",
    "IdentifierInUseError": "identifier_in_use",
    "InactiveStaffMemberError": "inactive_staff_member",
    "JobFunctionNotEnabledInUnitError": "job_function_not_enabled_in_unit",
    "InactiveAllocationsInUseError": "inactive_allocations_in_use",
    "MissingStaffRecordsError": "missing_staff_records",
    "ShiftBandInUseError": "shift_band_in_use",
    "ShiftDemandInUseError": "shift_demand_in_use",
    "BlockingViolationsError": "blocking_violations",
    "UnacknowledgedViolationsError": "unacknowledged_violations",
    "InvalidScheduleRequestError": "invalid_schedule_request",
    "InvalidIdentifierError": "invalid_identifier",
    "InvalidTimeRangeError": "invalid_time_range",
    "InvalidWeekdayError": "invalid_weekday",
    "InvalidDayCutoffError": "invalid_day_cutoff",
    "InvalidSchedulePeriodError": "invalid_schedule_period",
    "InvalidDemandQuantityError": "invalid_demand_quantity",
    "InvalidScheduleVersionError": "invalid_schedule_version",
    "InvalidAssignmentBreakError": "invalid_assignment_break",
    "DuplicateEntityIdError": "duplicate_entity_id",
    "DuplicateShiftBandError": "duplicate_shift_band",
    "DuplicateShiftDemandError": "duplicate_shift_demand",
    "DuplicateAssignmentError": "duplicate_assignment",
    "DuplicateAssignmentInBandError": "duplicate_assignment_in_band",
    "ShiftBandNotFoundError": "shift_band_not_found",
    "ShiftBandDayChangeError": "shift_band_day_change",
    "TimeRangeOutsidePeriodError": "time_range_outside_period",
    "ShiftDemandNotFoundError": "shift_demand_not_found",
    "AssignmentNotFoundError": "assignment_not_found",
    "InvalidValidationConfigError": "invalid_validation_config",
    "InvalidEvaluationInputError": "invalid_evaluation_input",
}


def test_a_lista_de_codes_e_exata() -> None:
    derivados = {}
    for classe in SCHEDULING_ERROR_STATUS:
        instancia = classe.__new__(classe)
        derivados[classe.__name__] = error_code(instancia)
    assert derivados == _CODES


def test_resolve_status_herda_do_pai_para_subclasse_nao_classificada() -> None:
    class _Nova(app_errors.ScheduleNotFoundError):
        pass

    assert resolve_status(_Nova("s1")) == 404  # noqa: PLR2004


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    register_scheduling_error_handlers(app)

    @app.get("/levanta/{caso}")
    def levanta(caso: str) -> None:
        raise _CASOS[caso]

    return TestClient(app)


def _violacao() -> Violation:
    return Violation(
        policy=PolicyKind.OVER_COVERAGE,
        mode=EnforcementMode.WARN,
        employee_id=None,
        demand_id=None,
        operational_days=(date(2026, 12, 7),),
        assignment_ids=frozenset({AssignmentId("a1")}),
        observed=Decimal(3),
        limit=Decimal(2),
    )


_CASOS: dict[str, Exception] = {
    "versao": app_errors.ScheduleVersionConflictError(1, 3),
    "vizinha": app_errors.ScheduleVersionConflictError(2, 2, changed_neighbour_id="s9"),
    "bloqueio": app_errors.BlockingViolationsError((_violacao(),)),
    "aceite": app_errors.UnacknowledgedViolationsError((_violacao(),)),
    "inativos": app_errors.InactiveAllocationsInUseError((AssignmentId("a1"), AssignmentId("a2"))),
    "ausentes": app_errors.MissingStaffRecordsError((AssignmentId("a3"),)),
    "funcao": app_errors.JobFunctionNotEnabledInUnitError("cook", "u1"),
    "id": app_errors.IdentifierInUseError("ShiftBandId", "f1"),
    "simples": app_errors.ScheduleNotFoundError("s1"),
    "dominio": dom_errors.DuplicateShiftBandError(),
}


def test_recusa_otimista_da_propria_escala(client: TestClient) -> None:
    resposta = client.get("/levanta/versao")
    assert resposta.status_code == 409  # noqa: PLR2004
    corpo = resposta.json()
    assert (corpo["type"], corpo["code"]) == ("scheduling_error", "schedule_version_conflict")
    assert (corpo["expected_version"], corpo["current_version"]) == (1, 3)
    assert corpo["changed_neighbour_id"] is None


def test_recusa_otimista_da_vizinha_traz_o_id_e_versoes_iguais(client: TestClient) -> None:
    corpo = client.get("/levanta/vizinha").json()
    assert corpo["changed_neighbour_id"] == "s9"
    assert corpo["expected_version"] == corpo["current_version"] == 2  # noqa: PLR2004


@pytest.mark.parametrize(
    ("caso", "code"), [("bloqueio", "blocking_violations"), ("aceite", "unacknowledged_violations")]
)
def test_violacoes_no_corpo(client: TestClient, caso: str, code: str) -> None:
    resposta = client.get(f"/levanta/{caso}")
    assert resposta.status_code == 422  # noqa: PLR2004
    corpo = resposta.json()
    assert corpo["code"] == code
    (violacao,) = corpo["violations"]
    assert violacao["policy"] == "over_coverage"
    assert violacao["key"]["assignment_ids"] == ["a1"]
    assert (violacao["observed"], violacao["limit"]) == ("3", "2")


@pytest.mark.parametrize(("caso", "ids"), [("inativos", ["a1", "a2"]), ("ausentes", ["a3"])])
def test_ids_de_alocacao_e_contagem(client: TestClient, caso: str, ids: list[str]) -> None:
    corpo = client.get(f"/levanta/{caso}").json()
    assert (corpo["assignment_ids"], corpo["count"]) == (ids, len(ids))


def test_funcao_nao_habilitada_traz_so_a_funcao(client: TestClient) -> None:
    resposta = client.get("/levanta/funcao")
    assert resposta.status_code == 409  # noqa: PLR2004
    corpo = resposta.json()
    assert corpo["job_function_id"] == "cook"
    assert set(corpo) == {"detail", "type", "code", "job_function_id"}


def test_id_em_uso_traz_o_tipo_e_o_valor(client: TestClient) -> None:
    corpo = client.get("/levanta/id").json()
    assert (corpo["id_type"], corpo["value"]) == ("ShiftBandId", "f1")


@pytest.mark.parametrize(("caso", "faixa"), [("simples", 404), ("dominio", 422)])
def test_erro_sem_estado_tem_so_os_tres_campos(client: TestClient, caso: str, faixa: int) -> None:
    resposta = client.get(f"/levanta/{caso}")
    assert resposta.status_code == faixa
    assert set(resposta.json()) == {"detail", "type", "code"}


def test_nenhum_corpo_nomeia_registro_invisivel(client: TestClient) -> None:
    """ADR 4.3.0001 §5: inativos e ausentes só por id de alocação."""
    for caso in ("inativos", "ausentes"):
        corpo = client.get(f"/levanta/{caso}").json()
        assert "employee_id" not in corpo
        assert EmployeeId("emp") not in str(corpo)


# --- auditoria de testes (Task 11 extra) ------------------------------------------------------


@pytest.mark.parametrize(
    "raiz", [dom_errors.SchedulingError, app_errors.SchedulingApplicationError]
)
def test_a_raiz_sem_entrada_cai_no_422_e_nunca_em_500(raiz: type[Exception]) -> None:
    """O default do `resolve_status` (classe não classificada) é 422 — degrada, não quebra."""
    assert resolve_status(raiz("x")) == 422  # type: ignore[arg-type]  # noqa: PLR2004
