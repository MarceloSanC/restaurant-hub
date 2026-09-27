"""Testes do use case `send_invitation` e do helper `_invitation` — Stage 3.5, CA16/CA17.

Dois contratos vivem aqui:

1. **O use case** envia exatamente uma mensagem, para o e-mail dado, com o link no
   corpo e o assunto da 2.5; a falha do sender propaga.
2. **O helper** é byte-idêntico ao que os dois módulos da 2.5 faziam inline
   antes de passar a chamá-lo (CA16). Os testes de `invite_user` e do reset só
   asserem `"token=" in body` — o que os protege de uma mudança silenciosa de
   formato é o **literal transcrito** abaixo, não derivado do helper.
"""

import pytest

from restaurant_hub.features.identity.application.dtos.commands import SendInvitationCommand
from restaurant_hub.features.identity.application.use_cases._invitation import (
    invitation_message,
    setup_link,
)
from restaurant_hub.features.identity.application.use_cases.send_invitation import (
    SendInvitationUseCase,
)
from restaurant_hub.features.identity.domain.value_objects.email import Email
from tests.fakes.shared.recording_email_sender import (
    EmailSenderFailure,
    RecordingEmailSender,
)

pytestmark = pytest.mark.unit

_LINK = "https://app.exemplo.com/definir-senha?token=setup-1"
# O assunto da Stage 2.5, transcrito — não importado do módulo que o define.
_ASSUNTO_DA_2_5 = "Convite para o Restaurant Hub"


def _comando(email: str = "convidado@x.com", link: str = _LINK) -> SendInvitationCommand:
    return SendInvitationCommand(email=Email(email), setup_link=link)


class TestUseCase:
    def test_envia_exatamente_uma_mensagem_para_o_email_dado(self) -> None:
        sender = RecordingEmailSender()

        SendInvitationUseCase(sender).execute(_comando("alguem@x.com"))

        assert len(sender.sent) == 1
        assert sender.sent[0].to == "alguem@x.com"

    def test_corpo_contem_o_link_e_o_assunto_e_o_da_2_5(self) -> None:
        """CA17 — a pessoa recebe o mesmo convite que receberia pela rota da 2.5."""
        sender = RecordingEmailSender()

        SendInvitationUseCase(sender).execute(_comando())

        mensagem = sender.sent[0]
        assert _LINK in mensagem.body_text
        assert mensagem.subject == _ASSUNTO_DA_2_5

    def test_falha_do_sender_propaga(self) -> None:
        """Regra 13 da 2.5 — reportar sucesso sem o e-mail ter saído é pior que falhar."""
        sender = RecordingEmailSender(fail_with=EmailSenderFailure("fora"))

        with pytest.raises(EmailSenderFailure):
            SendInvitationUseCase(sender).execute(_comando())

    def test_nao_envia_nada_alem_do_pedido(self) -> None:
        sender = RecordingEmailSender()

        SendInvitationUseCase(sender).execute(_comando())
        SendInvitationUseCase(sender).execute(_comando("outro@x.com"))

        assert [m.to for m in sender.sent] == ["convidado@x.com", "outro@x.com"]

    def test_o_repr_do_command_nao_carrega_o_link(self) -> None:
        """`repr=False` — credencial bearer viva nos locals do frame que falha."""
        assert "setup-1" not in repr(_comando())


class TestHelperByteIdentico:
    """CA16 — o helper reproduz o que `invite_user.py:209` e `request_password_reset.py:147`
    faziam inline na 2.5, byte a byte."""

    @pytest.mark.parametrize(
        ("base", "valor"),
        [
            ("https://app.exemplo.com", "setup-1"),
            ("https://app.exemplo.com/", "setup-1"),
            ("http://localhost:8000", "abc.def-ghi_jkl"),
            ("https://hub.cantina.com.br///", "x"),
        ],
    )
    def test_setup_link_e_o_literal_da_2_5(self, base: str, valor: str) -> None:
        # Transcrição literal da linha que os dois módulos tinham — se o helper
        # divergir dela, os e-mails de convite E de reset mudam juntos.
        esperado = f"{base.rstrip('/')}/definir-senha?token={valor}"
        assert setup_link(base, valor) == esperado

    def test_invitation_message_e_o_literal_da_2_5(self) -> None:
        mensagem = invitation_message("convidado@x.com", _LINK)

        assert mensagem.to == "convidado@x.com"
        assert mensagem.subject == _ASSUNTO_DA_2_5
        assert mensagem.body_text == (
            "Você foi convidado para o Restaurant Hub.\n\n"
            f"Defina a sua senha por este link:\n{_LINK}\n\n"
            "Se você não esperava este convite, ignore esta mensagem."
        )
