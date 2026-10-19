"""Protocolo das políticas de validação — a estratégia plugável (overview §7).

Política nova = uma classe com este formato + um membro de `PolicyKind` + a sua
entrada na `ValidationConfig` (concept 4.2 §7 D10). Não é port: é estratégia de
**domínio**, sem I/O, implementada e consumida dentro de `domain`.

Contrato de cada política: sem estado; devolve **todas** as violações do seu tipo
que envolvem a escala avaliada, com o `mode` de `config.rule_for(kind)`; não decide
se está habilitada (quem filtra é o avaliador).
"""

from typing import Protocol

from restaurant_hub.features.scheduling.domain.services.validation.context import (
    EvaluationContext,
)
from restaurant_hub.features.scheduling.domain.value_objects.validation_config import (
    PolicyKind,
    ValidationConfig,
)
from restaurant_hub.features.scheduling.domain.value_objects.violation import Violation


class ValidationPolicy(Protocol):
    """Uma política de validação da escala."""

    @property
    def kind(self) -> PolicyKind:
        """O tipo da política — chave da regra na config e da ordem de avaliação."""
        ...

    def evaluate(
        self, context: EvaluationContext, config: ValidationConfig
    ) -> tuple[Violation, ...]:
        """As violações deste tipo na escala avaliada."""
        ...
