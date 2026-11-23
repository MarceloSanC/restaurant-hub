"""Validadores da borda, requisito de acesso por rota e provedor de ator — BC scheduling.

**Este módulo não decide acesso.** Ele declara qual permissão cada rota exige e delega ao
port `AccessGuard`; as permissões atravessam a fronteira como **valores**, do módulo do port
(ADR 4.3.0002 §2), jamais como enum de identity.

## A ordem é contrato: autenticar → validar → autorizar (ADR 3.6.0002)

- **Autenticar primeiro**, por `Depends`: requisição sem credencial recebe 401, não um 422
  que deixaria quem não tem credencial sondar a forma do payload.
- **Validar identificadores antes de autorizar**: nenhum valor cru chega ao guard nem, por
  ele, a `units.find_by_id` dentro de identity. O byte NUL vira `DataError` no psycopg, que
  não é erro de nenhum BC e responderia **500** (finding do concept 4.4 §10).

## O que os validadores recusam, e nada além (ADR 2.3.0005: sem normalização silenciosa)

- `validate_identifier`: vazio, só-espaço e NUL ⇒ `InvalidIdentifierError` (422).
- `validate_creation_id`: além disso, o id que o **cliente cria** (faixa, demanda, alocação —
  ADR 4.3.0004) tem de ser UUID em texto canônico (`str(UUID(raw)) == raw`, minúsculo com
  hífens). Ids de referência e de path não: o da unidade é de identity, e o da escala, se não
  for UUID, simplesmente não existe (404).
- `validate_day`/`validate_instant`: ano entre 2 e 9998 ⇒ senão `InvalidScheduleRequestError`
  (422). O período (7 dias), as vizinhas (±1 dia) e o dia operacional de um instante antes do
  corte somam `timedelta`, e perto de `date.min`/`date.max` isso levanta `OverflowError` —
  500 (concept 4.5 §6, "Dia ou instante extremo").

**Limite medido:** segmento de path **vazio** não casa `[^/]+`, e o Starlette responde 404/405
sem que o validador rode (ADR 3.6.0002).
"""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Annotated, Final, Never
from uuid import UUID

from fastapi import Depends, Request

from restaurant_hub.features.scheduling.application.errors import InvalidScheduleRequestError
from restaurant_hub.features.scheduling.application.ports.out.access_guard import (
    PERMISSION_MANAGE_SCHEDULE,
    PERMISSION_VIEW_OWN_SCHEDULE,
    PERMISSION_VIEW_SCHEDULE,
    AccessGuard,
    Actor,
)
from restaurant_hub.features.scheduling.domain.exceptions.errors import InvalidIdentifierError

_BYTE_NUL: Final = "\x00"

# Os anos aceitos em dia e instante: longe o bastante de `date.min`/`date.max` para que
# nenhuma soma de dias do BC (período, vizinha, recorte de 42 dias, dia operacional) estoure.
MIN_YEAR: Final = 2
MAX_YEAR: Final = 9998


def validate_identifier(raw: str, *, entity: str) -> str:
    """Identificador vindo da requisição — path, query ou corpo —, devolvido **verbatim**.

    Raises:
        InvalidIdentifierError: vazio, só-espaço ou contendo o byte NUL (422).
    """
    if not raw.strip() or _BYTE_NUL in raw:
        raise InvalidIdentifierError(entity)
    return raw


def validate_creation_id(raw: str, *, entity: str) -> str:
    """Id que o cliente cria num lote: UUID em texto canônico (ADR 4.3.0004; D-IDS).

    Raises:
        InvalidIdentifierError: não é identificador válido ou não é UUID canônico (422).
    """
    validate_identifier(raw, entity=entity)
    try:
        canonical = str(UUID(raw))
    except ValueError as exc:
        raise InvalidIdentifierError(entity) from exc
    if canonical != raw:
        raise InvalidIdentifierError(entity)
    return raw


def validate_day(value: date, *, name: str) -> date:
    """Dia de calendário dentro dos anos aceitos.

    Raises:
        InvalidScheduleRequestError: ano fora de [2, 9998] (422).
    """
    if not MIN_YEAR <= value.year <= MAX_YEAR:
        raise InvalidScheduleRequestError(f"{name} fora dos anos aceitos ({MIN_YEAR} a {MAX_YEAR})")
    return value


def validate_instant(value: datetime, *, name: str) -> datetime:
    """Instante de parede dentro dos anos aceitos (o offset é recusado pelo domínio).

    Raises:
        InvalidScheduleRequestError: ano fora de [2, 9998] (422).
    """
    if not MIN_YEAR <= value.year <= MAX_YEAR:
        raise InvalidScheduleRequestError(f"{name} fora dos anos aceitos ({MIN_YEAR} a {MAX_YEAR})")
    return value


@dataclass(frozen=True)
class AccessRequirement:
    """O requisito de acesso de uma rota: a permissão exigida, sobre a unidade do path.

    É **declaração**, não decisão. Toda rota de scheduling nomeia a unidade (as três
    permissões são unit-scoped, ADR 4.1.0004 §1); o campo existe para que o teste de borda
    compare a rota com o requisito sem ler o corpo do handler.
    """

    permission: str
    names_unit: bool = True


# Os três requisitos da Stage 4.5 (concept §4.1). O sufixo `_ACCESS` evita o nome dos membros
# de `Permission` de identity, que scheduling nunca importa.
VIEW_SCHEDULE_ACCESS: Final = AccessRequirement(permission=PERMISSION_VIEW_SCHEDULE)
MANAGE_SCHEDULE_ACCESS: Final = AccessRequirement(permission=PERMISSION_MANAGE_SCHEDULE)
VIEW_OWN_SCHEDULE_ACCESS: Final = AccessRequirement(permission=PERMISSION_VIEW_OWN_SCHEDULE)


def _not_wired(name: str) -> Never:
    raise RuntimeError(
        f"dependência {name!r} não foi conectada pelo composition root — "
        "veja wire_dependencies() e create_app()"
    )


def get_access_guard() -> AccessGuard:
    """Chave do `dependency_overrides`, preenchida pelo composition root."""
    _not_wired("scheduling_access_guard")


def authenticated_actor(
    request: Request,
    guard: Annotated[AccessGuard, Depends(get_access_guard)],
) -> Actor:
    """Autenticação como **dependência**: roda antes da validação do corpo (401 antes de 422).

    A exceção sai crua (L-SG1): a faixa 401 é a de identity.
    """
    actor: Actor = guard.authenticate(request)
    return actor


SchedulingAccessGuard = Annotated[AccessGuard, Depends(get_access_guard)]
CurrentActor = Annotated[Actor, Depends(authenticated_actor)]
