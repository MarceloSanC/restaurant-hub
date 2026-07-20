"""Contrato de `EmailSender`: fake e adapter real respondem à mesma bateria.

O fake `RecordingEmailSender` é o que os use cases veem em teste; o
`ConsoleSender` é o que roda de verdade. Se os dois divergirem no contrato — por
exemplo, um aceitando um corpo vazio e o outro estourando —, o teste de use case
fica verde sobre um comportamento que a aplicação não tem.

O que o contrato pode assertar é limitado de propósito: `send` devolve `None` e o
port não expõe forma de inspecionar o que foi enviado (o fake expõe, mas isso é
recurso de teste, não contrato). Então a bateria verifica o que é comum e
observável — aceitar as mensagens sem levantar, em qualquer ordem e com qualquer
conteúdo bem formado.
"""

import io
from collections.abc import Callable

import pytest

from restaurant_hub.shared.application.ports.out.email_sender import (
    EmailMessage,
    EmailSender,
)
from restaurant_hub.shared.infrastructure.email.console_sender import ConsoleSender
from tests.fakes.shared.recording_email_sender import RecordingEmailSender

_IMPLEMENTACOES: list[tuple[str, Callable[[], EmailSender]]] = [
    ("fake", RecordingEmailSender),
    ("console", lambda: ConsoleSender(stream=io.StringIO())),
]


@pytest.fixture(params=_IMPLEMENTACOES, ids=[nome for nome, _ in _IMPLEMENTACOES])
def sender(request: pytest.FixtureRequest) -> EmailSender:
    _, fabrica = request.param
    return fabrica()


@pytest.mark.contract
class TestContratoEmailSender:
    def test_envia_mensagem_comum(self, sender: EmailSender) -> None:
        sender.send(EmailMessage(to="a@exemplo.com", subject="Assunto", body_text="Corpo"))

    def test_aceita_corpo_com_multiplas_linhas(self, sender: EmailSender) -> None:
        sender.send(
            EmailMessage(
                to="a@exemplo.com",
                subject="Assunto",
                body_text="Linha 1\nLinha 2\n\nLinha 4",
            )
        )

    def test_aceita_corpo_vazio(self, sender: EmailSender) -> None:
        """Corpo vazio não é erro do port — validar conteúdo é de quem compõe."""
        sender.send(EmailMessage(to="a@exemplo.com", subject="Assunto", body_text=""))

    def test_aceita_varias_mensagens_seguidas(self, sender: EmailSender) -> None:
        for indice in range(3):
            sender.send(
                EmailMessage(
                    to=f"destino{indice}@exemplo.com",
                    subject=f"Assunto {indice}",
                    body_text=f"Corpo {indice}",
                )
            )
