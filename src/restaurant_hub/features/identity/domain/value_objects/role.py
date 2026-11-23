"""Value object Role — papel fixo de acesso (RBAC) e o seu conjunto de permissões.

Conjunto **fechado** de 5 papéis (overview §3; kickoff #10). Não confundir com
**função de trabalho** (cozinheiro, atendente…), que é 100% customizável por
restaurante e pertence ao BC `staff` (Step 3) — vocabulários distintos (overview §9).

O mapa `Role -> frozenset[Permission]` é fixo e **total**: todo papel tem entrada,
mesmo que vazia (concept §5, regra 6). A totalidade é guardada por teste — papel
novo sem entrada no mapa quebra a suíte em vez de falhar em silêncio.
"""

from enum import StrEnum

from restaurant_hub.features.identity.domain.exceptions.errors import InvalidRoleError
from restaurant_hub.features.identity.domain.value_objects.permission import Permission


class Role(StrEnum):
    """Papel fixo de acesso de um usuário dentro (ou fora) de um tenant."""

    PLATFORM_ADMIN = "platform_admin"
    OWNER = "owner"
    MANAGER = "manager"
    HR = "hr"
    EMPLOYEE = "employee"

    @classmethod
    def from_string(cls, value: str) -> "Role":
        """Converte texto em `Role`, com erro de domínio se o papel for desconhecido."""
        try:
            return cls(value)
        except ValueError as exc:
            raise InvalidRoleError(value) from exc

    @property
    def permissions(self) -> frozenset[Permission]:
        """Conjunto fixo de permissões deste papel."""
        return _ROLE_PERMISSIONS[self]


# Mapa total papel -> permissões. `platform_admin` fica restrito a MANAGE_PLATFORM:
# acesso de plataforma não é acesso de restaurante (concept §5, regra 7).
#
# `manager` e `hr` coincidem nas permissões de identity e de staff — **dentro do BC
# `staff` eles são equivalentes**: as mesmas duas permissões de equipe, com o mesmo alcance
# (as unidades de que são membros) — e **divergem na escala**. O eixo real da divergência é
# **família de operação**, não alcance: RH mexe no cadastro do funcionário; mexer na escala é
# do gerente e do dono (ADR 3.4.0006 §1 e §2).
#
# **Restrição vinculante (ADR 3.4.0006 §3, superado em parte pelos ADRs 4.1.0004 e
# 4.5.0001):** `hr` **não recebe permissão de escrita sobre a escala** (`manage_schedule`);
# `hr` **lê** a escala das unidades de que é membro e vê a própria. Nisso consiste a
# divergência hr/manager — arquivo lido por quem estende o mapa. Consequência medida: pela
# regra "não se concede o que não se detém", `hr` não cria nem convida `manager`.
#
# `view_own_schedule` ("minha escala") é de **todo** papel do restaurante: quem trabalha na
# escala pode ter vínculo de login seja qual for o papel (Stage 3.10), e quem cria `employee`
# precisa deter o que ele detém (ADR 4.5.0001 §Decision 4). `manage_schedule_settings`,
# tenant-wide, é só do `owner` (§Decision 5).
_ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.PLATFORM_ADMIN: frozenset({Permission.MANAGE_PLATFORM}),
    Role.OWNER: frozenset(
        {
            Permission.MANAGE_TENANT,
            Permission.MANAGE_USERS,
            Permission.MANAGE_STAFF,
            Permission.MANAGE_JOB_FUNCTIONS,
            Permission.VIEW_SCHEDULE,
            Permission.MANAGE_SCHEDULE,
            Permission.VIEW_OWN_SCHEDULE,
            Permission.MANAGE_SCHEDULE_SETTINGS,
        }
    ),
    Role.MANAGER: frozenset(
        {
            Permission.MANAGE_USERS,
            Permission.MANAGE_STAFF,
            Permission.MANAGE_JOB_FUNCTIONS,
            Permission.VIEW_SCHEDULE,
            Permission.MANAGE_SCHEDULE,
            Permission.VIEW_OWN_SCHEDULE,
        }
    ),
    Role.HR: frozenset(
        {
            Permission.MANAGE_USERS,
            Permission.MANAGE_STAFF,
            Permission.MANAGE_JOB_FUNCTIONS,
            Permission.VIEW_SCHEDULE,
            Permission.VIEW_OWN_SCHEDULE,
        }
    ),
    Role.EMPLOYEE: frozenset({Permission.VIEW_OWN_SCHEDULE}),
}
