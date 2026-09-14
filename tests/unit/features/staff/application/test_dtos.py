"""Testes dos DTOs de fronteira da camada de aplicação do BC staff (concept §11).

Os DTOs são `frozen` por duas razões que estes testes travam separadamente:
**imutabilidade** (ninguém edita o command a meio caminho) e **igualdade por
valor** — é esta última que torna o `EmployeeResult` o alvo correto das
asserções "nenhum outro campo mudou" das Tasks 10 a 13. As entidades da 3.1 não
serviriam: elas comparam só por id.
"""

import ast
import dataclasses
import inspect
import pathlib
import typing
from datetime import datetime
from decimal import Decimal

import pytest

from restaurant_hub.features.staff.application import use_cases as pacote_use_cases
from restaurant_hub.features.staff.application.dtos import commands, queries, results
from restaurant_hub.features.staff.application.dtos.commands import (
    AssignJobFunctionsCommand,
    ChangeWorkloadProfileCommand,
    CopyEmployeeToUnitCommand,
    CreateEmployeeCommand,
    CreateJobFunctionCommand,
    CreateLoginForEmployeeCommand,
    DeactivateEmployeeCommand,
    DeclareShiftPreferenceCommand,
    DeleteEmployeeCommand,
    DeleteJobFunctionCommand,
    ReactivateEmployeeCommand,
    RegisterUnavailabilityCommand,
    RemoveUnavailabilityCommand,
    RenameEmployeeCommand,
    RenameJobFunctionCommand,
)
from restaurant_hub.features.staff.application.dtos.queries import (
    ListEmployeesQuery,
    ListJobFunctionsQuery,
)
from restaurant_hub.features.staff.application.dtos.results import (
    EmployeeLoginResult,
    EmployeeResult,
    JobFunctionResult,
)
from restaurant_hub.features.staff.application.ports.out.identity_gateway import LoginDelivery
from restaurant_hub.features.staff.application.use_cases._results import employee_result
from restaurant_hub.features.staff.domain.entities.employee import Employee
from restaurant_hub.features.staff.domain.entities.job_function import JobFunction
from restaurant_hub.features.staff.domain.value_objects.identifiers import (
    EmployeeId,
    JobFunctionId,
    TenantId,
    UnitId,
    UserId,
)
from restaurant_hub.features.staff.domain.value_objects.shift_preference import (
    DayPeriod,
    ShiftPreference,
)
from restaurant_hub.features.staff.domain.value_objects.unavailability_period import (
    UnavailabilityPeriod,
)
from restaurant_hub.features.staff.domain.value_objects.workload_profile import (
    FixedSchedule,
    OnDemand,
)

pytestmark = pytest.mark.unit

_TENANT = TenantId("t1")
_UNIDADE = UnitId("u1")
_FUNCAO = JobFunctionId("f1")
_FUNCIONARIO = EmployeeId("e1")
_FIXA = FixedSchedule(weekly_hours=Decimal("44"))
_PREFERENCIA = ShiftPreference(periods=frozenset({DayPeriod.NIGHT}))
_PERIODO = UnavailabilityPeriod(
    start=datetime(2026, 8, 3, 8, 0),
    end=datetime(2026, 8, 3, 12, 0),
)

_RESULTADO_BASE = EmployeeResult(
    id=_FUNCIONARIO,
    tenant_id=_TENANT,
    unit_id=_UNIDADE,
    name="Maria",
    workload_profile=_FIXA,
    shift_preference=_PREFERENCIA,
    job_function_ids=frozenset({_FUNCAO}),
    unavailabilities=(_PERIODO,),
    active=True,
)

# Uma instância de CADA um dos 18 DTOs — construir todos é critério de aceite,
# e é a lista que os testes de imutabilidade percorrem.
_TODOS_OS_DTOS: tuple[object, ...] = (
    CreateJobFunctionCommand(tenant_id=_TENANT, name="Cozinheiro"),
    RenameJobFunctionCommand(tenant_id=_TENANT, job_function_id=_FUNCAO, name="Chapeiro"),
    DeleteJobFunctionCommand(tenant_id=_TENANT, job_function_id=_FUNCAO),
    CreateEmployeeCommand(
        tenant_id=_TENANT,
        unit_id=_UNIDADE,
        name="Maria",
        workload_profile=_FIXA,
        job_function_ids=frozenset({_FUNCAO}),
    ),
    RenameEmployeeCommand(
        tenant_id=_TENANT, unit_id=_UNIDADE, employee_id=_FUNCIONARIO, name="Joana"
    ),
    AssignJobFunctionsCommand(
        tenant_id=_TENANT,
        unit_id=_UNIDADE,
        employee_id=_FUNCIONARIO,
        job_function_ids=frozenset({_FUNCAO}),
    ),
    ChangeWorkloadProfileCommand(
        tenant_id=_TENANT, unit_id=_UNIDADE, employee_id=_FUNCIONARIO, workload_profile=OnDemand()
    ),
    DeclareShiftPreferenceCommand(
        tenant_id=_TENANT, unit_id=_UNIDADE, employee_id=_FUNCIONARIO, shift_preference=_PREFERENCIA
    ),
    RegisterUnavailabilityCommand(
        tenant_id=_TENANT, unit_id=_UNIDADE, employee_id=_FUNCIONARIO, period=_PERIODO
    ),
    RemoveUnavailabilityCommand(
        tenant_id=_TENANT, unit_id=_UNIDADE, employee_id=_FUNCIONARIO, period=_PERIODO
    ),
    DeactivateEmployeeCommand(tenant_id=_TENANT, unit_id=_UNIDADE, employee_id=_FUNCIONARIO),
    ReactivateEmployeeCommand(tenant_id=_TENANT, unit_id=_UNIDADE, employee_id=_FUNCIONARIO),
    DeleteEmployeeCommand(tenant_id=_TENANT, unit_id=_UNIDADE, employee_id=_FUNCIONARIO),
    CopyEmployeeToUnitCommand(
        tenant_id=_TENANT, unit_id=_UNIDADE, employee_id=_FUNCIONARIO, target_unit_id=UnitId("u2")
    ),
    CreateLoginForEmployeeCommand(
        tenant_id=_TENANT,
        unit_id=_UNIDADE,
        employee_id=_FUNCIONARIO,
        email="maria@cantina.com",
        delivery=LoginDelivery.LINK,
    ),
    ListJobFunctionsQuery(tenant_id=_TENANT),
    ListEmployeesQuery(tenant_id=_TENANT, unit_id=_UNIDADE),
    JobFunctionResult(id=_FUNCAO, tenant_id=_TENANT, name="Cozinheiro"),
    _RESULTADO_BASE,
    EmployeeLoginResult(employee=_RESULTADO_BASE, setup_link="https://x/definir-senha?token=t"),
)


# 14 + 2 + 2 até a 3.4; a Stage 3.5 acrescenta `CreateLoginForEmployeeCommand` e
# `EmployeeLoginResult` (concept 3.5 §4).
_DTOS_ESPERADOS = 15 + 2 + 3  # commands + queries + results (concept §4)


def _dtos_declarados() -> set[type]:
    """Todas as classes declaradas nos três módulos de DTO.

    O filtro é **só** por módulo de origem, deliberadamente — mesma disciplina
    do `_application_error_classes()` do `test_errors.py`. Filtrar também por
    `dataclasses.is_dataclass` pareceria mais preciso e seria um falso verde: um
    command declarado como classe comum simplesmente não entraria na lista, e a
    suíte passaria — enquanto ele seria mutável na prática. Ser dataclass
    `frozen` é **asserção**, não filtro.
    """
    declaradas: set[type] = set()
    for modulo in (commands, queries, results):
        declaradas |= {
            obj
            for _, obj in inspect.getmembers(modulo, inspect.isclass)
            if obj.__module__ == modulo.__name__
        }
    return declaradas


def test_a_lista_de_dtos_cobre_todos_os_declarados_nos_tres_modulos() -> None:
    """A tupla `_TODOS_OS_DTOS` **é** o módulo, não uma amostra dele.

    Sem esta asserção a tupla é literal e ninguém a confronta com a realidade:
    um 19º command **sem `frozen`** acrescentado a `commands.py` escaparia das
    três guardas de uma vez (contagem, imutabilidade e igualdade por valor),
    porque nenhuma delas o enxergaria. É a mesma falha que o
    `test_errors.py` fechou na partição "404 vs. não-404".
    """
    assert {type(dto) for dto in _TODOS_OS_DTOS} == _dtos_declarados()


def test_a_stage_declara_exatamente_os_dtos_do_concept() -> None:
    """Guarda a contagem do concept §4: DTO novo ou removido força revisão."""
    assert len(_TODOS_OS_DTOS) == _DTOS_ESPERADOS
    # Nenhum DTO repetido na lista: N entradas de N tipos distintos.
    assert len({type(dto) for dto in _TODOS_OS_DTOS}) == _DTOS_ESPERADOS


@pytest.mark.parametrize(
    "dto_class",
    sorted(_dtos_declarados(), key=lambda cls: cls.__name__),
    ids=lambda cls: cls.__name__,
)
def test_todo_dto_declarado_e_dataclass_frozen(dto_class: type) -> None:
    """A checagem que o filtro por módulo (e não por `is_dataclass`) torna possível.

    Um DTO que nasça sem `@dataclass(frozen=True)` perde as duas propriedades de
    que a camada depende — imutabilidade e igualdade por valor — e falha **aqui**,
    em vez de ser silenciosamente ignorado pela suíte.
    """
    assert dataclasses.is_dataclass(dto_class), f"{dto_class.__name__} não é dataclass"
    assert dto_class.__dataclass_params__.frozen, f"{dto_class.__name__} não é frozen"  # type: ignore[attr-defined]


@pytest.mark.parametrize("dto", _TODOS_OS_DTOS, ids=lambda dto: type(dto).__name__)
def test_todo_dto_e_frozen(dto: object) -> None:
    """Command editado a meio caminho seria um contrato que muda sob o use case."""
    primeiro_campo = dataclasses.fields(dto)[0].name  # type: ignore[arg-type]
    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(dto, primeiro_campo, "outro")


@pytest.mark.parametrize("dto", _TODOS_OS_DTOS, ids=lambda dto: type(dto).__name__)
def test_todo_dto_tem_igualdade_por_valor(dto: object) -> None:
    """`frozen=True` gera `__eq__` por valor — o oposto das entidades da 3.1."""
    assert dataclasses.replace(dto) == dto  # type: ignore[type-var]


def test_criar_funcionario_sem_preferencia_usa_o_default_none() -> None:
    """`None` = sem preferência declarada (ADR 3.1.0004) — o default do cadastro novo."""
    comando = CreateEmployeeCommand(
        tenant_id=_TENANT,
        unit_id=_UNIDADE,
        name="Maria",
        workload_profile=_FIXA,
        job_function_ids=frozenset({_FUNCAO}),
    )
    assert comando.shift_preference is None


def test_declarar_preferencia_nao_tem_default() -> None:
    """Aqui `None` significa "LIMPE", não "não mexa" — por isso é obrigatório.

    Um default silencioso faria `DeclareShiftPreferenceCommand(tenant, id)`
    limpar a preferência sem que ninguém tivesse pedido — exatamente a
    ambiguidade que o ADR 3.2.0004 evitou ao recusar o update parcial.
    """
    campos = {campo.name: campo for campo in dataclasses.fields(DeclareShiftPreferenceCommand)}
    assert campos["shift_preference"].default is dataclasses.MISSING


def test_listagem_de_funcionarios_esconde_inativos_por_default() -> None:
    """Incluir desligado é opt-in explícito (L-E6)."""
    assert ListEmployeesQuery(tenant_id=_TENANT, unit_id=_UNIDADE).include_inactive is False
    incluindo = ListEmployeesQuery(tenant_id=_TENANT, unit_id=_UNIDADE, include_inactive=True)
    assert incluindo.include_inactive is True


def test_results_iguais_campo_a_campo_sao_iguais() -> None:
    """A base da asserção "nenhum outro campo mudou" das Tasks 10 a 13."""
    gemeo = EmployeeResult(
        id=_FUNCIONARIO,
        tenant_id=_TENANT,
        unit_id=_UNIDADE,
        name="Maria",
        workload_profile=FixedSchedule(weekly_hours=Decimal("44")),
        shift_preference=ShiftPreference(periods=frozenset({DayPeriod.NIGHT})),
        job_function_ids=frozenset({JobFunctionId("f1")}),
        unavailabilities=(_PERIODO,),
        active=True,
    )
    # Instâncias distintas, VOs reconstruídos: a igualdade é por valor mesmo.
    assert gemeo is not _RESULTADO_BASE
    assert gemeo == _RESULTADO_BASE


@pytest.mark.parametrize(
    ("campo", "outro_valor"),
    [
        ("id", EmployeeId("e2")),
        ("tenant_id", TenantId("t2")),
        ("unit_id", UnitId("u2")),
        ("name", "Joana"),
        ("workload_profile", OnDemand()),
        ("shift_preference", None),
        ("job_function_ids", frozenset({JobFunctionId("f2")})),
        ("unavailabilities", ()),
        ("active", False),
    ],
)
def test_divergir_em_um_unico_campo_torna_os_results_diferentes(
    campo: str, outro_valor: object
) -> None:
    """Um caso por campo, de propósito.

    Testar só um campo daria falso verde para os outros oito: é exatamente
    assim que uma comparação de result deixaria passar a mudança de um campo
    que o use case não deveria ter tocado.
    """
    divergente = dataclasses.replace(_RESULTADO_BASE, **{campo: outro_valor})
    assert divergente != _RESULTADO_BASE


def test_result_de_funcionario_tem_o_estado_de_ciclo_de_vida() -> None:
    """Sem `active` no result, a listagem não teria como distinguir o desligado."""
    nomes = {campo.name for campo in dataclasses.fields(EmployeeResult)}
    assert "active" in nomes


# --- vínculo de login (Stage 3.5) --------------------------------------------
#
# O guarda vacuoso da 3.2 (`test_nenhum_result_carrega_vinculo_de_login`) cumpriu
# o papel: falhou quando o campo chegou, e foi **substituído** por estes três. A
# decisão que ele protegia — a cópia não carrega o vínculo — agora é testada com
# conteúdo em `test_copy_employee_to_unit.py` (CA04).

_PASTA_DE_USE_CASES = pathlib.Path(pacote_use_cases.__file__).parent
_MODULO_DO_MAPPER = "_results"
# Contagem **transcrita** dos módulos que consomem `employee_result`: os 11 use
# cases que devolvem funcionário mais `create_login_for_employee` (3.5). Sem ela
# a varredura por AST abaixo passaria sobre uma pasta vazia.
_TOTAL_DE_CONSUMIDORES_DO_MAPPER = 12


def test_employee_result_carrega_o_vinculo_de_login() -> None:
    """`user_id` existe, é anotado `UserId | None` e nasce `None` (concept 3.5 §4)."""
    campos = {campo.name: campo for campo in dataclasses.fields(EmployeeResult)}
    assert "user_id" in campos
    assert campos["user_id"].type == UserId | None
    assert campos["user_id"].default is None
    assert _RESULTADO_BASE.user_id is None
    assert JobFunctionResult.__dataclass_fields__.keys() == {"id", "tenant_id", "name"}


def test_o_mapper_copia_todos_os_campos_inclusive_o_login() -> None:
    """A propriedade nuclear de D6, travada como **lei sobre todos os campos**.

    Achado 1 do Checkpoint C do bloco 1: sem este teste, `employee_result`
    omitindo `user_id` sobrevivia à suíte inteira — o default `None` mascarava a
    omissão, que é exatamente o modo de falha que o mapper existe para eliminar.
    A asserção itera `dataclasses.fields(EmployeeResult)`: um campo novo que o
    mapper esqueça reprova aqui sem que ninguém precise lembrar de estendê-lo.
    """
    vinculado = Employee(
        id=_FUNCIONARIO,
        tenant_id=_TENANT,
        unit_id=_UNIDADE,
        name="Maria",
        workload_profile=_FIXA,
        shift_preference=_PREFERENCIA,
        job_function_ids=frozenset({_FUNCAO}),
        unavailabilities=(_PERIODO,),
        active=False,
        user_id=UserId("login-1"),
    )

    resultado = employee_result(vinculado)

    for campo in dataclasses.fields(EmployeeResult):
        assert getattr(resultado, campo.name) == getattr(vinculado, campo.name), campo.name
    assert resultado.user_id == UserId("login-1")


def test_user_id_divergente_torna_os_results_diferentes() -> None:
    """Igualdade por valor alcança o campo novo — é a asserção de CA13/CA04."""
    com_login = dataclasses.replace(_RESULTADO_BASE, user_id=UserId("login-1"))
    assert com_login != _RESULTADO_BASE
    assert dataclasses.replace(com_login, user_id=None) == _RESULTADO_BASE


def _chamadas_a_employee_result(arvore: ast.AST) -> list[int]:
    """Toda `Call` cujo alvo se chama `EmployeeResult` — por nome **ou** por atributo.

    `results.EmployeeResult(...)` é `ast.Attribute`; só olhar `ast.Name` deixaria
    essa forma passar (achado 2 do Checkpoint C do bloco 1). Um alias
    (`import EmployeeResult as R; R(...)`) continua fora do alcance — e não é
    pego por mypy, que aceita alias como Python legítimo; o que o barra é a
    convenção de import direto por nome do repo e o grep de CA06 no gate.
    """
    return [
        no.lineno
        for no in ast.walk(arvore)
        if isinstance(no, ast.Call)
        and (
            (isinstance(no.func, ast.Name) and no.func.id == "EmployeeResult")
            or (isinstance(no.func, ast.Attribute) and no.func.attr == "EmployeeResult")
        )
    ]


def test_ca06_nenhum_use_case_constroi_employee_result_diretamente() -> None:
    """O único sítio é `_results.employee_result` (concept 3.5 D6, CA06).

    Varredura por AST, não por grep de texto: um `EmployeeResult(` dentro de
    docstring não conta. O que se procura é a **chamada**, por nome ou por
    atributo; o alias de import é o limite declarado (ver o helper).
    """
    culpados: dict[str, list[int]] = {}
    consumidores: list[str] = []
    for arquivo in sorted(_PASTA_DE_USE_CASES.glob("*.py")):
        if arquivo.stem in ("__init__", _MODULO_DO_MAPPER):
            continue
        arvore = ast.parse(arquivo.read_text(encoding="utf-8"))
        linhas = _chamadas_a_employee_result(arvore)
        if linhas:
            culpados[arquivo.stem] = linhas
        if any(
            isinstance(no, ast.ImportFrom)
            and (no.module or "").endswith(_MODULO_DO_MAPPER)
            and any(alias.name == "employee_result" for alias in no.names)
            for no in ast.walk(arvore)
        ):
            consumidores.append(arquivo.stem)

    assert culpados == {}, f"EmployeeResult construído fora do mapper: {culpados}"
    assert len(consumidores) == _TOTAL_DE_CONSUMIDORES_DO_MAPPER, sorted(consumidores)


def _tipos_folha(anotacao: object) -> set[object]:
    """Achata uma anotação nos seus tipos-**folha**, descartando os contêineres.

    `frozenset[JobFunctionId]` devolve `{JobFunctionId}`, não
    `{frozenset, JobFunctionId}`: quando há argumentos, a origem é substituída
    por eles. É o que se quer — a guarda pergunta "que tipo **trafega** neste
    campo", e `frozenset`/`tuple` são embalagem, não carga.

    A checagem precisa ser **estrutural**, não textual: `EmployeeId` contém a
    substring "Employee", então um `"Employee" not in str(anotacao)` reprovaria
    o id tipado e daria a impressão de estar guardando algo.
    """
    argumentos = typing.get_args(anotacao)
    if not argumentos:
        return {anotacao}
    folhas: set[object] = set()
    for argumento in argumentos:
        folhas |= _tipos_folha(argumento)
    return folhas


@pytest.mark.parametrize(
    "dto_class",
    sorted(_dtos_declarados(), key=lambda cls: cls.__name__),
    ids=lambda cls: cls.__name__,
)
def test_nenhum_campo_de_dto_e_anotado_com_entidade(dto_class: type) -> None:
    """Use case devolve DTO, nunca entidade (CLAUDE.md nota 6; LAYOUT §7).

    VO de domínio pode trafegar (`WorkloadProfile`, `ShiftPreference`,
    `UnavailabilityPeriod`); entidade, não — ela tem identidade e ciclo de vida,
    e vazá-la daria ao adapter da 3.4 acesso às transições do agregado.

    Roda sobre os **18** DTOs, não só sobre os dois results: a docstring de
    `commands.py` afirma a garantia para os commands ("nem `Employee` nem
    `JobFunction` aparecem em nenhum campo"), e afirmação de docstring sem teste
    é justamente o que a memória do projeto chama de conformidade não verificada.
    Um command que recebesse a entidade seria o caminho mais curto para o adapter
    da 3.4 montar o agregado por fora do domínio.
    """
    anotacoes = typing.get_type_hints(dto_class)
    for nome, anotacao in anotacoes.items():
        folhas = _tipos_folha(anotacao)
        assert Employee not in folhas, f"{dto_class.__name__}.{nome} expõe a entidade Employee"
        assert JobFunction not in folhas, (
            f"{dto_class.__name__}.{nome} expõe a entidade JobFunction"
        )


# ---------------------------------------------------------------------------
# CA11, metade "commands" — a unidade entra no pedido
# ---------------------------------------------------------------------------

_COMMANDS_DE_REGISTRO_EXISTENTE = (
    RenameEmployeeCommand,
    AssignJobFunctionsCommand,
    ChangeWorkloadProfileCommand,
    DeclareShiftPreferenceCommand,
    RegisterUnavailabilityCommand,
    RemoveUnavailabilityCommand,
    DeactivateEmployeeCommand,
    ReactivateEmployeeCommand,
    DeleteEmployeeCommand,
    CopyEmployeeToUnitCommand,
    CreateLoginForEmployeeCommand,
)
# Contagem do ADR 3.4.0007 §3, na mesma forma do `_DTOS_ESPERADOS` da §4 — dez
# até a 3.4; o 11º é o command de R17 (3.5), que também endereça o registro.
_COMMANDS_DE_REGISTRO_EXISTENTE_ESPERADOS = 11


def test_todo_command_de_registro_existente_esta_na_lista() -> None:
    """Guarda a contagem do ADR 3.4.0007 §3, como `_DTOS_ESPERADOS` guarda a §4.

    Um 11º command de registro existente que nascesse sem `unit_id` escaparia da
    parametrizacao abaixo se a lista fosse literal e ninguem a confrontasse.
    """
    dos_dez = set(_COMMANDS_DE_REGISTRO_EXISTENTE)
    com_employee_id = {
        cls
        for cls in _dtos_declarados()
        if any(campo.name == "employee_id" for campo in dataclasses.fields(cls))
        and cls.__module__ == commands.__name__
    }
    assert dos_dez == com_employee_id
    assert len(dos_dez) == _COMMANDS_DE_REGISTRO_EXISTENTE_ESPERADOS


@pytest.mark.parametrize(
    "command_class", _COMMANDS_DE_REGISTRO_EXISTENTE, ids=lambda cls: cls.__name__
)
def test_a_unidade_e_obrigatoria_e_sem_default(command_class: type) -> None:
    """CA11 — `unit_id` existe e **nao** tem default.

    Um `unit_id: UnitId | None = None` faria o campo ser esquecivel, e omitir
    viraria caminho de escalada — a propriedade que o ADR 3.2.0002 ja comprou
    para o tenant. Sem default, construir sem ele e `TypeError` na coleta.
    """
    campos = {campo.name: campo for campo in dataclasses.fields(command_class)}

    assert "unit_id" in campos, f"{command_class.__name__} nao carrega a unidade"
    assert campos["unit_id"].default is dataclasses.MISSING
    assert campos["unit_id"].default_factory is dataclasses.MISSING


@pytest.mark.parametrize(
    "command_class", _COMMANDS_DE_REGISTRO_EXISTENTE, ids=lambda cls: cls.__name__
)
def test_construir_sem_a_unidade_e_type_error(command_class: type) -> None:
    """A obrigatoriedade e do sistema de tipos **e** do runtime.

    A assercao sobre `dataclasses.MISSING` prova a declaracao; esta prova o
    efeito. Sao coisas diferentes: um `__init__` escrito a mao poderia declarar
    o campo sem default e ainda assim aceitar a omissao.
    """
    argumentos: dict[str, object] = {
        "tenant_id": _TENANT,
        "employee_id": _FUNCIONARIO,
        "name": "Joana",
        "job_function_ids": frozenset({_FUNCAO}),
        "workload_profile": OnDemand(),
        "shift_preference": _PREFERENCIA,
        "period": _PERIODO,
        "target_unit_id": UnitId("u2"),
        "email": "maria@cantina.com",
        "delivery": LoginDelivery.LINK,
    }
    nomes = {campo.name for campo in dataclasses.fields(command_class)} - {"unit_id"}

    with pytest.raises(TypeError, match="unit_id"):
        command_class(**{nome: argumentos[nome] for nome in nomes})


def test_copiar_distingue_a_unidade_de_origem_da_de_destino() -> None:
    """O par em que confundir os dois campos produz a exfiltracao cross-unidade.

    `unit_id` e a ORIGEM — a unidade que endereca o registro a ser lido — e
    `target_unit_id` e o destino. Sao campos distintos e nao permutaveis: trocar
    um pelo outro copiaria o registro errado, ou leria de uma unidade a que o
    chamador nao tem acesso.
    """
    origem = UnitId("u-origem")
    destino = UnitId("u-destino")

    comando = CopyEmployeeToUnitCommand(
        tenant_id=_TENANT,
        unit_id=origem,
        employee_id=_FUNCIONARIO,
        target_unit_id=destino,
    )

    assert comando.unit_id == origem
    assert comando.target_unit_id == destino
    assert comando.unit_id != comando.target_unit_id


# ---------------------------------------------------------------------------
# Stage 3.5 — o segredo no result (CA05)
# ---------------------------------------------------------------------------

_PASTA_DE_STAFF = pathlib.Path(pacote_use_cases.__file__).parents[2]


def test_employee_login_result_nao_imprime_o_link() -> None:
    """`repr=False` e sem default: o canal decide **explicitamente** `None` ou o link."""
    campos = {campo.name: campo for campo in dataclasses.fields(EmployeeLoginResult)}
    assert campos["setup_link"].repr is False
    assert campos["setup_link"].default is dataclasses.MISSING

    com_link = EmployeeLoginResult(
        employee=_RESULTADO_BASE, setup_link="https://x/definir-senha?token=s3gr3d0"
    )
    assert "s3gr3d0" not in repr(com_link)
    assert "definir-senha" not in repr(com_link)
    assert com_link.setup_link is not None


def test_create_login_command_nao_tem_default_para_o_canal() -> None:
    """Sem default: quem pede decide o canal — e o canal decide o prazo do link."""
    campos = {campo.name: campo for campo in dataclasses.fields(CreateLoginForEmployeeCommand)}
    assert campos["delivery"].default is dataclasses.MISSING
    assert campos["email"].default is dataclasses.MISSING


def _nomes_alcancados(no: ast.AST) -> set[str]:
    return {interno.id for interno in ast.walk(no) if isinstance(interno, ast.Name)} | {
        interno.attr for interno in ast.walk(no) if isinstance(interno, ast.Attribute)
    }


def test_ca05_nenhuma_excecao_de_staff_recebe_o_setup_link() -> None:
    """Varredura por AST de `features/staff/`: nenhum `raise` alcança `setup_link`.

    A exceção é o caminho pelo qual um segredo vira corpo de resposta ou linha de
    log sem que ninguém o tenha escrito de propósito: `LoginEmailAlreadyInUseError(email)`
    carrega o e-mail **porque** o e-mail é diagnóstico legítimo; um
    `SomethingError(setup_link)` faria o mesmo com o segredo. A varredura olha o
    que cada `raise` **alcança** — argumentos e o que eles derivam —, e reprova
    tanto `raise X(setup_link)` quanto `raise X(provisioned.setup_link)` e
    `link = provisioned.setup_link; raise X(link)` (pelo nome `link` derivado, o
    teste abaixo o cobre por caso plantado).
    """
    culpados: dict[str, list[int]] = {}
    for arquivo in sorted(_PASTA_DE_STAFF.rglob("*.py")):
        arvore = ast.parse(arquivo.read_text(encoding="utf-8"), filename=str(arquivo))
        for funcao in ast.walk(arvore):
            if not isinstance(funcao, ast.FunctionDef):
                continue
            derivados = {"setup_link"}
            for no in ast.walk(funcao):
                if isinstance(no, ast.Assign) and _nomes_alcancados(no.value) & derivados:
                    derivados |= {alvo.id for alvo in no.targets if isinstance(alvo, ast.Name)}
            for no in ast.walk(funcao):
                if (
                    isinstance(no, ast.Raise)
                    and no.exc is not None
                    and _nomes_alcancados(no.exc) & derivados
                ):
                    culpados.setdefault(str(arquivo.relative_to(_PASTA_DE_STAFF)), []).append(
                        no.lineno
                    )

    assert culpados == {}, f"`raise` alcançando o setup_link em staff: {culpados}"


def test_o_detector_de_ca05_reprova_os_tres_casos_plantados() -> None:
    """Guarda que nunca viu positivo não é guarda: direto, por atributo e por derivado."""
    plantados = (
        "def f(setup_link):\n    raise ValueError(setup_link)\n",
        "def f(p):\n    raise ValueError(p.setup_link)\n",
        "def f(p):\n    link = p.setup_link\n    raise ValueError(link)\n",
    )
    for codigo in plantados:
        funcao = ast.parse(codigo).body[0]
        assert isinstance(funcao, ast.FunctionDef)
        derivados = {"setup_link"}
        for no in ast.walk(funcao):
            if isinstance(no, ast.Assign) and _nomes_alcancados(no.value) & derivados:
                derivados |= {alvo.id for alvo in no.targets if isinstance(alvo, ast.Name)}
        alcancou = any(
            isinstance(no, ast.Raise)
            and no.exc is not None
            and bool(_nomes_alcancados(no.exc) & derivados)
            for no in ast.walk(funcao)
        )
        assert alcancou, codigo
