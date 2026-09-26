"""Use case: copiar o cadastro de um funcionário para outra unidade.

**Duplica; não compartilha, não vincula, não vaza** (workforce §3.7;
ADR 3.2.0003). O registro novo recebe **id novo**, `unit_id` da unidade destino
e o **mesmo `tenant_id`**; todo o resto do cadastro é duplicado — nome, perfil
de jornada, preferência, conjunto de funções, indisponibilidades **e o estado
`active`**.

A lista de exclusões é **fechada e explícita**: identidade (id novo), unidade
(destino) e vínculo de login (nunca). Carregar `active` como está não cria
nenhum estado inalcançável — registro inativo na unidade destino já é
alcançável por criar + desligar —, enquanto recusar a cópia de um desligado
abriria um quarto item numa lista que o ADR fechou.

**Por que não consome `JobFunctionRepository`.** A única razão para consultá-lo
seria checar o **estado** das funções copiadas, que deixou de existir
(ADR 3.2.0005). O conjunto de ids da origem já é referencialmente válido — foi
validado quando foi atribuído — e as funções são **tenant-scoped**, logo
continuam válidas na unidade destino. A corrida "função apagada entre a leitura
da origem e a gravação da cópia" é fechada pela lei **L-E4** do
`EmployeeRepository.add`, não por uma consulta extra aqui.

**Os dois registros são independentes por construção**, não por cuidado: as
entidades e VOs da 3.1 são `frozen`, então não há objeto mutável a compartilhar.
"""

from restaurant_hub.features.staff.application.dtos.commands import CopyEmployeeToUnitCommand
from restaurant_hub.features.staff.application.dtos.results import (
    EmployeeResult,
    to_employee_result,
)
from restaurant_hub.features.staff.application.errors import (
    EmployeeNotFoundError,
    SameUnitCopyError,
)
from restaurant_hub.features.staff.application.ports.out.employee_repository import (
    EmployeeRepository,
)
from restaurant_hub.features.staff.domain.entities.employee import Employee
from restaurant_hub.features.staff.domain.value_objects.identifiers import EmployeeId
from restaurant_hub.shared.application.ports.out.id_generator import IdGenerator


class CopyEmployeeToUnitUseCase:
    """Duplica o cadastro de um funcionário em outra unidade do mesmo tenant."""

    def __init__(self, employees: EmployeeRepository, id_generator: IdGenerator) -> None:
        self._employees = employees
        self._id_generator = id_generator

    def execute(self, command: CopyEmployeeToUnitCommand) -> EmployeeResult:
        """Cria a cópia na unidade destino.

        Raises:
            EmployeeNotFoundError: origem inexistente **no endereço (tenant + unidade)**. Vence o
                `SameUnitCopyError` quando as duas condições ocorrem — a
                resposta não pode revelar que o registro existe em outro tenant
                nem em que unidade ele está (§5.4).
            SameUnitCopyError: destino igual à unidade de origem.

        **`command.unit_id` é a ORIGEM; `command.target_unit_id` é o destino.**
        É o único ponto do BC onde as duas unidades convivem, e trocá-las
        reabriria exatamente a exfiltração que o ADR 3.4.0007 fecha: ler com o
        destino encontraria o registro alheio a partir da unidade do atacante.
        """
        # (1) Origem — lida **pela unidade de origem** (ADR 3.4.0007 §3).
        origin = self._employees.find_by_id(command.tenant_id, command.unit_id, command.employee_id)
        if origin is None:
            raise EmployeeNotFoundError(command.employee_id)
        # (2) Destino diferente da origem.
        if command.target_unit_id == origin.unit_id:
            raise SameUnitCopyError(command.target_unit_id)
        # (3) A cópia: id novo, unidade destino, mesmo tenant, resto duplicado.
        copy = Employee(
            id=EmployeeId(str(self._id_generator.next_id())),
            tenant_id=origin.tenant_id,
            unit_id=command.target_unit_id,
            name=origin.name,
            workload_profile=origin.workload_profile,
            shift_preference=origin.shift_preference,
            job_function_ids=origin.job_function_ids,
            unavailabilities=origin.unavailabilities,
            active=origin.active,
        )
        # (4) Escrita — a L-E4 revalida as funções aqui.
        self._employees.add(copy)
        return to_employee_result(copy)
