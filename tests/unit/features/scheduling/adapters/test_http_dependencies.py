"""Validadores da borda, requisitos de acesso e provedor de ator de scheduling (Stage 4.5).

Os validadores recusam exatamente o que o docstring do módulo diz, e nada além (ADR
2.3.0005): o resto do conjunto adversarial volta verbatim.
"""

from datetime import date, datetime

import pytest

from restaurant_hub.features.scheduling.adapters.inbound.http import dependencies
from restaurant_hub.features.scheduling.adapters.inbound.http.dependencies import (
    MANAGE_SCHEDULE_ACCESS,
    VIEW_OWN_SCHEDULE_ACCESS,
    VIEW_SCHEDULE_ACCESS,
    authenticated_actor,
    get_access_guard,
    validate_creation_id,
    validate_day,
    validate_identifier,
    validate_instant,
)
from restaurant_hub.features.scheduling.application.errors import InvalidScheduleRequestError
from restaurant_hub.features.scheduling.domain.exceptions.errors import InvalidIdentifierError
from tests.fakes.features.scheduling.in_memory_access_guard import InMemoryAccessGuard

pytestmark = pytest.mark.unit

_UUID = "0b7a1d4e-6c55-4f2c-9d0a-6f1e2b3c4d5e"


@pytest.mark.parametrize("valor", ["", " ", "\t\n", "u\x00", "\x00"])
def test_validate_identifier_recusa_vazio_so_espaco_e_nul(valor: str) -> None:
    with pytest.raises(InvalidIdentifierError):
        validate_identifier(valor, entity="unidade")


@pytest.mark.parametrize(
    "valor", ["u1", "José Antônio", "a" * 1000, " u1 ", "linha1\nlinha2", "👩‍🍳"]
)
def test_validate_identifier_devolve_o_resto_verbatim(valor: str) -> None:
    assert validate_identifier(valor, entity="unidade") == valor


def test_validate_creation_id_aceita_uuid_canonico() -> None:
    assert validate_creation_id(_UUID, entity="faixa") == _UUID


@pytest.mark.parametrize(
    "valor",
    [
        "",
        "f1",
        _UUID.upper(),
        "{" + _UUID + "}",
        _UUID.replace("-", ""),
        f"urn:uuid:{_UUID}",
        _UUID + "\x00",
        " " + _UUID,
    ],
    ids=["vazio", "nao-uuid", "maiusculo", "chaves", "sem-hifen", "urn", "nul", "espaco"],
)
def test_validate_creation_id_recusa_o_que_nao_e_uuid_canonico(valor: str) -> None:
    with pytest.raises(InvalidIdentifierError):
        validate_creation_id(valor, entity="faixa")


@pytest.mark.parametrize(
    "dia", [date(2, 1, 1), date(2026, 11, 23), date(9998, 12, 31)], ids=["min", "meio", "max"]
)
def test_validate_day_aceita_os_anos_de_2_a_9998(dia: date) -> None:
    assert validate_day(dia, name="first_day") == dia


@pytest.mark.parametrize("dia", [date.min, date(1, 12, 31), date(9999, 1, 1), date.max], ids=str)
def test_validate_day_recusa_dia_extremo(dia: date) -> None:
    with pytest.raises(InvalidScheduleRequestError, match="first_day"):
        validate_day(dia, name="first_day")


@pytest.mark.parametrize(
    "instante", [datetime(1, 1, 1, 3), datetime(9999, 12, 31, 23)], ids=["min", "max"]
)
def test_validate_instant_recusa_instante_extremo(instante: datetime) -> None:
    with pytest.raises(InvalidScheduleRequestError, match="start"):
        validate_instant(instante, name="start")


def test_validate_instant_aceita_instante_comum() -> None:
    instante = datetime(2026, 12, 7, 8)
    assert validate_instant(instante, name="start") is instante


def test_os_tres_requisitos_sao_as_permissoes_do_port_sobre_a_unidade() -> None:
    assert (
        VIEW_SCHEDULE_ACCESS.permission,
        MANAGE_SCHEDULE_ACCESS.permission,
        VIEW_OWN_SCHEDULE_ACCESS.permission,
    ) == ("view_schedule", "manage_schedule", "view_own_schedule")
    assert all(
        r.names_unit
        for r in (VIEW_SCHEDULE_ACCESS, MANAGE_SCHEDULE_ACCESS, VIEW_OWN_SCHEDULE_ACCESS)
    )


def test_get_access_guard_falha_alto_sem_wiring() -> None:
    with pytest.raises(RuntimeError, match="composition root"):
        get_access_guard()


def test_authenticated_actor_delega_ao_guard_e_deixa_a_recusa_crua() -> None:
    guard = InMemoryAccessGuard()
    ator = guard.issue("user-1", "t1")
    pedido = {"authorization": "Bearer user-1"}
    assert authenticated_actor(pedido, guard) is ator  # type: ignore[arg-type]
    with pytest.raises(Exception) as excinfo:
        authenticated_actor({}, guard)  # type: ignore[arg-type]
    assert excinfo.value is guard.authentication_error


def test_o_modulo_nao_nomeia_o_vocabulario_de_identity() -> None:
    """As permissões atravessam como valores (ADR 4.3.0002 §2)."""
    assert not {"Role", "Permission"} & set(vars(dependencies))
