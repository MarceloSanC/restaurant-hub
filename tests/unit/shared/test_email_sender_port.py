"""Testes do port compartilhado `EmailSender` e do seu fake (Stage 2.5, CA1)."""

import dataclasses

import pytest

from restaurant_hub.shared.application.ports.out.email_sender import EmailMessage
from tests.fakes.shared.recording_email_sender import (
    EmailSenderFailure,
    RecordingEmailSender,
)


def _mensagem(destinatario: str = "alguem@exemplo.com") -> EmailMessage:
    return EmailMessage(to=destinatario, subject="Assunto", body_text="Corpo")


class TestFormaDoPort:
    """A genericidade do port é asserida, não prometida."""

    def test_email_message_tem_exatamente_tres_campos(self) -> None:
        """CA1 — o port não pode ganhar vocabulário do primeiro consumidor.

        O import-linter garante a **direção** do import (`shared` não vê
        `features`), mas não impediria um campo `invitation_url` ou
        `setup_token`. É esta asserção que impede — e ela falha no momento em que
        alguém acrescentar um campo, que é exatamente quando a revisão humana
        deixaria passar por parecer inofensivo.
        """
        campos = {campo.name for campo in dataclasses.fields(EmailMessage)}

        assert campos == {"to", "subject", "body_text"}

    def test_email_message_e_imutavel(self) -> None:
        mensagem = _mensagem()

        with pytest.raises(dataclasses.FrozenInstanceError):
            mensagem.to = "outro@exemplo.com"  # type: ignore[misc]


class TestRecordingEmailSender:
    def test_registra_as_mensagens_na_ordem(self) -> None:
        sender = RecordingEmailSender()

        sender.send(_mensagem("primeiro@exemplo.com"))
        sender.send(_mensagem("segundo@exemplo.com"))

        assert [mensagem.to for mensagem in sender.sent] == [
            "primeiro@exemplo.com",
            "segundo@exemplo.com",
        ]

    def test_comeca_vazio(self) -> None:
        assert RecordingEmailSender().sent == ()

    def test_levanta_quando_configurado_para_falhar(self) -> None:
        sender = RecordingEmailSender(fail_with=EmailSenderFailure("provedor fora do ar"))

        with pytest.raises(EmailSenderFailure):
            sender.send(_mensagem())

    def test_falha_nao_registra_a_mensagem(self) -> None:
        """Um envio que estourou não entregou nada — o fake não pode fingir que sim."""
        sender = RecordingEmailSender(fail_with=EmailSenderFailure("provedor fora do ar"))

        with pytest.raises(EmailSenderFailure):
            sender.send(_mensagem())

        assert sender.sent == ()
