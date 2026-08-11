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

pytestmark = pytest.mark.contract

_PASTA = Path(__file__).parent

# Só as suítes de lei promovidas. `conftest.py` e este próprio arquivo estão
# fora — ver o docstring do módulo.
_MODULOS_DE_LEI = (
    "test_job_function_repository_laws.py",
    "test_employee_repository_laws.py",
)

# Nomes que só fazem sentido para quem está olhando a **implementação por trás**
# da fixture. `request`/`param` alcançam o parâmetro; `getfixturevalue` alcança
# a fixture crua (o `engine`), que é a porta dos fundos para o mesmo efeito.
_NOMES_PROIBIDOS = frozenset({"request", "param", "getfixturevalue"})

# Os ids dos parâmetros da fixture. Comparação **exata**: uma docstring que
# contenha a palavra não é uma ramificação, e confundir as duas coisas é o
# falso positivo que motivou usar AST em vez de grep.
_LITERAIS_PROIBIDOS = frozenset({"fake", "postgres"})


def _funcoes(modulo: str) -> list[ast.FunctionDef]:
    arvore = ast.parse((_PASTA / modulo).read_text(encoding="utf-8"))
    return [no for no in ast.walk(arvore) if isinstance(no, ast.FunctionDef)]


def _corpo_sem_docstring(funcao: ast.FunctionDef) -> list[ast.stmt]:
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


def _nos(funcao: ast.FunctionDef) -> list[ast.AST]:
    return [no for stmt in _corpo_sem_docstring(funcao) for no in ast.walk(stmt)]


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

    A regra é escopada ao que envolve `repos` de propósito: a suíte **usa**
    `type(excecao.value) is EmployeeNotFoundError` para asserir o tipo **exato**
    de uma exceção, que é asserção legítima e nada tem a ver com implementação
    de port. Proibir toda introspecção de tipo aqui tornaria o teste um
    obstáculo à precisão que ele deveria proteger.
    """
    violacoes: list[tuple[str, str]] = []
    for funcao in _funcoes(modulo):
        for no in _nos(funcao):
            if not isinstance(no, ast.Call) or not isinstance(no.func, ast.Name):
                continue
            if no.func.id not in {"isinstance", "type"} or not no.args:
                continue
            alcanca_repos = any(
                isinstance(interno, ast.Name) and interno.id == "repos"
                for interno in ast.walk(no.args[0])
            )
            if alcanca_repos:
                violacoes.append((funcao.name, no.func.id))
    assert violacoes == [], f"{modulo}: corpo inspeciona o tipo do repositório: {violacoes}"


@pytest.mark.parametrize("modulo", _MODULOS_DE_LEI)
def test_todo_teste_de_lei_recebe_a_fixture(modulo: str) -> None:
    """Metade estrutural de CA1: quem não recebe `repos` roda **uma** vez só.

    Sem esta asserção, um teste que esquecesse o parâmetro continuaria verde e
    silenciosamente deixaria de valer para as duas implementações — a suíte
    reportaria o mesmo verde exercitando metade do contrato. Inclui o único
    teste que não constrói sujeito (`…_a_lei_esta_documentada_no_port`), que
    recebe a fixture sem usá-la exatamente para que "cada teste roda duas vezes"
    valha **literalmente** no `--collect-only`.
    """
    sem_fixture = [
        funcao.name
        for funcao in _funcoes(modulo)
        if funcao.name.startswith("test_")
        and "repos" not in {argumento.arg for argumento in funcao.args.args}
    ]
    assert sem_fixture == [], f"{modulo}: teste de lei sem a fixture `repos`: {sem_fixture}"
