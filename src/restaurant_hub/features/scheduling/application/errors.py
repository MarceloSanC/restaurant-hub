"""Erros da camada de aplicação do BC scheduling (Stage 4.3, concept §4 e §6).

Duas raízes, uma por significado (ADR 3.9.0001, que supera o 2.2.0003):

- `SchedulingError` (domínio, Stage 4.1) — uma regra que o produto enuncia foi
  violada: escalas da unidade não se sobrepõem (L-SC2), a versão vista pelo editor é
  a vigente (decisão do sponsor F8, ADR 4.1.0001) — e a das vizinhas que a avaliação
  leu também (ADR 4.4.0005), violações bloqueantes e avisos sem
  aceite, registro desligado.
- `SchedulingApplicationError` (abaixo, sobre `ApplicationError`) — o caso de uso não
  pôde ser atendido por motivo que não é regra: o recurso endereçado não existe, um id
  enviado pelo cliente colide (ADR 4.3.0004), o pedido está malformado, ou o insumo
  que staff devolve está incompleto.

Cada classe tem **uma** base. O que cada erro vira para quem chamou é decidido pelo
adapter de entrada, num mapa explícito — o deste BC é da Stage 4.5.

**Ao contrário dos de domínio, alguns carregam estado**, porque a recusa só serve à
borda se disser o que recusou: a versão atual (conflito), as violações (recusa e
aceite pendente) e os ids das **alocações** que travam (D3 e registro ausente). Ids
de alocação são surrogates opacos: os dois erros que falam de registros **invisíveis**
(`InactiveAllocationsInUseError`, `MissingStaffRecordsError`) não carregam id nem nome
de registro (F7, ADR 4.3.0001 §5). Os dois da alocação (`StaffMemberNotFoundError`,
`InactiveStaffMemberError`) só ecoam o `employee_id` que o próprio pedido nomeou.

Erros de invariante do domínio (`ShiftBandInUseError`, `DuplicateEntityIdError`,
`InvalidTimeRangeError` etc.) **não** são reembrulhados: sobem como estão (concept
§5.11, D-ERRWRAP).
"""

from restaurant_hub.features.scheduling.domain.exceptions.errors import SchedulingError
from restaurant_hub.features.scheduling.domain.value_objects.identifiers import AssignmentId
from restaurant_hub.features.scheduling.domain.value_objects.violation import Violation
from restaurant_hub.shared.application.errors import ApplicationError


class SchedulingApplicationError(ApplicationError):
    """Raiz das falhas de caso de uso de scheduling que não são regra de negócio.

    Par de `SchedulingError` (domínio): todo erro deste BC descende de exatamente
    uma das duas (ADR 3.9.0001 §2).
    """


class ScheduleNotFoundError(SchedulingApplicationError):
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

    **Vizinha que mudou** (issue #199, ADR 4.4.0005): o `save` recusa também quando uma das
    escalas adjacentes que a avaliação leu não está mais como foi lida. Aí
    `changed_neighbour_id` nomeia a escala que hoje ocupa a vaga (ou a lida, se a vaga
    esvaziou) e as duas versões são as da escala **editada** — iguais, porque ela não
    mudou: o mesmo lote, reenviado sobre a mesma versão, é reavaliado contra a vizinha
    atual. Como o cliente oferece isso é da Stage 4.5.
    """

    def __init__(
        self,
        expected_version: int,
        current_version: int,
        *,
        changed_neighbour_id: str | None = None,
    ) -> None:
        if changed_neighbour_id is None:
            message = (
                f"a escala mudou: versão esperada {expected_version}, "
                f"versão atual {current_version}"
            )
        else:
            message = (
                f"a escala vizinha {changed_neighbour_id!r} mudou desde a avaliação "
                f"(versão da escala editada: {current_version})"
            )
        super().__init__(message)
        self.expected_version = expected_version
        self.current_version = current_version
        self.changed_neighbour_id = changed_neighbour_id


class SchedulePeriodTakenError(SchedulingError):
    """O período pedido cruza dia já coberto por outra escala da unidade (L-SC2)."""

    def __init__(self) -> None:
        super().__init__("a unidade já tem escala para um dos dias do período")


class IdentifierInUseError(SchedulingApplicationError):
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


class StaffMemberNotFoundError(SchedulingApplicationError):
    """Registro de funcionário que staff não devolve **na unidade** (alvo de alocação)."""

    def __init__(self, employee_id: str) -> None:
        super().__init__(f"funcionário não encontrado na unidade: {employee_id!r}")


class InactiveStaffMemberError(SchedulingError):
    """Registro desligado não pode ser alocado (ADR 4.1.0006)."""

    def __init__(self, employee_id: str) -> None:
        super().__init__(f"funcionário inativo não pode ser alocado: {employee_id!r}")


class JobFunctionNotFoundError(SchedulingApplicationError):
    """Função de trabalho fora do catálogo do tenant."""

    def __init__(self, job_function_id: str) -> None:
        super().__init__(f"função de trabalho não encontrada: {job_function_id!r}")


class JobFunctionNotEnabledInUnitError(SchedulingError):
    """Demanda de função que não vale na unidade da escala (issue #209, ADR 4.3.0005).

    A função existe no catálogo do tenant, mas a habilitação dela em staff não cobre a
    unidade (ADR 3.11.0001). Recusa o que o lote **introduz**: declarar a demanda ou
    aumentar o `N` de uma já gravada. Ecoa só o que o pedido nomeou e o endereço.
    """

    def __init__(self, job_function_id: str, unit_id: str) -> None:
        super().__init__(
            f"função de trabalho {job_function_id!r} não habilitada na unidade {unit_id!r}"
        )
        self.job_function_id = job_function_id
        self.unit_id = unit_id


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


class MissingStaffRecordsError(SchedulingApplicationError):
    """Registro alocado que staff não devolve — insumo incompleto, fail-closed (§5.12).

    Não vira "inativo" (ADR 4.2.0002 Alt D): a leitura e a edição recusam, com os
    ids das alocações afetadas (ADR 4.3.0003 §3).
    """

    def __init__(self, assignment_ids: tuple[AssignmentId, ...]) -> None:
        super().__init__(f"{len(assignment_ids)} alocação(ões) de registro que staff não devolve")
        self.assignment_ids = assignment_ids


class InvalidScheduleRequestError(SchedulingApplicationError):
    """Pedido malformado: dia que não é `date`, recorte inválido, limite fora da faixa."""

    def __init__(self, reason: str) -> None:
        super().__init__(f"pedido de escala inválido: {reason}")
