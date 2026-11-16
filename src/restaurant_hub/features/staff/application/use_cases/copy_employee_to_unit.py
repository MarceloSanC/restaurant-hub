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

**Consome `JobFunctionRepository` desde a Stage 3.11** (ADR 3.11.0002, que supera
nesse ponto o ADR 3.2.0003). Antes a cópia não o consultava: as funções valiam no
restaurante inteiro, logo continuavam válidas na unidade destino. Com a
habilitação por unidade isso deixou de ser verdade, e a regra "um registro só
detém função habilitada na sua unidade" vale para a cópia como vale para criar e
atribuir: se alguma função da origem não vale no destino, a cópia é **recusada** —
não habilita a função junto (quem copia tem `manage_staff`, não o catálogo) e não
deixa a função para trás (a lista de exclusões do ADR 3.2.0003 é fechada). O
gerente habilita a função no destino e repete a cópia.

A corrida "função apagada entre a leitura da origem e a gravação da cópia"
continua fechada pela lei **L-E4** do `EmployeeRepository.add`; a resolução daqui
só antecipa o mesmo `JobFunctionNotFoundError`.

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
    JobFunctionNotFoundError,
    SameUnitCopyError,
)
from restaurant_hub.features.staff.application.ports.out.access_guard import (
    PERMISSION_MANAGE_STAFF,
    AccessGuard,
)
from restaurant_hub.features.staff.application.ports.out.employee_repository import (
    EmployeeRepository,
)
from restaurant_hub.features.staff.application.ports.out.job_function_repository import (
    JobFunctionRepository,
)
from restaurant_hub.features.staff.application.use_cases._unit_enablement import (
    require_enabled_in_unit,
)
from restaurant_hub.features.staff.domain.entities.employee import Employee
from restaurant_hub.features.staff.domain.value_objects.identifiers import EmployeeId
from restaurant_hub.shared.application.ports.out.id_generator import IdGenerator


class CopyEmployeeToUnitUseCase:
    """Duplica o cadastro de um funcionário em outra unidade do mesmo tenant."""

    def __init__(
        self,
        employees: EmployeeRepository,
        job_functions: JobFunctionRepository,
        id_generator: IdGenerator,
        guard: AccessGuard,
    ) -> None:
        self._employees = employees
        self._job_functions = job_functions
        self._id_generator = id_generator
        self._guard = guard

    def execute(self, command: CopyEmployeeToUnitCommand) -> EmployeeResult:
        """Cria a cópia na unidade destino.

        Raises:
            EmployeeNotFoundError: origem inexistente **no endereço (tenant + unidade)**. Vence o
                `SameUnitCopyError` quando as duas condições ocorrem — a
                resposta não pode revelar que o registro existe em outro tenant
                nem em que unidade ele está (§5.4).
            SameUnitCopyError: destino igual à unidade de origem.
            JobFunctionNotFoundError: função da origem apagada entre a atribuição
                e a cópia.
            JobFunctionNotEnabledInUnitError: alguma função da origem não está
                habilitada na unidade destino (Stage 3.11). Perde para os dois
                primeiros: a resposta a um registro alheio ou a um destino igual
                à origem não diz nada sobre o catálogo.

        **`command.unit_id` é a ORIGEM; `command.target_unit_id` é o destino.**
        É o único ponto do BC onde as duas unidades convivem, e trocá-las
        reabriria exatamente a exfiltração que o ADR 3.4.0007 fecha: ler com o
        destino encontraria o registro alheio a partir da unidade do atacante.

        **As duas unidades são autorizadas antes de tudo** (Stage 3.7, ADR
        3.7.0001): a origem, depois o destino — dois alvos, duas chamadas
        (L-AG4) —, e as duas antes da leitura da origem, para que negar o destino
        não deixe nem a leitura para trás.
        """
        # (0) Autorização do alvo do command, antes de qualquer outra instrução
        # (ADR 3.7.0001 §4). A exceção do guard sobe crua (L-AG2).
        self._guard.authorize(
            command.actor,
            PERMISSION_MANAGE_STAFF,
            tenant_id=command.tenant_id,
            unit_id=command.unit_id,
        )
        self._guard.authorize(
            command.actor,
            PERMISSION_MANAGE_STAFF,
            tenant_id=command.tenant_id,
            unit_id=command.target_unit_id,
        )
        # (1) Origem — lida **pela unidade de origem** (ADR 3.4.0007 §3).
        origin = self._employees.find_by_id(command.tenant_id, command.unit_id, command.employee_id)
        if origin is None:
            raise EmployeeNotFoundError(command.employee_id)
        # (2) Destino diferente da origem.
        if command.target_unit_id == origin.unit_id:
            raise SameUnitCopyError(command.target_unit_id)
        # (2b) As funções da origem valem no destino? (ADR 3.11.0002). Resolvidas
        # antes da construção e do gerador de id: cópia recusada não consome id.
        found = self._job_functions.find_all_by_ids(command.tenant_id, origin.job_function_ids)
        missing = origin.job_function_ids - {job_function.id for job_function in found}
        if missing:
            raise JobFunctionNotFoundError(sorted(missing)[0])
        require_enabled_in_unit(found, command.target_unit_id)
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
