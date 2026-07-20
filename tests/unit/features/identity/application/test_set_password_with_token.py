"""Testes do use case `set_password_with_token` — CA8, CA8b, CA9, CA10, CA11b.

Este é o use case que uma requisição **não autenticada** alcança para trocar uma
credencial. Os testes aqui não são sobre o caminho feliz: são sobre replay, sobre
o alvo vir do token e não do pedido, e sobre a ordem em que os efeitos acontecem.
"""

from datetime import UTC, datetime, timedelta

import pytest

from restaurant_hub.features.identity.application.dtos.commands import (
    SetPasswordWithTokenCommand,
)
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
from restaurant_hub.features.identity.application.errors import InvalidSetupTokenError
from restaurant_hub.features.identity.application.use_cases.set_password_with_token import (
    SetPasswordWithTokenUseCase,
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
from tests.fakes.features.identity.in_memory_session_repository import (
    InMemorySessionRepository,
)
from tests.fakes.features.identity.in_memory_user_repository import InMemoryUserRepository
from tests.fakes.shared.fake_clock import FakeClock

_AGORA = datetime(2026, 7, 20, 12, 0, tzinfo=UTC)
_SENHA_NOVA = "senha-nova-do-convidado"
_VALOR = "setup-1"


class RepositorioQueFalhaAoGravar(InMemoryUserRepository):
    """Falha só em `set_password_hash` — para observar a ordem dos efeitos."""

    def set_password_hash(self, user_id: UserId, password_hash: PasswordHash) -> None:
        raise RuntimeError("banco indisponível")


class SessoesQueFalhamAoRevogar(InMemorySessionRepository):
    """Falha só em `revoke_all_for_user` — para observar o passo intermediário."""

    def revoke_all_for_user(self, user_id: UserId, revoked_at: datetime) -> None:
        raise RuntimeError("banco indisponível")


class Cenario:
    """Um usuário com um token de convite vivo e uma sessão aberta."""

    def __init__(
        self,
        *,
        users: InMemoryUserRepository | None = None,
        sessions: InMemorySessionRepository | None = None,
        expires_at: datetime | None = None,
        consumed_at: datetime | None = None,
        com_usuario: bool = True,
    ) -> None:
        self.users = users if users is not None else InMemoryUserRepository()
        self.sessions = sessions if sessions is not None else InMemorySessionRepository()
        self.tokens = InMemoryPasswordSetupTokenRepository()
        self.issuer = FakeSetupTokenIssuer()
        self.hasher = FakePasswordHasher()
        self.clock = FakeClock(_AGORA)

        if com_usuario:
            self.users.add(
                User(
                    id=UserId("user-1"),
                    email=Email("convidado@x.com"),
                    role=Role.MANAGER,
                    tenant_id=RestaurantId("rest-a"),
                ),
                self.hasher.unusable_hash(),
            )
            self.sessions.add(
                Session(
                    id=SessionId("sess-1"),
                    user_id=UserId("user-1"),
                    refresh_token_fingerprint="fp-sessao",
                    issued_at=_AGORA,
                    expires_at=_AGORA + timedelta(days=14),
                )
            )

        self.tokens.add(
            PasswordSetupToken(
                id=SetupTokenId("tok-1"),
                user_id=UserId("user-1"),
                purpose=SetupTokenPurpose.INVITATION,
                token_fingerprint=self.issuer.fingerprint(_VALOR),
                issued_at=_AGORA,
                expires_at=expires_at if expires_at is not None else _AGORA + timedelta(hours=72),
                consumed_at=consumed_at,
            )
        )

        self.use_case = SetPasswordWithTokenUseCase(
            users=self.users,
            sessions=self.sessions,
            tokens=self.tokens,
            token_issuer=self.issuer,
            hasher=self.hasher,
            clock=self.clock,
        )


def _comando(token: str = _VALOR, senha: str = _SENHA_NOVA) -> SetPasswordWithTokenCommand:
    return SetPasswordWithTokenCommand(token=token, plain_password=senha)


class TestCaminhoFeliz:
    def test_grava_o_hash_da_senha_nova(self) -> None:
        cenario = Cenario()

        cenario.use_case.execute(_comando())

        credenciais = cenario.users.find_credentials_by_email(Email("convidado@x.com"))
        assert credenciais is not None
        assert cenario.hasher.verify(_SENHA_NOVA, credenciais.password_hash) is True

    def test_grava_no_usuario_DO_TOKEN(self) -> None:
        """CA11b — o alvo vem do registro que o servidor gravou, não do pedido.

        O command não tem `user_id`, então não há como pedir outra conta; este
        teste prova que o hash foi parar exatamente no dono do token.
        """
        cenario = Cenario()
        outro = User(
            id=UserId("user-2"),
            email=Email("outro@x.com"),
            role=Role.MANAGER,
            tenant_id=RestaurantId("rest-a"),
        )
        cenario.users.add(outro, PasswordHash("hashed::intocada"))

        cenario.use_case.execute(_comando())

        credenciais_do_outro = cenario.users.find_credentials_by_email(Email("outro@x.com"))
        assert credenciais_do_outro is not None
        assert credenciais_do_outro.password_hash == "hashed::intocada"

    def test_consome_o_token(self) -> None:
        cenario = Cenario()

        cenario.use_case.execute(_comando())

        assert cenario.tokens.tokens[SetupTokenId("tok-1")].consumed_at == _AGORA

    def test_revoga_todas_as_sessoes_do_usuario(self) -> None:
        """CA8 / ADR 2.5.0003 — uma redefinição que não expulsa não recupera nada."""
        cenario = Cenario()

        cenario.use_case.execute(_comando())

        assert cenario.sessions.sessions[SessionId("sess-1")].revoked_at == _AGORA

    def test_invalida_tambem_convite_antigo_de_outro_proposito(self) -> None:
        """CA8 — a invalidação da redenção é **sem** escopo de propósito.

        Um convite de TTL longo que sobrevivesse permitiria redefinir a senha
        semanas depois, com um link antigo.
        """
        cenario = Cenario()
        cenario.tokens.add(
            PasswordSetupToken(
                id=SetupTokenId("tok-2"),
                user_id=UserId("user-1"),
                purpose=SetupTokenPurpose.PASSWORD_RESET,
                token_fingerprint="fp-outro",
                issued_at=_AGORA,
                expires_at=_AGORA + timedelta(days=30),
            )
        )

        cenario.use_case.execute(_comando())

        assert cenario.tokens.tokens[SetupTokenId("tok-2")].consumed_at == _AGORA

    def test_nao_devolve_nada(self) -> None:
        """Regra 14 — devolver tokens faria do link de e-mail uma sessão."""
        cenario = Cenario()

        assert cenario.use_case.execute(_comando()) is None


class TestReplay:
    def test_segunda_redencao_do_mesmo_token_falha(self) -> None:
        """CA9 — o replay morre no `consume`, não numa checagem prévia."""
        cenario = Cenario()
        cenario.use_case.execute(_comando())

        with pytest.raises(InvalidSetupTokenError):
            cenario.use_case.execute(_comando(senha="senha-do-atacante"))

    def test_segunda_redencao_nao_regrava_a_senha(self) -> None:
        """CA9 — a segunda tentativa não pode escrever nada.

        Sem esta asserção, uma implementação que consumisse **depois** de gravar
        passaria no teste acima e ainda assim deixaria o atacante definir a senha.
        """
        cenario = Cenario()
        cenario.use_case.execute(_comando())

        with pytest.raises(InvalidSetupTokenError):
            cenario.use_case.execute(_comando(senha="senha-do-atacante"))

        credenciais = cenario.users.find_credentials_by_email(Email("convidado@x.com"))
        assert credenciais is not None
        assert cenario.hasher.verify(_SENHA_NOVA, credenciais.password_hash) is True
        assert cenario.hasher.verify("senha-do-atacante", credenciais.password_hash) is False

    def test_token_ja_consumido_falha(self) -> None:
        cenario = Cenario(consumed_at=_AGORA - timedelta(minutes=1))

        with pytest.raises(InvalidSetupTokenError):
            cenario.use_case.execute(_comando())


class TestFalhasIndistinguiveis:
    """CA10 — as quatro causas produzem a **mesma** exceção e a mesma mensagem."""

    def test_token_desconhecido(self) -> None:
        cenario = Cenario()

        with pytest.raises(InvalidSetupTokenError):
            cenario.use_case.execute(_comando(token="nunca-emitido"))

    def test_token_expirado(self) -> None:
        cenario = Cenario(expires_at=_AGORA - timedelta(seconds=1))

        with pytest.raises(InvalidSetupTokenError):
            cenario.use_case.execute(_comando())

    def test_token_expirando_exatamente_agora(self) -> None:
        """A fronteira é half-open: em `now == expires_at` já expirou."""
        cenario = Cenario(expires_at=_AGORA)

        with pytest.raises(InvalidSetupTokenError):
            cenario.use_case.execute(_comando())

    def test_token_de_usuario_inexistente(self) -> None:
        """Regra 16 — `UserNotFoundError` vira `InvalidSetupTokenError`.

        Sem a conversão, o mapa da 2.4 responderia **404 com corpo falante** numa
        rota pública, confirmando ao atacante que a string apresentada era um
        token de verdade cujo dono foi removido.
        """
        cenario = Cenario(com_usuario=False)

        with pytest.raises(InvalidSetupTokenError):
            cenario.use_case.execute(_comando())

    def test_todas_as_causas_tem_a_mesma_mensagem(self) -> None:
        """Cada causa precisa alcançar o seu **próprio** `raise`.

        A primeira versão deste teste passava `token="nunca-emitido"` sempre que
        o usuário existia — isto é, em três dos quatro cenários —, de modo que
        três deles caíam no mesmo `raise` de "fingerprint não encontrado" e os
        argumentos `expires_at`/`consumed_at` eram construídos e ignorados. O
        `raise` do replay não era comparado por teste nenhum: bastava alguém
        introduzir uma subclasse com mensagem própria ali para abrir um oráculo
        de "token real versus chute" com a suíte inteira verde.
        """
        mensagens = set()

        # Cada tupla é (cenário, token a apresentar), escolhida para atingir um
        # `raise` distinto do use case.
        casos = [
            (Cenario(), "nunca-emitido"),  # fingerprint desconhecido
            (Cenario(expires_at=_AGORA - timedelta(seconds=1)), _VALOR),  # expirado
            (Cenario(consumed_at=_AGORA), _VALOR),  # já consumido
            (Cenario(com_usuario=False), _VALOR),  # usuário apagado
        ]
        for cenario, token in casos:
            with pytest.raises(InvalidSetupTokenError) as capturado:
                cenario.use_case.execute(_comando(token=token))
            mensagens.add(str(capturado.value))

        # E o replay, que só é alcançável redimindo duas vezes de verdade — é o
        # `raise` do `consume` que perde a corrida.
        cenario_replay = Cenario()
        cenario_replay.use_case.execute(_comando())
        with pytest.raises(InvalidSetupTokenError) as capturado:
            cenario_replay.use_case.execute(_comando())
        mensagens.add(str(capturado.value))

        assert len(mensagens) == 1

    def test_falha_ao_revogar_sessoes_ja_consumiu_o_token(self) -> None:
        """Falha no passo intermediário também deixa a conta mais fechada."""
        cenario = Cenario(sessions=SessoesQueFalhamAoRevogar())

        with pytest.raises(RuntimeError):
            cenario.use_case.execute(_comando())

        assert cenario.tokens.tokens[SetupTokenId("tok-1")].consumed_at == _AGORA


class TestOrdemFailClosed:
    """CA8b — toda falha parcial deixa a conta mais fechada, nunca mais aberta."""

    def test_falha_ao_gravar_a_senha_ja_consumiu_o_token(self) -> None:
        cenario = Cenario(users=RepositorioQueFalhaAoGravar())

        with pytest.raises(RuntimeError):
            cenario.use_case.execute(_comando())

        assert cenario.tokens.tokens[SetupTokenId("tok-1")].consumed_at == _AGORA

    def test_falha_ao_gravar_a_senha_ja_revogou_as_sessoes(self) -> None:
        """O ponto inteiro da ordem.

        Se a senha fosse gravada primeiro, uma falha em `revoke_all_for_user`
        deixaria a sessão do atacante viva **depois** de uma redefinição
        concluída — o buraco que o ADR 2.5.0003 fecha, reaberto por um erro
        transitório de banco.
        """
        cenario = Cenario(users=RepositorioQueFalhaAoGravar())

        with pytest.raises(RuntimeError):
            cenario.use_case.execute(_comando())

        assert cenario.sessions.sessions[SessionId("sess-1")].revoked_at == _AGORA

    def test_token_invalido_nao_revoga_sessao_nenhuma(self) -> None:
        """Quem apresenta lixo não derruba as sessões de ninguém.

        Sem esta garantia, a rota pública viraria um botão de logout remoto
        acionável por qualquer pessoa que adivinhasse um `user_id`.
        """
        cenario = Cenario()

        with pytest.raises(InvalidSetupTokenError):
            cenario.use_case.execute(_comando(token="nunca-emitido"))

        assert cenario.sessions.sessions[SessionId("sess-1")].revoked_at is None
