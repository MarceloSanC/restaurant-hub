"""CA2 — nenhum corpo de teste do contrato ramifica por implementação.

Um teste de contrato que sabe **qual** implementação está exercitando deixou de
ser um teste de contrato: virou dois testes diferentes que apenas se parecem, e
a divergência que a suíte existe para revelar passa a ser acomodada em vez de
denunciada. É o modo de falha mais barato de introduzir — basta um `if` numa
linha, com uma justificativa plausível ("o Postgres precisa de setup extra
aqui") — e o mais caro de detectar depois, porque a suíte continua verde.

**A verificação é por AST, e o concept é explícito sobre isso.** Grep dá falso
positivo: as palavras `fake` e `postgres` aparecem em docstring, em comentário e
no nome do próprio parâmetro da fixture, e um grep que as procurasse acusaria os
arquivos que estão corretos. O AST distingue **o que o código faz** do que o
texto diz — que é exatamente a distinção em jogo.

O `conftest.py` fica **fora** do escopo de propósito: é lá que a ramificação por
implementação **deve** existir (é a definição da fixture). Verificar o conftest
com esta regra proibiria o mecanismo em vez do abuso dele.
"""

import ast
from pathlib import Path

import pytest

from restaurant_hub.features.staff.adapters.out.postgres.employee_repository import (
    PostgresEmployeeRepository,
)
from restaurant_hub.features.staff.adapters.out.postgres.job_function_repository import (
    PostgresJobFunctionRepository,
)
from tests.contract.features.staff.conftest import (
    IMPLEMENTACOES,
    IMPLEMENTACOES_DO_GATEWAY,
    RepositoriosDeStaff,
)

pytestmark = pytest.mark.contract

_PASTA = Path(__file__).parent

# Só as suítes de lei promovidas. `conftest.py` e este próprio arquivo estão
# fora — ver o docstring do módulo.
#
# A lista é **escrita à mão** de propósito: um módulo removido da pasta tem de
# aparecer como falha, e não sumir da varredura. O preço é que ela mesma pode
# envelhecer — um terceiro módulo de lei nasce, ninguém o acrescenta aqui, e as
# quatro asserções de AST abaixo simplesmente não o enxergam, com a suíte verde.
# `test_a_lista_de_modulos_de_lei_cobre_a_pasta_inteira` cobra a pasta contra a
# lista, mesmo antídoto de `test_composition_root_staff.py` para a lista de use
# cases.
#
# **Módulo → nome da fixture de implementações.** Desde a Stage 3.5 a pasta tem
# uma suíte de lei que não é de repositório: as leis do `IdentityGateway`, cuja
# fixture se chama `gateway`. Os guardas "todo teste recebe a fixture" e "nenhum
# corpo inspeciona o tipo por trás dela" leem o nome daqui — generalização do
# guarda pelo seu próprio princípio (nenhuma ramificação por implementação), não
# afrouxamento: os três módulos ficam sob as mesmas quatro asserções.
_MODULOS_DE_LEI: dict[str, str] = {
    "test_job_function_repository_laws.py": "repos",
    "test_employee_repository_laws.py": "repos",
    "test_identity_gateway_laws.py": "gateway",
}

# O padrão que nomeia uma suíte de lei promovida. É a fonte da verdade contra a
# qual `_MODULOS_DE_LEI` é conferida.
_PADRAO_DE_MODULO_DE_LEI = "test_*laws*.py"

# Nomes que só fazem sentido para quem está olhando a **implementação por trás**
# da fixture. `request`/`param` alcançam o parâmetro; `getfixturevalue` alcança
# a fixture crua (o `engine`), que é a porta dos fundos para o mesmo efeito.
_NOMES_PROIBIDOS = frozenset({"request", "param", "getfixturevalue"})

# Os ids dos parâmetros das fixtures — das duas (`repos`: fake/postgres;
# `gateway`: fake/real). Comparação **exata**: uma docstring que contenha a
# palavra não é uma ramificação, e confundir as duas coisas é o falso positivo
# que motivou usar AST em vez de grep.
_LITERAIS_PROIBIDOS = frozenset({"fake", "postgres", "real"})


# `async def` é `ast.AsyncFunctionDef`, uma classe **distinta** de
# `ast.FunctionDef` — não uma subclasse. Filtrar só a segunda deixaria um teste
# de lei `async` invisível aos quatro guardas deste módulo, inclusive ao "todo
# teste recebe a fixture": ele poderia rodar uma vez só, contra uma
# implementação só, com a suíte verde.
_Funcao = ast.FunctionDef | ast.AsyncFunctionDef


def _funcoes(modulo: str) -> list[_Funcao]:
    arvore = ast.parse((_PASTA / modulo).read_text(encoding="utf-8"))
    return [no for no in ast.walk(arvore) if isinstance(no, ast.FunctionDef | ast.AsyncFunctionDef)]


def _corpo_sem_docstring(funcao: _Funcao) -> list[ast.stmt]:
    """Descarta a docstring — ela é prosa, e prosa não ramifica.

    Sem isto, qualquer docstring que explique a diferença entre as duas
    implementações (que é justamente o que se **quer** que esteja escrito) seria
    acusada como violação.
    """
    corpo = funcao.body
    primeiro = corpo[0] if corpo else None
    if (
        isinstance(primeiro, ast.Expr)
        and isinstance(primeiro.value, ast.Constant)
        and isinstance(primeiro.value.value, str)
    ):
        return corpo[1:]
    return corpo


def _nos(funcao: _Funcao) -> list[ast.AST]:
    return [no for stmt in _corpo_sem_docstring(funcao) for no in ast.walk(stmt)]


def test_a_lista_de_modulos_de_lei_cobre_a_pasta_inteira() -> None:
    """Fecha o buraco da lista explícita: ela pode ficar **incompleta**.

    As quatro asserções abaixo são parametrizadas por `_MODULOS_DE_LEI`, uma
    tupla de literais. Um terceiro módulo de lei nascendo na pasta não seria
    varrido por nenhuma delas — e o sintoma seria o melhor possível: tudo verde,
    com CA2 reportando conformidade sobre dois terços da suíte. É a mesma classe
    de defeito que a lista de use cases de `test_composition_root_staff.py`
    tinha, e o antídoto é o mesmo: cobrar a pasta contra a lista.
    """
    na_pasta = {arquivo.name for arquivo in _PASTA.glob(_PADRAO_DE_MODULO_DE_LEI)}

    assert na_pasta == set(_MODULOS_DE_LEI), (
        f"a lista deste teste divergiu da pasta — só na pasta: "
        f"{sorted(na_pasta - set(_MODULOS_DE_LEI))}; "
        f"só na lista: {sorted(set(_MODULOS_DE_LEI) - na_pasta)}"
    )


@pytest.mark.parametrize("modulo", _MODULOS_DE_LEI)
def test_nenhum_corpo_alcanca_o_parametro_da_fixture(modulo: str) -> None:
    """`request`, `param` e `getfixturevalue` não aparecem em corpo nenhum.

    São os três caminhos para descobrir qual implementação está por trás de
    `repos`. Fechados eles, a ramificação por implementação deixa de ser
    expressável sem que alguém a escreva de forma óbvia demais para passar em
    revisão.
    """
    violacoes = [
        (funcao.name, no.id if isinstance(no, ast.Name) else no.attr)
        for funcao in _funcoes(modulo)
        for no in _nos(funcao)
        if (isinstance(no, ast.Name) and no.id in _NOMES_PROIBIDOS)
        or (isinstance(no, ast.Attribute) and no.attr in _NOMES_PROIBIDOS)
    ]
    assert violacoes == [], f"{modulo}: corpo alcança o parâmetro da fixture: {violacoes}"


@pytest.mark.parametrize("modulo", _MODULOS_DE_LEI)
def test_nenhum_corpo_menciona_o_id_de_uma_implementacao(modulo: str) -> None:
    """Os literais `"fake"` e `"postgres"` não aparecem como **valor** em corpo nenhum.

    Comparação exata sobre constantes de string do AST: a palavra em docstring
    ou em comentário não é alcançada (comentários nem chegam ao AST), e é
    justamente onde ela deve aparecer — explicando por que as duas
    implementações precisam concordar.
    """
    violacoes = [
        (funcao.name, no.value)
        for funcao in _funcoes(modulo)
        for no in _nos(funcao)
        if isinstance(no, ast.Constant)
        and isinstance(no.value, str)
        and no.value in _LITERAIS_PROIBIDOS
    ]
    assert violacoes == [], f"{modulo}: corpo cita a implementação: {violacoes}"


@pytest.mark.parametrize("modulo", _MODULOS_DE_LEI)
def test_nenhum_corpo_inspeciona_o_tipo_de_um_repositorio(modulo: str) -> None:
    """Nada de `isinstance(repos.…, PostgresX)` — a via oblíqua para o mesmo fim.

    A regra é escopada ao que envolve a fixture de implementações do módulo
    (`repos` ou `gateway`) de propósito: a suíte **usa**
    `type(excecao.value) is EmployeeNotFoundError` para asserir o tipo **exato**
    de uma exceção, que é asserção legítima e nada tem a ver com implementação
    de port. Proibir toda introspecção de tipo aqui tornaria o teste um
    obstáculo à precisão que ele deveria proteger.
    """
    fixture = _MODULOS_DE_LEI[modulo]
    violacoes: list[tuple[str, str]] = []
    for funcao in _funcoes(modulo):
        for no in _nos(funcao):
            if not isinstance(no, ast.Call) or not isinstance(no.func, ast.Name):
                continue
            if no.func.id not in {"isinstance", "type"} or not no.args:
                continue
            alcanca_fixture = any(
                isinstance(interno, ast.Name) and interno.id == fixture
                for interno in ast.walk(no.args[0])
            )
            if alcanca_fixture:
                violacoes.append((funcao.name, no.func.id))
    assert violacoes == [], (
        f"{modulo}: corpo inspeciona o tipo por trás de `{fixture}`: {violacoes}"
    )


@pytest.mark.parametrize("modulo", _MODULOS_DE_LEI)
def test_todo_teste_de_lei_recebe_a_fixture(modulo: str) -> None:
    """Metade estrutural de CA1: quem não recebe a fixture roda **uma** vez só.

    Sem esta asserção, um teste que esquecesse o parâmetro continuaria verde e
    silenciosamente deixaria de valer para as duas implementações — a suíte
    reportaria o mesmo verde exercitando metade do contrato. Inclui o único
    teste que não constrói sujeito (`…_a_lei_esta_documentada_no_port`), que
    recebe a fixture sem usá-la exatamente para que "cada teste roda duas vezes"
    valha **literalmente** no `--collect-only`.
    """
    fixture = _MODULOS_DE_LEI[modulo]
    sem_fixture = [
        funcao.name
        for funcao in _funcoes(modulo)
        if funcao.name.startswith("test_")
        and fixture not in {argumento.arg for argumento in funcao.args.args}
    ]
    assert sem_fixture == [], f"{modulo}: teste de lei sem a fixture `{fixture}`: {sem_fixture}"


# ---------------------------------------------------------------------------
# O risco central da Stage: `[postgres]` rodar contra o fake
# ---------------------------------------------------------------------------
#
# A Stage inteira existe para provar `fake ≡ real`. Uma fixture que devolvesse o
# **fake** nos dois ramos transformaria a prova em duas execuções da mesma
# implementação — e o sintoma seria o **melhor resultado possível**: tudo verde,
# com o `--collect-only` mostrando `[fake]` e `[postgres]` para cada teste. É
# precisamente por isso que ninguém investigaria.
#
# Nenhum critério de §11 alcança esse defeito: CA1 conta as execuções, CA2 proíbe
# ramificação **no corpo do teste** e CA3 pede as leis verdes nos dois params —
# todos satisfeitos pelo defeito. Os dois testes abaixo são a extensão de
# critério registrada como `[decision]` na §7 do technical, e fecham as **duas**
# formas de falhar: o parâmetro sumir, e o ramo construir a coisa errada.
#
# Eles vivem aqui, e não nos módulos de lei, para não violar CA2 — o corpo de um
# teste de lei não pode conhecer a implementação.


def test_a_suite_de_contrato_roda_sobre_as_duas_implementacoes() -> None:
    """Primeira forma de falhar: o parâmetro `postgres` sumir de `IMPLEMENTACOES`.

    A suíte voltaria a exercitar uma implementação só e continuaria verde — com
    metade do contrato não verificado e nenhum sinal disso no output, porque o
    que desaparece é a **ausência** de uma variante, e ausência não falha.
    """
    assert set(IMPLEMENTACOES) == {"fake", "postgres"}


def test_a_suite_do_gateway_roda_sobre_o_fake() -> None:
    """O contrato do gateway nasce sobre o fake (Task 04 da 3.5); a Task 09
    acrescenta `"real"` e troca esta asserção pela exata — o mesmo par de
    guardas que o par de repositórios tem acima e abaixo."""
    assert "fake" in IMPLEMENTACOES_DO_GATEWAY


@pytest.mark.parametrize("repos", ["postgres"], indirect=True)
def test_o_par_postgres_nao_e_o_par_in_memory(repos: RepositoriosDeStaff) -> None:
    """Segunda forma de falhar: o ramo existir e construir a implementação errada.

    A asserção é sobre o **tipo concreto** — a única coisa que distingue as duas
    implementações de fora, já que ambas satisfazem o mesmo `Protocol` e por
    construção respondem igual a tudo que a suíte de lei pergunta.

    A parametrização indireta força o ramo `postgres` independentemente do que
    `IMPLEMENTACOES` declare, e é por isso que o teste acima existe **também**:
    sozinho, este passaria com o parâmetro removido da suíte inteira.

    `isinstance` sobre `repos` é proibido nos módulos de lei
    (`test_nenhum_corpo_inspeciona_o_tipo_de_um_repositorio`) e obrigatório aqui
    — a mesma introspecção é abuso lá e é o instrumento aqui, e a diferença é o
    escopo daquela regra, que lista os módulos de lei nominalmente.
    """
    assert isinstance(repos.job_functions, PostgresJobFunctionRepository)
    assert isinstance(repos.employees, PostgresEmployeeRepository)
