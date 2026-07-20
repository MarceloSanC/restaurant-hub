"""Testes dos mappers — sem banco.

Concentram-se nas duas regras que a persistência pode furar em silêncio: a
reidratação passar pelo construtor (revalidando invariantes) e o datetime
atravessar a fronteira aware em UTC.
"""

from datetime import UTC, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from restaurant_hub.features.identity.adapters.out.postgres import mappers
from restaurant_hub.features.identity.application.dtos.identifiers import PasswordHash, SessionId
from restaurant_hub.features.identity.application.dtos.session import Session
from restaurant_hub.features.identity.domain.entities.restaurant import Restaurant
from restaurant_hub.features.identity.domain.entities.unit import Unit
from restaurant_hub.features.identity.domain.entities.user import User
from restaurant_hub.features.identity.domain.exceptions.errors import (
    InvalidIdentifierError,
    InvalidRoleError,
    MissingTenantError,
    PlatformAdminTenantError,
)
from restaurant_hub.features.identity.domain.value_objects.email import Email
from restaurant_hub.features.identity.domain.value_objects.identifiers import (
    RestaurantId,
    UnitId,
    UserId,
)
from restaurant_hub.features.identity.domain.value_objects.role import Role
from restaurant_hub.features.identity.domain.value_objects.unit_membership import (
    UnitMembership,
)

pytestmark = pytest.mark.unit

_NOW = datetime(2026, 7, 19, 12, 0, tzinfo=UTC)
_HASH = PasswordHash("hashed::s3nha")


def _linha(**campos: object) -> SimpleNamespace:
    """Linha do SQLAlchemy é acessada por atributo — `SimpleNamespace` basta."""
    return SimpleNamespace(**campos)


# ---------------------------------------------------------------------------
# Round-trip fiel
# ---------------------------------------------------------------------------


def test_restaurante_faz_round_trip_com_name_verbatim() -> None:
    """`name` não é normalizado na persistência (ADR 2.3.0005).

    Normalizar aqui tornaria `add` lossy e faria o adapter divergir do fake, que
    guarda verbatim — a classe de bug que os contract tests existem para eliminar.
    """
    restaurante = Restaurant(id=RestaurantId("rest-1"), name="  Cantina  ")

    linha = mappers.restaurante_para_linha(restaurante)
    assert linha["name"] == "  Cantina  "

    de_volta = mappers.linha_para_restaurante(_linha(**linha))
    assert de_volta.id == "rest-1"
    assert de_volta.name == "  Cantina  "


def test_unidade_faz_round_trip() -> None:
    unidade = Unit(id=UnitId("unit-1"), restaurant_id=RestaurantId("rest-1"), name="Centro")
    de_volta = mappers.linha_para_unidade(_linha(**mappers.unidade_para_linha(unidade)))
    assert (de_volta.id, de_volta.restaurant_id, de_volta.name) == (
        "unit-1",
        "rest-1",
        "Centro",
    )


def test_usuario_faz_round_trip_e_o_hash_viaja_ao_lado() -> None:
    """`User` não carrega senha; o hash é coluna da mesma linha (DTO da 2.2)."""
    user = User(
        id=UserId("user-1"),
        email=Email("dono@x.com"),
        role=Role.OWNER,
        tenant_id=RestaurantId("rest-1"),
    )

    linha = mappers.usuario_para_linha(user, _HASH)
    assert linha["password_hash"] == _HASH
    assert linha["role"] == "owner"

    de_volta = mappers.linha_para_usuario(_linha(**linha))
    assert de_volta.id == "user-1"
    assert de_volta.email == Email("dono@x.com")
    assert de_volta.role is Role.OWNER
    assert de_volta.tenant_id == "rest-1"


def test_platform_admin_faz_round_trip_com_tenant_nulo() -> None:
    admin = User(
        id=UserId("admin-1"),
        email=Email("adm@x.com"),
        role=Role.PLATFORM_ADMIN,
        tenant_id=None,
    )
    linha = mappers.usuario_para_linha(admin, _HASH)
    assert linha["tenant_id"] is None

    de_volta = mappers.linha_para_usuario(_linha(**linha))
    assert de_volta.tenant_id is None
    assert de_volta.role is Role.PLATFORM_ADMIN


def test_vinculo_recebe_o_tenant_de_quem_grava() -> None:
    """`UnitMembership` só carrega dois ids; o tenant vem do repositório."""
    vinculo = UnitMembership(user_id=UserId("user-1"), unit_id=UnitId("unit-1"))

    linha = mappers.vinculo_para_linha(vinculo, RestaurantId("rest-1"))
    assert linha == {"user_id": "user-1", "unit_id": "unit-1", "tenant_id": "rest-1"}

    assert mappers.linha_para_vinculo(_linha(**linha)) == vinculo


def test_sessao_faz_round_trip_e_nao_carrega_valor_de_token() -> None:
    sessao = Session(
        id=SessionId("sess-1"),
        user_id=UserId("user-1"),
        refresh_token_fingerprint="fp::abc",
        issued_at=_NOW,
        expires_at=_NOW + timedelta(days=7),
    )
    linha = mappers.sessao_para_linha(sessao)

    assert set(linha) == {
        "id",
        "user_id",
        "refresh_token_fingerprint",
        "issued_at",
        "expires_at",
        "revoked_at",
    }
    assert mappers.linha_para_sessao(_linha(**linha)) == sessao


# ---------------------------------------------------------------------------
# Reidratação passa pelo construtor — I1 / CA15
# ---------------------------------------------------------------------------


def test_linha_com_platform_admin_e_tenant_levanta_ao_ler() -> None:
    """Linha inconsistente falha ALTO na leitura (I1).

    É a proteção que a auditoria da 2.1 pediu: se o mapper contornasse o
    construtor, esta linha voltaria como um `User` inválido e o resto do sistema o
    trataria como legítimo — um `platform_admin` com tenant enxergando o tenant.
    """
    with pytest.raises(PlatformAdminTenantError):
        mappers.linha_para_usuario(
            _linha(
                id="admin-1",
                email="adm@x.com",
                role="platform_admin",
                tenant_id="rest-1",
                password_hash=_HASH,
            )
        )


def test_linha_de_papel_de_restaurante_sem_tenant_levanta_ao_ler() -> None:
    with pytest.raises(MissingTenantError):
        mappers.linha_para_usuario(
            _linha(
                id="user-1",
                email="dono@x.com",
                role="owner",
                tenant_id=None,
                password_hash=_HASH,
            )
        )


def test_linha_com_papel_desconhecido_levanta_antes_de_construir_o_usuario() -> None:
    """`Role.from_string` roda primeiro — a ordem é parte da especificação (§6)."""
    with pytest.raises(InvalidRoleError):
        mappers.linha_para_usuario(
            _linha(
                id="user-1",
                email="dono@x.com",
                role="wizard",
                tenant_id="rest-1",
                password_hash=_HASH,
            )
        )


def test_linha_com_id_vazio_levanta_ao_ler() -> None:
    with pytest.raises(InvalidIdentifierError):
        mappers.linha_para_usuario(
            _linha(
                id="   ",
                email="dono@x.com",
                role="owner",
                tenant_id="rest-1",
                password_hash=_HASH,
            )
        )


def test_precedencia_papel_invalido_vence_tenant_inconsistente() -> None:
    """Com duas violações simultâneas, quem levanta é a checagem que roda antes.

    Fixar a precedência evita que a exceção observada dependa de detalhe de
    implementação — o finding de "precedência não especificada" da 2.1 aplicado à
    fronteira de leitura.
    """
    with pytest.raises(InvalidRoleError):
        mappers.linha_para_usuario(
            _linha(
                id="user-1",
                email="dono@x.com",
                role="wizard",
                tenant_id=None,
                password_hash=_HASH,
            )
        )


def test_precedencia_papel_invalido_vence_email_malformado() -> None:
    """`Role.from_string` roda ANTES de `Email` — §6 fixa essa ordem.

    Este é o par que a ordem dos argumentos do construtor não protege: se o mapper
    montar `User(...)` com `email=` escrito antes de `role=`, Python avalia os
    argumentos na ordem da FONTE e o chamador vê `InvalidEmailError` onde a spec
    manda `InvalidRoleError`. Manter os dois eixos corrompidos na mesma linha é o
    único jeito de a precedência ficar observável — com um eixo só, qualquer ordem
    passa.
    """
    with pytest.raises(InvalidRoleError):
        mappers.linha_para_usuario(
            _linha(
                id="user-1",
                email="nao-e-email",
                role="wizard",
                tenant_id="rest-1",
                password_hash=_HASH,
            )
        )


# ---------------------------------------------------------------------------
# Fuso — I10
# ---------------------------------------------------------------------------


def test_datetime_lido_em_outro_fuso_volta_em_utc() -> None:
    """O psycopg devolve `timestamptz` no fuso da SESSÃO, não em UTC.

    Sem normalizar, o mesmo instante voltaria como `-03:00` numa máquina em
    São Paulo e `+00:00` no runner — e `is_active` passaria a depender do fuso de
    quem consulta. Verificado empiricamente contra o Postgres na Fase 3A.
    """
    sao_paulo = timezone(timedelta(hours=-3))
    em_sao_paulo = _NOW.astimezone(sao_paulo)

    sessao = mappers.linha_para_sessao(
        _linha(
            id="sess-1",
            user_id="user-1",
            refresh_token_fingerprint="fp::abc",
            issued_at=em_sao_paulo,
            expires_at=em_sao_paulo + timedelta(days=7),
            revoked_at=None,
        )
    )

    assert sessao.issued_at.tzinfo == UTC
    assert sessao.expires_at.tzinfo == UTC
    # Mesmo instante, fuso normalizado.
    assert sessao.issued_at == _NOW


def test_datetime_naive_e_interpretado_como_utc() -> None:
    """Robustez: naive vindo do banco vira aware em UTC, nunca fica naive.

    Deixar passar naive faria `is_active` comparar naive com aware e levantar
    `TypeError` no meio de uma renovação de token.
    """
    sessao = mappers.linha_para_sessao(
        _linha(
            id="sess-1",
            user_id="user-1",
            refresh_token_fingerprint="fp::abc",
            issued_at=datetime(2026, 7, 19, 12, 0),
            expires_at=datetime(2026, 7, 26, 12, 0),
            revoked_at=None,
        )
    )
    assert sessao.issued_at.tzinfo == UTC
    assert sessao.is_active(_NOW) is True


def test_revoked_at_nulo_continua_nulo() -> None:
    sessao = mappers.linha_para_sessao(
        _linha(
            id="sess-1",
            user_id="user-1",
            refresh_token_fingerprint="fp::abc",
            issued_at=_NOW,
            expires_at=_NOW + timedelta(days=7),
            revoked_at=None,
        )
    )
    assert sessao.revoked_at is None


def test_revoked_at_preenchido_volta_em_utc() -> None:
    sao_paulo = timezone(timedelta(hours=-3))
    sessao = mappers.linha_para_sessao(
        _linha(
            id="sess-1",
            user_id="user-1",
            refresh_token_fingerprint="fp::abc",
            issued_at=_NOW,
            expires_at=_NOW + timedelta(days=7),
            revoked_at=_NOW.astimezone(sao_paulo),
        )
    )
    assert sessao.revoked_at is not None
    assert sessao.revoked_at.tzinfo == UTC
    assert sessao.revoked_at == _NOW
