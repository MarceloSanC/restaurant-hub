"""Testes do use case `request_password_reset` — CA12, CA12b, CA13.

O caminho feliz é o menos interessante daqui. O que estes testes protegem é a
**ausência de diferença** entre e-mail cadastrado e não cadastrado, e o fato de
que um pedido de redefinição não pode ser usado para matar o convite de ninguém.
"""

from datetime import UTC, datetime, timedelta

from restaurant_hub.features.identity.application.dtos.commands import (
    RequestPasswordResetCommand,
)
from restaurant_hub.features.identity.application.dtos.identifiers import SetupTokenId
from restaurant_hub.features.identity.application.dtos.setup_tokens import (
    PasswordSetupToken,
    SetupTokenPurpose,
)
from restaurant_hub.features.identity.application.use_cases.request_password_reset import (
    RequestPasswordResetUseCase,
)
from restaurant_hub.features.identity.domain.entities.user import User
from restaurant_hub.features.identity.domain.value_objects.email import Email
from restaurant_hub.features.identity.domain.value_objects.identifiers import (
    RestaurantId,
    UserId,
)
from restaurant_hub.features.identity.domain.value_objects.role import Role
from tests.fakes.features.identity.fake_password_hasher import FakePasswordHasher
from tests.fakes.features.identity.fake_setup_token_issuer import FakeSetupTokenIssuer
from tests.fakes.features.identity.in_memory_password_setup_token_repository import (
    InMemoryPasswordSetupTokenRepository,
)
from tests.fakes.features.identity.in_memory_user_repository import InMemoryUserRepository
from tests.fakes.shared.fake_clock import FakeClock
from tests.fakes.shared.fake_id_generator import FakeIdGenerator
from tests.fakes.shared.recording_email_sender import (
    EmailSenderFailure,
    RecordingEmailSender,
)

_AGORA = datetime(2026, 7, 20, 12, 0, tzinfo=UTC)
_TTL = timedelta(minutes=30)
_BASE_URL = "https://app.exemplo.com"
_CADASTRADO = "cadastrado@x.com"
_DESCONHECIDO = "nunca-vi@x.com"


class Cenario:
    """Um usuário cadastrado; o resto dos e-mails não existe."""

    def __init__(self, *, sender: RecordingEmailSender | None = None) -> None:
        self.users = InMemoryUserRepository()
        self.tokens = InMemoryPasswordSetupTokenRepository()
        self.issuer = FakeSetupTokenIssuer()
        self.sender = sender if sender is not None else RecordingEmailSender()
        self.hasher = FakePasswordHasher()

        self.users.add(
            User(
                id=UserId("user-1"),
                email=Email(_CADASTRADO),
                role=Role.MANAGER,
                tenant_id=RestaurantId("rest-a"),
            ),
            self.hasher.hash("senha-atual"),
        )

        self.use_case = RequestPasswordResetUseCase(
            users=self.users,
            tokens=self.tokens,
            token_issuer=self.issuer,
            email_sender=self.sender,
            id_generator=FakeIdGenerator(),
            clock=FakeClock(_AGORA),
            reset_ttl=_TTL,
            base_url=_BASE_URL,
        )


def _comando(email: str) -> RequestPasswordResetCommand:
    return RequestPasswordResetCommand(email=Email(email))


class TestEmailCadastrado:
    def test_emite_exatamente_um_token_de_redefinicao(self) -> None:
        cenario = Cenario()

        cenario.use_case.execute(_comando(_CADASTRADO))

        assert len(cenario.tokens.tokens) == 1
        token = next(iter(cenario.tokens.tokens.values()))
        assert token.user_id == UserId("user-1")
        assert token.purpose is SetupTokenPurpose.PASSWORD_RESET

    def test_envia_exatamente_uma_mensagem_com_o_link(self) -> None:
        cenario = Cenario()

        cenario.use_case.execute(_comando(_CADASTRADO))

        assert len(cenario.sender.sent) == 1
        assert cenario.sender.sent[0].to == _CADASTRADO
        assert "token=" in cenario.sender.sent[0].body_text

    def test_expiracao_usa_o_ttl_curto_injetado(self) -> None:
        """Redefinição é emergência de minutos; convite tolera dias."""
        cenario = Cenario()

        cenario.use_case.execute(_comando(_CADASTRADO))

        token = next(iter(cenario.tokens.tokens.values()))
        assert token.expires_at == _AGORA + _TTL

    def test_persiste_apenas_o_fingerprint(self) -> None:
        cenario = Cenario()

        cenario.use_case.execute(_comando(_CADASTRADO))

        token = next(iter(cenario.tokens.tokens.values()))
        assert token.token_fingerprint not in cenario.sender.sent[0].body_text


class TestEmailDesconhecido:
    """CA12 (nível de aplicação) — o caminho "não existe" é silêncio completo."""

    def test_nao_levanta(self) -> None:
        cenario = Cenario()

        assert cenario.use_case.execute(_comando(_DESCONHECIDO)) is None

    def test_nao_emite_token(self) -> None:
        cenario = Cenario()

        cenario.use_case.execute(_comando(_DESCONHECIDO))

        assert cenario.tokens.tokens == {}

    def test_nao_envia_mensagem(self) -> None:
        """Enviar para um endereço não cadastrado seria pior que vazar o status."""
        cenario = Cenario()

        cenario.use_case.execute(_comando(_DESCONHECIDO))

        assert cenario.sender.sent == ()

    def test_retorno_e_identico_ao_do_email_cadastrado(self) -> None:
        """A única saída observável do use case é `None` nos dois casos."""
        cenario = Cenario()

        conhecido = cenario.use_case.execute(_comando(_CADASTRADO))
        desconhecido = cenario.use_case.execute(_comando(_DESCONHECIDO))

        assert conhecido == desconhecido


class TestFalhaDoSenderEAbsorvida:
    """CA12b — a regra 8: sem ela, 500 significaria "cadastrado"."""

    def test_nao_levanta_quando_o_envio_falha(self) -> None:
        cenario = Cenario(sender=RecordingEmailSender(fail_with=EmailSenderFailure("fora")))

        assert cenario.use_case.execute(_comando(_CADASTRADO)) is None

    def test_retorno_continua_identico_ao_do_email_desconhecido(self) -> None:
        """O cenário do atacante: sondar durante uma queda do provedor.

        Se a exceção subisse, o e-mail cadastrado daria 500 e o desconhecido 202
        — enumeração completa, sem precisar medir tempo nenhum.
        """
        cenario = Cenario(sender=RecordingEmailSender(fail_with=EmailSenderFailure("fora")))

        com_falha = cenario.use_case.execute(_comando(_CADASTRADO))
        desconhecido = cenario.use_case.execute(_comando(_DESCONHECIDO))

        assert com_falha == desconhecido

    def test_o_token_fica_emitido_mesmo_com_o_envio_falhando(self) -> None:
        """O usuário pode pedir de novo; a emissão anterior é invalidada."""
        cenario = Cenario(sender=RecordingEmailSender(fail_with=EmailSenderFailure("fora")))

        cenario.use_case.execute(_comando(_CADASTRADO))

        assert len(cenario.tokens.tokens) == 1


class TestInvalidacaoEscopadaPorProposito:
    """CA13 — dois pedidos deixam um token vivo; o convite pendente sobrevive."""

    def test_segundo_pedido_invalida_o_primeiro(self) -> None:
        cenario = Cenario()
        cenario.use_case.execute(_comando(_CADASTRADO))
        primeiro = next(iter(cenario.tokens.tokens.values())).id

        cenario.use_case.execute(_comando(_CADASTRADO))

        assert cenario.tokens.tokens[primeiro].consumed_at == _AGORA
        vivos = [t for t in cenario.tokens.tokens.values() if t.consumed_at is None]
        assert len(vivos) == 1

    def test_nao_mata_convite_pendente_do_mesmo_usuario(self) -> None:
        """O escopo por propósito é o que impede a negação de serviço.

        Sem ele, esta rota **pública** mataria o link de convite de qualquer
        vítima, em laço, no instante em que ela o clicasse.
        """
        cenario = Cenario()
        cenario.tokens.add(
            PasswordSetupToken(
                id=SetupTokenId("convite-pendente"),
                user_id=UserId("user-1"),
                purpose=SetupTokenPurpose.INVITATION,
                token_fingerprint="fp-convite",
                issued_at=_AGORA,
                expires_at=_AGORA + timedelta(hours=72),
            )
        )

        cenario.use_case.execute(_comando(_CADASTRADO))

        assert cenario.tokens.tokens[SetupTokenId("convite-pendente")].consumed_at is None

    def test_nao_toca_em_token_de_outro_usuario(self) -> None:
        cenario = Cenario()
        outro = User(
            id=UserId("user-2"),
            email=Email("outro@x.com"),
            role=Role.MANAGER,
            tenant_id=RestaurantId("rest-a"),
        )
        cenario.users.add(outro, cenario.hasher.hash("x"))
        cenario.use_case.execute(_comando("outro@x.com"))
        token_do_outro = next(iter(cenario.tokens.tokens.values())).id

        cenario.use_case.execute(_comando(_CADASTRADO))

        assert cenario.tokens.tokens[token_do_outro].consumed_at is None
