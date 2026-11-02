"""Os recursos Docker das worktrees: projeto compose, portas reservadas e órfãos (issue #84).

Cada worktree sobe o seu Postgres com `docker compose up`, num projeto compose
com o nome da pasta dela (GIT-WORKFLOW §"Por que o devcontainer não conflita
entre worktrees"). Removida a worktree sem `docker compose down -v`, o projeto
fica: o container segue publicando a `POSTGRES_PORT` no host, e a worktree
seguinte, que lia só os `.env` das worktrees registradas, podia receber essa
porta e rodar a suíte contra o banco velho. Este módulo é a fonte única de três
respostas, e os scripts que as usam importam daqui:

- **qual é o projeto compose de uma pasta** (`compose_project_name`) e como
  derrubá-lo pelo rótulo `com.docker.compose.project`, sem o arquivo do compose
  e sem a pasta (`remove_project`) — o `worktree-rm.py`;
- **quais portas do host os containers reservam**, inclusive os parados, que
  voltam a publicá-las no próximo `start` (`published_host_ports`) — o
  `worktree-new.py`;
- **quais projetos são órfãos**: de uma worktree que não existe mais (`main()`,
  `make worktree-orphans`).

**Docker parado.** Cada consulta levanta `DockerUnavailable` em vez de devolver
vazio: "não há container" e "não consegui perguntar" não podem sair iguais —
foi assim que a porta do órfão parecia livre. Quem chama decide e avisa.

Uso:
    python scripts/worktree_docker.py            # lista os órfãos
    python scripts/worktree_docker.py --prune    # e os derruba (containers, volumes, redes)

Exit codes:
  0  listagem (ou limpeza) concluída — com ou sem órfãos
  1  Docker parado ou ausente: nada foi conferido
  2  algum recurso de órfão não saiu no `--prune`
"""

from __future__ import annotations

import argparse
import contextlib
import json
import re
import subprocess
import sys
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_LABEL = "com.docker.compose.project"
WORKING_DIR_LABEL = "com.docker.compose.project.working_dir"
# O VS Code Dev Containers sobe o compose como `<pasta>_devcontainer`.
DEVCONTAINER_SUFFIX = "_devcontainer"
# Teto de cada chamada ao docker: o Docker Desktop iniciando responde devagar, e
# o script não pode ficar pendurado nele.
DOCKER_TIMEOUT = 30

# Pasta de worktree = branch com `/` trocada por `-` (`worktree-new.py`). Os tipos
# espelham `BRANCH_TYPES` do `worktree-new.py` (CONVENTIONS §4).
_WORKTREE_PROJECT_RE = re.compile(
    r"^(feat|fix|refactor|test|docs|style|perf|chore|ci|build|hotfix)-\d+-[a-z0-9]"
)


class DockerUnavailable(Exception):
    """O daemon não respondeu (parado, ausente do PATH ou estourou o tempo)."""


@dataclass
class ProjectResources:
    """O que um projeto compose deixou no Docker."""

    containers: list[str] = field(default_factory=list)
    volumes: list[str] = field(default_factory=list)
    networks: list[str] = field(default_factory=list)

    def empty(self) -> bool:
        return not (self.containers or self.volumes or self.networks)


# ---------------------------------------------------------------------------
# docker
# ---------------------------------------------------------------------------


def docker(*args: str) -> subprocess.CompletedProcess[str]:
    """`docker <args>` capturado; `DockerUnavailable` se o daemon não responde.

    Saída diferente de 0 com o daemon de pé (recurso em uso, já removido) volta
    ao chamador, que decide.
    """
    try:
        cp = subprocess.run(
            ["docker", *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=DOCKER_TIMEOUT,
        )
    except FileNotFoundError as e:
        raise DockerUnavailable("`docker` não está no PATH") from e
    except subprocess.TimeoutExpired as e:
        raise DockerUnavailable(f"`docker {args[0]}` passou de {DOCKER_TIMEOUT}s") from e
    if cp.returncode != 0 and _daemon_down(cp.stderr):
        raise DockerUnavailable(cp.stderr.strip().splitlines()[0] if cp.stderr.strip() else "")
    return cp


def _daemon_down(stderr: str) -> bool:
    """A mensagem do CLI quando não há daemon (Linux, Docker Desktop no Windows/macOS)."""
    text = stderr.lower()
    return any(
        marker in text
        for marker in (
            "cannot connect to the docker daemon",
            "failed to connect to the docker api",
            "error during connect",
            "is the docker daemon running",
        )
    )


def _lines(cp: subprocess.CompletedProcess[str]) -> list[str]:
    return [line.strip() for line in cp.stdout.splitlines() if line.strip()]


def ensure_daemon() -> None:
    """Levanta `DockerUnavailable` se o daemon não responde ao `docker info`."""
    cp = docker("info", "--format", "{{.ServerVersion}}")
    if cp.returncode != 0:
        raise DockerUnavailable(cp.stderr.strip() or f"`docker info` saiu com {cp.returncode}")


# ---------------------------------------------------------------------------
# projeto compose
# ---------------------------------------------------------------------------


def compose_project_name(path: Path) -> str:
    """O nome de projeto que o `docker compose` dá à pasta `path`.

    A regra do compose (`NormalizeProjectName`): minúsculas, só `a-z0-9_-`, sem
    `_`/`-` no começo.
    """
    name = re.sub(r"[^a-z0-9_-]", "", path.name.lower())
    return name.lstrip("_-")


def project_resources(project: str) -> ProjectResources:
    """Containers (inclusive parados), volumes e redes com o rótulo do projeto."""
    label = f"label={PROJECT_LABEL}={project}"
    return ProjectResources(
        containers=_lines(docker("ps", "-a", "--filter", label, "--format", "{{.Names}}")),
        volumes=_lines(docker("volume", "ls", "--filter", label, "--format", "{{.Name}}")),
        networks=_lines(docker("network", "ls", "--filter", label, "--format", "{{.Name}}")),
    )


def remove_project(project: str) -> tuple[ProjectResources, list[str]]:
    """O `docker compose down -v` do projeto, pelo rótulo: sem arquivo e sem pasta.

    Containers saem primeiro (`rm -f` para também os de pé), depois volumes e
    redes, que o container em uso seguraria. Devolve o que achou e as falhas
    (`"<recurso>: <stderr>"`); lista vazia de falhas = projeto limpo.
    """
    found = project_resources(project)
    failures: list[str] = []
    for kind, names, cmd in (
        ("container", found.containers, ("rm", "-f")),
        ("volume", found.volumes, ("volume", "rm")),
        ("rede", found.networks, ("network", "rm")),
    ):
        for name in names:
            cp = docker(*cmd, name)
            if cp.returncode != 0:
                failures.append(f"{kind} {name}: {cp.stderr.strip()}")
    return found, failures


# ---------------------------------------------------------------------------
# portas reservadas
# ---------------------------------------------------------------------------


def published_host_ports() -> set[int]:
    """Portas do host que algum container publica — de pé **ou parado**.

    O `docker ps` não mostra as portas do container parado, mas o `start` dele
    as toma de volta; a fonte é o `HostConfig.PortBindings` do `inspect`.

    O `docker ps` que falha por motivo fora dos marcadores de `_daemon_down`
    (`permission denied` no socket, sem o grupo docker) sairia com a lista
    vazia: o `ensure_daemon` antes faz dele `DockerUnavailable`, não "sem portas".
    """
    ensure_daemon()
    ids = _lines(docker("ps", "-aq"))
    if not ids:
        return set()
    cp = docker("inspect", "--format", "{{json .HostConfig.PortBindings}}", *ids)
    ports: set[int] = set()
    for line in _lines(cp):
        with contextlib.suppress(json.JSONDecodeError):
            bindings = json.loads(line) or {}
            for entries in bindings.values():
                for entry in entries or []:
                    with contextlib.suppress(ValueError, TypeError):
                        ports.add(int(entry.get("HostPort", "")))
    return ports


# ---------------------------------------------------------------------------
# órfãos
# ---------------------------------------------------------------------------


def compose_projects() -> dict[str, set[str]]:
    """Projeto compose → `working_dir`s rotulados, de containers, volumes e redes.

    Só os containers carregam o `working_dir`; volume ou rede que sobrou sem
    container entra com o conjunto vazio.
    """
    projects: dict[str, set[str]] = {}
    fmt = f'{{{{.Label "{PROJECT_LABEL}"}}}}\t{{{{.Label "{WORKING_DIR_LABEL}"}}}}'
    for line in _lines(docker("ps", "-a", "--filter", f"label={PROJECT_LABEL}", "--format", fmt)):
        project, _, working_dir = line.partition("\t")
        projects.setdefault(project, set())
        if working_dir.strip():
            projects[project].add(working_dir.strip())
    label_fmt = f'{{{{.Label "{PROJECT_LABEL}"}}}}'
    for kind in ("volume", "network"):
        cp = docker(kind, "ls", "--filter", f"label={PROJECT_LABEL}", "--format", label_fmt)
        for project in _lines(cp):
            projects.setdefault(project, set())
    return projects


def _under(path: str, parent: Path) -> bool:
    """`path` mora dentro de `parent` — sem diferenciar caixa nem `\\`/`/` (Windows)."""
    norm = path.replace("\\", "/").rstrip("/").lower() + "/"
    base = str(parent).replace("\\", "/").rstrip("/").lower() + "/"
    return norm.startswith(base)


def live_projects(worktrees: Iterable[Path]) -> set[str]:
    """Projetos das worktrees registradas cuja pasta existe (e o do devcontainer delas)."""
    live: set[str] = set()
    for wt in worktrees:
        if wt.is_dir():
            name = compose_project_name(wt)
            live.update({name, name + DEVCONTAINER_SUFFIX})
    return live


def find_orphans(
    projects: dict[str, set[str]], worktrees: Iterable[Path], worktrees_parent: Path
) -> list[str]:
    """Projetos de worktree sem worktree viva, em ordem alfabética.

    É de worktree o projeto com `working_dir` dentro de `../<repo>-worktrees/`,
    ou, sem `working_dir` (só volume ou rede sobrou), com nome no formato da
    pasta de uma branch (`fix-84-...`). Órfão é o que nenhuma worktree registrada
    e presente no disco reivindica. O projeto do checkout principal, fora de
    `worktrees_parent` e sem nome de branch, nunca entra.
    """
    live = live_projects(worktrees)
    orphans = []
    for project, dirs in projects.items():
        if project in live:
            continue
        if any(_under(d, worktrees_parent) for d in dirs) or (
            not dirs and _WORKTREE_PROJECT_RE.match(project)
        ):
            orphans.append(project)
    return sorted(orphans)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _force_utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        if stream.encoding and stream.encoding.lower() == "utf-8":
            continue
        with contextlib.suppress(AttributeError, OSError):
            stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]


def registered_worktrees() -> tuple[Path, list[Path]]:
    """`(checkout principal, worktrees registradas)` do `git worktree list --porcelain`."""
    cp = subprocess.run(
        ["git", "worktree", "list", "--porcelain"],
        capture_output=True,
        text=True,
        check=True,
    )
    paths = [
        Path(line.split(" ", 1)[1])
        for line in cp.stdout.splitlines()
        if line.startswith("worktree ")
    ]
    return paths[0], paths


def describe(project: str, found: ProjectResources) -> list[str]:
    lines = [f"  {project}"]
    for kind, names in (
        ("containers", found.containers),
        ("volumes", found.volumes),
        ("redes", found.networks),
    ):
        if names:
            lines.append(f"    {kind}: {', '.join(names)}")
    return lines


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--prune",
        action="store_true",
        help="Derruba os órfãos listados: containers, volumes (o banco) e redes.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    _force_utf8_stdio()
    args = _build_parser().parse_args(argv)
    principal, worktrees = registered_worktrees()
    parent = principal.parent / f"{principal.name}-worktrees"
    try:
        ensure_daemon()
        orphans = find_orphans(compose_projects(), worktrees, parent)
        if not orphans:
            print("Nenhum projeto compose órfão de worktree.")
            return 0
        print(f"Projetos compose de worktrees que não existem mais ({len(orphans)}):")
        failures: list[str] = []
        for project in orphans:
            if args.prune:
                found, failed = remove_project(project)
                failures.extend(failed)
            else:
                found = project_resources(project)
            print("\n".join(describe(project, found)))
    except DockerUnavailable as e:
        print(
            f"AVISO: Docker indisponível ({e}) — nada foi conferido. Suba o Docker e rode de novo.",
            file=sys.stderr,
        )
        return 1
    if not args.prune:
        print("\nPara derrubar: make worktree-orphans ARGS=--prune")
        return 0
    for failure in failures:
        print(f"AVISO: não saiu — {failure}", file=sys.stderr)
    print("Órfãos derrubados." if not failures else "Limpeza incompleta.")
    return 2 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
