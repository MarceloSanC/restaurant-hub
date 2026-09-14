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
    """Nome obrigatório vazio, só-whitespace, ou contendo o byte NUL.

    Nomes válidos são preservados verbatim (ADR 3.1.0002). São **dois** os
    formatos rejeitados, e só dois: a ausência de conteúdo (nenhum caractere
    não-whitespace) e a presença do byte NUL (0x00) — este último porque o driver do
    Postgres o recusa client-side, e sem a regra no domínio o fake gravaria o que
    o banco real não aceita (ADR 3.4.0003 §1 e §2). Acento, emoji com ZWJ,
    quebra de linha, aspas e strings longas **continuam aceitos**: a restrição é exatamente do
    tamanho da divergência medida, não maior.

    `reason` existe para que a mensagem não afirme algo falso — dizer "não pode
    ser vazio" sobre um nome que tem conteúdo seria descrever o defeito errado a
    quem recebe o 422.
    """

    def __init__(self, entity: str, reason: str = "não pode ser vazio") -> None:
        super().__init__(f"nome de {entity} {reason}")


class InvalidDayPeriodError(StaffError):
    """Período do dia desconhecido — fora do conjunto fechado de `DayPeriod`.

    Espelha `InvalidRoleError` de identity: a conversão de texto para o enum
    falha como **erro de domínio**, e não como o `ValueError` cru do `StrEnum`
    (que não é `StaffError`, não tem handler, e viraria 500 na borda).
    """

    def __init__(self, value: str) -> None:
        super().__init__(f"período do dia inválido: {value!r}")


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


class EmployeeAlreadyHasLoginError(StaffError):
    """Registro que **já** tem login recebendo um segundo (ADR 3.5.0004 §2).

    O vínculo é definido **uma vez** por registro (concept 3.5 §5.5): não há
    "trocar o login" — desvincular/relinkar é finding para Stage própria. É
    conflito com estado **já gravado**, e por isso 409 na borda; herda só de
    `StaffError` para que a MRO não a leve a 404.
    """

    def __init__(self, employee_id: str) -> None:
        super().__init__(f"funcionário já tem login vinculado: {employee_id!r}")


class TerminatedEmployeeLoginError(StaffError):
    """Registro **desligado** recebendo login (ADR 3.5.0004 §2, alternativa D).

    Criar login é **conceder acesso**, não editar um campo — e desligar corta
    acesso (kickoff #4; ADR 3.5.0003). Um desligado que **já** tinha login o
    mantém como história; o que não existe é login **novo** para quem saiu. A
    precedência com `EmployeeAlreadyHasLoginError` é do domínio: vinculado vence
    desligado (concept 3.5 CA01).
    """

    def __init__(self, employee_id: str) -> None:
        super().__init__(f"funcionário desligado não pode receber login: {employee_id!r}")
