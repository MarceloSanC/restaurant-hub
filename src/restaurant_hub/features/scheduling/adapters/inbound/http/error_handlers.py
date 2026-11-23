"""Mapa exceção → status HTTP do BC scheduling (Stage 4.5, ADR 4.5.0002).

**Mora na feature, não em `shared`**, e é **um handler só, registrado sobre as duas raízes**
do BC — `SchedulingError` (domínio) e `SchedulingApplicationError` (aplicação), ADR 3.9.0001.
Não há rede genérica para `ApplicationError`: uma raiz sem registro responderia 500, e
`tests/unit/test_status_map.py` cobra o registro de cada raiz e a totalidade do mapa.

**As faixas são as de staff** (ADR 3.4.0002 §4), aplicadas a scheduling (concept 4.5 §6):

- **404** — o recurso endereçado não existe no endereço (a escala do path, ADR 3.4.0007) e,
  como `JobFunctionNotFoundError` de staff, o registro ou a função de **outro agregado** que o
  corpo nomeia.
- **409** — conflito com estado **gravado**: a versão que mudou, o período já coberto, o id já
  usado, a referência que impede a remoção, o registro desligado, a função que não vale na
  unidade, as alocações de registros invisíveis.
- **422** — o pedido ou o conteúdo viola uma invariante, inclusive o **valor interno** da
  escala que o lote nomeia e não existe (`ShiftBandNotFoundError`, como
  `UnavailabilityNotFoundError` de staff) e a invariante do agregado que o **próprio lote**
  quebra (os `Duplicate*`, como `OverlappingUnavailabilityError` de staff). As violações
  bloqueantes e os avisos sem aceite também: o lote é bem formado, a escala que ele produziria
  é que quebra a regra.

**Scheduling não registra 401 nem 403, e a ausência é a decisão** (L-SG1): as duas faixas são
de identity, com corpo constante (ADR 2.4.0001); um 403 de scheduling distinguível do de
identity seria um oráculo.

**O corpo** (concept 4.5 §4.3): `{"detail", "type": "scheduling_error", "code", ...}`. O
`type` separa este 422 do `RequestValidationError` do framework (corpo constante
`validation_error`); o `code` é o nome da classe em snake_case sem o sufixo `Error`, e é por
ele que o cliente escolhe entre reenviar, reler, aceitar ou desfazer. As recusas com estado
acrescentam campos — e nenhum deles nomeia registro **invisível** (inativo ou ausente em
staff) senão pelo id da alocação (ADR 4.3.0001 §5).

**A recusa otimista** (ADR 4.4.0005 §Decision 3): `changed_neighbour_id` nulo — a própria
escala mudou, reler e refazer; preenchido — uma vizinha mudou e a escala editada não
(`expected_version == current_version`), reenviar o mesmo lote.
"""

import re
from typing import Final

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from restaurant_hub.features.scheduling.adapters.inbound.http.schemas import ViolationResponse
from restaurant_hub.features.scheduling.application.errors import (
    BlockingViolationsError,
    IdentifierInUseError,
    InactiveAllocationsInUseError,
    InactiveStaffMemberError,
    InvalidScheduleRequestError,
    JobFunctionNotEnabledInUnitError,
    JobFunctionNotFoundError,
    MissingStaffRecordsError,
    ScheduleNotFoundError,
    SchedulePeriodTakenError,
    ScheduleVersionConflictError,
    SchedulingApplicationError,
    StaffMemberNotFoundError,
    UnacknowledgedViolationsError,
)
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

# O que este BC pode levantar: as suas duas raízes (ADR 3.9.0001 §2).
type SchedulingFailure = SchedulingError | SchedulingApplicationError

HTTP_NOT_FOUND: Final = 404
HTTP_CONFLICT: Final = 409
HTTP_UNPROCESSABLE: Final = 422

# O discriminador do corpo de erro de scheduling (ver o docstring do módulo).
SCHEDULING_ERROR_TYPE: Final = "scheduling_error"

SCHEDULING_ERROR_STATUS: Final[dict[type[SchedulingFailure], int]] = {
    # 404 — a escala do path; o registro e a função que o corpo nomeia (outros agregados).
    ScheduleNotFoundError: HTTP_NOT_FOUND,
    StaffMemberNotFoundError: HTTP_NOT_FOUND,
    JobFunctionNotFoundError: HTTP_NOT_FOUND,
    # 409 — conflito com estado gravado.
    # A versão vista não é a vigente, ou uma vizinha lida mudou (ADR 4.4.0005).
    ScheduleVersionConflictError: HTTP_CONFLICT,
    SchedulePeriodTakenError: HTTP_CONFLICT,
    # Id de criação já usado na escala ou na vizinha (ADR 4.3.0004).
    IdentifierInUseError: HTTP_CONFLICT,
    # O registro está desligado em staff (ADR 4.1.0006) — precedente
    # `TerminatedEmployeeLoginError` de staff.
    InactiveStaffMemberError: HTTP_CONFLICT,
    # A função não vale na unidade (ADR 4.3.0005); o homônimo de staff também é 409.
    JobFunctionNotEnabledInUnitError: HTTP_CONFLICT,
    # Referências que impedem a remoção.
    ShiftBandInUseError: HTTP_CONFLICT,
    ShiftDemandInUseError: HTTP_CONFLICT,
    InactiveAllocationsInUseError: HTTP_CONFLICT,
    # Registro alocado que staff não devolve (ADR 4.3.0003 §3). Sai também das leituras, e
    # nenhuma ação do cliente o resolve: o reparo é da issue #194 (ADR 4.5.0002).
    MissingStaffRecordsError: HTTP_CONFLICT,
    # 422 — pedido ou conteúdo que viola invariante.
    BlockingViolationsError: HTTP_UNPROCESSABLE,
    UnacknowledgedViolationsError: HTTP_UNPROCESSABLE,
    InvalidScheduleRequestError: HTTP_UNPROCESSABLE,
    InvalidIdentifierError: HTTP_UNPROCESSABLE,
    InvalidTimeRangeError: HTTP_UNPROCESSABLE,
    InvalidSchedulePeriodError: HTTP_UNPROCESSABLE,
    InvalidDemandQuantityError: HTTP_UNPROCESSABLE,
    InvalidAssignmentBreakError: HTTP_UNPROCESSABLE,
    ShiftBandDayChangeError: HTTP_UNPROCESSABLE,
    TimeRangeOutsidePeriodError: HTTP_UNPROCESSABLE,
    # Valor interno da escala que o lote nomeia e não existe — 422, não 404, como
    # `UnavailabilityNotFoundError` de staff (ADR 3.4.0002 §4).
    ShiftBandNotFoundError: HTTP_UNPROCESSABLE,
    ShiftDemandNotFoundError: HTTP_UNPROCESSABLE,
    AssignmentNotFoundError: HTTP_UNPROCESSABLE,
    # Invariante do agregado quebrada pelo próprio lote (aplicado em memória, ADR 4.3.0001) —
    # 422, não 409, como `OverlappingUnavailabilityError` de staff. O id que já existe na
    # escala é recusado antes, com `IdentifierInUseError`.
    DuplicateEntityIdError: HTTP_UNPROCESSABLE,
    DuplicateShiftBandError: HTTP_UNPROCESSABLE,
    DuplicateShiftDemandError: HTTP_UNPROCESSABLE,
    DuplicateAssignmentError: HTTP_UNPROCESSABLE,
    DuplicateAssignmentInBandError: HTTP_UNPROCESSABLE,
    # Entradas por **totalidade**, inalcançáveis por HTTP na Stage 4.5 (concept §6): a
    # configuração é da 4.8; o insumo do avaliador é montado pelo use case; a versão
    # comparada é a lida do banco. Não escrever e2e esperando produzi-las.
    InvalidWeekdayError: HTTP_UNPROCESSABLE,
    InvalidDayCutoffError: HTTP_UNPROCESSABLE,
    InvalidValidationConfigError: HTTP_UNPROCESSABLE,
    InvalidEvaluationInputError: HTTP_UNPROCESSABLE,
    InvalidScheduleVersionError: HTTP_UNPROCESSABLE,
}

_CAMEL_BOUNDARY: Final = re.compile(r"(?<!^)(?=[A-Z])")


def resolve_status(exc: SchedulingFailure) -> int:
    """Status da exceção, pelo `__mro__` (a totalidade continua exigindo entrada própria)."""
    for exc_type in type(exc).__mro__:
        status = SCHEDULING_ERROR_STATUS.get(exc_type)
        if status is not None:
            return status
    return HTTP_UNPROCESSABLE


def error_code(exc: BaseException) -> str:
    """O `code` do corpo: o nome da classe em snake_case, sem o sufixo `Error`."""
    name = type(exc).__name__.removesuffix("Error")
    return _CAMEL_BOUNDARY.sub("_", name).lower()


def _state_of(exc: SchedulingFailure) -> dict[str, object]:
    """Os campos de estado da recusa (concept 4.5 §4.3), ou nenhum."""
    match exc:
        case ScheduleVersionConflictError():
            return {
                "expected_version": exc.expected_version,
                "current_version": exc.current_version,
                "changed_neighbour_id": exc.changed_neighbour_id,
            }
        case BlockingViolationsError() | UnacknowledgedViolationsError():
            return {
                "violations": [
                    ViolationResponse.from_violation(v).model_dump(mode="json")
                    for v in exc.violations
                ]
            }
        case InactiveAllocationsInUseError() | MissingStaffRecordsError():
            return {
                "assignment_ids": list(exc.assignment_ids),
                "count": len(exc.assignment_ids),
            }
        case JobFunctionNotEnabledInUnitError():
            return {"job_function_id": exc.job_function_id}
        case IdentifierInUseError():
            return {"id_type": exc.id_type, "value": exc.value}
        case _:
            return {}


def build_error_response(exc: SchedulingFailure) -> JSONResponse:
    """A resposta do erro de scheduling: status do mapa, discriminador, `code` e estado."""
    return JSONResponse(
        status_code=resolve_status(exc),
        content={
            "detail": str(exc),
            "type": SCHEDULING_ERROR_TYPE,
            "code": error_code(exc),
            **_state_of(exc),
        },
    )


def register_scheduling_error_handlers(app: FastAPI) -> None:
    """Registra o handler único do BC sobre as **duas** raízes (ADR 3.9.0001 §4)."""

    @app.exception_handler(SchedulingApplicationError)
    @app.exception_handler(SchedulingError)
    async def scheduling_error_handler(request: Request, exc: SchedulingFailure) -> JSONResponse:
        return build_error_response(exc)
