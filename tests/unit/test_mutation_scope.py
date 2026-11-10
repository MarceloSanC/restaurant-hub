"""O escopo do teste de mutação (M2 da issue #45) aponta para arquivos que existem.

**Por que existe: um caminho morto no `only_mutate` exclui o módulo em silêncio.**
O mutmut filtra os arquivos de `source_paths` por `fnmatch` contra cada padrão de
`only_mutate`. Um padrão que não casa com arquivo nenhum não produz erro, não
produz aviso — produz uma corrida com um módulo a menos, e um relatório que
continua dizendo "N mutantes, N mortos" sobre um universo menor que o declarado.

Foi exatamente o que aconteceu no rename `adapters/in/` → `adapters/inbound/`:
o `pyproject.toml` ficou com `adapters/in/http/dependencies.py`, e a corrida
seguinte mediu **três** dos quatro módulos que decidem acesso, reportando zero
sobreviventes sobre a borda que extrai o Bearer sem tê-la mutado uma vez sequer.
Achado por revisão, não por sintoma — que é o modo de falha que este arquivo
existe para tornar barulhento.

**Lista explícita + asserção de que ela cobre a configuração**, o par de sempre.
A lista aqui é a dos módulos que decidem acesso (os quatro da issue e o port da
Stage 2.7); a asserção seguinte cobra
o `pyproject.toml` contra ela nos dois sentidos, para que nem um módulo saia do
escopo por edição distraída, nem um quinto entre sem que a issue que o justifica
seja escrita neste arquivo.
"""

import ast
import fnmatch
import os
import pathlib
import subprocess
import sys
import tomllib
from collections.abc import Iterable

import pytest

pytestmark = pytest.mark.unit

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_PYPROJECT = _REPO_ROOT / "pyproject.toml"

# Os módulos que decidem acesso: os quatro que a issue #45 nomeia e o port da
# Stage 2.7. Um novo entra aqui com a justificativa ao lado — e só então no
# `pyproject.toml`.
_MODULOS_DE_ACESSO = frozenset(
    {
        # Os quatro passos do guard (ADR 2.2.0002).
        "src/restaurant_hub/features/identity/application/use_cases/authorize_action.py",
        # A visibilidade de unidade — o eixo B do acesso.
        "src/restaurant_hub/features/identity/domain/entities/user.py",
        # O `AccessGuard` de staff: resolve o tenant omitido e impõe L-AG3 num
        # `raise`. Substituiu o `composition_root.py` na issue #47, que moveu
        # para cá o `_IdentityAccessGuard` — o critério de entrada é o mesmo.
        "src/restaurant_hub/features/staff/adapters/out/identity/local_access_guard.py",
        # A borda que extrai o Bearer e delega ao use case.
        "src/restaurant_hub/features/identity/adapters/inbound/http/dependencies.py",
        # "Não se concede o que não se detém" — `required_permissions_for_role`, que
        # saiu de `dependencies.py` na Stage 2.7 para que os use cases de identity
        # declarem o mesmo requisito (ADR 2.7.0001). Sem esta entrada a regra
        # deixaria, sem ninguém notar, o conjunto que a mutação mede.
        "src/restaurant_hub/features/identity/application/ports/out/action_authorizer.py",
    }
)


def _config_do_mutmut() -> dict[str, object]:
    with _PYPROJECT.open("rb") as arquivo:
        return dict(tomllib.load(arquivo)["tool"]["mutmut"])


def test_todo_caminho_do_only_mutate_existe() -> None:
    """A asserção que faltava no dia do rename.

    `fnmatch` sobre caminho inexistente não reprova nada — apenas deixa o módulo
    de fora. Aqui a existência é cobrada antes de a corrida ser lançada.
    """
    caminhos = _config_do_mutmut()["only_mutate"]
    assert isinstance(caminhos, list)
    ausentes = sorted(caminho for caminho in caminhos if not (_REPO_ROOT / caminho).is_file())

    assert ausentes == [], (
        f"only_mutate aponta para arquivo que não existe: {ausentes}. O mutmut "
        f"não reprova — ele exclui o módulo em silêncio e reporta a corrida "
        f"como completa."
    )


def test_o_escopo_do_mutmut_e_exatamente_os_modulos_de_acesso() -> None:
    """Nos dois sentidos: nada sai sem ser notado, nada entra sem justificativa.

    Um módulo a menos é o rename repetido; um módulo a mais é o escopo
    crescendo sem a issue que o justifica — e a corrida noturna ficando mais
    lenta sem que ninguém tenha decidido isso.
    """
    caminhos = _config_do_mutmut()["only_mutate"]
    assert isinstance(caminhos, list)

    assert set(caminhos) == _MODULOS_DE_ACESSO, (
        f"só no pyproject: {sorted(set(caminhos) - _MODULOS_DE_ACESSO)}; "
        f"só nesta lista: {sorted(_MODULOS_DE_ACESSO - set(caminhos))}"
    )


def test_todo_caminho_do_also_copy_existe() -> None:
    """O mesmo defeito, do outro lado: `also_copy` para caminho ausente.

    Um `also_copy` morto não derruba a corrida — e o arquivo que ele deveria
    levar para o sandbox simplesmente não vai, o que reaparece como
    `FileNotFoundError` dentro de um teste, longe da causa. Medido na primeira
    corrida desta configuração, antes de `docs/` entrar na lista.
    """
    caminhos = _config_do_mutmut()["also_copy"]
    assert isinstance(caminhos, list)
    ausentes = sorted(caminho for caminho in caminhos if not (_REPO_ROOT / caminho).exists())

    assert ausentes == [], f"also_copy aponta para caminho que não existe: {ausentes}"


def test_o_gate_estrutural_do_check_layout_fica_fora_da_corrida() -> None:
    """A exclusão de `test_check_layout.py` é deliberada e continua declarada.

    Dentro de `mutants/`, `authorize_action.py` tem uma cópia por mutante, e o
    Gate 8 (um sítio de construção por result) reprova sobre um arquivo que o
    mutmut escreveu. (Até a issue #47 o Gate 1 também, pelo `composition_root.py`
    mutado.)
    Se alguém tirar o `--ignore` por achar que é sobra, a corrida volta a morrer
    na coleta de estatísticas — e este teste diz o porquê antes disso.
    """
    selecao = _config_do_mutmut()["pytest_add_cli_args_test_selection"]
    assert isinstance(selecao, list)

    # Conjunto exato, não pertinência: um segundo `--ignore` entraria calado e a
    # corrida mediria menos suíte com o mesmo "N/N" — a mesma classe do caminho
    # morto em `only_mutate` que este arquivo existe para tornar barulhento.
    assert selecao == ["--ignore=tests/unit/test_check_layout.py"]

    ignorado = selecao[0].removeprefix("--ignore=")
    assert (_REPO_ROOT / ignorado).is_file(), (
        f"o --ignore aponta para {ignorado}, que não existe: a exclusão está morta "
        f"e a corrida voltaria a morrer na coleta de estatísticas"
    )


# ---------------------------------------------------------------------------
# Guarda de classe do `also_copy` (issue #87; F3 da #7).
#
# O mutmut roda a suíte numa cópia em `mutants/` que só leva o código de
# `source_paths`, os defaults dele e o `also_copy`. Teste que lê um arquivo da
# raiz fora desse conjunto morre na coleta de estatísticas (`failed to collect
# stats`), e a corrida inteira sai sem testar um mutante: foi a #7 com o
# `.pre-commit-config.yaml`, a #58 com o `docker-compose.yml` e a #87 com o
# `.claude/hooks/`. Cada caso foi corrigido no próprio arquivo; esta guarda fecha
# a classe.
#
# **Varredura estática, aproximação por excesso.** Toda constante de string de
# todo `.py` rastreado (testes, scripts e hooks que a suíte executa, e o `src/`)
# que, normalizada, nomeia um caminho rastreado do repositório conta como
# leitura possível — `_REPO_ROOT / ".claude" / "hooks"` rende `".claude"`, e
# `".claude/skills/*/SKILL.md"` rende `".claude/skills"`. Cada arquivo rastreado
# sob esse caminho tem de estar na cópia. Uma menção que não é leitura (um nome
# numa tabela de casos) cobra uma entrada a mais no `also_copy`, que custa
# nada; o contrário custaria a corrida. Fica fora o caminho montado só em tempo
# de execução, sem nenhum literal que o nomeie — o limite de qualquer varredura
# estática.
#
# **O que não é leitura do repositório (issue #139):** o literal que é operando
# de uma cadeia `/` cuja base deriva de um diretório temporário (`tmp_path`, as
# outras fixtures de tmp do pytest, `tempfile`) dentro da mesma função. Ele
# monta uma fixture — `parent / "wt" / ".devcontainer"`, com `parent` vindo de
# `tmp_path` — e não lê a raiz. A derivação é um ponto fixo sobre as
# atribuições da função (`=`, `:=`, `for`, `with … as`), só para alvos que são
# nomes; o mesmo literal sob `_REPO_ROOT`, na mesma linha ou em outra função,
# continua contando. **Na dúvida, a raiz vence:** um nome só é temporário se
# **toda** ligação dele na função deriva de tmp; o nome ligado a um valor que
# menciona um nome ancorado em `__file__` (`_REPO_ROOT`, `ROOT`…) é da raiz, e
# a base que menciona a raiz não está sob tmp; e `a, b = x, y` liga elemento a
# elemento. Assim `p = tmp_path; p = R`, `base = tmp_path if c else R` e
# `dst, src = tmp_path, R` seguem cobrando.
# ---------------------------------------------------------------------------

# Os defaults que o mutmut 3.7.0 soma ao `also_copy` (`configuration.py`, no
# `return Config(also_copy=[...] + [...])`). `test*.py` na raiz é um glob dele.
_DEFAULTS_DO_MUTMUT = (
    "tests",
    "test",
    "setup.cfg",
    "pyproject.toml",
    "uv.lock",
    "poetry.lock",
    "Pipfile.lock",
    "pdm.lock",
)
_GLOB_DE_RAIZ_DO_MUTMUT = "test*.py"
_CURINGAS = frozenset("*?[")
# As fixtures de diretório temporário do pytest e o módulo `tempfile` (issue #139).
_TEMPORARIOS = frozenset({"tmp_path", "tmp_path_factory", "tmpdir", "tmpdir_factory", "tempfile"})


def _sem_variaveis_do_git() -> dict[str, str]:
    """O ambiente sem `GIT_*`: dentro de um hook, `GIT_INDEX_FILE` mudaria a lista."""
    return {chave: valor for chave, valor in os.environ.items() if not chave.startswith("GIT_")}


def _git(cwd: pathlib.Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
        env=_sem_variaveis_do_git(),
    ).stdout


def _raiz_do_git() -> pathlib.Path:
    """A raiz segundo o git, como no `test_eol_policy.py`.

    Dentro de `mutants/` o `parents[2]` é a cópia, que não tem índice; pelo
    `--show-toplevel` a guarda lê o repositório de verdade nos dois cenários e
    dá o mesmo veredito dentro e fora da corrida.
    """
    return pathlib.Path(_git(_REPO_ROOT, "rev-parse", "--show-toplevel").strip())


def _rastreados(raiz: pathlib.Path) -> list[str]:
    return [caminho for caminho in _git(raiz, "ls-files", "-z").split("\0") if caminho]


def _dentro(caminho: str, entrada: str) -> bool:
    return caminho == entrada or caminho.startswith(entrada + "/")


def _caminho_citado(literal: str) -> str | None:
    """O caminho que uma constante de string nomeia, ou `None` se não nomeia um.

    Texto com espaço (docstring, mensagem) não é caminho. O sufixo a partir do
    primeiro componente com curinga cai: o glob lê o que está sob o prefixo.
    """
    texto = literal.strip().replace("\\", "/")
    if not texto or any(caractere.isspace() for caractere in texto):
        return None
    while texto.startswith("./"):
        texto = texto[2:]
    componentes: list[str] = []
    for componente in texto.split("/"):
        if _CURINGAS & set(componente):
            break
        componentes.append(componente)
    citado = "/".join(componentes).rstrip("/")
    return citado or None


def _copiado(caminho: str, copia: list[str]) -> bool:
    if "/" not in caminho and fnmatch.fnmatchcase(caminho, _GLOB_DE_RAIZ_DO_MUTMUT):
        return True
    return any(_dentro(caminho, entrada) for entrada in copia)


def _nomes(no: ast.AST) -> set[str]:
    return {filho.id for filho in ast.walk(no) if isinstance(filho, ast.Name)}


def _nomes_ligados(alvo: ast.AST) -> set[str]:
    """Os nomes que um alvo de atribuição liga — `x[i] = …` e `o.a = …` não ligam nenhum."""
    if isinstance(alvo, ast.Name):
        return {alvo.id}
    if isinstance(alvo, ast.Starred):
        return _nomes_ligados(alvo.value)
    if isinstance(alvo, ast.Tuple | ast.List):
        return set().union(*(_nomes_ligados(elemento) for elemento in alvo.elts))
    return set()


def _ligacao(alvo: ast.AST, valor: ast.AST) -> list[tuple[set[str], set[str]]]:
    """`a, b = x, y` liga elemento a elemento; o resto liga todo alvo a todo o valor."""
    if (
        isinstance(alvo, ast.Tuple | ast.List)
        and isinstance(valor, ast.Tuple | ast.List)
        and len(alvo.elts) == len(valor.elts)
        and not any(isinstance(e, ast.Starred) for e in (*alvo.elts, *valor.elts))
    ):
        return [par for a, v in zip(alvo.elts, valor.elts, strict=True) for par in _ligacao(a, v)]
    return [(_nomes_ligados(alvo), _nomes(valor))]


def _ligacoes(nos: Iterable[ast.AST]) -> list[tuple[set[str], set[str]]]:
    """(nomes ligados, nomes usados no valor) de cada atribuição entre `nos`."""
    ligacoes: list[tuple[set[str], set[str]]] = []
    for no in nos:
        if isinstance(no, ast.Assign):
            for alvo in no.targets:
                ligacoes.extend(_ligacao(alvo, no.value))
        elif isinstance(no, ast.AugAssign):
            ligacoes.append((_nomes_ligados(no.target), _nomes(no.value) | _nomes(no.target)))
        elif isinstance(no, ast.AnnAssign | ast.NamedExpr) and no.value:
            ligacoes.extend(_ligacao(no.target, no.value))
        elif isinstance(no, ast.For | ast.AsyncFor | ast.comprehension):
            ligacoes.append((_nomes_ligados(no.target), _nomes(no.iter)))
        elif isinstance(no, ast.withitem) and no.optional_vars is not None:
            ligacoes.append((_nomes_ligados(no.optional_vars), _nomes(no.context_expr)))
    return ligacoes


def _fecho(sementes: set[str], ligacoes: list[tuple[set[str], set[str]]]) -> set[str]:
    """Ponto fixo: todo nome ligado a um valor que menciona um nome do conjunto entra nele."""
    conjunto = set(sementes)
    mudou = True
    while mudou:
        mudou = False
        for ligados, usados in ligacoes:
            if ligados - conjunto and usados & conjunto:
                conjunto |= ligados
                mudou = True
    return conjunto


def _ancorados_do_modulo(arvore: ast.Module) -> set[str]:
    """`__file__` e os nomes de módulo ancorados nele — `_REPO_ROOT = Path(__file__)…`."""
    return _fecho({"__file__"}, _ligacoes(arvore.body))


def _derivados_de_temporario(
    funcao: ast.FunctionDef | ast.AsyncFunctionDef, ancorados_do_modulo: set[str]
) -> tuple[set[str], set[str]]:
    """(temporários, ancorados) da função — os nomes que guardam um caminho de tmp e os da raiz.

    Dois pontos fixos: o dos ancorados parte dos nomes de módulo ancorados em
    `__file__`; o dos temporários, de `_TEMPORARIOS`. Um nome com alguma ligação
    que não deriva de tmp deixa de ser tmp (`p = tmp_path; p = Path.cwd()`). Quem
    decide entre os dois é `_literais_sob_temporario`: a base que menciona um
    ancorado não está sob tmp — a raiz vence.
    """
    ligacoes = _ligacoes(ast.walk(funcao))
    ancorados = _fecho(ancorados_do_modulo, ligacoes)
    derivados = _fecho(set(_TEMPORARIOS), ligacoes)
    mudou = True
    while mudou:
        mudou = False
        for ligados, usados in ligacoes:
            if ligados & derivados and not usados & derivados:
                derivados -= ligados
                mudou = True
    return derivados, ancorados


def _base_da_cadeia(no: ast.BinOp) -> ast.expr:
    """O operando mais à esquerda de `a / b / c` — o `a`."""
    while isinstance(no.left, ast.BinOp) and isinstance(no.left.op, ast.Div):
        no = no.left
    return no.left


def _literais_sob_temporario(arvore: ast.Module) -> set[ast.AST]:
    """Os literais que montam um caminho sob um diretório temporário (issue #139)."""
    literais: set[ast.AST] = set()
    ancorados_do_modulo = _ancorados_do_modulo(arvore)
    for funcao in ast.walk(arvore):
        if not isinstance(funcao, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        derivados, ancorados = _derivados_de_temporario(funcao, ancorados_do_modulo)
        for no in ast.walk(funcao):
            if not (
                isinstance(no, ast.BinOp)
                and isinstance(no.op, ast.Div)
                and isinstance(no.right, ast.Constant)
            ):
                continue
            base = _nomes(_base_da_cadeia(no))
            if base & derivados and not base & ancorados:
                literais.add(no.right)
    return literais


def _leituras_fora_da_copia(
    fontes: dict[str, str], rastreados: list[str], copia: list[str]
) -> list[str]:
    """Cada `<fonte>:<linha> '<literal>' -> <arquivo fora da cópia>`, ordenado.

    `fontes` mapeia o caminho de um `.py` ao seu texto; `copia` é o que vai para
    `mutants/` (`also_copy` + `source_paths` + defaults), sem barra final.
    """
    raizes = {caminho.split("/")[0] for caminho in rastreados}
    achados: set[str] = set()
    for fonte, texto in fontes.items():
        arvore = ast.parse(texto, filename=fonte)
        sob_temporario = _literais_sob_temporario(arvore)
        for no in ast.walk(arvore):
            if not (isinstance(no, ast.Constant) and isinstance(no.value, str)):
                continue
            if no in sob_temporario:
                continue
            citado = _caminho_citado(no.value)
            if citado is None or citado.split("/")[0] not in raizes:
                continue
            for arquivo in rastreados:
                if _dentro(arquivo, citado) and not _copiado(arquivo, copia):
                    achados.add(f"{fonte}:{no.lineno} {no.value!r} -> {arquivo}")
    return sorted(achados)


def _copia_declarada(config: dict[str, object]) -> list[str]:
    also_copy = config["also_copy"]
    source_paths = config["source_paths"]
    assert isinstance(also_copy, list)
    assert isinstance(source_paths, list)
    entradas = [*also_copy, *source_paths, *_DEFAULTS_DO_MUTMUT]
    return [str(entrada).rstrip("/") for entrada in entradas]


def test_todo_arquivo_da_raiz_citado_no_codigo_vai_para_a_copia_do_mutmut() -> None:
    """A guarda: nenhum literal do repositório nomeia arquivo que a cópia deixa de fora.

    Reprovar aqui é a corrida noturna morrendo na coleta, dito antes da noite.
    O conserto é a entrada no `also_copy` do `pyproject.toml`.
    """
    fontes, rastreados, copia = _repositorio()

    achados = _leituras_fora_da_copia(fontes, rastreados, copia)

    assert achados == [], (
        "arquivos citados no código que o mutmut não copia para `mutants/` — a "
        "corrida de mutação morre na coleta de estatísticas. Inclua no `also_copy` "
        "do pyproject.toml:\n" + "\n".join(achados)
    )


def _repositorio() -> tuple[dict[str, str], list[str], list[str]]:
    """As fontes `.py`, os arquivos rastreados e a cópia declarada do repositório real."""
    raiz = _raiz_do_git()
    rastreados = _rastreados(raiz)
    with (raiz / "pyproject.toml").open("rb") as arquivo:
        config = dict(tomllib.load(arquivo)["tool"]["mutmut"])
    fontes = {
        caminho: (raiz / caminho).read_text(encoding="utf-8")
        for caminho in rastreados
        if caminho.endswith(".py")
    }
    return fontes, rastreados, _copia_declarada(config)


def test_a_varredura_le_o_repositorio_e_nao_uma_lista_vazia() -> None:
    """Sem isto a guarda passaria calada sobre zero fontes e zero arquivos rastreados."""
    fontes, rastreados, _ = _repositorio()

    assert ".claude/hooks/git_guard.py" in rastreados
    assert "tests/unit/test_git_guard.py" in fontes
    assert "scripts/check_harness.py" in fontes


@pytest.mark.parametrize(
    ("retirada", "esperado"),
    [
        # O caso da #87, sobre o repositório de verdade.
        (".claude/hooks", "'.claude' -> .claude/hooks/git_guard.py"),
        # Um não-`.py`: a lista de rastreados não pode encolher para só código.
        (".claude/settings.json", "'.claude' -> .claude/settings.json"),
        # Achado vindo de `scripts/`, não só de `tests/`.
        (".claude/skills", "scripts/check_harness.py:"),
    ],
)
def test_a_guarda_real_acusa_a_entrada_retirada_da_copia(retirada: str, esperado: str) -> None:
    """Controle negativo: sem a entrada, a guarda do repositório real reprova.

    Prova que a varredura do teste acima tem fontes e rastreados de verdade — um
    filtro que a reduzisse a `src/` ou só a `.py` passaria nele calado.
    """
    fontes, rastreados, copia = _repositorio()
    assert retirada in copia

    achados = _leituras_fora_da_copia(
        fontes, rastreados, [entrada for entrada in copia if entrada != retirada]
    )

    assert any(esperado in achado for achado in achados), achados


def test_a_raiz_e_a_do_git_e_nao_a_do_arquivo(monkeypatch: pytest.MonkeyPatch) -> None:
    """Dentro de `mutants/` o `parents[2]` é a cópia; a raiz tem de vir do git."""
    monkeypatch.setattr(sys.modules[__name__], "_REPO_ROOT", _REPO_ROOT / "src")

    assert (_raiz_do_git() / "pyproject.toml").is_file()


def test_o_git_roda_sem_as_variaveis_do_ambiente_do_hook(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Num hook do git, `GIT_DIR`/`GIT_INDEX_FILE` apontariam a lista para outro índice."""
    monkeypatch.setenv("GIT_DIR", str(tmp_path))
    monkeypatch.setenv("GIT_INDEX_FILE", str(tmp_path / "index"))

    assert ".claude/hooks/git_guard.py" in _rastreados(_raiz_do_git())


def test_os_defaults_sao_os_do_mutmut_instalado(monkeypatch: pytest.MonkeyPatch) -> None:
    """`_DEFAULTS_DO_MUTMUT` é cópia à mão; aqui ela é confrontada com o mutmut.

    Um default inventado (`.claude`, digamos) esconderia da guarda exatamente a
    classe da #87. O mutmut só está no extra `mutation`: o teste roda onde ele
    está instalado — a corrida noturna e o ambiente de quem atualiza o mutmut.
    """
    configuracao = pytest.importorskip("mutmut.configuration")
    raiz = _raiz_do_git()
    monkeypatch.chdir(raiz)
    also_copy = _config_do_mutmut()["also_copy"]
    assert isinstance(also_copy, list)

    do_mutmut = [caminho.as_posix() for caminho in configuracao._load_config().also_copy]
    declarados = [str(entrada).rstrip("/") for entrada in also_copy]
    globs = do_mutmut[len(declarados) + len(_DEFAULTS_DO_MUTMUT) :]

    assert do_mutmut[: len(declarados)] == declarados
    assert tuple(do_mutmut[len(declarados) : len(declarados) + len(_DEFAULTS_DO_MUTMUT)]) == (
        _DEFAULTS_DO_MUTMUT
    )
    assert all(fnmatch.fnmatchcase(caminho, _GLOB_DE_RAIZ_DO_MUTMUT) for caminho in globs)


def test_arquivo_do_also_copy_vem_depois_do_diretorio_que_cria_o_pai() -> None:
    """O mutmut copia arquivo com `shutil.copy2`, que não cria o diretório-pai.

    `.claude/settings.json` antes de `.claude/hooks/` quebraria a corrida com
    `FileNotFoundError` antes da coleta (mutmut 3.7.0, `copy_also_copy_files`).
    """
    raiz = _raiz_do_git()
    also_copy = _config_do_mutmut()["also_copy"]
    assert isinstance(also_copy, list)
    vistos: list[str] = []
    orfaos: list[str] = []
    for entrada in (str(item) for item in also_copy):
        pai = entrada.rstrip("/").rpartition("/")[0]
        # `copytree` de um diretório cria os ancestrais dele e a árvore abaixo.
        criado = any(_dentro(d, pai) or _dentro(pai, d) for d in vistos)
        if (raiz / entrada).is_file() and pai and not criado:
            orfaos.append(entrada)
        if (raiz / entrada).is_dir():
            vistos.append(entrada.rstrip("/"))

    assert orfaos == [], f"arquivos do also_copy antes do diretório que cria o pai: {orfaos}"


_RASTREADOS_DE_EXEMPLO = [
    ".claude/hooks/git_guard.py",
    ".claude/settings.json",
    "Makefile",
    "docs/a.md",
    "src/pacote/m.py",
    "src/outro/n.py",
    "tests/unit/test_x.py",
    "test_raiz.py",
]


@pytest.mark.parametrize(
    ("codigo", "copia", "esperado"),
    [
        # O caso da #87: o literal do diretório cobra tudo o que há debaixo dele.
        (
            'R / ".claude" / "hooks"',
            ["docs"],
            [
                "t.py:1 '.claude' -> .claude/hooks/git_guard.py",
                "t.py:1 '.claude' -> .claude/settings.json",
            ],
        ),
        ('R / ".claude"', [".claude/hooks"], ["t.py:1 '.claude' -> .claude/settings.json"]),
        ('R / ".claude"', [".claude/hooks", ".claude/settings.json"], []),
        # Glob: lê o que está sob o prefixo antes do curinga.
        (
            '"./.claude/*/git_guard.py"',
            [],
            [
                "t.py:1 './.claude/*/git_guard.py' -> .claude/hooks/git_guard.py",
                "t.py:1 './.claude/*/git_guard.py' -> .claude/settings.json",
            ],
        ),
        ('"Makefile"', [], ["t.py:1 'Makefile' -> Makefile"]),
        ('"Makefile"', ["Makefile"], []),
        ('"docs\\\\a.md"', [], ["t.py:1 'docs\\\\a.md' -> docs/a.md"]),
        # Normalização: barra final, `./` repetido, espaço nas pontas, os três curingas.
        ('"docs/"', [], ["t.py:1 'docs/' -> docs/a.md"]),
        ('"././Makefile"', [], ["t.py:1 '././Makefile' -> Makefile"]),
        ('" Makefile\\n"', [], ["t.py:1 ' Makefile\\n' -> Makefile"]),
        ('"docs/a?.md"', [], ["t.py:1 'docs/a?.md' -> docs/a.md"]),
        ('"docs/[ab].md"', [], ["t.py:1 'docs/[ab].md' -> docs/a.md"]),
        # Texto com espaço não é caminho, nem quando o corte no curinga deixaria um.
        ('"docs/* não casa"', [], []),
        # Prefixo de nome não é diretório: `Make` não cita o `Makefile`.
        ('"Make"', [], []),
        ('"Makefile"', ["Make"], ["t.py:1 'Makefile' -> Makefile"]),
        # Diretório-pai de um `source_path` não está copiado por inteiro.
        ('"src"', ["src/pacote"], ["t.py:1 'src' -> src/outro/n.py"]),
        ('"src/pacote/m.py"', ["src/pacote"], []),
        # Os defaults do mutmut: `tests/` e o glob `test*.py` da raiz.
        ('"tests/unit"', ["tests"], []),
        ('"test_raiz.py"', [], []),
        # Não é caminho: texto com espaço, raiz não rastreada, caminho sem arquivo.
        ('"Makefile e docs"', [], []),
        ('".env"', [], []),
        ('"docs/nao_existe.md"', [], []),
        ('""', [], []),
        ("42", [], []),
    ],
)
def test_a_varredura_acusa_o_que_a_copia_deixa_de_fora(
    codigo: str, copia: list[str], esperado: list[str]
) -> None:
    assert _leituras_fora_da_copia({"t.py": codigo}, _RASTREADOS_DE_EXEMPLO, copia) == esperado


_CITA_CLAUDE = [
    "t.py:{linha} '.claude' -> .claude/hooks/git_guard.py",
    "t.py:{linha} '.claude' -> .claude/settings.json",
]


# Um módulo que ancora `R` na raiz, como os testes reais fazem com `_REPO_ROOT`.
_RAIZ = "R = Path(__file__).resolve().parents[2]\n"


def _cita_claude(linha: int) -> list[str]:
    return [achado.format(linha=linha) for achado in _CITA_CLAUDE]


@pytest.mark.parametrize(
    ("codigo", "esperado"),
    [
        # A forma da #139: o diretório-pai vem de um helper que recebeu `tmp_path`.
        (
            "def t(tmp_path):\n"
            "    principal, wts, parent = _worktrees(tmp_path)\n"
            '    parent / "wt" / ".claude"\n',
            [],
        ),
        ('def t(tmp_path):\n    tmp_path / ".claude"\n', []),
        ('async def t(tmp_path):\n    tmp_path / ".claude"\n', []),
        ('def t(tmpdir):\n    tmpdir / ".claude"\n', []),
        ('def t(tmp_path_factory):\n    tmp_path_factory.mktemp("x") / ".claude"\n', []),
        # Derivação em cadeia e por cada forma de ligar um nome.
        ('def t(tmp_path):\n    a = tmp_path\n    b = a / "x"\n    b / ".claude"\n', []),
        ('def t(tmp_path):\n    a: Path = tmp_path\n    a / ".claude"\n', []),
        ('def t(tmp_path):\n    a = b = tmp_path\n    b / ".claude"\n', []),
        ('def t(tmp_path):\n    *a, = [tmp_path]\n    a[0] / ".claude"\n', []),
        ('def t(tmp_path):\n    if (a := tmp_path):\n        a / ".claude"\n', []),
        ('def t(tmp_path):\n    for d in tmp_path.iterdir():\n        d / ".claude"\n', []),
        ('def t(tmp_path):\n    [d / ".claude" for d in tmp_path.iterdir()]\n', []),
        (
            'def t():\n    with tempfile.TemporaryDirectory() as d:\n        Path(d) / ".claude"\n',
            [],
        ),
        # A leitura de verdade continua contando — o caso da #87.
        ('def t():\n    R / ".claude" / "hooks"\n', _cita_claude(2)),
        # …mesmo na função que também monta fixture sob `tmp_path`.
        (
            'def t(tmp_path):\n    tmp_path / ".claude"\n    R / ".claude"\n',
            _cita_claude(3),
        ),
        (
            "def t(tmp_path):\n"
            "    shutil.copytree(\n"
            '        R / ".claude",\n'
            '        tmp_path / ".claude",\n'
            "    )\n",
            _cita_claude(3),
        ),
        # A derivação é por função: o mesmo nome em outra função não é tmp.
        (
            'def a(tmp_path):\n    p = tmp_path\ndef b():\n    p / ".claude"\n',
            _cita_claude(4),
        ),
        # Nome que não deriva de tmp não vira derivado por estar na mesma função.
        ('def t(tmp_path):\n    p = R\n    q = tmp_path\n    p / ".claude"\n', _cita_claude(4)),
        # Atribuição a subscrito ou atributo não liga nome nenhum.
        (
            'def t(tmp_path):\n    o.p = tmp_path\n    c["k"] = tmp_path\n    o / ".claude"\n',
            _cita_claude(4),
        ),
        # Fora de uma cadeia `/`, o literal conta mesmo na função de tmp.
        ('def t(tmp_path):\n    open(".claude")\n', _cita_claude(2)),
        # Literal à esquerda da cadeia não está sob tmp.
        ('def t(tmp_path):\n    ".claude" / tmp_path\n', _cita_claude(2)),
        # Fora de função não há derivação: o literal conta.
        ('tmp_path / ".claude"\n', _cita_claude(1)),
        # Na dúvida, a raiz vence: nome que também liga à raiz não é tmp.
        (
            _RAIZ + 'def t(tmp_path):\n    p = tmp_path\n    p = R\n    p / ".claude"\n',
            _cita_claude(5),
        ),
        (
            _RAIZ
            + 'def t(tmp_path):\n    p = tmp_path\n    p = p if c else R\n    p / ".claude"\n',
            _cita_claude(5),
        ),
        (
            _RAIZ + 'def t(tmp_path):\n    b = tmp_path if c else R\n    b / ".claude"\n',
            _cita_claude(4),
        ),
        (
            _RAIZ + 'def t(tmp_path):\n    b = _copia(tmp_path, R)\n    b / ".claude"\n',
            _cita_claude(4),
        ),
        (
            _RAIZ + 'def t(tmp_path):\n    for d, s in [(tmp_path, R)]:\n        s / ".claude"\n',
            _cita_claude(4),
        ),
        # `a, b = x, y` liga elemento a elemento: só `d` é tmp.
        (
            _RAIZ + 'def t(tmp_path):\n    d, s = tmp_path / "c", R\n'
            '    s / ".claude"\n    d / ".claude"\n',
            _cita_claude(4),
        ),
        # A âncora vale também declarada dentro da função.
        (
            "def t(tmp_path):\n    R = Path(__file__).parents[2]\n"
            '    p = tmp_path\n    p = R\n    p / ".claude"\n',
            _cita_claude(5),
        ),
        # Religar a algo que não é tmp nem âncora também tira o nome de tmp.
        (
            'def t(tmp_path):\n    p = tmp_path\n    p = Path.cwd()\n    p / ".claude"\n',
            _cita_claude(4),
        ),
        # A base da cadeia que menciona a raiz não está sob tmp.
        (_RAIZ + 'def t(tmp_path):\n    (tmp_path if c else R) / ".claude"\n', _cita_claude(3)),
        # `p /= …` mantém `p` em tmp: o alvo também é lido.
        ('def t(tmp_path):\n    p = tmp_path\n    p /= "x"\n    p / ".claude"\n', []),
    ],
)
def test_caminho_montado_sob_diretorio_temporario_nao_e_leitura_da_raiz(
    codigo: str, esperado: list[str]
) -> None:
    """Issue #139: fixture sob `tmp_path` não é citação; leitura da raiz continua sendo."""
    assert _leituras_fora_da_copia({"t.py": codigo}, _RASTREADOS_DE_EXEMPLO, []) == esperado


_FIXTURE_DA_84 = "tests/unit/test_worktree_docker.py:"


def test_a_fixture_da_issue_84_nao_e_citacao_e_a_leitura_real_continua(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """O falso positivo que deixou o `develop` vermelho, sobre o arquivo de verdade.

    `test_worktree_docker.py` monta o diretório do devcontainer sob `tmp_path`.
    Sem o filtro a guarda o cobraria no `also_copy` (controle negativo abaixo);
    com ele, não. Com `.claude/hooks` fora da cópia, a mesma varredura ainda
    acusa o `test_git_guard.py` — o caso da #87. O nome do diretório não aparece
    como literal aqui: este arquivo também é varrido.
    """
    fontes, rastreados, copia = _repositorio()
    sem_hooks = [entrada for entrada in copia if entrada != ".claude/hooks"]

    achados = _leituras_fora_da_copia(fontes, rastreados, sem_hooks)

    assert not any(achado.startswith(_FIXTURE_DA_84) for achado in achados), achados
    assert any(
        achado.startswith("tests/unit/test_git_guard.py:")
        and achado.endswith("-> .claude/hooks/git_guard.py")
        for achado in achados
    ), achados

    monkeypatch.setattr(sys.modules[__name__], "_literais_sob_temporario", lambda _: set())
    sem_filtro = _leituras_fora_da_copia(fontes, rastreados, sem_hooks)
    assert any(achado.startswith(_FIXTURE_DA_84) for achado in sem_filtro), sem_filtro


def test_a_copia_declarada_soma_also_copy_source_paths_e_defaults() -> None:
    copia = _copia_declarada({"also_copy": ["docs/", "Makefile"], "source_paths": ["src/x"]})

    assert copia == ["docs", "Makefile", "src/x", *_DEFAULTS_DO_MUTMUT]
