"""A lei "nome inválido não toca o port", quantificada sobre o domínio inteiro.

**Por que este arquivo existe.** A lei já estava escrita — concept 3.2 §5.16, na
nota que fecha a tabela de precedência: *"a checagem mais barata que possa falhar
sozinha vem primeiro"*, e a validação de nome é local, não custa I/O e falha
sozinha. Mas ela tinha **um único representante**:
`test_criar_com_nome_vazio_nao_toca_o_port`, sobre `create_job_function`. Os
outros use cases que recebem nome nunca foram medidos, e o desvio de
`rename_job_function` — sondar unicidade **antes** de o domínio ver o nome —
sobreviveu à 3.2, à 3.3 e à 3.4 com a suíte verde, até virar **500** pelo HTTP
real na Stage 3.6 (ADR 3.6.0004).

É a família de defeito *"lei universal, representante estreito"*: nada aqui
descobre comportamento novo; o que muda é o **quantificador**. Por isso a lei é
parametrizada sobre o produto `use case x nome inválido`, e o domínio dos use
cases é **derivado** dos commands que carregam `name`, não listado.

**A conduta permitida é declarada por use case, e é exata.** Nem toda chamada ao
port é violação: `rename_*` tem de carregar o registro **antes** de qualquer
outra coisa (precedência de §5.16 — id inexistente vence tudo, para que a
resposta não confirme a existência de um nome a quem pediu por um id que não é
dele). O que a lei proíbe é a chamada que **carrega o nome** — `find_by_name` —
e a escrita. Asserir igualdade com a conduta permitida, em vez de "não contém
`find_by_name`", pega também uma escrita indevida e uma segunda leitura.

**`create_employee` é exceção documentada e NÃO entra na lei.** A tabela de §5.16
declara a ordem dele como *"(1) resolver o conjunto de funções → ausência; (2)
construir o `Employee`; (3) `add`"*, e a nota que fecha a tabela justifica a
inversão: a entidade **não pode** ser construída sem o conjunto resolvido, e
construir primeiro produziria `InvalidNameError` num pedido cuja falha real é
**referencial**, escondendo do gerente a causa que ele precisa ler. Daí
`JobFunctionNotFoundError` vencer o nome vazio. Asserir a lei sobre ele
**contradiria o concept** — por isso ele aparece aqui só como exclusão nomeada,
travada pela guarda de domínio abaixo.
"""

import dataclasses
from collections.abc import Callable
from decimal import Decimal
from typing import Final

import pytest

from restaurant_hub.features.staff.application.dtos import commands as commands_module
from restaurant_hub.features.staff.application.dtos.commands import (
    CreateEmployeeCommand,
    CreateJobFunctionCommand,
    RenameEmployeeCommand,
    RenameJobFunctionCommand,
)
from restaurant_hub.features.staff.application.use_cases.create_job_function import (
    CreateJobFunctionUseCase,
)
from restaurant_hub.features.staff.application.use_cases.rename_employee import (
    RenameEmployeeUseCase,
)
from restaurant_hub.features.staff.application.use_cases.rename_job_function import (
    RenameJobFunctionUseCase,
)
from restaurant_hub.features.staff.domain.entities.employee import Employee
from restaurant_hub.features.staff.domain.entities.job_function import JobFunction
from restaurant_hub.features.staff.domain.exceptions.errors import InvalidNameError
from restaurant_hub.features.staff.domain.value_objects.identifiers import (
    EmployeeId,
    JobFunctionId,
    TenantId,
    UnitId,
)
from restaurant_hub.features.staff.domain.value_objects.workload_profile import FixedSchedule
from tests.fakes.features.staff.in_memory_staff_store import StaffFakes, staff_repositories
from tests.fakes.features.staff.stub_access_guards import TEST_ACTOR
from tests.fakes.shared.fake_id_generator import FakeIdGenerator

pytestmark = pytest.mark.unit

_A = TenantId("tenant-a")
_U1 = UnitId("u1")
_F1 = JobFunctionId("f1")
_E1 = EmployeeId("e1")

# Os três nomes que o domínio recusa (3.1 + ADR 3.4.0003). O NUL entra **junto**
# com os dois vazios de propósito: o desvio de ordem é o mesmo nos três, e tratar
# só o NUL sugeriria que o defeito é do Postgres — ele não é. O NUL é apenas a
# espécie em que a consulta inútil vira 500 em vez de consulta inútil.
NOMES_INVALIDOS: Final = ("", "   ", "Ana\x00Souza")

# O use case que a nota de §5.16 isenta, com a razão. Nomeado aqui — e não
# esquecido — porque a guarda de domínio abaixo cobra que toda entrada nova seja
# classificada como coberta **ou** como exceção justificada.
COMMAND_EXCETUADO: Final = CreateEmployeeCommand

# Cardinalidades esperadas, nomeadas para que a asserção diga **o que** conta:
# quatro commands carregam `name`, um deles é a exceção documentada.
CASOS_ESPERADOS: Final = 3
NOMES_INVALIDOS_ESPERADOS: Final = 3


def _com_registros() -> StaffFakes:
    """Função e funcionário gravados — os alvos que os `rename_*` carregam."""
    fakes = staff_repositories()
    fakes.job_functions.add(JobFunction(id=_F1, tenant_id=_A, name="Cozinheiro"))
    fakes.employees.add(
        Employee(
            id=_E1,
            tenant_id=_A,
            unit_id=_U1,
            name="Maria",
            workload_profile=FixedSchedule(weekly_hours=Decimal("44")),
            shift_preference=None,
            job_function_ids=frozenset({_F1}),
            unavailabilities=(),
        )
    )
    return fakes


def _renomear_funcao(fakes: StaffFakes, nome: str) -> None:
    RenameJobFunctionUseCase(fakes.job_functions).execute(
        RenameJobFunctionCommand(actor=TEST_ACTOR, tenant_id=_A, job_function_id=_F1, name=nome)
    )


def _renomear_funcionario(fakes: StaffFakes, nome: str) -> None:
    RenameEmployeeUseCase(fakes.employees).execute(
        RenameEmployeeCommand(
            actor=TEST_ACTOR, tenant_id=_A, unit_id=_U1, employee_id=_E1, name=nome
        )
    )


def _criar_funcao(fakes: StaffFakes, nome: str) -> None:
    CreateJobFunctionUseCase(fakes.job_functions, FakeIdGenerator()).execute(
        CreateJobFunctionCommand(actor=TEST_ACTOR, tenant_id=_A, name=nome)
    )


@dataclasses.dataclass(frozen=True)
class CasoDaLei:
    """Um use case sob a lei, com a conduta que §5.16 lhe permite antes do nome."""

    command: type
    invocar: Callable[[StaffFakes, str], None]
    conduta_permitida: tuple[str, ...]


# A conduta permitida sai **linha a linha** da tabela de §5.16 (com a errata de
# 2026-08-29 na linha de `rename_job_function`), não da leitura do código: se
# saísse do código, a expectativa concordaria com qualquer ordem implementada.
CASOS: Final = (
    CasoDaLei(
        command=CreateJobFunctionCommand,
        invocar=_criar_funcao,
        # "(1) construir a entidade; (2) find_by_name; (3) add" — nada antes da
        # construção, logo nenhuma chamada.
        conduta_permitida=(),
    ),
    CasoDaLei(
        command=RenameJobFunctionCommand,
        invocar=_renomear_funcao,
        # "(1) carregar → NotFound; (2) transição → InvalidNameError; (3)
        # find_by_name; (4) update" — só o carregamento precede o nome.
        conduta_permitida=("job_functions.find_by_id",),
    ),
    CasoDaLei(
        command=RenameEmployeeCommand,
        invocar=_renomear_funcionario,
        # "(1) carregar → EmployeeNotFoundError; (2) transição → InvalidNameError;
        # (3) update" — idem.
        conduta_permitida=("employees.find_by_id",),
    ),
)


def _commands_com_nome() -> set[type]:
    """Os commands da 3.2 que carregam um campo `name` — o domínio, derivado."""
    return {
        objeto
        for objeto in vars(commands_module).values()
        if dataclasses.is_dataclass(objeto)
        and isinstance(objeto, type)
        and any(campo.name == "name" for campo in dataclasses.fields(objeto))
    }


def test_o_dominio_da_lei_cobre_todo_command_que_carrega_nome() -> None:
    """A guarda contra o representante estreito — e contra a varredura vazia.

    Um quinto command com `name` (um `RenameUnitCommand`, um
    `RenameJobFunctionInBulkCommand`) fica vermelho **aqui**, obrigando a
    classificá-lo: ou entra na lei, ou entra em `COMMAND_EXCETUADO` com a razão.
    Sem esta asserção, a lei continuaria universal no nome e estreita no domínio
    — que é exatamente como o defeito de `rename_job_function` sobreviveu a três
    Stages.

    A contagem dos casos é asserida junto porque `parametrize` sobre sequência
    vazia produz **zero** testes, e zero testes passam.
    """
    cobertos = {caso.command for caso in CASOS}

    assert cobertos | {COMMAND_EXCETUADO} == _commands_com_nome()
    assert COMMAND_EXCETUADO not in cobertos
    assert len(CASOS) == CASOS_ESPERADOS
    assert len(NOMES_INVALIDOS) == NOMES_INVALIDOS_ESPERADOS


@pytest.mark.parametrize("nome", NOMES_INVALIDOS, ids=repr)
@pytest.mark.parametrize("caso", CASOS, ids=lambda c: c.command.__name__)
def test_nome_invalido_nao_alcanca_nenhuma_chamada_que_o_carregue(
    caso: CasoDaLei, nome: str
) -> None:
    """O produto inteiro: 3 use cases x 3 nomes inválidos.

    A asserção é **igualdade** com a conduta permitida, não "não contém
    `find_by_name`": igualdade pega também um `update` indevido e uma segunda
    leitura, e não precisa ser reescrita quando o port ganhar um método novo.
    """
    fakes = _com_registros()
    antes = len(fakes.store.calls)

    with pytest.raises(InvalidNameError):
        caso.invocar(fakes, nome)

    assert fakes.store.calls[antes:] == list(caso.conduta_permitida)
