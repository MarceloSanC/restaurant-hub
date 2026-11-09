"""Invariantes do `.pre-commit-config.yaml`: hook e gate rodam a mesma ferramenta.

Por que este teste existe (issue #7): o pre-commit é o primeiro gate que se vê, e o
`make check` é o que decide. Quando os dois discordam, o hook ensina errado — e as
duas direções já aconteceram neste repositório:

- **Hook mais frouxo que o gate.** Na Stage 1.1 o hook de ruff, pinado por `rev` em
  `v0.6.9`, aprovou commits que o `make lint` (o ruff que o `uv` resolvia) rejeitava;
  o defeito só aparecia depois do commit.
- **Hook mais estrito que o gate.** O `mirrors-mypy` rodava o mypy 1.11.2 num
  ambiente isolado, sem PyJWT nem argon2, só sobre os arquivos do commit, e reprovava
  o que o `make typecheck` (mypy 2.2.0 sobre o venv e o programa inteiros) aprovava.
  O código de `src/` ganhou contornos para passar nos dois (Stage 2.4, §7).

A causa comum é uma segunda fonte de versão: o `rev` de um repositório remoto e as
`additional_dependencies` de um ambiente isolado são resolvidos fora do `uv.lock` e
se afastam dele sem aviso. A issue #7 tirou essa fonte — todo hook é `local` e chama
a ferramenta pelo `uv run` — e este arquivo impede a volta dela, em duas classes:

1. **Nenhuma versão de ferramenta fora do lock:** nenhum `rev`, nenhuma
   `additional_dependencies`. É o mecanismo anti-drift: sem segunda fonte de versão,
   não há o que derivar.
2. **Cada hook que espelha um target do Makefile roda o comando desse target**, lido
   do próprio Makefile: o mesmo binário, nenhuma flag que mude as regras e, para o
   mypy, o mesmo conjunto de arquivos. Um comando copiado à mão para o YAML seria a
   deriva de volta, agora entre o hook e o Makefile.

Não testar aqui nome, ordem nem o hook de mensagem de commit: nenhum deles é fonte
de versão nem espelha target do `make check`.
"""

from __future__ import annotations

import re
import shlex
from pathlib import Path
from typing import Any

import pytest
import yaml

from tests.unit._makefile import recipe as _recipe

pytestmark = pytest.mark.unit

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PRECOMMIT_CONFIG = _REPO_ROOT / ".pre-commit-config.yaml"

# `uv run <ferramenta>` e `uv run ruff <subcomando>`: os tokens que identificam o
# binário (e, no ruff, o modo). O que vem depois são flags ou os caminhos do target.
_TOOL_PREFIX_LEN = 3
_RUFF_PREFIX_LEN = 4

# Flags que mudam só *como* o ruff roda sobre os arquivos do commit, nunca *quais
# regras* valem. `--force-exclude` faz o ruff respeitar as exclusões da configuração
# também para arquivo passado por nome, que é como o pre-commit passa, e `--fix`
# aplica as correções seguras. Qualquer outra (`--select`, `--ignore`, `--config`)
# faria o hook julgar por regras que não são as do target.
_RUFF_CHECK_FLAGS = frozenset({"--force-exclude", "--fix"})
_RUFF_FORMAT_FLAGS = frozenset({"--force-exclude"})

# Sem `--force-exclude`, o ruff checa todo arquivo passado por nome, até o que a
# configuração exclui; com diretório, como o Makefile passa, ele respeita a
# exclusão. Medido na issue #7: `ruff check --extend-exclude X X` acha o erro de X,
# e com `--force-exclude` ou com o diretório não acha. O pre-commit passa por nome,
# então é a flag que dá ao hook o veredito do target.
_RUFF_REQUIRED_FLAGS = frozenset({"--force-exclude"})

# Tags de `types` que todo arquivo `.py` do repositório carrega. Um filtro `types`
# com qualquer outra (`executable`, por exemplo) tiraria arquivos do hook.
_PYTHON_FILE_TAGS = frozenset({"file", "text", "python"})

# O estágio em que o hook roda no `git commit` e no `pre-commit run` (`commit` é o
# nome legado do mesmo estágio).
_COMMIT_STAGES = frozenset({"pre-commit", "commit"})

# Os hooks que espelham um target do Makefile.
_MIRRORED_HOOKS = ("ruff-format", "ruff", "mypy", "lint-imports")

# Hooks que rodam um script do repositório, e não uma ferramenta de terceiros: o
# `check_commit_msg.py` só importa a biblioteca padrão, então não há versão de
# pacote a derivar do lock, e rodá-lo sem o `uv run` o mantém utilizável antes do
# `uv sync`. Hook novo entra aqui por decisão, editando o teste, nunca por deriva.
_REPO_SCRIPT_HOOKS = frozenset({"check-commit-msg"})


@pytest.fixture(scope="module")
def config() -> dict[str, Any]:
    """O `.pre-commit-config.yaml` parseado."""
    parsed: dict[str, Any] = yaml.safe_load(_PRECOMMIT_CONFIG.read_text(encoding="utf-8"))
    return parsed


@pytest.fixture(scope="module")
def hooks(config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Os hooks de todos os repositórios, por `id` (a unicidade tem teste próprio)."""
    return {hook["id"]: hook for repo in config["repos"] for hook in repo["hooks"]}


def _hook(hooks: dict[str, dict[str, Any]], hook_id: str) -> dict[str, Any]:
    assert hook_id in hooks, (
        f"o hook `{hook_id}` sumiu do .pre-commit-config.yaml — sem ele, o pre-commit "
        f"deixa de checar o que o gate checa"
    )
    return hooks[hook_id]


def _command(hook: dict[str, Any]) -> list[str]:
    """O que o pre-commit executa: `entry` seguido de `args`."""
    return [*shlex.split(hook["entry"]), *hook.get("args", [])]


def _positional(command: list[str], prefix_len: int) -> list[str]:
    """Os argumentos posicionais depois do prefixo: os caminhos que o target cobre."""
    return [token for token in command[prefix_len:] if not token.startswith("-")]


def _passes_filters(filters: dict[str, Any], path: str) -> bool:
    """`path` passa pelos `files` e `exclude` de `filters` (um hook ou o arquivo)?

    Os defaults são os do pre-commit: `files` vazio casa tudo, `exclude` `^$` não
    exclui nada.
    """
    files = filters.get("files", "")
    exclude = filters.get("exclude", "^$")
    return re.search(files, path) is not None and re.search(exclude, path) is None


def _receives(config: dict[str, Any], hook: dict[str, Any], path: str) -> bool:
    """O pre-commit entregaria `path` a este hook?

    Valem os dois níveis de filtro: o `files`/`exclude` do topo do arquivo, que o
    pre-commit aplica antes de todos os hooks, e o do próprio hook. Um
    `exclude: ^tests/` no topo tira `tests/` de todo hook sem tocar em nenhum deles.
    """
    return _passes_filters(config, path) and _passes_filters(hook, path)


def _receives_python(config: dict[str, Any], hook: dict[str, Any], path: str) -> bool:
    """Como `_receives`, para um arquivo `.py`: inclui os filtros por tipo."""
    types_ok = set(hook.get("types", [])) <= _PYTHON_FILE_TAGS
    types_or_ok = "python" in hook.get("types_or", ["python"])
    return _receives(config, hook, path) and types_ok and types_or_ok


def _assert_triggered_by(config: dict[str, Any], hook: dict[str, Any], paths: list[str]) -> None:
    """O hook dispara quando o commit traz qualquer um de `paths`.

    O filtro tem de ser só por caminho: um filtro por tipo deixaria de fora os
    arquivos que decidem o veredito sem ser Python (`pyproject.toml`, `uv.lock`,
    `.importlinter`).
    """
    type_filters = sorted(key for key in ("types", "types_or", "exclude_types") if key in hook)
    assert type_filters == [], (
        f"o hook `{hook['id']}` filtra por tipo ({type_filters}): arquivos que não são "
        f"Python e decidem o veredito deixariam de disparar o hook"
    )
    ignored = [path for path in paths if not _receives(config, hook, path)]
    assert ignored == [], (
        f"um commit só com {ignored} não dispara o hook `{hook['id']}`, mas muda o "
        f"veredito do target que ele espelha"
    )


def test_mirrored_hooks_run_at_commit(
    config: dict[str, Any], hooks: dict[str, dict[str, Any]]
) -> None:
    """Os hooks que espelham o gate rodam no `git commit` e no `pre-commit run`.

    Um `stages: [manual]` (ou `pre-push`) tira o hook do commit sem nenhum sinal, e o
    commit passa pelo que o gate reprova: a direção da Stage 1.1, por outro caminho.
    Sem `stages` no hook, vale o `default_stages` do arquivo; sem os dois, todos.
    """
    off_commit: list[str] = []
    for hook_id in _MIRRORED_HOOKS:
        stages = _hook(hooks, hook_id).get("stages", config.get("default_stages"))
        if stages is not None and not _COMMIT_STAGES & set(stages):
            off_commit.append(f"{hook_id}: {stages}")
    assert off_commit == [], (
        f"hook que espelha o gate fora do estágio de commit: {off_commit}. Ele deixa de "
        f"rodar no `git commit` e no `pre-commit run`, e o commit passa sem ele."
    )


def test_hook_ids_are_unique(config: dict[str, Any]) -> None:
    """Um `id` repetido esconderia um dos hooks das asserções deste arquivo.

    O pre-commit roda os dois, mas o dicionário por `id` guarda só o último. Medido na
    issue #7: um `mirrors-mypy` reintroduzido antes do hook local ficava fora de toda
    asserção que lê o dicionário.
    """
    ids = [hook["id"] for repo in config["repos"] for hook in repo["hooks"]]
    repeated = sorted({hook_id for hook_id in ids if ids.count(hook_id) > 1})
    assert repeated == [], f"hook declarado mais de uma vez: {repeated}"


def test_no_repo_pins_its_own_tool_version(config: dict[str, Any]) -> None:
    """Nenhum repositório com `rev`: a versão de toda ferramenta vem do `uv.lock`.

    O `rev` de um repositório remoto é uma segunda fonte de versão, e nada a amarra
    à do lock: o `uv lock --upgrade` sobe a do projeto e deixa a do hook onde estava.
    Foi assim que o ruff do hook ficou em `v0.6.9` (Stage 1.1) e o mypy em 1.11.2
    contra o 2.2.0 do lock (issue #7).

    Hook de uma ferramenta que **não** está no lock pode, um dia, justificar um
    repositório remoto. Ele entra por decisão, editando este teste, nunca por deriva.
    """
    pinned = [repo["repo"] for repo in config["repos"] if "rev" in repo]
    assert pinned == [], (
        f"repositório com `rev` no .pre-commit-config.yaml: {pinned}. Cada `rev` é uma "
        f"versão de ferramenta fora do uv.lock, que se afasta da do projeto sem aviso. "
        f"Use um hook `local` com `entry: uv run <ferramenta>` (issue #7)."
    )


def test_no_hook_installs_its_own_dependencies(config: dict[str, Any]) -> None:
    """Nenhum hook com `additional_dependencies`: nada se resolve fora do lock.

    `additional_dependencies` monta um ambiente isolado, resolvido quando o hook se
    instala. O do `mirrors-mypy` tinha seis pacotes, e nem o PyJWT nem o argon2
    estavam entre eles: as duas libs viravam `Any`, e o hook reprovava
    `no-any-return` onde o `make typecheck` via `str` e `Literal[True]` (Stage 2.4,
    §7). Um hook `local` com `language: python` e esta chave reabriria o defeito.

    Varre a configuração, e não o dicionário por `id`: um hook repetido ficaria
    escondido atrás do outro de mesmo `id`.
    """
    isolated = sorted(
        hook["id"]
        for repo in config["repos"]
        for hook in repo["hooks"]
        if hook.get("additional_dependencies")
    )
    assert isolated == [], (
        f"hook com `additional_dependencies`: {isolated}. É um ambiente com versões "
        f"resolvidas fora do uv.lock; rode a ferramenta do projeto com `uv run` (issue #7)."
    )


def test_mypy_hook_runs_exactly_make_typecheck(hooks: dict[str, dict[str, Any]]) -> None:
    """O hook de mypy roda o comando do `make typecheck`, sobre o programa inteiro.

    O mesmo comando, e não só o mesmo mypy: a versão igual não basta. Com a lista de
    arquivos do commit (o default do pre-commit), o mypy checa esses arquivos e o que
    eles importam, mas não quem importa **deles**. Medido na issue #7: trocar a
    assinatura de `Clock.now` passava no hook em modo arquivo e dava 18 erros em 11
    arquivos no `make typecheck`, com o mesmo mypy 2.2.0.
    """
    hook = _hook(hooks, "mypy")
    typecheck = _recipe("typecheck")
    assert [_command(hook)] == typecheck, (
        f"o hook de mypy roda {_command(hook)}, e o `make typecheck` roda {typecheck}. "
        f"Hook e target precisam do mesmo comando, senão julgam coisas diferentes."
    )
    assert hook.get("pass_filenames") is False, (
        "o hook de mypy precisa de `pass_filenames: false`: com a lista de arquivos do "
        "commit ele não olha para quem importa o que mudou, e aprova o que o "
        "`make typecheck` reprova"
    )


def test_mypy_hook_triggers_on_every_input_of_its_verdict(
    config: dict[str, Any], hooks: dict[str, dict[str, Any]]
) -> None:
    """O hook dispara sempre que muda algo que decide o veredito do `make typecheck`.

    Com `pass_filenames: false` o pre-commit ainda só roda o hook se algum arquivo do
    commit passar pelo filtro. Ficam de fora, se o filtro os esquecer: um caminho que
    o target checa (o antigo `files: ^src/` deixava `tests/fakes/` sem hook), a
    configuração do mypy (`[tool.mypy]` no `pyproject.toml`) e o lock, porque o
    commit que sobe o mypy ou um pacote tipado é justamente o que muda o veredito.
    """
    hook = _hook(hooks, "mypy")
    [typecheck] = _recipe("typecheck")
    checked = _positional(typecheck, _TOOL_PREFIX_LEN)
    assert checked, f"o `make typecheck` não nomeia caminho nenhum: {typecheck}"
    inputs = [f"{path.rstrip('/')}/module.py" for path in checked]
    _assert_triggered_by(config, hook, [*inputs, "pyproject.toml", "uv.lock"])


@pytest.mark.parametrize(
    ("hook_id", "target", "allowed_flags"),
    [
        pytest.param("ruff", "lint", _RUFF_CHECK_FLAGS, id="ruff-check-vs-make-lint"),
        pytest.param("ruff-format", "fmt", _RUFF_FORMAT_FLAGS, id="ruff-format-vs-make-fmt"),
        pytest.param(
            "ruff-format", "fmt-check", _RUFF_FORMAT_FLAGS, id="ruff-format-vs-make-fmt-check"
        ),
    ],
)
def test_ruff_hooks_run_the_ruff_of_their_make_target(
    config: dict[str, Any],
    hooks: dict[str, dict[str, Any]],
    hook_id: str,
    target: str,
    allowed_flags: frozenset[str],
) -> None:
    """Os hooks de ruff rodam o ruff do target, sem mudar regra nem encolher escopo.

    O hook recebe os arquivos do commit. O lint e a formatação são por arquivo, então
    o veredito sobre cada arquivo é o do target desde que três coisas valham, e são
    elas que se cobram aqui: o mesmo binário e subcomando (`uv run ruff ...`, a
    versão do lock), nenhuma flag que mude as regras e um filtro que entregue ao hook
    todo diretório que o target cobre. O `ruff-format` é cobrado contra os dois
    targets de formatação: o `make fmt`, que é como o projeto formata, e o
    `make fmt-check`, que é como o `make check` confere a formatação (issue #99,
    `docs/runbooks/validate-ci-gate.md` §Class 2).
    """
    hook = _hook(hooks, hook_id)
    command = _command(hook)
    prefix = command[:_RUFF_PREFIX_LEN]
    recipe = _recipe(target)
    matching = [line for line in recipe if line[:_RUFF_PREFIX_LEN] == prefix]
    assert len(matching) == 1, (
        f"o hook `{hook_id}` roda {prefix}, e o `make {target}` precisa ter exatamente "
        f"um comando que comece assim; tem {recipe}. O hook chama o ruff do projeto "
        f"pelo `uv run`, como o target."
    )

    extra = sorted(set(command[_RUFF_PREFIX_LEN:]) - allowed_flags)
    assert extra == [], (
        f"o hook `{hook_id}` passa {extra} ao ruff: flag que muda as regras faz o hook "
        f"julgar diferente do `make {target}`"
    )
    missing = sorted(_RUFF_REQUIRED_FLAGS - set(command[_RUFF_PREFIX_LEN:]))
    assert missing == [], (
        f"o hook `{hook_id}` precisa de {missing}: o pre-commit passa os arquivos por "
        f"nome, e sem a flag o ruff checa até o que a configuração exclui, que o "
        f"`make {target}` (por diretório) pula"
    )

    directories = _positional(matching[0], _RUFF_PREFIX_LEN)
    assert directories, f"o `make {target}` não nomeia caminho nenhum: {matching[0]}"
    uncovered = [
        path
        for path in directories
        if not _receives_python(config, hook, f"{path.rstrip('/')}/m.py")
    ]
    assert uncovered == [], (
        f"o hook `{hook_id}` não recebe arquivos de {uncovered}, que o `make {target}` "
        f"cobre: o commit passaria no hook e reprovaria no gate"
    )


def test_lint_imports_hook_runs_exactly_make_import_check(
    config: dict[str, Any], hooks: dict[str, dict[str, Any]]
) -> None:
    """O hook de import-linter roda o comando do `make import-check`.

    Já era assim antes da issue #7 — é o padrão que ela estendeu aos outros hooks. Fica
    cobrado aqui porque a mesma deriva o alcançaria: com `entry: lint-imports`, sem o
    `uv run`, o console script viria do PATH de quem commita, numa versão que o lock
    não controla. E o hook dispara também pelo `.importlinter`: um commit que só muda
    um contrato muda o veredito do target.
    """
    hook = _hook(hooks, "lint-imports")
    import_check = _recipe("import-check")
    assert [_command(hook)] == import_check, (
        f"o hook de import-linter roda {_command(hook)}, e o `make import-check` roda "
        f"{import_check}"
    )
    assert hook.get("pass_filenames") is False, (
        "o lint-imports analisa o grafo inteiro e não aceita lista de arquivos: o hook "
        "precisa de `pass_filenames: false`"
    )
    _assert_triggered_by(config, hook, ["src/restaurant_hub/module.py", ".importlinter"])


def test_every_tool_hook_runs_through_uv_run(config: dict[str, Any]) -> None:
    """Todo hook, e não só os que espelham um target, roda a ferramenta pelo `uv run`.

    Os testes de espelho cobram os hooks de `_MIRRORED_HOOKS`. Um hook novo fora dessa
    lista (um segundo ruff com `entry: ruff check`, por exemplo) traria a ferramenta
    do PATH de quem commita, numa versão que o lock não controla, sem reprovar nada:
    medido na auditoria de testes da issue #7. `language: system` é o que faz o
    `entry` rodar no ambiente do projeto; outra linguagem monta um ambiente próprio.
    """
    outside_lock = sorted(
        f"{hook['id']}: language={hook.get('language')!r}, entry={hook['entry']!r}"
        for repo in config["repos"]
        for hook in repo["hooks"]
        if hook["id"] not in _REPO_SCRIPT_HOOKS
        and (hook.get("language") != "system" or shlex.split(hook["entry"])[:2] != ["uv", "run"])
    )
    assert outside_lock == [], (
        f"hook que não roda a ferramenta pelo `uv run` em `language: system`: "
        f"{outside_lock}. A versão dele vem de fora do uv.lock (issue #7)."
    )
