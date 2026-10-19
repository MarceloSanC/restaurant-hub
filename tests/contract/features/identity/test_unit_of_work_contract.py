"""Contrato da unidade de trabalho de identity — a MESMA suíte no fake e no Postgres (CA2).

Cada lei do port (`unit_of_work.py`, L1 a L6) tem aqui pelo menos um teste que não
sabe com qual implementação está falando. O ponto de cada parametrização:

- **L1 por método de escrita.** A atomicidade não é propriedade da unidade
  sozinha: é da unidade **e** de cada repositório pedir a conexão dela. Um método
  esquecido escapa da unidade em silêncio; por isso a lei é exercida método a
  método, os doze.
- **L3 com erro originado no banco.** Um injetor em Python que levanta antes de
  delegar nunca aborta a transação do Postgres — e é justamente o aborto que o
  savepoint por chamada existe para conter. O teste usa uma violação real de
  `uq_sessions_fingerprint`.
- **L4 por método de leitura.** Leitura que não usasse a conexão da unidade
  enxergaria o banco de antes dela.

Leis que dependem de recursos que só o Postgres tem (pool de conexões, threads com
conexões distintas, um segundo engine) vivem na integração, em
`tests/integration/features/identity/adapters/out/postgres/test_unit_of_work.py`.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest

from restaurant_hub.features.identity.application.dtos.identifiers import (
    PasswordHash,
    SessionId,
    SetupTokenId,
)
from restaurant_hub.features.identity.application.dtos.session import Session
from restaurant_hub.features.identity.application.dtos.setup_tokens import (
    PasswordSetupToken,
    SetupTokenPurpose,
)
from restaurant_hub.features.identity.application.errors import (
    SessionFingerprintAlreadyExistsError,
)
from restaurant_hub.features.identity.domain.entities.restaurant import Restaurant
from restaurant_hub.features.identity.domain.entities.unit import Unit
from restaurant_hub.features.identity.domain.entities.user import User
from restaurant_hub.features.identity.domain.value_objects.email import Email
from restaurant_hub.features.identity.domain.value_objects.identifiers import (
    RestaurantId,
    UnitId,
    UserId,
)
from restaurant_hub.features.identity.domain.value_objects.role import Role
from tests.contract.features.identity.conftest import Repositorios

pytestmark = pytest.mark.contract

_AGORA = datetime(2026, 10, 19, 12, 0, tzinfo=UTC)
_DIA = timedelta(days=1)
_HASH = PasswordHash("hashed::um")


class _Falha(Exception):
    """Exceção do teste: nenhuma implementação a conhece, então nenhuma a traduz."""


def _sessao(n: str, *, expirada: bool = False, user: str = "user-1") -> Session:
    return Session(
        id=SessionId(f"sess-{n}"),
        user_id=UserId(user),
        refresh_token_fingerprint=f"fp::{n}",
        issued_at=_AGORA - 2 * _DIA,
        expires_at=_AGORA - _DIA if expirada else _AGORA + _DIA,
    )


def _token(n: str, *, expirado: bool = False) -> PasswordSetupToken:
    return PasswordSetupToken(
        id=SetupTokenId(f"tok-{n}"),
        user_id=UserId("user-1"),
        purpose=SetupTokenPurpose.INVITATION,
        token_fingerprint=f"tfp::{n}",
        issued_at=_AGORA - 2 * _DIA,
        expires_at=_AGORA - _DIA if expirado else _AGORA + _DIA,
    )


def _usuario(user_id: str, email: str) -> User:
    return User(
        id=UserId(user_id), email=Email(email), role=Role.OWNER, tenant_id=RestaurantId("rest-a")
    )


def _semear(repos: Repositorios) -> None:
    """Estado de partida, gravado fora de unidade (cada chamada comita sozinha — L6)."""
    repos.restaurantes.add(Restaurant(id=RestaurantId("rest-a"), name="Cantina"))
    repos.unidades.add(Unit(id=UnitId("unit-a1"), restaurant_id=RestaurantId("rest-a"), name="C"))
    repos.usuarios.add(_usuario("user-1", "um@x.com"), _HASH)
    repos.sessoes.add(_sessao("1"))
    repos.sessoes.add(_sessao("x", expirada=True))
    repos.tokens_de_setup.add(_token("1"))
    repos.tokens_de_setup.add(_token("x", expirado=True))


def _retrato(repos: Repositorios) -> tuple[object, ...]:
    """Tudo o que as escritas da tabela abaixo podem mudar, lido pelos próprios ports."""
    credenciais = repos.usuarios.find_credentials_by_email(Email("um@x.com"))
    return (
        repos.restaurantes.find_by_id(RestaurantId("rest-b")),
        repos.unidades.find_by_id(UnitId("unit-a2")),
        repos.usuarios.find_by_id(UserId("user-2")),
        repos.usuarios.list_memberships(UserId("user-2")),
        credenciais.password_hash if credenciais is not None else None,
        tuple(repos.sessoes.find_by_fingerprint(f"fp::{n}") for n in ("1", "2", "x")),
        tuple(repos.tokens_de_setup.find_by_fingerprint(f"tfp::{n}") for n in ("1", "2", "x")),
    )


def _vincular_user_2(repos: Repositorios) -> None:
    unidade = repos.unidades.find_by_id(UnitId("unit-a1"))
    assert unidade is not None
    user_2 = _usuario("user-2", "dois@x.com")
    repos.usuarios.add(user_2, _HASH, [user_2.link_to_unit(unidade)])


# Os doze métodos de escrita dos cinco ports. Um método novo de escrita num port de
# identity precisa entrar aqui — é o que mantém a L1 total.
_ESCRITAS: dict[str, Callable[[Repositorios], object]] = {
    "restaurantes.add": lambda r: r.restaurantes.add(
        Restaurant(id=RestaurantId("rest-b"), name="Outro")
    ),
    "unidades.add": lambda r: r.unidades.add(
        Unit(id=UnitId("unit-a2"), restaurant_id=RestaurantId("rest-a"), name="Praia")
    ),
    "usuarios.add": _vincular_user_2,
    "usuarios.set_password_hash": lambda r: r.usuarios.set_password_hash(
        UserId("user-1"), PasswordHash("hashed::dois")
    ),
    "sessoes.add": lambda r: r.sessoes.add(_sessao("2")),
    "sessoes.revoke": lambda r: r.sessoes.revoke(SessionId("sess-1"), _AGORA),
    "sessoes.revoke_all_for_user": lambda r: r.sessoes.revoke_all_for_user(
        UserId("user-1"), _AGORA
    ),
    "sessoes.purge_expired": lambda r: r.sessoes.purge_expired(_AGORA),
    "tokens.add": lambda r: r.tokens_de_setup.add(_token("2")),
    "tokens.consume": lambda r: r.tokens_de_setup.consume(SetupTokenId("tok-1"), _AGORA),
    "tokens.invalidate_all_for_user": lambda r: r.tokens_de_setup.invalidate_all_for_user(
        UserId("user-1"), _AGORA
    ),
    "tokens.purge_expired": lambda r: r.tokens_de_setup.purge_expired(_AGORA),
}


# ---------------------------------------------------------------------------
# L1 — tudo ou nada
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("escrita", sorted(_ESCRITAS))
def test_l1_escrita_desfeita_quando_a_unidade_sai_por_excecao(
    repos: Repositorios, escrita: str
) -> None:
    _semear(repos)
    antes = _retrato(repos)

    with pytest.raises(_Falha), repos.unidade_de_trabalho.transaction():
        _ESCRITAS[escrita](repos)
        assert _retrato(repos) != antes  # a escrita aconteceu, dentro da unidade
        raise _Falha

    assert _retrato(repos) == antes


@pytest.mark.parametrize("escrita", sorted(_ESCRITAS))
def test_l1_escrita_mantida_quando_a_unidade_sai_normalmente(
    repos: Repositorios, escrita: str
) -> None:
    _semear(repos)
    antes = _retrato(repos)

    with repos.unidade_de_trabalho.transaction():
        _ESCRITAS[escrita](repos)

    assert _retrato(repos) != antes


def test_l1_as_doze_escritas_juntas_somem_juntas(repos: Repositorios) -> None:
    _semear(repos)
    antes = _retrato(repos)

    with pytest.raises(_Falha), repos.unidade_de_trabalho.transaction():
        for escrita in sorted(_ESCRITAS):
            _ESCRITAS[escrita](repos)
        raise _Falha

    assert _retrato(repos) == antes


# ---------------------------------------------------------------------------
# L2 — a exceção atravessa intacta
# ---------------------------------------------------------------------------


def test_l2_a_excecao_que_sai_e_o_mesmo_objeto(repos: Repositorios) -> None:
    _semear(repos)
    falha = _Falha("mensagem preservada")

    with pytest.raises(_Falha) as capturada, repos.unidade_de_trabalho.transaction():
        repos.sessoes.add(_sessao("2"))
        raise falha

    assert capturada.value is falha


# ---------------------------------------------------------------------------
# L3 — chamada que falha não deixa efeito próprio nem envenena a unidade
# ---------------------------------------------------------------------------


def test_l3_violacao_real_de_constraint_nao_envenena_a_unidade(repos: Repositorios) -> None:
    """A recusa vem do banco (`uq_sessions_fingerprint`), e a unidade comita o resto."""
    _semear(repos)

    with repos.unidade_de_trabalho.transaction():
        repos.sessoes.add(_sessao("2"))
        with pytest.raises(SessionFingerprintAlreadyExistsError):
            repos.sessoes.add(
                Session(
                    id=SessionId("sess-3"),
                    user_id=UserId("user-1"),
                    refresh_token_fingerprint="fp::2",
                    issued_at=_AGORA,
                    expires_at=_AGORA + _DIA,
                )
            )
        repos.tokens_de_setup.add(_token("2"))

    segunda = repos.sessoes.find_by_fingerprint("fp::2")
    assert segunda is not None
    assert segunda.id == "sess-2"
    assert repos.tokens_de_setup.find_by_fingerprint("tfp::2") is not None


# ---------------------------------------------------------------------------
# L4 — leitura dentro vê as escritas da própria unidade
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Leitura:
    escrever: Callable[[Repositorios], object]
    ler: Callable[[Repositorios], object]


def _hash_trocado(repos: Repositorios) -> bool:
    credenciais = repos.usuarios.find_credentials_by_email(Email("um@x.com"))
    return credenciais is not None and credenciais.password_hash == "hashed::dois"


def _sessao_1_revogada(repos: Repositorios) -> bool:
    sessao = repos.sessoes.find_by_fingerprint("fp::1")
    return sessao is not None and sessao.revoked_at is not None


def _token_1_consumido(repos: Repositorios) -> bool:
    token = repos.tokens_de_setup.find_by_fingerprint("tfp::1")
    return token is not None and token.consumed_at is not None


_LEITURAS: dict[str, _Leitura] = {
    "restaurantes.find_by_id": _Leitura(
        _ESCRITAS["restaurantes.add"],
        lambda r: r.restaurantes.find_by_id(RestaurantId("rest-b")) is not None,
    ),
    "unidades.find_by_id": _Leitura(
        _ESCRITAS["unidades.add"], lambda r: r.unidades.find_by_id(UnitId("unit-a2")) is not None
    ),
    "usuarios.find_by_id": _Leitura(
        _vincular_user_2, lambda r: r.usuarios.find_by_id(UserId("user-2")) is not None
    ),
    "usuarios.exists_by_email": _Leitura(
        _vincular_user_2, lambda r: r.usuarios.exists_by_email(Email("dois@x.com"))
    ),
    "usuarios.find_credentials_by_email": _Leitura(
        _ESCRITAS["usuarios.set_password_hash"],
        _hash_trocado,
    ),
    "usuarios.list_memberships": _Leitura(
        _vincular_user_2, lambda r: len(r.usuarios.list_memberships(UserId("user-2"))) == 1
    ),
    "sessoes.find_by_fingerprint": _Leitura(
        _ESCRITAS["sessoes.revoke"],
        _sessao_1_revogada,
    ),
    "tokens.find_by_fingerprint": _Leitura(
        _ESCRITAS["tokens.consume"],
        _token_1_consumido,
    ),
}


@pytest.mark.parametrize("leitura", sorted(_LEITURAS))
def test_l4_leitura_dentro_da_unidade_ve_a_escrita_dela(repos: Repositorios, leitura: str) -> None:
    _semear(repos)
    caso = _LEITURAS[leitura]
    assert caso.ler(repos) is False

    with pytest.raises(_Falha), repos.unidade_de_trabalho.transaction():
        caso.escrever(repos)
        assert caso.ler(repos) is True
        raise _Falha

    assert caso.ler(repos) is False


# ---------------------------------------------------------------------------
# L5 — não reentrante
# ---------------------------------------------------------------------------


def test_l5_unidade_aninhada_levanta_e_a_externa_segue_utilizavel(repos: Repositorios) -> None:
    _semear(repos)

    with repos.unidade_de_trabalho.transaction():
        repos.sessoes.add(_sessao("2"))
        with pytest.raises(RuntimeError, match="L5"), repos.unidade_de_trabalho.transaction():
            repos.tokens_de_setup.add(_token("2"))  # pragma: no cover — nunca roda
        repos.tokens_de_setup.add(_token("3"))

    assert repos.sessoes.find_by_fingerprint("fp::2") is not None
    assert repos.tokens_de_setup.find_by_fingerprint("tfp::2") is None
    assert repos.tokens_de_setup.find_by_fingerprint("tfp::3") is not None


def test_l5_unidade_fechada_libera_a_seguinte(repos: Repositorios) -> None:
    _semear(repos)

    with pytest.raises(_Falha), repos.unidade_de_trabalho.transaction():
        raise _Falha
    with repos.unidade_de_trabalho.transaction():
        repos.sessoes.add(_sessao("2"))

    assert repos.sessoes.find_by_fingerprint("fp::2") is not None


# ---------------------------------------------------------------------------
# L6 — fora da unidade nada muda
# ---------------------------------------------------------------------------


def test_l6_escrita_fora_da_unidade_nao_e_desfeita_por_unidade_posterior(
    repos: Repositorios,
) -> None:
    _semear(repos)
    repos.sessoes.add(_sessao("2"))

    with pytest.raises(_Falha), repos.unidade_de_trabalho.transaction():
        repos.tokens_de_setup.add(_token("2"))
        raise _Falha

    assert repos.sessoes.find_by_fingerprint("fp::2") is not None
    assert repos.tokens_de_setup.find_by_fingerprint("tfp::2") is None
