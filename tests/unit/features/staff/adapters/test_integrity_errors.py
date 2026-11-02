"""Tradução de `IntegrityError` → erros de aplicação de staff — CA8b e CA15b.

Metade destes testes cobre o que **é** traduzido; a outra metade cobre o que
**deliberadamente não é**. A segunda metade importa tanto quanto a primeira: a
não-tradução das FKs de filha e das CHECK é decisão explícita (concept §6), e
decisão sem teste vira omissão silenciosa na primeira vez que alguém "consertar"
o mapa achando que faltava uma entrada.

O teste que carrega o ADR 3.3.0004 inteiro é
`test_a_mesma_constraint_tem_dois_significados_conforme_a_operacao`: a **mesma**
`fk_employee_job_functions_job_function` devolve `JobFunctionNotFoundError` sob
`ON_WRITE_EMPLOYEE` e `JobFunctionInUseError` sob `ON_DELETE_JOB_FUNCTION`.
Nenhum mapa global consegue as duas.
"""

from types import SimpleNamespace

import pytest
from sqlalchemy.exc import IntegrityError

from restaurant_hub.features.staff.adapters.out.postgres import integrity_errors
from restaurant_hub.features.staff.adapters.out.postgres.integrity_errors import (
    ON_DELETE_JOB_FUNCTION,
    ON_INSERT_JOB_FUNCTION,
    ON_UPDATE_JOB_FUNCTION,
    ON_WRITE_EMPLOYEE,
    ConstraintMap,
)
from restaurant_hub.features.staff.application.errors import (
    EmployeeAlreadyExistsError,
    JobFunctionAlreadyExistsError,
    JobFunctionInUseError,
    JobFunctionNameAlreadyExistsError,
    JobFunctionNotFoundError,
    StaffApplicationError,
)
from restaurant_hub.features.staff.domain.exceptions.errors import StaffError

pytestmark = pytest.mark.unit

_TODOS_OS_MAPAS: tuple[ConstraintMap, ...] = (
    ON_INSERT_JOB_FUNCTION,
    ON_UPDATE_JOB_FUNCTION,
    ON_DELETE_JOB_FUNCTION,
    ON_WRITE_EMPLOYEE,
)

# Lista completa do concept §6 "O que NÃO é traduzido, deliberadamente" —
# conferida contra §9. Nenhuma delas pode virar erro de negócio em mapa nenhum.
_NUNCA_TRADUZIDAS = (
    "fk_employee_job_functions_employee",
    "fk_employee_unavailabilities_employee",
    "fk_employee_shift_preferences_employee",
    "pk_employee_job_functions",
    "pk_employee_unavailabilities",
    "pk_employee_shift_preferences",
    "ck_employees_workload_kind_known",
    "ck_employees_workload_iff_hours",
    "ck_employees_weekly_hours_positive",
    "ck_employee_unavailabilities_period",
    "ck_employee_shift_preferences_period_known",
)


def _erro(constraint: str | None) -> IntegrityError:
    """`IntegrityError` com o `diag.constraint_name` que o psycopg 3 expõe."""
    original = SimpleNamespace(diag=SimpleNamespace(constraint_name=constraint))
    return IntegrityError("INSERT ...", {}, original)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Cada entrada de cada um dos quatro mapas
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("constraint", "esperado"),
    [
        ("pk_job_functions", JobFunctionAlreadyExistsError),
        ("uq_job_functions_id_tenant", JobFunctionAlreadyExistsError),
        ("uq_job_functions_tenant_name", JobFunctionNameAlreadyExistsError),
    ],
)
def test_mapa_de_insercao_de_funcao(constraint: str, esperado: type[Exception]) -> None:
    """L-JF1: colisão de id (global) e de nome (por tenant, verbatim)."""
    traduzido = integrity_errors.translate(_erro(constraint), ON_INSERT_JOB_FUNCTION, "f1")
    assert isinstance(traduzido, esperado)
    # Nada escapa da hierarquia e vira 500 por descuido — todos herdam de
    # `StaffError`, que tem handler registrado.
    assert isinstance(traduzido, StaffError | StaffApplicationError)


def test_mapa_de_atualizacao_de_funcao_so_traduz_conflito_de_nome() -> None:
    """L-JF2: `id` só entra no `WHERE` e `tenant_id` nunca entra no `SET` (§5.3).

    Mapear as constraints de identidade aqui faria o mapa afirmar um caminho
    que o `UPDATE` não tem como alcançar — e um mapa que descreve caminhos
    inexistentes é um mapa que ninguém consegue auditar.
    """
    assert set(ON_UPDATE_JOB_FUNCTION) == {"uq_job_functions_tenant_name"}
    traduzido = integrity_errors.translate(
        _erro("uq_job_functions_tenant_name"), ON_UPDATE_JOB_FUNCTION, "Cozinheiro"
    )
    assert isinstance(traduzido, JobFunctionNameAlreadyExistsError)


def test_mapa_de_remocao_de_funcao_traduz_a_fk_restrict() -> None:
    """L-JF3: o `RESTRICT` **é** a guarda de remoção, e vira erro tipado."""
    traduzido = integrity_errors.translate(
        _erro("fk_employee_job_functions_job_function"), ON_DELETE_JOB_FUNCTION, "f1"
    )
    assert isinstance(traduzido, JobFunctionInUseError)


@pytest.mark.parametrize(
    ("constraint", "esperado"),
    [
        ("pk_employees", EmployeeAlreadyExistsError),
        ("uq_employees_id_tenant", EmployeeAlreadyExistsError),
        ("fk_employee_job_functions_job_function", JobFunctionNotFoundError),
    ],
)
def test_mapa_de_escrita_de_funcionario(constraint: str, esperado: type[Exception]) -> None:
    """L-E1 (backstop da colisão de id) e L-E4 (backstop da pré-checagem)."""
    traduzido = integrity_errors.translate(_erro(constraint), ON_WRITE_EMPLOYEE, "e1")
    assert isinstance(traduzido, esperado)
    assert isinstance(traduzido, StaffError | StaffApplicationError)


def test_os_quatro_mapas_estao_completos_e_sao_exatamente_estes() -> None:
    """Congela o conteúdo dos quatro mapas — CA8b lido como conjunto.

    Uma entrada acrescentada em silêncio muda o erro que a 3.4 devolve sem que
    nenhum outro teste note; uma removida devolve o `IntegrityError` cru, que
    vira 500. Os dois lados são regressão.
    """
    assert dict(ON_INSERT_JOB_FUNCTION) == {
        "pk_job_functions": JobFunctionAlreadyExistsError,
        "uq_job_functions_id_tenant": JobFunctionAlreadyExistsError,
        "uq_job_functions_tenant_name": JobFunctionNameAlreadyExistsError,
    }
    assert dict(ON_UPDATE_JOB_FUNCTION) == {
        "uq_job_functions_tenant_name": JobFunctionNameAlreadyExistsError,
    }
    assert dict(ON_DELETE_JOB_FUNCTION) == {
        "fk_employee_job_functions_job_function": JobFunctionInUseError,
    }
    assert dict(ON_WRITE_EMPLOYEE) == {
        "pk_employees": EmployeeAlreadyExistsError,
        "uq_employees_id_tenant": EmployeeAlreadyExistsError,
        "fk_employee_job_functions_job_function": JobFunctionNotFoundError,
    }


# ---------------------------------------------------------------------------
# CA8b — a mesma constraint, os dois significados
# ---------------------------------------------------------------------------


def test_a_mesma_constraint_tem_dois_significados_conforme_a_operacao() -> None:
    """ADR 3.3.0004, o teste que carrega a decisão inteira.

    Mesmo nome, mesmo sqlstate `23503`, dois significados de negócio opostos. Um
    mapa global responderia errado em metade dos casos — e erraria de forma
    **plausível**: "função não encontrada" ao apagar uma função que existe, ou
    "função em uso" ao atribuir a função de outro restaurante. Erro plausível
    não convida a investigar, que é o que o torna pior que o erro cru.
    """
    erro = _erro("fk_employee_job_functions_job_function")

    ao_gravar_funcionario = integrity_errors.translate(erro, ON_WRITE_EMPLOYEE, "f97")
    ao_apagar_funcao = integrity_errors.translate(erro, ON_DELETE_JOB_FUNCTION, "f97")

    assert isinstance(ao_gravar_funcionario, JobFunctionNotFoundError)
    assert not isinstance(ao_gravar_funcionario, JobFunctionInUseError)
    assert isinstance(ao_apagar_funcao, JobFunctionInUseError)
    assert not isinstance(ao_apagar_funcao, JobFunctionNotFoundError)


# ---------------------------------------------------------------------------
# CA15b — o que deliberadamente NÃO é traduzido
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("constraint", _NUNCA_TRADUZIDAS)
@pytest.mark.parametrize(
    "mapa",
    _TODOS_OS_MAPAS,
    ids=["insert_funcao", "update_funcao", "delete_funcao", "escrita_funcionario"],
)
def test_constraint_sem_significado_de_negocio_sobe_intacta(
    mapa: ConstraintMap, constraint: str
) -> None:
    """Concept §6, lista completa — e contra **os quatro** mapas.

    As FKs de filha, as PKs das filhas e as cinco CHECK só são alcançáveis por
    bug do mapper ou por escrita feita por fora do domínio. Traduzi-las
    produziria um 4xx plausível escondendo o defeito.
    """
    erro = _erro(constraint)
    assert integrity_errors.translate(erro, mapa, "x") is erro


@pytest.mark.parametrize(
    "mapa",
    _TODOS_OS_MAPAS,
    ids=["insert_funcao", "update_funcao", "delete_funcao", "escrita_funcionario"],
)
def test_constraint_desconhecida_sobe_intacta(mapa: ConstraintMap) -> None:
    """Inventar erro de negócio para o que não se entende perde o bug de vista."""
    erro = _erro("uq_alguma_coisa_nova")
    assert integrity_errors.translate(erro, mapa, "x") is erro


def test_a_fk_de_funcao_nao_e_traduzida_nas_operacoes_que_nao_a_alcancam() -> None:
    """A constraint ambígua **não** vira coringa: fora das duas operações que a
    alcançam, ela sobe crua.

    Traduzi-la em `ON_INSERT_JOB_FUNCTION`/`ON_UPDATE_JOB_FUNCTION` seria voltar
    ao mapa global por outro caminho — e responderia um erro de negócio para uma
    operação que não tem como violá-la.
    """
    erro = _erro("fk_employee_job_functions_job_function")
    assert integrity_errors.translate(erro, ON_INSERT_JOB_FUNCTION, "f1") is erro
    assert integrity_errors.translate(erro, ON_UPDATE_JOB_FUNCTION, "f1") is erro


def test_erro_sem_nome_de_constraint_sobe_intacto() -> None:
    """Sem `diag.constraint_name` não há como decidir — degradar para parsing de
    mensagem trocaria uma falha explícita por uma silenciosa."""
    erro = _erro(None)
    assert integrity_errors.translate(erro, ON_WRITE_EMPLOYEE, "x") is erro


def test_erro_sem_diag_algum_sobe_intacto() -> None:
    """Outro driver, ou erro que não é de constraint."""
    erro = IntegrityError("INSERT ...", {}, Exception("boom"))  # type: ignore[arg-type]
    assert integrity_errors.translate(erro, ON_WRITE_EMPLOYEE, "x") is erro
    assert integrity_errors.constraint_name(erro) is None


def test_detalhe_chega_na_mensagem_do_erro_traduzido() -> None:
    """Sem a chave em conflito, a mensagem é inútil para diagnóstico.

    E a **forma** do detalhe é contrato em L-E4 (CA8c): a menor id ausente no
    caminho comum, o conjunto `sorted()` no backstop. Aqui só se assere que o
    valor fornecido pelo repositório chega intacto.
    """
    traduzido = integrity_errors.translate(_erro("pk_employees"), ON_WRITE_EMPLOYEE, "e-42")
    assert "e-42" in str(traduzido)

    do_backstop = integrity_errors.translate(
        _erro("fk_employee_job_functions_job_function"), ON_WRITE_EMPLOYEE, "['f97', 'f99']"
    )
    assert "f97" in str(do_backstop)
    assert "f99" in str(do_backstop)
