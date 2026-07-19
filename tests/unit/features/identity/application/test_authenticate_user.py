"""Testes do use case `authenticate_user` — concept CA6, CA7, CA15."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from restaurant_hub.features.identity.application.dtos.commands import (
    AuthenticateUserCommand,
)
from restaurant_hub.features.identity.application.dtos.identifiers import PasswordHash
from restaurant_hub.features.identity.application.errors import InvalidCredentialsError
from restaurant_hub.features.identity.application.use_cases.authenticate_user import (
    AuthenticateUserUseCase,
)
from restaurant_hub.features.identity.domain.entities.user import User
from restaurant_hub.features.identity.domain.value_objects.email import Email
from restaurant_hub.features.identity.domain.value_objects.identifiers import (
    RestaurantId,
    UserId,
)
from restaurant_hub.features.identity.domain.value_objects.role import Role
from tests.fakes.features.identity.fake_password_hasher import FakePasswordHasher
from tests.fakes.features.identity.fake_token_issuer import FakeTokenIssuer
from tests.fakes.features.identity.in_memory_session_repository import (
    InMemorySessionRepository,
)
from tests.fakes.features.identity.in_memory_user_repository import InMemoryUserRepository
from tests.fakes.shared.fake_clock import FakeClock
from tests.fakes.shared.fake_id_generator import FakeIdGenerator

pytestmark = pytest.mark.unit

_NOW = datetime(2026, 7, 18, 12, 0, tzinfo=UTC)
_ACCESS_TTL = timedelta(minutes=15)
_REFRESH_TTL = timedelta(days=7)
_SESSION_UUID = UUID("44444444-4444-4444-4444-444444444444")
_USER_ID = UserId("user-1")
_SENHA = "s3nha"


class _Fixture:
    def __init__(self, *, com_usuario: bool = True) -> None:
        self.users = InMemoryUserRepository()
        self.sessions = InMemorySessionRepository()
        self.hasher = FakePasswordHasher()
        self.issuer = FakeTokenIssuer()
        self.clock = FakeClock(_NOW)
        self.user = User(
            id=_USER_ID,
            email=Email("dono@x.com"),
            role=Role.OWNER,
            tenant_id=RestaurantId("rest-1"),
        )
        if com_usuario:
            self.users.add(self.user, self.hasher.hash(_SENHA))
        self.use_case = AuthenticateUserUseCase(
            self.users,
            self.sessions,
            self.hasher,
            self.issuer,
            FakeIdGenerator([_SESSION_UUID]),
            self.clock,
            _ACCESS_TTL,
            _REFRESH_TTL,
        )


def _command(senha: str = _SENHA, email: str = "dono@x.com") -> AuthenticateUserCommand:
    return AuthenticateUserCommand(email=Email(email), plain_password=senha)


def test_login_valido_emite_par_de_tokens() -> None:
    """CA6 — caminho feliz."""
    fixture = _Fixture()

    result = fixture.use_case.execute(_command())

    assert result.user_id == _USER_ID
    assert result.access_token
    assert result.refresh_token
    assert result.access_token_expires_at == _NOW + _ACCESS_TTL
    assert result.refresh_token_expires_at == _NOW + _REFRESH_TTL


def test_login_valido_persiste_sessao_ativa_com_o_fingerprint_do_token_emitido() -> None:
    """CA6 — a correspondência é recomputada pelo caminho que a 2.4 vai percorrer.

    Comparar `session.refresh_token_fingerprint` com o campo do token emitido
    passaria mesmo num adapter que derivasse o fingerprint de dois jeitos
    diferentes na emissão e na consulta. Aqui derivamos do **valor devolvido ao
    cliente**, que é como a 2.4 localiza a sessão no refresh.
    """
    fixture = _Fixture()

    result = fixture.use_case.execute(_command())

    esperado = fixture.issuer.fingerprint(result.refresh_token)
    session = fixture.sessions.find_by_fingerprint(esperado)
    assert session is not None
    assert session.user_id == _USER_ID
    assert session.is_active(_NOW) is True
    assert session.issued_at == _NOW
    assert session.expires_at == _NOW + _REFRESH_TTL
    assert session.revoked_at is None


def test_sessao_carrega_o_id_gerado_e_as_claims_referenciam_a_sessao() -> None:
    """`session_id` nas claims é o gancho que fecha a janela residual na 2.4."""
    fixture = _Fixture()

    fixture.use_case.execute(_command())

    assert fixture.issuer.issued_claims[0].session_id == str(_SESSION_UUID)
    assert fixture.issuer.issued_claims[0].subject == _USER_ID
    assert fixture.issuer.issued_claims[0].expires_at == _NOW + _ACCESS_TTL


def test_claims_carregam_papel_e_tenant_do_usuario() -> None:
    """Evita que o guard da 2.4 tenha de reconsultar o banco a cada requisição."""
    fixture = _Fixture()

    fixture.use_case.execute(_command())

    claims = fixture.issuer.issued_claims[0]
    assert claims.role is Role.OWNER
    assert claims.tenant_id == RestaurantId("rest-1")


def test_valor_do_refresh_token_nunca_chega_ao_repositorio_de_sessao() -> None:
    """CA15 — um dump do banco não pode devolver refresh token utilizável."""
    fixture = _Fixture()

    result = fixture.use_case.execute(_command())

    for session in fixture.sessions.sessions.values():
        assert result.refresh_token not in vars(session).values()
        assert session.refresh_token_fingerprint != result.refresh_token


def test_senha_errada_e_rejeitada_sem_criar_sessao() -> None:
    """CA7."""
    fixture = _Fixture()

    with pytest.raises(InvalidCredentialsError):
        fixture.use_case.execute(_command(senha="errada"))

    assert fixture.sessions.sessions == {}


def test_email_inexistente_e_rejeitado_sem_criar_sessao() -> None:
    """CA7."""
    fixture = _Fixture(com_usuario=False)

    with pytest.raises(InvalidCredentialsError):
        fixture.use_case.execute(_command())

    assert fixture.sessions.sessions == {}


def test_email_inexistente_e_senha_errada_sao_indistinguiveis() -> None:
    """CA7 — mesmo tipo E mesma mensagem, para não vazar quais contas existem."""
    inexistente = _Fixture(com_usuario=False)
    senha_errada = _Fixture()

    with pytest.raises(InvalidCredentialsError) as erro_inexistente:
        inexistente.use_case.execute(_command())
    with pytest.raises(InvalidCredentialsError) as erro_senha:
        senha_errada.use_case.execute(_command(senha="errada"))

    assert type(erro_inexistente.value) is type(erro_senha.value)
    assert str(erro_inexistente.value) == str(erro_senha.value)


def test_email_inexistente_ainda_paga_o_custo_da_verificacao() -> None:
    """CA7 — a defesa contra enumeração por tempo de resposta.

    Sem esta chamada, o caminho "e-mail não existe" retorna em microssegundos
    enquanto "senha errada" paga o argon2 inteiro. A diferença é medível de fora
    e revela quais e-mails estão cadastrados — mesmo com a mensagem idêntica.
    """
    fixture = _Fixture(com_usuario=False)

    with pytest.raises(InvalidCredentialsError):
        fixture.use_case.execute(_command())

    assert fixture.hasher.verify_calls == 1


def test_verificacao_do_email_inexistente_usa_o_hash_dummy_do_port() -> None:
    """O hash constante vem do adapter, não da camada de aplicação.

    A aplicação não tem como fabricar um hash argon2 legítimo nem deve conhecer
    os parâmetros de custo dele — por isso `dummy_hash()` faz parte do contrato.
    """
    fixture = _Fixture(com_usuario=False)
    dummy = fixture.hasher.dummy_hash()

    with pytest.raises(InvalidCredentialsError):
        fixture.use_case.execute(_command())

    assert fixture.hasher.verify(_SENHA, dummy) is False


def test_hash_guardado_e_o_usado_na_verificacao() -> None:
    """Fecha o ciclo com `create_user`: o que foi gravado autentica de fato."""
    fixture = _Fixture()
    guardado = fixture.users.password_hashes[_USER_ID]

    assert guardado == PasswordHash("hashed::s3nha")
    assert fixture.use_case.execute(_command()).user_id == _USER_ID


def test_logins_sucessivos_abrem_sessoes_distintas() -> None:
    """Cada login é uma sessão própria — é o que permite revogar uma sem as outras."""
    fixture = _Fixture()

    primeiro = fixture.use_case.execute(_command())
    segundo = fixture.use_case.execute(_command())

    assert primeiro.refresh_token != segundo.refresh_token
    assert len(fixture.sessions.sessions) == len({primeiro.refresh_token, segundo.refresh_token})
