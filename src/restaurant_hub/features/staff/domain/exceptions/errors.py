"""Exceções de domínio do bounded context staff.

Todas herdam de `StaffError`, que por sua vez herda de `DomainError`
(`shared/domain`) — o error handler HTTP (Stage 2.4) converte a hierarquia
`DomainError` em resposta 4xx. Aqui garante-se apenas a hierarquia e a mensagem;
nenhuma exceção carrega estado além do texto.
"""

from restaurant_hub.shared.domain.exceptions.base import DomainError


class StaffError(DomainError):
    """Erro de negócio do bounded context staff."""


class InvalidIdentifierError(StaffError):
    """Identificador de entidade vazio ou só-whitespace.

    Entidade sem identidade é entidade inválida. Importa em especial para o
    `tenant_id`/`unit_id`: um identificador vazio criaria um balde de falso
    isolamento entre tenants/unidades.
    """

    def __init__(self, entity: str) -> None:
        super().__init__(f"identificador de {entity} não pode ser vazio")


class InvalidNameError(StaffError):
    """Nome obrigatório vazio ou só-whitespace (`Employee`/`JobFunction`).

    Nomes válidos são preservados verbatim (ADR 3.1.0002); o único formato
    rejeitado é a ausência de conteúdo (nenhum caractere não-whitespace).
    """

    def __init__(self, entity: str) -> None:
        super().__init__(f"nome de {entity} não pode ser vazio")


class InvalidWeeklyHoursError(StaffError):
    """Carga semanal contratada fora do domínio válido — deve ser positiva e finita."""

    def __init__(self, value: object) -> None:
        super().__init__(f"carga semanal contratada inválida: {value!r} (deve ser > 0 e finita)")


class EmptyShiftPreferenceError(StaffError):
    """Preferência de turno com conjunto vazio de períodos (ADR 3.1.0004).

    "Sem preferência" se expressa com `None` no `Employee`, nunca com conjunto vazio.
    """

    def __init__(self) -> None:
        super().__init__("preferência de turno exige ao menos um período")


class EmptyJobFunctionsError(StaffError):
    """Funcionário sem nenhuma função atribuída (ADR 3.1.0006)."""

    def __init__(self) -> None:
        super().__init__("funcionário exige ao menos uma função atribuída")


class InvalidUnavailabilityPeriodError(StaffError):
    """Período de indisponibilidade malformado (`start >= end` ou datetime tz-aware).

    Instantes são wall-clock ingênuos no fuso da unidade (ADR 3.1.0005).
    """

    def __init__(self, reason: str) -> None:
        super().__init__(f"período de indisponibilidade inválido: {reason}")


class OverlappingUnavailabilityError(StaffError):
    """Períodos de indisponibilidade sobrepostos no mesmo funcionário.

    Semântica semi-aberta `[início, fim)` — adjacentes não conflitam (ADR 3.1.0001).
    """

    def __init__(self) -> None:
        super().__init__("períodos de indisponibilidade não podem se sobrepor")


class UnavailabilityNotFoundError(StaffError):
    """Remoção de período de indisponibilidade inexistente no registro."""

    def __init__(self) -> None:
        super().__init__("período de indisponibilidade não encontrado no registro")
