"""Use case: enviar o convite de definição de senha para um link já emitido.

É a segunda metade de `InviteUserUseCase`, separada porque quem provisiona a conta
(`ProvisionAccountUseCase`) não sabe se o link vai por e-mail ou em mãos — o
gateway de staff decide pelo canal escolhido pelo gestor (Stage 3.5, R17) e só
chama este use case no canal `email`.

**A falha do `EmailSender` propaga**, como no convite da 2.5 (regra 13):
reportar sucesso sem que o e-mail tenha saído deixaria uma conta inacessível e
um gestor convencido de que convidou. A conta já existe quando isto falha — o
caminho de recuperação é o pedido público de redefinição de senha.

Não emite token, não consulta repositório, não decide nada: recebe o link pronto
e o coloca na mensagem que `_invitation.invitation_message` compõe — assunto e
corpo idênticos aos do convite da 2.5.
"""

from restaurant_hub.features.identity.application.dtos.commands import SendInvitationCommand
from restaurant_hub.features.identity.application.use_cases._invitation import (
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
            Exception: qualquer falha do `EmailSender` sobe (regra 13 da 2.5).
        """
        self._email_sender.send(invitation_message(command.email.value, command.setup_link))
