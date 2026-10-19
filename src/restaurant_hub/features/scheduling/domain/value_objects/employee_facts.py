"""Value objects dos fatos de staff que as políticas leem — por dados, nunca por tipo.

Scheduling não importa staff (contrato `bc-independence`): a 4.3 lê o registro pelo
`StaffReadPort` e entrega aqui só o que as políticas precisam (concept 4.2 §4). Os
tipos são **deste** BC; os valores espelham os de staff:

- a carga semanal contratada em horas `Decimal`, como o perfil de jornada fixa de
  staff a guarda (`NUMERIC` sem precisão) — sem converter para minutos inteiros,
  que exigiria arredondar 22,33h (concept 4.2 §7 D9); `None` = sob demanda;
- as janelas de indisponibilidade como o período de indisponibilidade de staff:
  instantes ingênuos (wall-clock da unidade), `start < end`, **sem** exigência de
  minuto inteiro nem teto de duração (férias de semanas);
- o estado ativo: o registro inativo é pulado por toda política (ADR 4.1.0006).
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from restaurant_hub.features.scheduling.domain.exceptions.errors import (
    InvalidEvaluationInputError,
)
from restaurant_hub.features.scheduling.domain.value_objects.identifiers import (
    EmployeeId,
    JobFunctionId,
)


@dataclass(frozen=True)
class UnavailabilityWindow:
    """Janela `[start, end)` em que o registro não pode ser escalado.

    Attributes:
        start: início (inclusivo) — datetime ingênuo.
        end: fim (exclusivo) — datetime ingênuo; `start < end`.
    """

    start: datetime
    end: datetime

    def __post_init__(self) -> None:
        # `datetime`, não `date`: um `date` cru quebraria em `tzinfo` com AttributeError.
        if not isinstance(self.start, datetime) or not isinstance(self.end, datetime):
            raise InvalidEvaluationInputError(
                "janela de indisponibilidade deve ter instantes datetime"
            )
        # Tz-aware ANTES de comparar: start < end só roda entre instantes ingênuos.
        if self.start.tzinfo is not None or self.end.tzinfo is not None:
            raise InvalidEvaluationInputError(
                "janela de indisponibilidade deve ter instantes ingênuos (sem tzinfo)"
            )
        if self.start >= self.end:
            raise InvalidEvaluationInputError(
                "janela de indisponibilidade: início deve anteceder o fim"
            )


@dataclass(frozen=True)
class EmployeeFacts:
    """O que as políticas sabem de um registro de funcionário da unidade.

    Attributes:
        employee_id: o registro (valor emitido por staff).
        active: se o registro está ativo; inativo não é avaliado.
        job_function_ids: as funções que o registro detém **hoje**.
        contracted_weekly_hours: carga semanal em horas; `None` = sob demanda.
        unavailabilities: as janelas de indisponibilidade do registro — sem default:
            esquecê-las calaria a política `block` fixa em silêncio.
    """

    employee_id: EmployeeId
    active: bool
    job_function_ids: frozenset[JobFunctionId]
    contracted_weekly_hours: Decimal | None
    unavailabilities: tuple[UnavailabilityWindow, ...]

    def __post_init__(self) -> None:
        horas = self.contracted_weekly_hours
        if horas is not None and not isinstance(horas, Decimal):
            raise InvalidEvaluationInputError(
                f"carga semanal contratada deve ser Decimal (recebido: {horas!r})"
            )
        # is_finite() ANTES de comparar: comparar NaN com 0 levantaria InvalidOperation.
        if horas is not None and (not horas.is_finite() or horas <= 0):
            raise InvalidEvaluationInputError(
                f"carga semanal contratada deve ser finita e > 0 (recebido: {horas})"
            )
