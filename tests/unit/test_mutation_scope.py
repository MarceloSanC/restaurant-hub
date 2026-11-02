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
A lista aqui é a dos quatro módulos que a issue nomeia; a asserção seguinte cobra
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

import pytest

pytestmark = pytest.mark.unit

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_PYPROJECT = _REPO_ROOT / "pyproject.toml"

# Os quatro módulos que decidem acesso, como a issue #45 os nomeia. Um quinto
# entra aqui com a justificativa ao lado — e só então no `pyproject.toml`.
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
        for no in ast.walk(ast.parse(texto, filename=fonte)):
            if not (isinstance(no, ast.Constant) and isinstance(no.value, str)):
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


def test_a_copia_declarada_soma_also_copy_source_paths_e_defaults() -> None:
    copia = _copia_declarada({"also_copy": ["docs/", "Makefile"], "source_paths": ["src/x"]})

    assert copia == ["docs", "Makefile", "src/x", *_DEFAULTS_DO_MUTMUT]
