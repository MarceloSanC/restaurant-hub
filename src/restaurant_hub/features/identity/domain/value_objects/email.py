"""Value object Email — endereço de login do usuário.

Frozen e auto-validado: normaliza (trim + lowercase) e valida um formato
pragmático no `__post_init__`. **Não** implementa a RFC 5322 (concept §7) —
validação exaustiva de e-mail é fonte de falso-negativo; o que o domínio garante é
que um `Email` nunca existe malformado. A **unicidade global** do e-mail é
invariante de persistência (Stage 2.3), não deste value object.
"""

import re
from dataclasses import dataclass

from restaurant_hub.features.identity.domain.exceptions.errors import InvalidEmailError

# local@dominio.tld — sem espaços, exatamente um "@", com ponto no domínio.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@dataclass(frozen=True)
class Email:
    """Endereço de e-mail normalizado e validado.

    Attributes:
        value: e-mail já normalizado (trim + lowercase).
    """

    value: str

    def __post_init__(self) -> None:
        normalized = self.value.strip().lower()
        if not _EMAIL_RE.match(normalized):
            # Reporta o valor original recebido, não o normalizado.
            raise InvalidEmailError(self.value)
        # frozen=True bloqueia o setattr comum; normalizar exige contorná-lo.
        object.__setattr__(self, "value", normalized)
