"""Composição do convite — a **única** casa do formato do link de definição de senha.

Até a Stage 3.5 o formato `{base_url}/definir-senha?token=` vivia em dois
lugares (`invite_user.py` e `request_password_reset.py`), duplicado de
propósito enquanto eram dois fluxos. Com `ProvisionAccountUseCase` (que
**devolve** o link) e `SendInvitationUseCase` (que o envia) haveria quatro cópias
— e quatro cópias de um formato que o front-end consome é o cenário em que uma
diverge sem que nenhum teste note. Este módulo tem um `_` no nome porque é
detalhe interno da camada, não um use case — não entra no wiring e não tem
`execute`.

`setup_link` e `invitation_message` não decidem nada: não emitem token, não
escolhem TTL, não enviam. Só concatenam — por isso não recebem port nenhum e não têm
estado. A **byte-identidade** com o formato anterior é asserida em
`test_send_invitation.py`, que transcreve o literal antigo e o compara com
`setup_link(...)` (CA16).

**`deliver_invitation` é a exceção, e é a única casa da política de falha do envio
do convite** (issue #170). Recebe o port e envia; se o envio falha, registra só o
tipo da falha e o `user_id` — como `RequestPasswordResetUseCase` faz desde a issue
#26 — e levanta `InvitationNotSentError`. Os dois use cases que convidam depois de
comitar a conta (`InviteUserUseCase` e `ProvisionRestaurantUseCase`) passam por
aqui, e por isso as três rotas de convite herdam a mesma garantia de uma vez.
Desde a issue #175 o terceiro chamador é `SendInvitationUseCase`, a entrega pela
fachada no canal `email` do login de funcionário (R17 de staff): a quarta rota.
"""

import logging

from restaurant_hub.features.identity.application.errors import InvitationNotSentError
from restaurant_hub.shared.application.ports.out.email_sender import (
    EmailMessage,
    EmailSender,
)

_SUBJECT = "Convite para o Restaurant Hub"

_log = logging.getLogger(__name__)


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
        subject=_SUBJECT,
        body_text=(
            "Você foi convidado para o Restaurant Hub.\n\n"
            f"Defina a sua senha por este link:\n{link}\n\n"
            "Se você não esperava este convite, ignore esta mensagem."
        ),
    )


def deliver_invitation(email_sender: EmailSender, message: EmailMessage, user_id: str) -> None:
    """Envia o convite de uma conta **já comitada**; se falhar, troca a falha.

    A falha continua subindo (regra 13 da 2.5): quem convidou precisa saber que o
    e-mail não saiu. O que muda é **o que** sobe e o que fica registrado.

    - **No log, só o tipo e o `user_id`.** Sem `exc_info` e sem `str(exc)`: a
      mensagem e o traceback de uma falha de provedor podem ecoar o destinatário
      ou o corpo, e o corpo leva o link — que é credencial (issue #170).
    - **Sobe `InvitationNotSentError`, levantada fora do `except`.** Dentro dele,
      o Python amarraria a falha original em `__context__`, e qualquer formatação
      de traceback adiante a imprimiria com a mensagem. Fora, a cadeia nasce vazia.

    Raises:
        InvitationNotSentError: o `EmailSender` levantou qualquer `Exception`.
    """
    try:
        email_sender.send(message)
    except Exception as exc:  # o port não fixa o tipo da falha: é do adapter
        failure = type(exc)
    else:
        return
    _log.error(
        "convite não enviado (conta já gravada): user_id=%s erro=%s",
        user_id,
        f"{failure.__module__}.{failure.__qualname__}",
    )
    raise InvitationNotSentError(user_id)
