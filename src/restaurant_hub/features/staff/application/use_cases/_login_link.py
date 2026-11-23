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
"""

from restaurant_hub.features.staff.application.ports.out.employee_repository import (
    EmployeeRepository,
)
from restaurant_hub.features.staff.application.ports.out.identity_gateway import (
    IdentityGateway,
)
from restaurant_hub.features.staff.domain.entities.employee import Employee


def end_active_link(
    employees: EmployeeRepository, gateway: IdentityGateway, employee: Employee
) -> None:
    """Revoga as sessões do login quando o registro é a fonte do acesso dele.

    A regra do ADR 3.8.0001 decisões 1 e 2, nesta ordem, cada passo só se o
    anterior pedir:

    1. **o registro está ativo e tem login** — o vínculo de um desligado não é
       vínculo ativo; encerrá-lo (desligar de novo, desvincular um desligado) não
       toca identity;
    2. **nenhum outro registro ativo da mesma unidade aponta para o login** — se
       houver, é ele que ainda concede o acesso. `list_by_unit` devolve só ativos
       (L-E6). Só a unidade: nenhuma operação de staff atravessa unidades
       implicitamente (workforce §3.1);
    3. **o login é de funcionário** (L-IG5) — gerente ou dono tira a autoridade do
       papel, não do registro, e revogar não protegeria nada.

    A consulta local decide antes de cruzar a fronteira. Em R19, `employee` é o
    registro lido, ainda com o login **antigo**.

    Raises:
        Exception: a falha da listagem, da consulta de papel (L-IG5) ou da
            revogação (L-IG4) sobe crua — o chamador não grava.
    """
    user_id = employee.user_id
    if not employee.active or user_id is None:
        return
    shared = any(
        other.user_id == user_id and other.id != employee.id
        for other in employees.list_by_unit(employee.tenant_id, employee.unit_id)
    )
    if shared:
        return
    if gateway.is_employee_login(user_id):
        gateway.revoke_login_sessions(user_id)
