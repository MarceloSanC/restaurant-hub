"""Use case: encontrar uma conta pelo e-mail.

Nasce na Stage 3.10 para a fachada (ADR 3.10.0002 §2). Staff vincula a um
registro de funcionário uma conta que já existe no restaurante — o gerente ou
dono que também trabalha na escala —, e o gerente a nomeia pelo e-mail. Staff
precisa de três fatos para decidir se a conta é vinculável: o restaurante dela,
as unidades de que ela é membro e se ela enxerga todas as unidades sem
membership. A **decisão** é de staff; aqui só se responde.

**Só leitura.** `find_credentials_by_email` (o hash não sai daqui — ADR 3.10.0002
§Alternative F registra o método dedicado como evolução) e `list_memberships`.

**As memberships são filtradas pelo `user_id` da conta.** O port de usuários não
promete o filtro (decisão 3 do seu docstring): quem casa usuário e unidade é o
consumidor, e aqui o consumidor é este use case.

**O alcance de todas as unidades é a regra de visibilidade de identity**
(`User.bypasses_unit_scope`), entregue como fato, não como papel: staff não nomeia
o vocabulário de papéis (ADR 3.8.0001 Alt. F). Para conta sem tenant
(`platform_admin`) o fato é falso — não há tenant cujas unidades alcançar.

**E-mail sem conta devolve `None`, não erro**, como `GetAccountRoleUseCase`: para
quem pergunta, "não existe" é uma resposta. E-mail malformado nem chega aqui — o
`Email` o recusa na fachada.

Não autoriza e não recebe ator: só a fachada o chama, e é exclusão nomeada do
inventário do ADR 0.0.0020. Quem chama pela fachada responde pela autorização: em
staff, vincular e trocar o login autorizam `manage_staff` e `manage_users` sobre a
unidade antes de perguntar (ADR 3.10.0002 §5).
"""

from restaurant_hub.features.identity.application.dtos.commands import (
    FindAccountByEmailCommand,
)
from restaurant_hub.features.identity.application.dtos.results import AccountSummaryResult
from restaurant_hub.features.identity.application.ports.out.user_repository import (
    UserRepository,
)


class FindAccountByEmailUseCase:
    """Devolve id, tenant, unidades e alcance da conta, ou `None` se o e-mail não tem conta."""

    def __init__(self, users: UserRepository) -> None:
        self._users = users

    def execute(self, command: FindAccountByEmailCommand) -> AccountSummaryResult | None:
        """Consulta a conta; não levanta por e-mail sem conta.

        Raises:
            Exception: a falha do repositório sobe como é — devolvê-la como `None`
                faria staff responder "conta inexistente" numa falha de identity.
        """
        credentials = self._users.find_credentials_by_email(command.email)
        if credentials is None:
            return None
        user = credentials.user
        unit_ids = sorted(
            membership.unit_id
            for membership in self._users.list_memberships(user.id)
            if membership.user_id == user.id
        )
        return AccountSummaryResult(
            user_id=user.id,
            tenant_id=user.tenant_id,
            unit_ids=tuple(unit_ids),
            sees_every_unit=user.tenant_id is not None and user.bypasses_unit_scope(),
        )
