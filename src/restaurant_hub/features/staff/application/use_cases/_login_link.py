"""Regras compartilhadas pelas transições do vínculo de login (Stage 3.10).

Módulo auxiliar, não use case (o prefixo `_` o tira das varreduras da pasta, como
`_unit_enablement.py`). Mora em `use_cases/` porque as regras consultam ports — o
repositório de funcionários e o gateway de identity — e por isso não são domínio
puro (concept 3.10 D6).

**`end_active_link` é o ponto único da regra de fim de vínculo** (ADR 3.8.0001
decisão 5; ADR 3.10.0001 §5). Toda transição que encerra o vínculo **ativo** de um
registro — desligar (R13), trocar o login (R19) e desvincular (R20) — chama esta
função com o registro que leu, **antes** de gravar (ADR 3.5.0003 §2), e nenhum use
case chama `revoke_login_sessions` ou `is_employee_login` fora daqui:
`tests/unit/features/staff/application/test_login_link_single_point.py` trava as
duas coisas por varredura de AST, e a regra 10 de `scripts/check_layout.py` conta a
chamada como a escrita em identity do use case que a faz.

**`resolve_linkable_login` é a elegibilidade da conta existente** (ADR 3.10.0002 §3)
e "um login por unidade" (ADR 3.10.0001 §6), compartilhados por vincular e trocar.
"""

from restaurant_hub.features.staff.application.errors import (
    LoginAccountNotFoundError,
    LoginAlreadyLinkedInUnitError,
)
from restaurant_hub.features.staff.application.ports.out.employee_repository import (
    EmployeeRepository,
)
from restaurant_hub.features.staff.application.ports.out.identity_gateway import (
    IdentityGateway,
)
from restaurant_hub.features.staff.domain.entities.employee import Employee
from restaurant_hub.features.staff.domain.value_objects.identifiers import UserId


def end_active_link(gateway: IdentityGateway, employee: Employee) -> None:
    """Revoga as sessões do login quando o registro é a fonte do acesso dele.

    A regra do ADR 3.8.0001 decisões 1 e 2, nesta ordem, cada passo só se o
    anterior pedir:

    1. **o registro está ativo e tem login** — o vínculo de um desligado não é
       vínculo ativo; encerrá-lo (desligar de novo, desvincular um desligado) não
       toca identity;
    2. **o login é de funcionário** (L-IG5) — gerente ou dono tira a autoridade do
       papel, não do registro, e revogar não protegeria nada.

    A condição "nenhum outro registro ativo da mesma unidade aponta para o login"
    (ADR 3.8.0001 decisão 1) vale **por construção** e não é lida: o índice
    `uq_employees_tenant_unit_user` impede dois registros da unidade com o mesmo
    login (issue #241, ADR 0.0.0025 §4). Lê-la só mudaria o desfecho num estado
    que o banco recusa — e ali deixaria as sessões vivas. Outra unidade não conta
    (workforce §3.1; concept 3.8 §13 Q4).

    A consulta local decide antes de cruzar a fronteira. Em R19, `employee` é o
    registro lido, ainda com o login **antigo**.

    Raises:
        Exception: a falha da consulta de papel (L-IG5) ou da revogação (L-IG4)
            sobe crua — o chamador não grava.
    """
    user_id = employee.user_id
    if not employee.active or user_id is None:
        return
    if gateway.is_employee_login(user_id):
        gateway.revoke_login_sessions(user_id)


def resolve_linkable_login(
    employees: EmployeeRepository, gateway: IdentityGateway, email: str, employee: Employee
) -> UserId:
    """A conta que o e-mail nomeia, se ela pode ser vinculada ao registro (R4 e R10).

    Usada por vincular conta existente (R18) e por trocar o login (R19), **depois**
    das guardas locais e da autorização. Ordem:

    1. a conta do e-mail (L-IG6); e-mail malformado sobe `InvalidLoginEmailError`;
    2. **se a conta é o login atual do registro**, devolve-o sem mais checagens —
       ele já é do registro (só R19 chega aqui: em R18 o registro não tem login);
    3. **elegibilidade** (ADR 3.10.0002 §3): a conta existe, é do tenant do registro
       e alcança a unidade dele — é membro, ou alcança todas as unidades do tenant
       (o dono). Qualquer outro caso, inclusive `platform_admin` (sem tenant), é o
       **mesmo** `LoginAccountNotFoundError`;
    4. **um login por unidade** (ADR 3.10.0001 §6): outro registro da unidade, ativo
       ou desligado, já vinculado à conta ⇒ `LoginAlreadyLinkedInUnitError`. A
       checagem lê a unidade antes da escrita; o vínculo concorrente que passa por
       ela é recusado pela escrita (`link_login`/`relink_login`, com o mesmo erro),
       sob o índice único da unidade (issue #241, ADR 0.0.0025).

    Raises:
        LoginAccountNotFoundError: conta inexistente ou fora do alcance do registro.
        LoginAlreadyLinkedInUnitError: a conta já está em outro registro da unidade.
        InvalidLoginEmailError: e-mail malformado (do gateway, L-IG6).
        Exception: qualquer outra falha de identity ou da listagem sobe crua.
    """
    account = gateway.find_login_by_email(email)
    if account is not None and account.user_id == employee.user_id:
        return account.user_id
    if (
        account is None
        or account.tenant_id != employee.tenant_id
        or not (account.every_unit or employee.unit_id in account.unit_ids)
    ):
        raise LoginAccountNotFoundError(email)
    already_linked = any(
        other.user_id == account.user_id and other.id != employee.id
        for other in employees.list_by_unit(
            employee.tenant_id, employee.unit_id, include_inactive=True
        )
    )
    if already_linked:
        raise LoginAlreadyLinkedInUnitError(employee.id)
    return account.user_id
