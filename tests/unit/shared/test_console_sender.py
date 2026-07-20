"""Testes do adapter `ConsoleSender` (Stage 2.5, CA2)."""

import io
import sys

import pytest

from restaurant_hub.shared.application.ports.out.email_sender import EmailMessage
from restaurant_hub.shared.infrastructure.email.console_sender import ConsoleSender


def _mensagem() -> EmailMessage:
    return EmailMessage(
        to="convidado@exemplo.com",
        subject="Voce foi convidado",
        body_text="Defina a sua senha: https://exemplo.com/senha?token=abc123",
    )


class TestConsoleSender:
    def test_escreve_destinatario_assunto_e_corpo(self) -> None:
        """CA2 — os três campos aparecem na saída, ou o adapter não entregou nada."""
        saida = io.StringIO()

        ConsoleSender(stream=saida).send(_mensagem())

        escrito = saida.getvalue()
        assert "convidado@exemplo.com" in escrito
        assert "Voce foi convidado" in escrito
        assert "https://exemplo.com/senha?token=abc123" in escrito

    def test_mensagens_sucessivas_se_acumulam(self) -> None:
        saida = io.StringIO()
        sender = ConsoleSender(stream=saida)
        envios = 2

        for _ in range(envios):
            sender.send(_mensagem())

        assert saida.getvalue().count("convidado@exemplo.com") == envios

    def test_default_e_stdout(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """O caminho do default também é exercitado.

        Sem este teste a linha do `sys.stdout` fica descoberta, e a cobertura da
        Stage cairia por causa da única linha que nenhum outro teste alcança —
        justamente a que roda em produção.
        """
        capturado = io.StringIO()
        monkeypatch.setattr(sys, "stdout", capturado)

        ConsoleSender().send(_mensagem())

        assert "convidado@exemplo.com" in capturado.getvalue()
