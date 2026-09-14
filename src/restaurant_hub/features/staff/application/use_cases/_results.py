"""O único sítio de construção de `EmployeeResult` (Stage 3.5, concept D6).

Até a 3.5 o DTO era construído inline em **11** use cases — o mesmo bloco de nove
linhas, copiado. Acrescentar um campo ao registro exigia tocar os 11, e esquecer
um era **silencioso**: o result nascia com o default e nenhum teste de use case
pegava, porque cada um olha só o seu. Com o vínculo de login chegando ao
registro, a omissão deixaria uma das 12 rotas que devolvem funcionário
respondendo `user_id: null` para um registro vinculado.

É a direção do **Gate 8 da issue #45** ("um sítio de construção por `*Result`"),
aplicada ao BC que a Stage já toca. A trava é estrutural, não de disciplina:
`test_dtos.py` varre por AST a pasta `use_cases/` e reprova qualquer `Call` a
`EmployeeResult` fora deste módulo, e conta os consumidores desta função.

**Por que em `use_cases/` e com `_`:** é auxiliar da camada — não é use case, não
é DTO, não é port. O prefixo o tira das varreduras que enumeram use cases
(`test_application_guards.py`, `test_composition_root_staff.py`) pela convenção
que já valia para módulos privados. Não é método do DTO: DTO sem comportamento
é o Gate 6 da mesma issue.
"""

from restaurant_hub.features.staff.application.dtos.results import EmployeeResult
from restaurant_hub.features.staff.domain.entities.employee import Employee


def employee_result(employee: Employee) -> EmployeeResult:
    """Copia **todos** os campos da entidade para o DTO — inclusive `user_id`."""
    return EmployeeResult(
        id=employee.id,
        tenant_id=employee.tenant_id,
        unit_id=employee.unit_id,
        name=employee.name,
        workload_profile=employee.workload_profile,
        shift_preference=employee.shift_preference,
        job_function_ids=employee.job_function_ids,
        unavailabilities=employee.unavailabilities,
        active=employee.active,
        user_id=employee.user_id,
    )
