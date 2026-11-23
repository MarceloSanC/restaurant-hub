"""Rotas HTTP do BC scheduling (Stage 4.5, concept §4.1).

**Adapter fino.** Cada rota: valida os identificadores (e os dias) que chegaram, autoriza a
permissão da rota na unidade do path pelo port, converte o corpo em DTOs, chama **um** use
case e mapeia o result para o schema de resposta. Sem regra de negócio, sem decisão de acesso.

**A ordem é contrato: autenticar → validar identificadores → autorizar → converter valores →
use case** (ADR 3.6.0002). Autenticar é `Depends` (`CurrentActor`), antes até da validação do
corpo. Os identificadores são validados antes de autorizar; instantes, quantidades e decimais
viram value object depois, como a conversão texto → value object de staff.

**O tenant de todo command e query sai de `AuthorizedScope.tenant_id`** da autorização da
borda, com o tenant **omitido** — o guard o resolve do ator (L-SG5, ADR 0.0.0005). Nenhuma rota
o nomeia, nenhum schema o aceita.

**Nenhuma rota lê `AuthorizedScope.unit_id`** (ADR 3.6.0001): a unidade do command é a do
path. Há varredura de AST que reprova o atributo neste módulo.

**O ator vai em todo command e query** (ADR 4.3.0002): o use case autoriza de novo. A
autorização daqui é defesa em profundidade — e é a que fecha o 403 antes de qualquer leitura.

**Os provedores `_get_*`** são só as chaves de `app.dependency_overrides`, preenchido pelo
composition root; chamados de verdade, levantam.
"""

from datetime import date
from typing import Annotated, Never

from fastapi import APIRouter, Depends, status

from restaurant_hub.features.scheduling.adapters.inbound.http.dependencies import (
    MANAGE_SCHEDULE_ACCESS,
    VIEW_OWN_SCHEDULE_ACCESS,
    VIEW_SCHEDULE_ACCESS,
    CurrentActor,
    SchedulingAccessGuard,
    validate_day,
    validate_identifier,
)
from restaurant_hub.features.scheduling.adapters.inbound.http.schemas import (
    CalendarResponse,
    CreateScheduleRequest,
    EvaluateScheduleRequest,
    EvaluationResponse,
    MyScheduleResponse,
    PublishScheduleRequest,
    ScheduleResponse,
    ScheduleSummaryResponse,
    check_acknowledgement_identifiers,
    check_operation_identifiers,
    to_acknowledgement,
    to_operation,
)
from restaurant_hub.features.scheduling.application.dtos.commands import (
    CreateScheduleCommand,
    PublishScheduleCommand,
)
from restaurant_hub.features.scheduling.application.dtos.queries import (
    EvaluateScheduleQuery,
    GetCalendarQuery,
    GetMyScheduleQuery,
    GetScheduleQuery,
    ListPastSchedulesQuery,
)
from restaurant_hub.features.scheduling.application.use_cases.create_schedule import (
    CreateScheduleUseCase,
)
from restaurant_hub.features.scheduling.application.use_cases.evaluate_schedule import (
    EvaluateScheduleUseCase,
)
from restaurant_hub.features.scheduling.application.use_cases.get_calendar import (
    GetCalendarUseCase,
)
from restaurant_hub.features.scheduling.application.use_cases.get_my_schedule import (
    GetMyScheduleUseCase,
)
from restaurant_hub.features.scheduling.application.use_cases.get_schedule import (
    GetScheduleUseCase,
)
from restaurant_hub.features.scheduling.application.use_cases.list_past_schedules import (
    ListPastSchedulesUseCase,
)
from restaurant_hub.features.scheduling.application.use_cases.publish_schedule import (
    PublishScheduleUseCase,
)
from restaurant_hub.features.scheduling.domain.value_objects.identifiers import (
    ScheduleId,
    UnitId,
)

router = APIRouter(tags=["scheduling"])

_UNIT = "unidade"
_SCHEDULE = "escala"


def _not_wired(name: str) -> Never:
    raise RuntimeError(
        f"dependência {name!r} não foi conectada pelo composition root — "
        "veja wire_dependencies() e create_app()"
    )


def _get_create_schedule() -> CreateScheduleUseCase:
    _not_wired("scheduling_create_schedule")


def _get_get_schedule() -> GetScheduleUseCase:
    _not_wired("scheduling_get_schedule")


def _get_evaluate_schedule() -> EvaluateScheduleUseCase:
    _not_wired("scheduling_evaluate_schedule")


def _get_publish_schedule() -> PublishScheduleUseCase:
    _not_wired("scheduling_publish_schedule")


def _get_calendar() -> GetCalendarUseCase:
    _not_wired("scheduling_get_calendar")


def _get_list_past_schedules() -> ListPastSchedulesUseCase:
    _not_wired("scheduling_list_past_schedules")


def _get_my_schedule() -> GetMyScheduleUseCase:
    _not_wired("scheduling_get_my_schedule")


# ---------------------------------------------------------------------------
# S1 — criar a escala do período
# ---------------------------------------------------------------------------


@router.post(
    "/units/{unit_id}/schedules",
    response_model=ScheduleSummaryResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_schedule(
    unit_id: str,
    payload: CreateScheduleRequest,
    actor: CurrentActor,
    guard: SchedulingAccessGuard,
    use_case: Annotated[CreateScheduleUseCase, Depends(_get_create_schedule)],
) -> ScheduleSummaryResponse:
    """Cria a escala vazia do período que começa em `first_day` (id do servidor)."""
    unit = validate_identifier(unit_id, entity=_UNIT)
    scope = guard.authorize(actor, MANAGE_SCHEDULE_ACCESS.permission, unit_id=unit)
    result = use_case.execute(
        CreateScheduleCommand(
            actor=actor,
            tenant_id=scope.tenant_id,
            unit_id=UnitId(unit),
            first_day=validate_day(payload.first_day, name="first_day"),
        )
    )
    return ScheduleSummaryResponse.from_result(result)


# ---------------------------------------------------------------------------
# S6 — escalas anteriores (antes de S2: `/schedules` sem id)
# ---------------------------------------------------------------------------


@router.get("/units/{unit_id}/schedules", response_model=list[ScheduleSummaryResponse])
def list_past_schedules(  # noqa: PLR0913 — endereço + query (2) + ator, guard e use case
    unit_id: str,
    before: date,
    actor: CurrentActor,
    guard: SchedulingAccessGuard,
    use_case: Annotated[ListPastSchedulesUseCase, Depends(_get_list_past_schedules)],
    limit: int = 10,
) -> list[ScheduleSummaryResponse]:
    """As escalas que terminam antes de `before`, da mais recente, até `limit` (1 a 52)."""
    unit = validate_identifier(unit_id, entity=_UNIT)
    scope = guard.authorize(actor, VIEW_SCHEDULE_ACCESS.permission, unit_id=unit)
    results = use_case.execute(
        ListPastSchedulesQuery(
            actor=actor,
            tenant_id=scope.tenant_id,
            unit_id=UnitId(unit),
            before=validate_day(before, name="before"),
            limit=limit,
        )
    )
    return [ScheduleSummaryResponse.from_result(r) for r in results]


# ---------------------------------------------------------------------------
# S2 — ler a escala vigente com as violações atuais
# ---------------------------------------------------------------------------


@router.get("/units/{unit_id}/schedules/{schedule_id}", response_model=ScheduleResponse)
def get_schedule(
    unit_id: str,
    schedule_id: str,
    actor: CurrentActor,
    guard: SchedulingAccessGuard,
    use_case: Annotated[GetScheduleUseCase, Depends(_get_get_schedule)],
) -> ScheduleResponse:
    """A escala vigente, com faixas, alocações de registros ativos e violações atuais."""
    unit = validate_identifier(unit_id, entity=_UNIT)
    schedule = validate_identifier(schedule_id, entity=_SCHEDULE)
    scope = guard.authorize(actor, VIEW_SCHEDULE_ACCESS.permission, unit_id=unit)
    result = use_case.execute(
        GetScheduleQuery(
            actor=actor,
            tenant_id=scope.tenant_id,
            unit_id=UnitId(unit),
            schedule_id=ScheduleId(schedule),
        )
    )
    return ScheduleResponse.from_result(result)


# ---------------------------------------------------------------------------
# S3 — avaliar um lote ao vivo, sem gravar
# ---------------------------------------------------------------------------


@router.post(
    "/units/{unit_id}/schedules/{schedule_id}/evaluations", response_model=EvaluationResponse
)
def evaluate_schedule(  # noqa: PLR0913 — endereço (2) + corpo + ator, guard e use case
    unit_id: str,
    schedule_id: str,
    payload: EvaluateScheduleRequest,
    actor: CurrentActor,
    guard: SchedulingAccessGuard,
    use_case: Annotated[EvaluateScheduleUseCase, Depends(_get_evaluate_schedule)],
) -> EvaluationResponse:
    """Avalia o lote sobre a versão vista — **200**: nada é criado nem gravado."""
    unit = validate_identifier(unit_id, entity=_UNIT)
    schedule = validate_identifier(schedule_id, entity=_SCHEDULE)
    check_operation_identifiers(payload.operations)
    scope = guard.authorize(actor, MANAGE_SCHEDULE_ACCESS.permission, unit_id=unit)
    result = use_case.execute(
        EvaluateScheduleQuery(
            actor=actor,
            tenant_id=scope.tenant_id,
            unit_id=UnitId(unit),
            schedule_id=ScheduleId(schedule),
            expected_version=payload.expected_version,
            operations=tuple(to_operation(op) for op in payload.operations),
        )
    )
    return EvaluationResponse.from_result(result)


# ---------------------------------------------------------------------------
# S4 — publicar um lote, com os aceites
# ---------------------------------------------------------------------------


@router.post(
    "/units/{unit_id}/schedules/{schedule_id}/publications", response_model=ScheduleResponse
)
def publish_schedule(  # noqa: PLR0913 — endereço (2) + corpo + ator, guard e use case
    unit_id: str,
    schedule_id: str,
    payload: PublishScheduleRequest,
    actor: CurrentActor,
    guard: SchedulingAccessGuard,
    use_case: Annotated[PublishScheduleUseCase, Depends(_get_publish_schedule)],
) -> ScheduleResponse:
    """Publica o lote — **200, não 201**: grava uma nova versão da mesma escala, sem URL nova."""
    unit = validate_identifier(unit_id, entity=_UNIT)
    schedule = validate_identifier(schedule_id, entity=_SCHEDULE)
    check_operation_identifiers(payload.operations)
    check_acknowledgement_identifiers(payload.acknowledgements)
    scope = guard.authorize(actor, MANAGE_SCHEDULE_ACCESS.permission, unit_id=unit)
    result = use_case.execute(
        PublishScheduleCommand(
            actor=actor,
            tenant_id=scope.tenant_id,
            unit_id=UnitId(unit),
            schedule_id=ScheduleId(schedule),
            expected_version=payload.expected_version,
            operations=tuple(to_operation(op) for op in payload.operations),
            acknowledgements=tuple(to_acknowledgement(a) for a in payload.acknowledgements),
        )
    )
    return ScheduleResponse.from_result(result)


# ---------------------------------------------------------------------------
# S5 — calendário de um recorte (dia, semana ou mês: até 42 dias)
# ---------------------------------------------------------------------------


@router.get("/units/{unit_id}/calendar", response_model=CalendarResponse)
def get_calendar(  # noqa: PLR0913 — endereço + recorte (2) + ator, guard e use case
    unit_id: str,
    first_day: date,
    last_day: date,
    actor: CurrentActor,
    guard: SchedulingAccessGuard,
    use_case: Annotated[GetCalendarUseCase, Depends(_get_calendar)],
) -> CalendarResponse:
    """As escalas que cruzam o recorte e as faixas cujo dia operacional cai nele."""
    unit = validate_identifier(unit_id, entity=_UNIT)
    scope = guard.authorize(actor, VIEW_SCHEDULE_ACCESS.permission, unit_id=unit)
    result = use_case.execute(
        GetCalendarQuery(
            actor=actor,
            tenant_id=scope.tenant_id,
            unit_id=UnitId(unit),
            first_day=validate_day(first_day, name="first_day"),
            last_day=validate_day(last_day, name="last_day"),
        )
    )
    return CalendarResponse.from_result(result)


# ---------------------------------------------------------------------------
# S7 — "minha escala": os turnos do próprio ator na unidade
# ---------------------------------------------------------------------------


@router.get("/units/{unit_id}/my-schedule", response_model=MyScheduleResponse)
def get_my_schedule(  # noqa: PLR0913 — endereço + recorte (2) + ator, guard e use case
    unit_id: str,
    first_day: date,
    last_day: date,
    actor: CurrentActor,
    guard: SchedulingAccessGuard,
    use_case: Annotated[GetMyScheduleUseCase, Depends(_get_my_schedule)],
) -> MyScheduleResponse:
    """Os turnos dos registros ativos vinculados ao login do token, na unidade (D-OWN)."""
    unit = validate_identifier(unit_id, entity=_UNIT)
    scope = guard.authorize(actor, VIEW_OWN_SCHEDULE_ACCESS.permission, unit_id=unit)
    result = use_case.execute(
        GetMyScheduleQuery(
            actor=actor,
            tenant_id=scope.tenant_id,
            unit_id=UnitId(unit),
            first_day=validate_day(first_day, name="first_day"),
            last_day=validate_day(last_day, name="last_day"),
        )
    )
    return MyScheduleResponse.from_result(result)
