"""Testes do use case `send_invitation` e do helper `_invitation` — Stage 3.5, CA16/CA17.

Três contratos vivem aqui:

1. **O use case** envia exatamente uma mensagem, para o e-mail dado, com o link no
   corpo e o assunto da 2.5; a falha do sender propaga.
2. **O helper** é byte-idêntico ao que os dois módulos da 2.5 faziam inline
   antes de passar a chamá-lo (CA16). Os testes de `invite_user` e do reset só
   asserem `"token=" in body` — o que os protege de uma mudança silenciosa de
   formato é o **literal transcrito** abaixo, não derivado do helper.
3. **`deliver_invitation`** (issue #170): a falha do sender sobe trocada por
   `InvitationNotSentError`, sem cadeia de volta à original, e o log leva só o tipo
   dela e o `user_id` — nunca a mensagem, que pode ecoar destinatário e link.
"""

import logging

import pytest

from restaurant_hub.features.identity.application.dtos.commands import SendInvitationCommand
from restaurant_hub.features.identity.application.errors import InvitationNotSentError
from restaurant_hub.features.identity.application.use_cases._invitation import (
    deliver_invitation,
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


# ---------------------------------------------------------------------------
# deliver_invitation — issue #170
# ---------------------------------------------------------------------------

_LOGGER = "restaurant_hub.features.identity.application.use_cases._invitation"
_DESTINATARIO = "vitima@x.com"


class FalhaQueEcoa(Exception):
    """Falha de provedor que repete na mensagem tudo o que recebeu — o pior caso."""


class _SenderQueEcoaNaFalha:
    """Falha com o destinatário e o corpo inteiro (link incluído) na mensagem."""

    def send(self, message: object) -> None:
        raise FalhaQueEcoa(f"recusado: {message!r}")


class TestDeliverInvitation:
    def test_envia_a_mensagem_e_nao_registra_nada(self, caplog: pytest.LogCaptureFixture) -> None:
        sender = RecordingEmailSender()
        mensagem = invitation_message(_DESTINATARIO, _LINK)
        caplog.set_level(logging.DEBUG)

        deliver_invitation(sender, mensagem, "user-1")

        assert sender.sent == (mensagem,)
        assert [r for r in caplog.records if r.name == _LOGGER] == []

    def test_falha_sobe_trocada_com_o_user_id(self) -> None:
        with pytest.raises(InvitationNotSentError) as excinfo:
            deliver_invitation(
                _SenderQueEcoaNaFalha(), invitation_message(_DESTINATARIO, _LINK), "user-9"
            )

        assert excinfo.value.user_id == "user-9"

    def test_a_falha_trocada_nao_carrega_cadeia_ate_a_original(self) -> None:
        """Levantada fora do `except`: nem `__cause__` nem `__context__`.

        Com `raise ... from None` dentro do `except`, `__context__` ainda guardaria a
        original — só a impressão dela seria suprimida —, e qualquer código que
        percorresse a cadeia chegaria à mensagem com o link.
        """
        with pytest.raises(InvitationNotSentError) as excinfo:
            deliver_invitation(
                _SenderQueEcoaNaFalha(), invitation_message(_DESTINATARIO, _LINK), "user-9"
            )

        assert excinfo.value.__cause__ is None
        assert excinfo.value.__context__ is None
        assert _LINK not in str(excinfo.value)
        assert _DESTINATARIO not in str(excinfo.value)

    def test_registra_so_o_tipo_e_o_user_id(self, caplog: pytest.LogCaptureFixture) -> None:
        """O registro existe (não é silêncio) e não carrega mensagem nem traceback."""
        caplog.set_level(logging.DEBUG)

        with pytest.raises(InvitationNotSentError):
            deliver_invitation(
                _SenderQueEcoaNaFalha(), invitation_message(_DESTINATARIO, _LINK), "user-9"
            )

        [registro] = [r for r in caplog.records if r.name == _LOGGER]
        assert registro.levelno == logging.ERROR
        assert registro.exc_info is None
        assert registro.args == ("user-9", f"{__name__}.FalhaQueEcoa")
        assert "user_id=user-9" in registro.getMessage()
        for vazamento in (_DESTINATARIO, _LINK, "setup-1", "recusado"):
            assert vazamento not in caplog.text
