"""Guardas mecânicas da camada application do BC staff (Task 13).

Estes testes não exercitam comportamento: eles **inspecionam a forma** do pacote
`use_cases` e dos DTOs. Existem porque as duas regras que protegem são do tipo
que ninguém quebra de propósito — quebra-se ao acrescentar um arquivo meses
depois, e nenhum teste de comportamento repara.

1. **ADR 3.2.0005** — a função de trabalho não tem ciclo de vida. A guarda é
   contra a **reintrodução** do estado que o sponsor removeu: um
   `deactivate_job_function.py` novo, um `include_inactive` numa query de
   função, um campo `active` no `JobFunctionResult`.
2. **CLAUDE.md nota 6 / LAYOUT §7** — use case devolve DTO, nunca entidade.
"""

import dataclasses
import importlib
import inspect
import pkgutil
import typing

import pytest

from restaurant_hub.features.staff.application import use_cases as pacote_use_cases
from restaurant_hub.features.staff.application.dtos import commands, queries
from restaurant_hub.features.staff.application.dtos.results import (
    EmployeeLoginResult,
    EmployeeResult,
    JobFunctionResult,
)
from restaurant_hub.features.staff.domain.entities.employee import Employee
from restaurant_hub.features.staff.domain.entities.job_function import JobFunction

pytestmark = pytest.mark.unit

# 16 até a 3.4; a Stage 3.5 acrescenta `create_login_for_employee` (R17).
_USE_CASES_ESPERADOS = 17


def _modulos_de_use_case() -> list[str]:
    return sorted(
        modulo.name
        for modulo in pkgutil.iter_modules(pacote_use_cases.__path__)
        if not modulo.name.startswith("_")
    )


def _classes_de_use_case() -> list[type]:
    """Toda classe `*UseCase` declarada no pacote."""
    encontradas: list[type] = []
    for nome in _modulos_de_use_case():
        modulo = importlib.import_module(f"{pacote_use_cases.__name__}.{nome}")
        encontradas.extend(
            obj
            for _, obj in inspect.getmembers(modulo, inspect.isclass)
            if obj.__module__ == modulo.__name__ and obj.__name__.endswith("UseCase")
        )
    return encontradas


def test_o_pacote_tem_exatamente_os_use_cases_declarados() -> None:
    """Um arquivo por use case (LAYOUT §7), e a contagem do concept §4.

    A lista literal é o ponto: use case novo ou removido força revisão
    consciente, em vez de entrar de carona.
    """
    assert _modulos_de_use_case() == [
        "assign_job_functions",
        "change_workload_profile",
        "copy_employee_to_unit",
        "create_employee",
        "create_job_function",
        "create_login_for_employee",
        "deactivate_employee",
        "declare_shift_preference",
        "delete_employee",
        "delete_job_function",
        "list_employees",
        "list_job_functions",
        "reactivate_employee",
        "register_unavailability",
        "remove_unavailability",
        "rename_employee",
        "rename_job_function",
    ]
    assert len(_classes_de_use_case()) == _USE_CASES_ESPERADOS


# --- guarda 1: a função de trabalho não tem ciclo de vida (ADR 3.2.0005) -----


def test_nao_existe_use_case_de_ativacao_de_funcao() -> None:
    """`deactivate_employee` existe; `deactivate_job_function` **não pode** existir.

    A checagem é sobre módulos que combinem o verbo de ciclo de vida com o
    substantivo `job_function` — desativar **funcionário** é legítimo
    (ADR 3.2.0006) e não pode ser pego por engano.
    """
    for nome in _modulos_de_use_case():
        combina_verbo = "activate" in nome or "deactivate" in nome
        assert not (combina_verbo and "job_function" in nome), (
            f"{nome}: a função de trabalho não tem ciclo de vida (ADR 3.2.0005)"
        )


def test_nenhum_dto_de_funcao_carrega_estado() -> None:
    """Nem o result, nem os commands, nem a query de função têm `active`.

    Cobre os quatro pontos por onde o estado voltaria: campo de result, campo
    de command, parâmetro de query e flag de listagem.
    """
    assert "active" not in {campo.name for campo in dataclasses.fields(JobFunctionResult)}

    for modulo in (commands, queries):
        for _, classe in inspect.getmembers(modulo, inspect.isclass):
            if classe.__module__ != modulo.__name__ or "JobFunction" not in classe.__name__:
                continue
            nomes = {campo.name for campo in dataclasses.fields(classe)}
            assert "active" not in nomes, f"{classe.__name__} reintroduz estado na função"
            assert "include_inactive" not in nomes, (
                f"{classe.__name__} reintroduz filtro de estado na função"
            )


def test_a_listagem_de_funcoes_nao_tem_filtro_de_estado() -> None:
    """`ListEmployeesQuery` tem `include_inactive`; `ListJobFunctionsQuery` não.

    O contraste é o teste: a flag existe no lugar onde há estado a filtrar, e
    não existe onde não há.
    """
    de_funcao = {campo.name for campo in dataclasses.fields(queries.ListJobFunctionsQuery)}
    de_funcionario = {campo.name for campo in dataclasses.fields(queries.ListEmployeesQuery)}
    assert "include_inactive" not in de_funcao
    assert "include_inactive" in de_funcionario


# --- guarda 2: use case devolve DTO, nunca entidade --------------------------


def _tipos_folha(anotacao: object) -> set[object]:
    """Achata a anotação nos seus tipos-folha (ver `test_dtos.py`)."""
    argumentos = typing.get_args(anotacao)
    if not argumentos:
        return {anotacao}
    folhas: set[object] = set()
    for argumento in argumentos:
        folhas |= _tipos_folha(argumento)
    return folhas


@pytest.mark.parametrize("use_case", _classes_de_use_case(), ids=lambda classe: classe.__name__)
def test_nenhum_use_case_devolve_entidade(use_case: type) -> None:
    """CLAUDE.md nota 6: DTO para fora, sempre.

    Vazar a entidade daria ao adapter da 3.4 acesso às **transições** do
    agregado — ele poderia chamar `deactivate()` direto e gravar por um caminho
    que nenhum use case controla.
    """
    anotacoes = typing.get_type_hints(use_case.execute)
    retorno = anotacoes.get("return")
    folhas = _tipos_folha(retorno)
    assert Employee not in folhas, f"{use_case.__name__} devolve a entidade Employee"
    assert JobFunction not in folhas, f"{use_case.__name__} devolve a entidade JobFunction"


@pytest.mark.parametrize("use_case", _classes_de_use_case(), ids=lambda classe: classe.__name__)
def test_todo_use_case_devolve_result_ou_none(use_case: type) -> None:
    """O contrapositivo: o retorno é um dos dois results, tupla deles, ou `None`.

    Sem esta metade, um use case que devolvesse `dict` ou um primitivo passaria
    na guarda acima — não é entidade, afinal — e a fronteira que a 3.4 herda
    deixaria de ser tipada sem que nada reclamasse.
    """
    retorno = typing.get_type_hints(use_case.execute).get("return")
    # `Ellipsis` entra na lista porque `tuple[JobFunctionResult, ...]` — a forma
    # declarada dos dois use cases de listagem — achata para
    # `{JobFunctionResult, Ellipsis}`. É parte da sintaxe da tupla homogênea,
    # não um tipo que trafega.
    # `EmployeeLoginResult` (3.5) embrulha um `EmployeeResult` e o link — é result,
    # não entidade; a varredura de entidade em `test_dtos.py` o cobre campo a campo.
    permitidos = {EmployeeResult, EmployeeLoginResult, JobFunctionResult, type(None), Ellipsis}
    assert _tipos_folha(retorno) <= permitidos, f"{use_case.__name__} devolve {retorno!r}"


def test_nenhum_use_case_recebe_clock() -> None:
    """Concept §7: o staff v1 não carimba tempo.

    Um `Clock` injetado "por precaução" criaria dependência sem consumidor — e
    a próxima Stage o encontraria e assumiria que há semântica temporal aqui.
    """
    for use_case in _classes_de_use_case():
        parametros = typing.get_type_hints(use_case.__init__)
        nomes = {tipo.__name__ for tipo in parametros.values() if hasattr(tipo, "__name__")}
        assert "Clock" not in nomes, f"{use_case.__name__} recebe Clock"


def test_todo_use_case_expoe_execute() -> None:
    """A forma `<Nome>UseCase(deps…).execute(command)` do concept §4."""
    for use_case in _classes_de_use_case():
        assert callable(getattr(use_case, "execute", None)), (
            f"{use_case.__name__} não expõe `execute`"
        )
