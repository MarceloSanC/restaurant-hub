"""Value object Permission — capacidades de acesso do BC identity.

É o **eixo A** do modelo de acesso: o que um papel *faz*. A **visibilidade de
unidade** (quais unidades um usuário enxerga) é o eixo B, resolvido por `User` a
partir do papel e das `UnitMembership` — "ver o tenant inteiro" **não** é uma
permissão, é bypass de escopo (concept §3, §5).

Semente enxuta do BC identity; as Stages/BCs seguintes (`staff`, `scheduling`)
estendem o vocabulário com as suas próprias capacidades.

**As permissões divergem no eixo de unidade**, e a divergência é declarada aqui:
`MANAGE_STAFF` é **unit-scoped** (o registro de funcionário mora numa unidade e
a ação tem de nomeá-la), enquanto `MANAGE_JOB_FUNCTIONS` é **tenant-wide** (o
catálogo de funções pertence ao restaurante — `workforce.md` §3.2 — e não tem
unidade a nomear). Uma permissão só não pode ser as duas coisas, e é por isso
que são duas (ADR 3.4.0006 §4).
"""

from enum import StrEnum


class Permission(StrEnum):
    """Capacidade de acesso concedida por um papel."""

    MANAGE_PLATFORM = "manage_platform"
    MANAGE_TENANT = "manage_tenant"
    MANAGE_USERS = "manage_users"
    MANAGE_STAFF = "manage_staff"
    MANAGE_JOB_FUNCTIONS = "manage_job_functions"


# Permissões cujo alvo é o **restaurante**, não a unidade — o critério de entrada
# neste conjunto e o único. Quem exerce uma delas fica dispensado de declarar a
# unidade alvo no passo 4 de `AuthorizeActionUseCase` (ADR 3.4.0008 §1 e §2).
#
# A dispensa é **por permissão, nunca por papel**: um papel unit-scoped continua
# unit-scoped para todo o resto que detém. Por isso `MANAGE_STAFF` está fora
# **de propósito** — registro de funcionário mora numa unidade, e pô-lo aqui
# daria alcance cross-unidade sobre cadastros (ADR 3.4.0008 §3).
#
# Acrescentar membro aqui é ato deliberado e revisado: há teste com lista
# esperada explícita, então a entrada nova não passa como diff de uma palavra
# (ADR 3.4.0008 §5).
TENANT_WIDE_PERMISSIONS: frozenset[Permission] = frozenset({Permission.MANAGE_JOB_FUNCTIONS})
