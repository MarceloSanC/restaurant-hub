"""Fake do port compartilhado `EmailSender`.

Guarda as mensagens em memória, para que o teste assere **o que** foi enviado —
e não apenas que algo foi. É o que permite verificar que o corpo do convite
carrega o token e que o pedido de redefinição de senha não envia nada quando o
e-mail não existe.

`fail_with` existe porque duas regras do concept dependem do **modo de falha**,
não do caminho feliz: o convite deixa a exceção propagar (regra 13) e o pedido de
redefinição a absorve (regra 8). Sem um sender que falha sob demanda, a segunda
regra — que é a que fecha um oráculo de enumeração — não teria como ser testada.
"""

from restaurant_hub.shared.application.ports.out.email_sender import (
    EmailMessage,
    EmailSender,
)


class EmailSenderFailure(RuntimeError):
    """Falha simulada de envio."""


class RecordingEmailSender:
    """Sender de teste que registra as mensagens, ou falha sob demanda."""

    def __init__(self, *, fail_with: Exception | None = None) -> None:
        self._sent: list[EmailMessage] = []
        self._fail_with = fail_with

    @property
    def sent(self) -> tuple[EmailMessage, ...]:
        """Mensagens enviadas, na ordem de envio."""
        return tuple(self._sent)

    def send(self, message: EmailMessage) -> None:
        """Registra a mensagem — ou levanta, se configurado para falhar.

        Quando configurado para falhar, **não** registra: um adapter real que
        estourou no meio do envio não entregou nada, e um fake que registrasse
        assim mesmo faria um teste de falha passar por engano.
        """
        if self._fail_with is not None:
            raise self._fail_with
        self._sent.append(message)


_conforms: EmailSender = RecordingEmailSender()
