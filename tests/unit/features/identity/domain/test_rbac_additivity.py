"""Aditividade do vocabulário de acesso — CA20, na metade **provada**.

As duas fixtures de **fechamento** de `test_role_permission.py`
(`test_permission_e_conjunto_fechado` e `test_conteudo_exato_do_mapa_por_papel`)
existem para exigir atualização consciente quando o conjunto cresce: elas mudam
sempre que uma Stage estende o vocabulário, e isso é o teste funcionando.

O que **não** pode mudar é a **decisão de acesso**: membro sumindo de
`Permission`, papel perdendo permissão que já tinha. Sem este arquivo, a prova
disso dependeria de alguém ler um `git diff` e uma mensagem de commit —
auditoria por olho, exatamente o modo de falha que a Stage 3.4 existe para
fechar.

**As asserções são de subconjunto (`<=`), não de igualdade, de propósito:**
crescer é permitido, encolher não. O arquivo sobrevive a esta Stage e passa a
guardar **toda** extensão futura do vocabulário.
"""

import pytest

from restaurant_hub.features.identity.domain.value_objects.permission import Permission
from restaurant_hub.features.identity.domain.value_objects.role import Role

pytestmark = pytest.mark.unit

# Baselines congeladas: o vocabulário **anterior** à Stage 3.4. Não atualizar ao
# estender o mapa — é justamente o ponto fixo contra o qual a aditividade é
# medida. Uma Stage futura pode acrescentar uma baseline nova (do seu próprio
# ponto de partida); nunca afrouxar esta.
BASELINE_PERMISSIONS = {"manage_platform", "manage_tenant", "manage_users"}
BASELINE_ROLE_PERMISSIONS: dict[Role, set[Permission]] = {
    Role.PLATFORM_ADMIN: {Permission.MANAGE_PLATFORM},
    Role.OWNER: {Permission.MANAGE_TENANT, Permission.MANAGE_USERS},
    Role.MANAGER: {Permission.MANAGE_USERS},
    Role.HR: {Permission.MANAGE_USERS},
    Role.EMPLOYEE: set(),
}


def test_nenhum_membro_foi_removido_do_enum_permission() -> None:
    """Toda permissão que já existia continua existindo."""
    assert BASELINE_PERMISSIONS.issubset({p.value for p in Permission})


@pytest.mark.parametrize("papel", list(BASELINE_ROLE_PERMISSIONS))
def test_nenhum_papel_perdeu_permissao_que_ja_tinha(papel: Role) -> None:
    """Toda concessão papel↔permissão que já existia continua valendo."""
    assert BASELINE_ROLE_PERMISSIONS[papel].issubset(papel.permissions)
