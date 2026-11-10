"""Use case: enviar o convite de definição de senha para um link já emitido.

É a segunda metade de `InviteUserUseCase`, separada porque quem provisiona a conta
(`ProvisionAccountUseCase`) não sabe se o link vai por e-mail ou em mãos — o
gateway de staff decide pelo canal escolhido pelo gestor (Stage 3.5, R17) e só
chama este use case no canal `email`.

**A falha do `EmailSender` propaga**, como no convite da 2.5 (regra 13):
reportar sucesso sem que o e-mail tenha saído deixaria uma conta inacessível e
um gestor convencido de que convidou. A conta já existe quando isto falha — o
caminho de recuperação é o pedido público de redefinição de senha.

**E propaga trocada, como nos outros convites** (issue #175): o envio passa por
`_invitation.deliver_invitation`, que registra só o tipo da falha e o `user_id`
do command e levanta `InvitationNotSentError` sem cadeia até a original — cuja
mensagem pode ecoar o destinatário e o link. Até a #175 este era o único call
site de `EmailSender.send` fora dessa política, e a falha chegava crua ao
servidor ASGI, que a registrava com traceback.

Não emite token, não consulta repositório, não decide nada: recebe o link pronto
e o coloca na mensagem que `_invitation.invitation_message` compõe — assunto e
corpo idênticos aos do convite da 2.5. O `user_id` também chega pronto, de quem
provisionou a conta; este use case não o confere contra o e-mail.
"""

from restaurant_hub.features.identity.application.dtos.commands import SendInvitationCommand
from restaurant_hub.features.identity.application.use_cases._invitation import (
    deliver_invitation,
    invitation_message,
)
from restaurant_hub.shared.application.ports.out.email_sender import EmailSender


class SendInvitationUseCase:
    """Compõe e envia a mensagem de convite com o link recebido."""

    def __init__(self, email_sender: EmailSender) -> None:
        self._email_sender = email_sender

    def execute(self, command: SendInvitationCommand) -> None:
        """Envia o convite.

        Raises:
            InvitationNotSentError: o `EmailSender` falhou (regra 13 da 2.5; issue
                #175).
        """
        deliver_invitation(
            self._email_sender,
            invitation_message(command.email.value, command.setup_link),
            command.user_id,
        )
