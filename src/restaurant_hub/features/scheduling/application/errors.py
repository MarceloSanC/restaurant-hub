"""Erros da camada de aplicação do BC scheduling (Stage 4.3, concept §4 e §6).

Todos herdam de `SchedulingError` (domínio, Stage 4.1) e, por consequência, de
`DomainError` — a única raiz com handler HTTP registrado (ADR 2.2.0003). O mapa de
status deste BC é da Stage 4.5.

Os **três** erros de "não encontrado" herdam também de `NotFoundError`, **nesta
ordem**: a MRO fica `… -> SchedulingError -> NotFoundError -> DomainError`, e o
lookup de handler (que percorre `type(exc).__mro__`) alcança o handler da raiz do BC
antes do genérico — o mesmo arranjo de `staff/application/errors.py`.

**Ao contrário dos de domínio, alguns carregam estado**, porque a recusa só serve à
borda se disser o que recusou: a versão atual (conflito), as violações (recusa e
aceite pendente) e os ids das **alocações** que travam (D3 e registro ausente). Ids
de alocação são surrogates opacos — nenhum erro carrega id nem nome de registro de
funcionário (F7, ADR 4.3.0001 §5).

Erros de invariante do domínio (`ShiftBandInUseError`, `DuplicateEntityIdError`,
`InvalidTimeRangeError` etc.) **não** são reembrulhados: sobem como estão (concept
§5.11, D-ERRWRAP).
"""

from restaurant_hub.features.scheduling.domain.exceptions.errors import SchedulingError
from restaurant_hub.features.scheduling.domain.value_objects.identifiers import AssignmentId
from restaurant_hub.features.scheduling.domain.value_objects.violation import Violation
from restaurant_hub.shared.domain.exceptions.base import NotFoundError


class ScheduleNotFoundError(SchedulingError, NotFoundError):
    """Escala inexistente **no endereço** (tenant, unidade, escala) — ADR 3.4.0007.

    Escala de outra unidade ou de outro tenant cai aqui: id alheio é indistinguível
    de inexistente.
    """

    def __init__(self, schedule_id: str) -> None:
        super().__init__(f"escala não encontrada: {schedule_id!r}")


class ScheduleVersionConflictError(SchedulingError):
    """A versão vista pelo editor não é a vigente (ADR 4.1.0001 §2).

    Carrega a versão atual; o estado atual chega pela releitura (concept,
    divergência 12).
    """

    def __init__(self, expected_version: int, current_version: int) -> None:
        super().__init__(
            f"a escala mudou: versão esperada {expected_version}, versão atual {current_version}"
        )
        self.expected_version = expected_version
        self.current_version = current_version


class SchedulePeriodTakenError(SchedulingError):
    """O período pedido cruza dia já coberto por outra escala da unidade (L-SC2)."""

    def __init__(self) -> None:
        super().__init__("a unidade já tem escala para um dos dias do período")


class IdentifierInUseError(SchedulingError):
    """Id de escala ou de entidade interna já usado na unidade (ADR 4.3.0004)."""

    def __init__(self, id_type: str, value: str) -> None:
        super().__init__(f"{id_type} já está em uso na unidade: {value!r}")
        self.id_type = id_type
        self.value = value


class BlockingViolationsError(SchedulingError):
    """A mudança introduz violação em modo `block` (ADR 4.3.0001 §3)."""

    def __init__(self, violations: tuple[Violation, ...]) -> None:
        super().__init__(f"a mudança introduz {len(violations)} violação(ões) bloqueante(s)")
        self.violations = violations


class UnacknowledgedViolationsError(SchedulingError):
    """A mudança introduz violação `warn` sem aceite que a cubra (ADR 4.3.0001 §3)."""

    def __init__(self, violations: tuple[Violation, ...]) -> None:
        super().__init__(f"a mudança introduz {len(violations)} aviso(s) sem aceite")
        self.violations = violations


class StaffMemberNotFoundError(SchedulingError, NotFoundError):
    """Registro de funcionário que staff não devolve **na unidade** (alvo de alocação)."""

    def __init__(self, employee_id: str) -> None:
        super().__init__(f"funcionário não encontrado na unidade: {employee_id!r}")


class InactiveStaffMemberError(SchedulingError):
    """Registro desligado não pode ser alocado (ADR 4.1.0006)."""

    def __init__(self, employee_id: str) -> None:
        super().__init__(f"funcionário inativo não pode ser alocado: {employee_id!r}")


class JobFunctionNotFoundError(SchedulingError, NotFoundError):
    """Função de trabalho fora do catálogo do tenant."""

    def __init__(self, job_function_id: str) -> None:
        super().__init__(f"função de trabalho não encontrada: {job_function_id!r}")


class InactiveAllocationsInUseError(SchedulingError):
    """Faixa ou demanda presa só por alocações de registros desligados (D3).

    Carrega a contagem e os ids das alocações — nunca o registro —, para a gerente
    desalocá-las num ato explícito no mesmo lote (ADR 4.3.0001 §5).
    """

    def __init__(self, assignment_ids: tuple[AssignmentId, ...]) -> None:
        super().__init__(
            f"{len(assignment_ids)} alocação(ões) de registro inativo impedem a remoção"
        )
        self.assignment_ids = assignment_ids

    @property
    def count(self) -> int:
        """Quantas alocações de registro inativo travam a remoção."""
        return len(self.assignment_ids)


class MissingStaffRecordsError(SchedulingError):
    """Registro alocado que staff não devolve — insumo incompleto, fail-closed (§5.12).

    Não vira "inativo" (ADR 4.2.0002 Alt D): a leitura e a edição recusam, com os
    ids das alocações afetadas (ADR 4.3.0003 §3).
    """

    def __init__(self, assignment_ids: tuple[AssignmentId, ...]) -> None:
        super().__init__(f"{len(assignment_ids)} alocação(ões) de registro que staff não devolve")
        self.assignment_ids = assignment_ids


class InvalidScheduleRequestError(SchedulingError):
    """Pedido malformado: dia que não é `date`, recorte inválido, limite fora da faixa."""

    def __init__(self, reason: str) -> None:
        super().__init__(f"pedido de escala inválido: {reason}")
