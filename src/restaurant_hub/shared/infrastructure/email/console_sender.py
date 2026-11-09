"""Adapter de `EmailSender` que escreve a mensagem numa saída de texto local.

É o adapter que satisfaz o DoD da Stage 2.5 em desenvolvimento, e é também o que
o ADR 0.0.0004 §Decision 7 exige numa corrida autônoma: **nada sai da máquina**.
O provedor real (Resend, decidido no kickoff #7) entra na Stage 6.2, com a
credencial do sponsor, e trocá-lo é substituir esta classe no composition root —
nenhum use case muda.

**Este adapter imprime o corpo, portanto imprime o token de convite.** Em
desenvolvimento isso é o recurso, não o defeito: é assim que se pega o link sem
caixa de entrada. Em produção seria vazamento de credencial em log, e por isso o
adapter de produção da 6.2 **não** deve registrar o corpo. A observação está aqui,
e não só no concept, porque é aqui que alguém vai olhar antes de copiar este
arquivo para escrever o próximo sender.

**A saída é injetada, não capturada.** Escrever direto em `sys.stdout` e testar
com `capsys` amarraria o teste a estado global do processo; recebendo o
`TextIO`, o teste passa um `StringIO` e lê o que foi escrito. O default continua
sendo `sys.stdout`, que é o que faz sentido para quem roda `make run`.
"""

import sys
from typing import TextIO

from restaurant_hub.shared.application.ports.out.email_sender import EmailMessage

_SEPARATOR = "-" * 72


class ConsoleSender:
    """Implementação de `EmailSender` que escreve a mensagem em texto puro."""

    def __init__(self, stream: TextIO | None = None) -> None:
        self._stream = stream if stream is not None else sys.stdout

    def send(self, message: EmailMessage) -> None:
        """Escreve destinatário, assunto e corpo na saída configurada.

        `flush` explícito: quando a saída é um pipe (Docker, CI, `make run` com
        stdout redirecionado), o buffer do Python só esvazia ao encher ou ao sair
        do processo, e a mensagem apareceria minutos depois do envio — ou nunca,
        se o processo morresse antes. Para um adapter cujo propósito **é** ser
        lido na hora, o buffer atrasado equivale a não ter enviado.
        """
        self._stream.write(
            f"{_SEPARATOR}\n"
            f"To: {message.to}\n"
            f"Subject: {message.subject}\n"
            f"\n"
            f"{message.body_text}\n"
            f"{_SEPARATOR}\n"
        )
        self._stream.flush()
