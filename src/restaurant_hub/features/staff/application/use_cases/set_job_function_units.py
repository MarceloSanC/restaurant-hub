"""Use case: substituir as unidades em que uma função de trabalho vale.

A função continua do restaurante; o que muda é **onde** ela está habilitada
(Stage 3.11, ADR 3.11.0001 §5). O command traz o estado final desejado — todas as
unidades, ou um conjunto —, não um delta: mesma forma do `assign_job_functions`
(ADR 3.1.0006).

**Quem pode: alcance sobre o que muda.** Cada unidade acrescentada e cada unidade
removida é um alvo de `manage_job_functions`; passar de ou para "todas as
unidades" exige `manage_tenant`. É o que deixa o gerente habilitar na sua unidade
uma função que já existe em outra — o nome é único no restaurante, então criar uma
homônima não é caminho —, sem alcançar a unidade alheia, e o que o impede de tirar
a função de uma unidade que não enxerga.

**A ordem é o contrato, com uma exceção declarada ao ADR 3.7.0001 §4.** O que muda
depende da habilitação **gravada**, então a função é lida *antes* de a diferença
ser autorizada: tenant → existência → diferença → transição → guarda → escrita. A
leitura não é oráculo — o que ela revela (onde a função vale) é o que o catálogo já
mostra a quem passou na autorização do tenant, que vem primeiro.

**A guarda** (ADR 3.11.0002): um registro de funcionário só detém função habilitada
na sua unidade. Estreitar a habilitação enquanto algum registro — ativo ou
desligado — de uma unidade que sairia detém a função é recusado, com o mesmo erro
da remoção guardada. É *check-then-act*: nenhuma constraint fecha a corrida com uma
atribuição concorrente (limite declarado no ADR).

**A escrita é condicional à habilitação lida** (issue #206). A diferença é
autorizada contra o que foi lido; se outra alteração de unidades comitar entre a
leitura e a escrita, o port recusa com `JobFunctionEnablementChangedError` em vez
de gravar o conjunto deste pedido por cima — o que tiraria, por um ator sem
alcance, uma unidade que só o outro escritor alcançava (ADR 3.11.0001 §5, nota de
fechamento). Quem recebe a recusa relê e reenvia.
"""

from restaurant_hub.features.staff.application.dtos.commands import SetJobFunctionUnitsCommand
from restaurant_hub.features.staff.application.dtos.results import (
    JobFunctionResult,
    to_job_function_result,
)
from restaurant_hub.features.staff.application.errors import (
    JobFunctionInUseError,
    JobFunctionNotFoundError,
)
from restaurant_hub.features.staff.application.ports.out.access_guard import (
    PERMISSION_MANAGE_JOB_FUNCTIONS,
    AccessGuard,
)
from restaurant_hub.features.staff.application.ports.out.employee_repository import (
    EmployeeRepository,
)
from restaurant_hub.features.staff.application.ports.out.job_function_repository import (
    JobFunctionRepository,
)
from restaurant_hub.features.staff.application.use_cases._unit_enablement import (
    authorize_enablement_change,
    named_units,
    to_unit_enablement,
)


class SetJobFunctionUnitsUseCase:
    """Substitui a habilitação por unidade de uma função do tenant."""

    def __init__(
        self,
        job_functions: JobFunctionRepository,
        employees: EmployeeRepository,
        guard: AccessGuard,
    ) -> None:
        self._job_functions = job_functions
        self._employees = employees
        self._guard = guard

    def execute(self, command: SetJobFunctionUnitsCommand) -> JobFunctionResult:
        """Substitui as unidades da função.

        Raises:
            JobFunctionNotFoundError: id inexistente **no tenant** — antes de
                qualquer autorização de unidade.
            InvalidUnitEnablementError: `unit_ids` vazio ou com id em branco
                (domínio, 3.11).
            JobFunctionInUseError: algum registro (ativo ou desligado) de uma
                unidade que deixaria de ser coberta detém a função.
            JobFunctionEnablementChangedError: a habilitação gravada mudou entre a
                leitura e a escrita (L-JF7 revisada, issue #206); nada é gravado.
        """
        # (0) Autorização do alvo do command, antes de qualquer outra instrução
        # (ADR 3.7.0001 §4). A exceção do guard sobe crua (L-AG2).
        self._guard.authorize(
            command.actor, PERMISSION_MANAGE_JOB_FUNCTIONS, tenant_id=command.tenant_id
        )
        # (1) Existência no tenant — é dela que sai a habilitação atual.
        job_function = self._job_functions.find_by_id(command.tenant_id, command.job_function_id)
        if job_function is None:
            raise JobFunctionNotFoundError(command.job_function_id)
        # (2) Alcance sobre o que muda (exceção declarada: depois da leitura).
        current = job_function.unit_enablement
        authorize_enablement_change(
            self._guard,
            command.actor,
            command.tenant_id,
            old=named_units(current),
            new=command.unit_ids,
        )
        # (3) Transição: o domínio recusa a habilitação vazia aqui, antes do port.
        enablement = to_unit_enablement(command.unit_ids)
        changed = job_function.with_enablement(enablement)
        # (4) Guarda: nenhuma unidade que **deixa de ser coberta** pode ter registro
        # detendo a função. "Todas" cobre tudo — não há o que consultar. A pergunta
        # é sobre o que esta mudança tira (coberta antes, não depois), e não sobre
        # toda unidade fora da habilitação nova: um registro que a corrida declarada
        # no ADR 3.11.0002 deixou fora de qualquer habilitação não pode travar um
        # alargamento que nem toca a unidade dele.
        if not enablement.all_units:
            holding = self._employees.list_units_referencing_job_function(
                command.tenant_id, command.job_function_id
            )
            if any(
                current.covers(unit_id) and not enablement.covers(unit_id) for unit_id in holding
            ):
                raise JobFunctionInUseError(command.job_function_id)
        # (5) Escrita — só a habilitação (L-JF7); o nome não é regravado. Condicional
        # à habilitação **lida** (issue #206): a diferença foi autorizada contra
        # `current`, e se outra alteração a mudou desde a leitura o port recusa com
        # `JobFunctionEnablementChangedError` em vez de gravar por cima.
        self._job_functions.update_enablement(changed, expected=current)
        return to_job_function_result(changed)
