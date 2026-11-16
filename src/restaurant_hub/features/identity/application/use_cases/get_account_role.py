"""Use case: consultar o papel de uma conta.

Nasce na Stage 3.8 para a fachada (ADR 3.8.0001 §3). O ADR decide que desligar
um registro de funcionário em staff só corta as sessões do login vinculado
quando o acesso dele vem **do registro**; uma das condições é a conta ser de
funcionário — gerente e dono que também trabalham na escala tiram a autoridade
do papel, não do registro. É essa condição que staff pergunta aqui. Staff não
conhece `Role`: pergunta pela fachada, que devolve o valor em texto, e o gateway
de staff compara com o literal que já detém.

**Só leitura.** Uma linha sobre `UserRepository.find_by_id`.

**Conta desconhecida devolve `None`, não erro.** Para quem pergunta, "não existe"
é uma resposta: um login sem conta não tem sessão a revogar, e o desligamento não
pode falhar por isso (L-IG5 de staff). É o primeiro use case de identity a
devolver `Result | None` — espelha o `find_by_id` do repositório, pelo mesmo
motivo.

Não autoriza e não recebe ator: só a fachada o chama, e é exclusão nomeada do
inventário do ADR 0.0.0020 (desde a Stage 2.7, os use cases de identity que agem por
um ator autorizam o próprio alvo; os facade-only, não). Quem chama pela fachada
responde pela autorização do seu lado: em staff, `deactivate_employee` autoriza
`manage_staff` antes de perguntar (ADR 3.7.0001).
"""

from restaurant_hub.features.identity.application.dtos.commands import GetAccountRoleCommand
from restaurant_hub.features.identity.application.dtos.results import AccountRoleResult
from restaurant_hub.features.identity.application.ports.out.user_repository import (
    UserRepository,
)


class GetAccountRoleUseCase:
    """Devolve o papel da conta, ou `None` se ela não existe."""

    def __init__(self, users: UserRepository) -> None:
        self._users = users

    def execute(self, command: GetAccountRoleCommand) -> AccountRoleResult | None:
        """Consulta o papel; não levanta por conta desconhecida.

        Raises:
            Exception: a falha do repositório sobe como é — traduzi-la, ou
                devolvê-la como `None`, faria o desligamento gravar com a sessão
                viva (L-IG5 de staff).
        """
        user = self._users.find_by_id(command.user_id)
        if user is None:
            return None
        return AccountRoleResult(role=user.role)
