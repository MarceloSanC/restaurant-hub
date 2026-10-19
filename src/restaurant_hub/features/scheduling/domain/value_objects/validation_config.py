"""Value objects da configuração de validação — `PolicyKind`, modos, regra e `ValidationConfig`.

A configuração é do **restaurante** (tenant), igual para todas as unidades (ADR
4.1.0003; concept 4.2 §3). Por política configurável: habilitada, modo
(`block`/`warn`) e parâmetros. Os parâmetros são **minutos inteiros** (ADR 4.1.0007
§3): nenhuma política conta horas em `float`.

**Defaults num sítio só.** Os valores legais — 11h de descanso (CLT art. 66), 10h
por dia (CLT arts. 58 + 59 § 2º), 44h por semana (CF art. 7º XIII) — são default de
parâmetro livre, nunca regra (overview §6: "CLT não é hard-coded"), e vivem só em
`ValidationConfig.default()` (concept 4.2 §5.2, CA1).

A indisponibilidade **não tem campo**: é `block` fixo e sempre habilitada (ADR
4.1.0003 (a) "Configurable: nothing"; ADR 4.2.0002 Decision 4).
"""

from dataclasses import dataclass
from enum import StrEnum

from restaurant_hub.features.scheduling.domain.exceptions.errors import (
    InvalidValidationConfigError,
)


class PolicyKind(StrEnum):
    """As nove políticas v1 — conjunto fechado; a ordem de declaração é a de avaliação."""

    OVERLAP = "overlap"
    UNAVAILABILITY = "unavailability"
    REST_BETWEEN_SHIFTS = "rest_between_shifts"
    DAILY_CAP = "daily_cap"
    WEEKLY_CAP = "weekly_cap"
    WORKLOAD = "workload"
    FUNCTION_MISMATCH = "function_mismatch"
    OVER_COVERAGE = "over_coverage"
    BREAK_DIVERGENCE = "break_divergence"


class EnforcementMode(StrEnum):
    """`block` recusa a mutação; `warn` é salvo com aceite consciente (ADR 4.1.0001 §1)."""

    BLOCK = "block"
    WARN = "warn"


class WorkloadDirection(StrEnum):
    """Direção da política de carga: só o excesso, ou o desvio nos dois sentidos."""

    EXCESS = "excess"
    BOTH = "both"


@dataclass(frozen=True)
class PolicyRule:
    """Habilitação e modo de uma política.

    Attributes:
        enabled: se a política é avaliada.
        mode: o modo das violações que ela produz.
    """

    enabled: bool
    mode: EnforcementMode

    def __post_init__(self) -> None:
        # Tipo exato, não só valor: a reidratação da 4.4 traz texto do banco, e um StrEnum é
        # `==` ao seu texto mas não `is` — `"block"` cru sumiria de `Evaluation.blocking`.
        if type(self.enabled) is not bool:
            raise InvalidValidationConfigError(
                f"enabled deve ser bool (recebido: {self.enabled!r})"
            )
        if not isinstance(self.mode, EnforcementMode):
            raise InvalidValidationConfigError(
                f"mode deve ser um EnforcementMode (recebido: {self.mode!r})"
            )


_REGRA_DA_INDISPONIBILIDADE = PolicyRule(enabled=True, mode=EnforcementMode.BLOCK)


@dataclass(frozen=True)
class ValidationConfig:
    """Configuração de validação do restaurante.

    Attributes:
        overlap … break_divergence: regra de cada uma das oito políticas configuráveis.
        min_rest_minutes: descanso mínimo entre jornadas; `>= 0` (doc §3.6.2, "livre ≥ 0").
        daily_cap_minutes: teto de horas do dia operacional; `> 0`.
        weekly_cap_minutes: teto de horas da semana de apuração; `> 0`.
        workload_tolerance_minutes: tolerância da carga contratada; `>= 0`.
        workload_direction: direção da política de carga.
    """

    overlap: PolicyRule
    rest_between_shifts: PolicyRule
    daily_cap: PolicyRule
    weekly_cap: PolicyRule
    workload: PolicyRule
    function_mismatch: PolicyRule
    over_coverage: PolicyRule
    break_divergence: PolicyRule
    min_rest_minutes: int
    daily_cap_minutes: int
    weekly_cap_minutes: int
    workload_tolerance_minutes: int
    workload_direction: WorkloadDirection

    def __post_init__(self) -> None:
        regras = {
            "overlap": self.overlap,
            "rest_between_shifts": self.rest_between_shifts,
            "daily_cap": self.daily_cap,
            "weekly_cap": self.weekly_cap,
            "workload": self.workload,
            "function_mismatch": self.function_mismatch,
            "over_coverage": self.over_coverage,
            "break_divergence": self.break_divergence,
        }
        for nome, regra in regras.items():
            if not isinstance(regra, PolicyRule):
                raise InvalidValidationConfigError(
                    f"{nome} deve ser um PolicyRule (recebido: {regra!r})"
                )
        if not isinstance(self.workload_direction, WorkloadDirection):
            raise InvalidValidationConfigError(
                "workload_direction deve ser um WorkloadDirection "
                f"(recebido: {self.workload_direction!r})"
            )
        inteiros = {
            "min_rest_minutes": self.min_rest_minutes,
            "daily_cap_minutes": self.daily_cap_minutes,
            "weekly_cap_minutes": self.weekly_cap_minutes,
            "workload_tolerance_minutes": self.workload_tolerance_minutes,
        }
        for nome, valor in inteiros.items():
            # `type is int`, não `isinstance`: `bool` é `int` e passaria como 0/1 minuto.
            if type(valor) is not int:
                raise InvalidValidationConfigError(
                    f"{nome} deve ser um número inteiro de minutos (recebido: {valor!r})"
                )
        nao_negativos = {
            "min_rest_minutes": self.min_rest_minutes,
            "workload_tolerance_minutes": self.workload_tolerance_minutes,
        }
        for nome, valor in nao_negativos.items():
            if valor < 0:
                raise InvalidValidationConfigError(f"{nome} deve ser >= 0 (recebido: {valor})")
        positivos = {
            "daily_cap_minutes": self.daily_cap_minutes,
            "weekly_cap_minutes": self.weekly_cap_minutes,
        }
        for nome, valor in positivos.items():
            if valor <= 0:
                raise InvalidValidationConfigError(f"{nome} deve ser > 0 (recebido: {valor})")

    @classmethod
    def default(cls) -> "ValidationConfig":
        """Os defaults do ADR 4.1.0003 (a) e do ADR 4.1.0011 — o **único** sítio deles.

        Todas habilitadas; sobreposição `block` (impossibilidade física), as demais
        `warn` (a lei admite exceção); descanso 11h, teto diário 10h, teto semanal 44h,
        tolerância 0 e direção "excesso".
        """
        aviso = PolicyRule(enabled=True, mode=EnforcementMode.WARN)
        return cls(
            overlap=PolicyRule(enabled=True, mode=EnforcementMode.BLOCK),
            rest_between_shifts=aviso,
            daily_cap=aviso,
            weekly_cap=aviso,
            workload=aviso,
            function_mismatch=aviso,
            over_coverage=aviso,
            break_divergence=aviso,
            min_rest_minutes=660,
            daily_cap_minutes=600,
            weekly_cap_minutes=2640,
            workload_tolerance_minutes=0,
            workload_direction=WorkloadDirection.EXCESS,
        )

    def rule_for(self, kind: PolicyKind) -> PolicyRule:
        """A regra da política — a da indisponibilidade é fixa, `block` e habilitada."""
        regras = {
            PolicyKind.OVERLAP: self.overlap,
            PolicyKind.UNAVAILABILITY: _REGRA_DA_INDISPONIBILIDADE,
            PolicyKind.REST_BETWEEN_SHIFTS: self.rest_between_shifts,
            PolicyKind.DAILY_CAP: self.daily_cap,
            PolicyKind.WEEKLY_CAP: self.weekly_cap,
            PolicyKind.WORKLOAD: self.workload,
            PolicyKind.FUNCTION_MISMATCH: self.function_mismatch,
            PolicyKind.OVER_COVERAGE: self.over_coverage,
            PolicyKind.BREAK_DIVERGENCE: self.break_divergence,
        }
        return regras[kind]
