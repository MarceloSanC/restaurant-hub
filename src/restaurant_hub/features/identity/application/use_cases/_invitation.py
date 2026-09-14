"""Composição do convite — a **única** casa do formato do link de definição de senha.

Até a Stage 3.5 o formato `{base_url}/definir-senha?token=` vivia em dois
lugares (`invite_user.py` e `request_password_reset.py`), duplicado de
propósito enquanto eram dois fluxos. Com `ProvisionAccountUseCase` (que
**devolve** o link) e `SendInvitationUseCase` (que o envia) haveria quatro cópias
— e quatro cópias de um formato que o front-end consome é o cenário em que uma
diverge sem que nenhum teste note. Este módulo tem um `_` no nome porque é
detalhe interno da camada, não um use case — não entra no wiring e não tem
`execute`; a mesma convenção do `_results.py` de staff (Task 03 desta Stage).

O helper não decide nada: não emite token, não escolhe TTL, não envia. Só
concatena — por isso não recebe port nenhum e não tem estado. A **byte-identidade**
com o formato anterior é asserida em `test_send_invitation.py`, que transcreve
o literal antigo e o compara com `setup_link(...)` (CA16).
"""

from restaurant_hub.shared.application.ports.out.email_sender import EmailMessage

_ASSUNTO = "Convite para o Restaurant Hub"


def setup_link(base_url: str, token_value: str) -> str:
    """Monta o link que a pessoa abre para definir a senha.

    `rstrip('/')` porque `base_url` vem de configuração e alguém vai escrevê-la
    com barra no fim; sem isso o link sairia com `//definir-senha`.
    """
    return f"{base_url.rstrip('/')}/definir-senha?token={token_value}"


def invitation_message(to: str, link: str) -> EmailMessage:
    """A mensagem de convite — assunto e corpo idênticos aos da Stage 2.5.

    A composição vive num helper e não num `EmailComposer` intermediário porque o
    corpo tem três linhas, que o non-goal do roadmap manda manter simples.
    """
    return EmailMessage(
        to=to,
        subject=_ASSUNTO,
        body_text=(
            "Você foi convidado para o Restaurant Hub.\n\n"
            f"Defina a sua senha por este link:\n{link}\n\n"
            "Se você não esperava este convite, ignore esta mensagem."
        ),
    )
