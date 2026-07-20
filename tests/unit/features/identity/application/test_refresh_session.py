"""Testes da rotação de refresh token com detecção de reuso.

O teste mais importante deste arquivo não é o caminho feliz — é
`test_precedencia_revogado_vence_expirado`. Ele fixa uma ordem de checagens que,
se invertida, não quebra nenhum outro teste, não aparece numa revisão de diff, e
transforma o cenário do token roubado num "expirou, tudo bem".
"""

from datetime import UTC, datetime, timedelta

import pytest

from restaurant_hub.features.identity.application.dtos.commands import (
    RefreshSessionCommand,
    RevokeSessionCommand,
)
from restaurant_hub.features.identity.application.dtos.identifiers import (
    PasswordHash,
    SessionId,
)
from restaurant_hub.features.identity.application.dtos.results import (
    AuthenticationResult,
)
from restaurant_hub.features.identity.application.dtos.session import Session
from restaurant_hub.features.identity.application.errors import (
    InvalidRefreshTokenError,
    RefreshTokenReuseError,
)
from restaurant_hub.features.identity.application.use_cases.refresh_session import (
    RefreshSessionUseCase,
)
from restaurant_hub.features.identity.application.use_cases.revoke_session import (
    RevokeSessionUseCase,
)
from restaurant_hub.features.identity.domain.entities.user import User
from restaurant_hub.features.identity.domain.value_objects.email import Email
from restaurant_hub.features.identity.domain.value_objects.identifiers import (
    RestaurantId,
    UserId,
)
from restaurant_hub.features.identity.domain.value_objects.role import Role
from tests.fakes.features.identity.fake_token_issuer import FakeTokenIssuer
from tests.fakes.features.identity.in_memory_session_repository import (
    InMemorySessionRepository,
)
from tests.fakes.features.identity.in_memory_user_repository import (
    InMemoryUserRepository,
)
from tests.fakes.shared.fake_clock import FakeClock
from tests.fakes.shared.fake_id_generator import FakeIdGenerator

pytestmark = pytest.mark.unit

_NOW = datetime(2026, 7, 19, 12, 0, tzinfo=UTC)
_ACCESS_TTL = timedelta(minutes=15)
_REFRESH_TTL = timedelta(days=14)
_USER_ID = UserId("user-1")


class _FalhaDeEscrita(Exception):
    """A falha transitória de banco do cenário "rotação não-atômica" (concept §6)."""


class _SessionRepositoryInstrumentado(InMemorySessionRepository):
    """Registra a ordem das escritas e permite armar uma falha no `add`.

    Existe para tornar observável um contrato que nenhuma outra asserção alcança:
    o use case chama `revoke` e `add`, e uma suíte que só olhe o estado final ao
    fim de uma rotação bem-sucedida passa idêntica nas duas ordens.
    """

    def __init__(self) -> None:
        super().__init__()
        self.chamadas: list[str] = []
        self.add_deve_falhar = False

    def add(self, session: Session) -> None:
        self.chamadas.append("add")
        if self.add_deve_falhar:
            raise _FalhaDeEscrita()
        super().add(session)

    def revoke(self, session_id: SessionId, revoked_at: datetime) -> None:
        self.chamadas.append("revoke")
        super().revoke(session_id, revoked_at)


class _Fixture:
    """Grafo montado com fakes — o mesmo que o composition root monta com reais."""

    def __init__(self, sessions: InMemorySessionRepository | None = None) -> None:
        self.users = InMemoryUserRepository()
        self.sessions = sessions if sessions is not None else InMemorySessionRepository()
        self.issuer = FakeTokenIssuer()
        self.clock = FakeClock(_NOW)
        self.use_case = RefreshSessionUseCase(
            users=self.users,
            sessions=self.sessions,
            token_issuer=self.issuer,
            id_generator=FakeIdGenerator(),
            clock=self.clock,
            access_token_ttl=_ACCESS_TTL,
            refresh_token_ttl=_REFRESH_TTL,
        )
        self.logout_use_case = RevokeSessionUseCase(
            sessions=self.sessions,
            token_issuer=self.issuer,
            clock=self.clock,
        )
        self.user = User(
            id=_USER_ID,
            email=Email("dono@restaurante.com"),
            role=Role.OWNER,
            tenant_id=RestaurantId("rest-1"),
        )

    def com_usuario(self) -> "_Fixture":
        self.users.add(self.user, PasswordHash("hashed::irrelevante"), ())
        return self

    def com_sessao(
        self,
        *,
        refresh_value: str = "refresh-original",
        revogada: bool = False,
        expirada: bool = False,
        session_id: str = "sess-1",
    ) -> Session:
        session = Session(
            id=SessionId(session_id),
            user_id=_USER_ID,
            refresh_token_fingerprint=self.issuer.fingerprint(refresh_value),
            issued_at=_NOW - timedelta(days=1),
            expires_at=_NOW - timedelta(hours=1) if expirada else _NOW + _REFRESH_TTL,
            revoked_at=_NOW - timedelta(minutes=5) if revogada else None,
        )
        self.sessions.add(session)
        return session


def _rotacionar(fixture: _Fixture, valor: str = "refresh-original") -> AuthenticationResult:
    return fixture.use_case.execute(RefreshSessionCommand(refresh_token=valor))


# ---------------------------------------------------------------------------
# Caminho feliz
# ---------------------------------------------------------------------------


def test_rotacao_revoga_a_antiga_e_grava_a_nova() -> None:
    """As duas metades importam: revogar sem gravar deslogaria o usuário."""
    fixture = _Fixture().com_usuario()
    antiga = fixture.com_sessao()

    resultado = _rotacionar(fixture)

    assert fixture.sessions.sessions[antiga.id].revoked_at == _NOW
    novas = [s for s in fixture.sessions.sessions.values() if s.id != antiga.id]
    assert len(novas) == 1
    # O que foi gravado é o FINGERPRINT, nunca o valor entregue ao cliente
    # (ADR 2.2.0001) — um dump do banco não devolve token utilizável.
    assert novas[0].refresh_token_fingerprint == fixture.issuer.fingerprint(resultado.refresh_token)
    assert novas[0].refresh_token_fingerprint != resultado.refresh_token


def test_rotacao_emite_par_novo_com_ttl_injetado() -> None:
    fixture = _Fixture().com_usuario()
    fixture.com_sessao()

    resultado = _rotacionar(fixture)

    assert resultado.access_token_expires_at == _NOW + _ACCESS_TTL
    assert resultado.refresh_token_expires_at == _NOW + _REFRESH_TTL
    assert resultado.refresh_token != "refresh-original"


def test_refresh_antigo_deixa_de_servir_apos_rotacao() -> None:
    """Reapresentar o token rotacionado é reuso — o ponto do desenho todo."""
    fixture = _Fixture().com_usuario()
    fixture.com_sessao()
    _rotacionar(fixture)

    with pytest.raises(RefreshTokenReuseError):
        _rotacionar(fixture)


def test_claims_do_token_novo_refletem_o_papel_atual_do_usuario() -> None:
    """O usuário é recarregado do repositório, não copiado da sessão.

    Sem isso, uma mudança de papel só valeria no próximo login — e um usuário
    rebaixado continuaria rotacionando tokens com o papel antigo indefinidamente.
    """
    fixture = _Fixture().com_usuario()
    fixture.com_sessao()

    _rotacionar(fixture)

    assert fixture.issuer.issued_claims[-1].role is Role.OWNER
    assert fixture.issuer.issued_claims[-1].subject == _USER_ID


# ---------------------------------------------------------------------------
# Detecção de reuso — e a precedência que a torna real
# ---------------------------------------------------------------------------


def test_refresh_revogado_revoga_todas_as_sessoes_do_usuario() -> None:
    fixture = _Fixture().com_usuario()
    fixture.com_sessao(revogada=True, session_id="sess-comprometida")
    outra = fixture.com_sessao(
        refresh_value="refresh-de-outro-dispositivo", session_id="sess-outra"
    )

    with pytest.raises(RefreshTokenReuseError):
        _rotacionar(fixture)

    # A sessão do outro dispositivo cai junto. É o comportamento desejado sob
    # suspeita de roubo — e o efeito colateral declarado no concept §5 regra 6.
    assert fixture.sessions.sessions[outra.id].revoked_at == _NOW


def test_precedencia_revogado_vence_expirado() -> None:
    """A ordem dos passos 3 e 4 é contrato, e este teste é o que a segura.

    Um refresh **revogado e também expirado** tem de disparar reuso, não
    expiração. Se as checagens fossem invertidas, este cenário — que é exatamente
    o do token roubado e guardado por um tempo — cairia em
    `InvalidRefreshTokenError`, as demais sessões do usuário continuariam vivas, e
    nenhum outro teste da suíte perceberia.
    """
    fixture = _Fixture().com_usuario()
    fixture.com_sessao(revogada=True, expirada=True)
    outra = fixture.com_sessao(refresh_value="outro", session_id="sess-outra")

    with pytest.raises(RefreshTokenReuseError):
        _rotacionar(fixture)

    assert fixture.sessions.sessions[outra.id].revoked_at == _NOW


# ---------------------------------------------------------------------------
# A ordem das ESCRITAS — o outro contrato invisível em diff
# ---------------------------------------------------------------------------


def test_revoke_da_antiga_precede_o_add_da_nova() -> None:
    """A ordem das escritas do passo 6 é contrato, e este teste é o que a segura.

    Irmão de `test_precedencia_revogado_vence_expirado`: lá a precedência é das
    **checagens** (passos 3 e 4), aqui é das **escritas**. As duas são invisíveis
    numa revisão de diff e nenhuma outra asserção da suíte as alcança — ao fim de
    uma rotação bem-sucedida o estado final é idêntico nas duas ordens.

    O cenário é literalmente o que o concept §6 declara aceito sob o nome
    "rotação não-atômica": `revoke` confirma, `add` falha. Com a ordem correta, o
    token antigo já está morto e o cliente cai em detecção de reuso no retry —
    erra para o lado seguro. Invertida, a falha deixaria a sessão antiga **viva**,
    abrindo a janela em que dois refresh valem ao mesmo tempo — o pior trade num
    sistema cuja principal defesa é detectar reuso.
    """
    sessions = _SessionRepositoryInstrumentado()
    fixture = _Fixture(sessions=sessions).com_usuario()
    antiga = fixture.com_sessao()
    sessions.chamadas.clear()  # descarta o `add` da própria montagem
    sessions.add_deve_falhar = True

    with pytest.raises(_FalhaDeEscrita):
        _rotacionar(fixture)

    assert sessions.chamadas == ["revoke", "add"]
    # E a consequência que dá sentido à ordem: a antiga não sobrevive à falha.
    assert fixture.sessions.sessions[antiga.id].revoked_at == _NOW


# ---------------------------------------------------------------------------
# Recusas — todas indistinguíveis para o cliente
# ---------------------------------------------------------------------------


def test_refresh_desconhecido_e_recusado() -> None:
    fixture = _Fixture().com_usuario()

    with pytest.raises(InvalidRefreshTokenError):
        _rotacionar(fixture, "nunca-emitido")


def test_refresh_expirado_e_recusado_sem_revogar_familia() -> None:
    """Expirado não é reuso: nada de derrubar as outras sessões do usuário."""
    fixture = _Fixture().com_usuario()
    fixture.com_sessao(expirada=True)
    outra = fixture.com_sessao(refresh_value="outro", session_id="sess-outra")

    with pytest.raises(InvalidRefreshTokenError):
        _rotacionar(fixture)

    assert fixture.sessions.sessions[outra.id].revoked_at is None


def test_sessao_de_usuario_inexistente_e_recusada() -> None:
    """Sessão órfã — o usuário sumiu por baixo dela. Não é reuso, não é 404."""
    fixture = _Fixture()  # sem `com_usuario()`
    fixture.com_sessao()

    with pytest.raises(InvalidRefreshTokenError):
        _rotacionar(fixture)


def test_nenhuma_sessao_nova_e_criada_em_caminho_de_falha() -> None:
    fixture = _Fixture().com_usuario()
    fixture.com_sessao(expirada=True)
    antes = len(fixture.sessions.sessions)

    with pytest.raises(InvalidRefreshTokenError):
        _rotacionar(fixture)

    assert len(fixture.sessions.sessions) == antes


def test_mensagens_de_recusa_nao_distinguem_a_causa() -> None:
    """Concept §5 regra 10: o cliente não deve saber qual foi o erro.

    As duas classes existem para o teste e para a auditoria; a mensagem, que é o
    que chega perto do cliente, é a mesma.
    """
    assert str(InvalidRefreshTokenError()) == str(RefreshTokenReuseError())


def test_refresh_apos_logout_e_tratado_como_reuso() -> None:
    """CA23 — o efeito colateral do logout, promovido a comportamento contratado.

    O passo 3 da rotação não sabe **por que** a sessão foi revogada: um único
    campo `revoked_at` serve a logout, rotação e incidente. A consequência é que
    reapresentar em `/auth/refresh` um token que saiu por logout conta como reuso
    e derruba as demais sessões do usuário — inclusive as de outros dispositivos.

    Um cliente correto não faz isso (recebeu 204 e descartou o token), mas um
    retry automático ou uma requisição em voo fazem. O comportamento erra para o
    lado seguro e está declarado no concept §5 regra 6; este teste é o que impede
    que ele mude sem que ninguém perceba — em particular, impede que uma Stage
    futura "conserte" o passo 3 para ignorar revogação por logout e, com isso,
    abra um caminho em que um token roubado sobrevive a um logout.
    """
    fixture = _Fixture().com_usuario()
    fixture.com_sessao(refresh_value="refresh-do-celular", session_id="sess-celular")
    desktop = fixture.com_sessao(refresh_value="refresh-do-desktop", session_id="sess-desktop")

    fixture.logout_use_case.execute(RevokeSessionCommand(refresh_token="refresh-do-celular"))

    with pytest.raises(RefreshTokenReuseError):
        _rotacionar(fixture, "refresh-do-celular")

    assert fixture.sessions.sessions[desktop.id].revoked_at == _NOW
