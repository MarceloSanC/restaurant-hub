"""Testes dos adapters SystemClock e Uuid4Generator contra seus ports.

Os ports Clock e IdGenerator são Protocols (structural typing) — os testes
verificam que as implementações concretas satisfazem o contrato na prática:
assinatura, tipo de retorno e semântica (UTC, unicidade).
"""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from restaurant_hub.shared.application.ports.out.clock import Clock
from restaurant_hub.shared.application.ports.out.id_generator import IdGenerator
from restaurant_hub.shared.infrastructure.clock.system_clock import SystemClock
from restaurant_hub.shared.infrastructure.uuid_generator.uuid4_generator import (
    Uuid4Generator,
)

pytestmark = pytest.mark.unit

UUID4_VERSION = 4
SAMPLE_SIZE = 100


def _public_members(protocol: type) -> list[str]:
    return [name for name in dir(protocol) if not name.startswith("_")]


def test_system_clock_satisfaz_o_port_clock() -> None:
    # Introspecção real: todo membro público do Protocol precisa existir e ser
    # chamável no adapter (mypy não checa tests/, então a verificação é aqui).
    clock = SystemClock()
    for member in _public_members(Clock):
        assert callable(getattr(clock, member))


def test_now_retorna_datetime_com_timezone_utc() -> None:
    now = SystemClock().now()
    assert isinstance(now, datetime)
    assert now.tzinfo is UTC


def test_now_acompanha_o_relogio_do_sistema() -> None:
    before = datetime.now(tz=UTC)
    observed = SystemClock().now()
    after = datetime.now(tz=UTC)
    assert before - timedelta(seconds=1) <= observed <= after + timedelta(seconds=1)


def test_uuid4_generator_satisfaz_o_port_id_generator() -> None:
    generator = Uuid4Generator()
    for member in _public_members(IdGenerator):
        assert callable(getattr(generator, member))


def test_next_id_retorna_uuid_versao_4() -> None:
    new_id = Uuid4Generator().next_id()
    assert isinstance(new_id, UUID)
    assert new_id.version == UUID4_VERSION


def test_next_id_gera_ids_unicos() -> None:
    generator = Uuid4Generator()
    ids = {generator.next_id() for _ in range(SAMPLE_SIZE)}
    assert len(ids) == SAMPLE_SIZE
