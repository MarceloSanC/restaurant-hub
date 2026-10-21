"""Política de fim de linha do repositório (issue #8): o `.gitattributes` faz o que promete.

**Por que existe: a quebra desta política é silenciosa onde a suíte roda.** No Linux e no
CI (`ubuntu-latest`) o `core.autocrlf` não está ligado, então apagar o `.gitattributes` ou
reordenar uma regra deixa o `make check` inteiro verde. O estrago aparece no Windows, que é
o ambiente de desenvolvimento do projeto (ADR 1.1.0001), com o `core.autocrlf=true` que o
instalador do Git for Windows grava: checkout em CRLF, aviso "LF will be replaced by CRLF"
em todo `git add` e um segundo `git` sem autocrlf (o do MSYS2) lendo a working tree inteira
como modificada. Medido no `develop` em que a política entrou: 518 arquivos e 130.052 linhas.

Duas camadas:

1. **Estado do repositório**, no índice real: todo arquivo rastreado recebe a regra da sua
   classe, texto está em LF no índice e conteúdo que o git lê como binário tem regra
   `binary`. A última é a falha do `9951acd`: um byte NUL fez o git tratar um
   `technical.md` como binário, a normalização foi pulada e o blob entrou em CRLF.
2. **Efeito da política**, num repositório descartável com o `.gitattributes` real, operado
   com a configuração do Git for Windows: o que sai no checkout, o que o `git add` avisa, o
   que um `git` sem autocrlf enxerga e o que acontece com os bytes de um binário.

**`integration`, não `unit`.** O teste roda o binário do git, e o marker `unit` desta suíte
é "sem I/O" (o `test_git_guard.py` injeta o git justamente para continuar unit). Sem git no
PATH, ou fora de um repositório git, o teste falha alto: um gate que se pula sem a
ferramenta é o "verde por não ter olhado" que a Stage 1.2 catalogou.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

# Espelho deliberado das regras do `.gitattributes`, o par "lista explícita + asserção"
# desta suíte (como em `test_mutation_scope.py`). A regra de um binário protege um formato
# que ainda não tem arquivo rastreado: apagá-la lá não muda nada no índice, e só o espelho
# percebe.
_BINARY_SUFFIXES = frozenset(
    {
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".webp",
        ".ico",
        ".pdf",
        ".ttf",
        ".otf",
        ".woff",
        ".woff2",
        ".zip",
        ".gz",
    }
)
_CRLF_SUFFIXES = frozenset({".bat", ".cmd"})

# O atributo efetivo de cada classe, no vocabulário do `git ls-files --eol`
# (git-ls-files(1) §--eol).
_ATTR_TEXT = "text=auto eol=lf"
_ATTR_BINARY = "-text"
_ATTR_CRLF = "text eol=crlf"

# Uma amostra de cada forma de nome que o repositório rastreia: extensão, sem extensão,
# dotfile, subdiretório.
_TEXT_SAMPLES = ("app.py", "docs/nota.md", "Makefile", ".env.example", "uv.lock")
_LF_CONTENT = b"linha 1\nlinha 2\n"

# Variáveis que apontam o git para outro repositório. O git as exporta para os hooks; um
# `make check` rodado de dentro de um hook as herdaria, e o `git add` do sandbox escreveria
# no índice do repositório real.
_GIT_LOCATION_VARS = frozenset(
    {"GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY", "GIT_COMMON_DIR"}
)


def _clean_env(**extra: str) -> dict[str, str]:
    env = {name: value for name, value in os.environ.items() if name not in _GIT_LOCATION_VARS}
    env.update(extra)
    return env


def _git(cwd: Path, *args: str, env: dict[str, str]) -> subprocess.CompletedProcess[bytes]:
    """Roda o git e falha o teste, com o stderr, se ele sair com erro."""
    if shutil.which("git") is None:
        pytest.fail("git não está no PATH: a política de fim de linha só se verifica com o git")
    result = subprocess.run(["git", *args], cwd=cwd, env=env, capture_output=True, check=False)
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", errors="replace")
        pytest.fail(f"`git {' '.join(args)}` saiu com {result.returncode}: {stderr}")
    return result


@dataclass(frozen=True)
class _Entry:
    """Uma linha do `git ls-files --eol`: o caminho, o conteúdo no índice e o atributo."""

    path: str
    index_eol: str  # "lf", "crlf", "mixed", "none", "-text" ou "" (git-ls-files(1))
    attr: str


def _parse_ls_files_eol(raw: bytes) -> list[_Entry]:
    entries = []
    for record in raw.decode("utf-8").split("\0"):
        if not record:
            continue
        meta, path = record.split("\t", 1)
        fields = meta.split()
        entries.append(
            _Entry(
                path=path,
                index_eol=fields[0].removeprefix("i/"),
                attr=" ".join(fields[2:]).removeprefix("attr/"),
            )
        )
    return entries


def _expected_attr(path: str) -> str:
    suffix = Path(path).suffix
    if suffix in _BINARY_SUFFIXES:
        return _ATTR_BINARY
    if suffix in _CRLF_SUFFIXES:
        return _ATTR_CRLF
    return _ATTR_TEXT


def _off_policy(entries: list[_Entry]) -> list[str]:
    return [
        f"{entry.path}: {entry.attr or '(sem atributo: cai no core.autocrlf)'}"
        f" (esperado: {_expected_attr(entry.path)})"
        for entry in entries
        if entry.attr != _expected_attr(entry.path)
    ]


# ---------------------------------------------------------------------------
# Camada 1 — o índice real
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def repo_root() -> Path:
    """A raiz do repositório segundo o próprio git, e não por `parents[2]`.

    O mutmut roda esta suíte numa cópia em `mutants/` (`[tool.mutmut]` do pyproject), que
    não leva o `.gitattributes` nem tem índice. Pelo `--show-toplevel` o teste lê o
    repositório de verdade nos dois cenários, em vez de passar sobre uma lista vazia.
    """
    here = Path(__file__).resolve().parent
    out = _git(here, "rev-parse", "--show-toplevel", env=_clean_env()).stdout
    return Path(out.decode("utf-8").strip())


@pytest.fixture(scope="module")
def tracked(repo_root: Path) -> list[_Entry]:
    """Os arquivos rastreados, como o `git ls-files --eol` os descreve."""
    raw = _git(repo_root, "ls-files", "-z", "--eol", env=_clean_env()).stdout
    entries = _parse_ls_files_eol(raw)
    assert ".gitattributes" in {entry.path for entry in entries}, (
        "o `.gitattributes` não está rastreado: não há política de fim de linha para conferir"
    )
    return entries


def test_every_tracked_file_gets_the_rule_of_its_class(tracked: list[_Entry]) -> None:
    """Todo arquivo rastreado recebe do `.gitattributes` o atributo da sua classe.

    Pega o arquivo apagado (todo caminho fica sem atributo e volta ao `core.autocrlf` de
    cada máquina), a regra geral sem `eol=lf` e a regra que contradiz a classe de um
    arquivo existente (ex.: `*.md -text`).
    """
    wrong = _off_policy(tracked)
    assert not wrong, "arquivos fora da política de fim de linha:\n" + "\n".join(wrong)


def test_text_is_stored_with_lf_in_the_index(tracked: list[_Entry]) -> None:
    """Nenhum texto rastreado está em CRLF (ou misto) no índice.

    Binário declarado fica de fora: os bytes dele são o conteúdo, e um PDF tem CRLF de
    verdade.
    """
    crlf = [
        f"{entry.path}: i/{entry.index_eol}"
        for entry in tracked
        if entry.attr != _ATTR_BINARY and entry.index_eol in {"crlf", "mixed"}
    ]
    assert not crlf, "texto com CRLF no índice (rodar `git add --renormalize .`):\n" + "\n".join(
        crlf
    )


def test_content_git_reads_as_binary_has_a_binary_rule(tracked: list[_Entry]) -> None:
    """O que o git classifica como binário pelo conteúdo tem regra `binary` explícita.

    Os dois casos que isto pega: um formato binário novo sem regra (some do diff e fica à
    mercê da heurística) e um texto que ganhou um byte NUL, a falha do `9951acd`.
    """
    undeclared = [
        entry.path for entry in tracked if entry.index_eol == "-text" and entry.attr != _ATTR_BINARY
    ]
    assert not undeclared, (
        "conteúdo binário sem regra `binary` no `.gitattributes` (formato novo? byte NUL num"
        " texto?):\n" + "\n".join(undeclared)
    )


# ---------------------------------------------------------------------------
# Camada 2 — o efeito da política com a configuração do Git for Windows
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Sandbox:
    """Repositório descartável com o `.gitattributes` real, operado como o Git for Windows.

    A config de sistema e a global ficam de fora (`GIT_CONFIG_NOSYSTEM`, `GIT_CONFIG_GLOBAL`)
    e o `core.autocrlf` vai na linha de comando, que vence qualquer outra fonte: o resultado
    é o mesmo no Linux, no CI e no Windows de quem roda.
    """

    root: Path
    env: dict[str, str]

    def git(self, *args: str, autocrlf: str = "true") -> subprocess.CompletedProcess[bytes]:
        config = ("-c", f"core.autocrlf={autocrlf}", "-c", "core.safecrlf=warn")
        return _git(self.root, *config, *args, env=self.env)

    def write(self, name: str, content: bytes) -> None:
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    def read(self, name: str) -> bytes:
        return (self.root / name).read_bytes()

    def remove(self, *names: str) -> None:
        for name in names:
            (self.root / name).unlink()


@pytest.fixture
def sandbox(tmp_path: Path, repo_root: Path) -> _Sandbox:
    empty_config = tmp_path / "empty.gitconfig"
    empty_config.write_bytes(b"")
    root = tmp_path / "repo"
    root.mkdir()
    box = _Sandbox(
        root=root,
        env=_clean_env(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=str(empty_config)),
    )
    box.git("-c", "init.defaultBranch=main", "init", "-q")
    shutil.copyfile(repo_root / ".gitattributes", root / ".gitattributes")
    box.git("add", ".gitattributes")
    return box


def test_every_declared_suffix_gets_the_rule_of_its_class(sandbox: _Sandbox) -> None:
    """Cada extensão do espelho recebe do `.gitattributes` o atributo da sua classe.

    É o que a camada 1 não vê: hoje não há binário nem arquivo de lote rastreado. Pega a
    regra de binário apagada e a regra geral movida para o fim do arquivo, onde ela
    sobrescreveria as exceções ("a later line overrides an earlier line", gitattributes(5)).
    """
    names = [f"amostra{suffix}" for suffix in sorted(_BINARY_SUFFIXES | _CRLF_SUFFIXES)]
    names += _TEXT_SAMPLES
    for name in names:
        sandbox.write(name, b"x\n")
    sandbox.git("add", "--", *names)
    wrong = _off_policy(_parse_ls_files_eol(sandbox.git("ls-files", "-z", "--eol").stdout))
    assert not wrong, "extensões declaradas fora da classe:\n" + "\n".join(wrong)


def test_windows_checkout_keeps_lf_and_add_raises_no_warning(sandbox: _Sandbox) -> None:
    """O caminho feliz do critério 3 da issue, com `core.autocrlf=true`.

    Texto escrito em LF entra sem o aviso "LF will be replaced by CRLF" e volta do checkout
    em LF, e a working tree resultante não difere do índice.
    """
    for name in _TEXT_SAMPLES:
        sandbox.write(name, _LF_CONTENT)
    added = sandbox.git("add", "--", *_TEXT_SAMPLES)
    assert added.stderr == b"", "`git add` avisou: " + added.stderr.decode("utf-8", "replace")

    sandbox.remove(*_TEXT_SAMPLES)
    sandbox.git("checkout", "--", ".")
    rewritten = [name for name in _TEXT_SAMPLES if sandbox.read(name) != _LF_CONTENT]
    assert not rewritten, f"o checkout com autocrlf=true trocou o fim de linha de {rewritten}"
    assert sandbox.git("diff", "--name-only").stdout == b""


def test_crlf_written_by_an_editor_reaches_the_index_as_lf(sandbox: _Sandbox) -> None:
    """Arquivo que um editor grava em CRLF entra no índice em LF e volta do checkout em LF."""
    sandbox.write("editor.py", b"a = 1\r\nb = 2\r\n")
    sandbox.git("add", "--", "editor.py")
    assert sandbox.git("cat-file", "blob", ":editor.py").stdout == b"a = 1\nb = 2\n"

    sandbox.remove("editor.py")
    sandbox.git("checkout", "--", "editor.py")
    assert sandbox.read("editor.py") == b"a = 1\nb = 2\n"


def test_crlf_worktree_is_unchanged_for_a_git_without_autocrlf(sandbox: _Sandbox) -> None:
    """A regressão do ADR 1.1.0001: dois binários do git, duas configs, a mesma working tree.

    A working tree em CRLF é a de um clone feito antes da política com `autocrlf=true`; o
    `git` do MSYS2 lê essa mesma árvore sem autocrlf. Sem a política, cada arquivo aparece
    inteiro modificado. Com ela, os dois lados normalizam para o mesmo blob.
    """
    for name in _TEXT_SAMPLES:
        sandbox.write(name, _LF_CONTENT)
    sandbox.git("add", "--", *_TEXT_SAMPLES)
    for name in _TEXT_SAMPLES:
        sandbox.write(name, _LF_CONTENT.replace(b"\n", b"\r\n"))

    for autocrlf in ("false", "true"):
        changed = sandbox.git("diff", "--name-only", autocrlf=autocrlf).stdout
        assert changed == b"", f"com autocrlf={autocrlf}, churn fantasma em: {changed.decode()}"


def test_declared_binary_keeps_its_bytes(sandbox: _Sandbox) -> None:
    """Binário quase todo ASCII é guardado e devolvido byte a byte.

    Sem a regra, o `text=auto` lê este PDF como texto e o `git add` tira os CR do blob:
    corrupção silenciosa, porque o checkout não os devolve.
    """
    payload = b"%PDF-1.4\r\n1 0 obj << /Type /Catalog >> endobj\r\n%%EOF\r\n"
    sandbox.write("escala.pdf", payload)
    sandbox.git("add", "--", "escala.pdf")
    assert sandbox.git("cat-file", "blob", ":escala.pdf").stdout == payload

    sandbox.remove("escala.pdf")
    sandbox.git("checkout", "--", "escala.pdf")
    assert sandbox.read("escala.pdf") == payload
