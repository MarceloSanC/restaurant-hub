"""Unit de `scripts/worktree_docker.py` — o Postgres órfão de uma worktree removida (issue #84).

Removida a worktree sem `docker compose down -v`, o projeto compose dela fica: o
container segue com a `POSTGRES_PORT` publicada, e a worktree seguinte podia
receber a porta e rodar a suíte contra o banco velho. Os testes fixam:

- o nome do projeto é o que o compose dá à pasta;
- `remove_project` derruba containers, volumes e redes **pelo rótulo**, sem a pasta;
- `published_host_ports` conta os containers parados (o `start` toma a porta de volta);
- Docker parado levanta `DockerUnavailable` — nunca devolve "nada" como se tivesse olhado;
- órfão é o projeto de worktree sem worktree viva; o do checkout principal nunca é.

O docker é um falso em memória que responde às linhas de comando que o módulo usa
(`FakeDocker`); o `subprocess.run` real só aparece nos testes de `docker()`.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType

import pytest

pytestmark = pytest.mark.unit

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "worktree_docker.py"

EXIT_LEFTOVERS = 2
DOWN = (
    "failed to connect to the docker API at npipe:////./pipe/dockerDesktopLinuxEngine; "
    "check if the path is correct and if the daemon is running"
)


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("worktree_docker", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


wd = _load()


def _cp(
    stdout: str = "", returncode: int = 0, stderr: str = ""
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(["docker"], returncode, stdout, stderr)


@dataclass
class Container:
    name: str
    project: str | None
    working_dir: str = ""
    ports: dict[str, list[dict[str, str]]] | None = None
    running: bool = True


@dataclass
class FakeDocker:
    """O daemon em memória: containers, volumes e redes com o rótulo do projeto."""

    containers: list[Container] = field(default_factory=list)
    volumes: dict[str, str] = field(default_factory=dict)  # nome → projeto
    networks: dict[str, str] = field(default_factory=dict)
    up: bool = True
    info_error: str | None = None  # daemon que responde, mas recusa (`permission denied`)
    fail_rm: set[str] = field(default_factory=set)
    calls: list[tuple[str, ...]] = field(default_factory=list)

    def __call__(self, *args: str) -> subprocess.CompletedProcess[str]:  # noqa: PLR0911
        self.calls.append(args)
        if not self.up:
            raise wd.DockerUnavailable(DOWN)
        label = self._label(args)
        match args[0], args[1] if len(args) > 1 else "":
            case "info", _:
                if self.info_error:
                    return _cp(returncode=1, stderr=self.info_error)
                return _cp("27.0.0\n")
            case "ps", "-aq":
                return _cp("".join(f"id-{c.name}\n" for c in self.containers))
            case "ps", _:
                # sem `-a`, o `docker ps` não lista o container parado
                selected = [
                    c
                    for c in self.containers
                    if self._matches(c.project, label) and (c.running or "-a" in args)
                ]
                if "{{.Names}}" in args:
                    return _cp("".join(f"{c.name}\n" for c in selected))
                return _cp("".join(f"{c.project}\t{c.working_dir}\n" for c in selected))
            case "inspect", _:
                # a configuração guarda as portas de todo container; o estado de rede,
                # só as do que está de pé
                by_id = {f"id-{c.name}": c for c in self.containers}
                template, ids = args[2], args[3:]
                if template == "{{json .HostConfig.PortBindings}}":
                    return _cp("".join(f"{json.dumps(by_id[i].ports)}\n" for i in ids))
                assert template == "{{json .NetworkSettings.Ports}}", template
                live = [by_id[i].ports if by_id[i].running else {} for i in ids]
                return _cp("".join(f"{json.dumps(ports)}\n" for ports in live))
            case ("volume" | "network") as kind, "ls":
                store = self.volumes if kind == "volume" else self.networks
                selected_names = [n for n, p in store.items() if self._matches(p, label)]
                if "{{.Name}}" in args:
                    return _cp("".join(f"{n}\n" for n in selected_names))
                return _cp("".join(f"{store[n]}\n" for n in selected_names))
            case "rm", "-f":
                return self._remove(args[2], lambda: self._drop_container(args[2]))
            case ("volume" | "network") as kind, "rm":
                store = self.volumes if kind == "volume" else self.networks
                return self._remove(args[2], lambda: store.pop(args[2]))
        raise AssertionError(f"comando inesperado: docker {' '.join(args)}")

    @staticmethod
    def _label(args: tuple[str, ...]) -> str | None:
        for i, arg in enumerate(args[:-1]):
            if arg == "--filter":
                return args[i + 1].removeprefix("label=")
        return None

    @staticmethod
    def _matches(project: str | None, label: str | None) -> bool:
        if label is None:
            return True
        key, _, value = label.partition("=")
        assert key == wd.PROJECT_LABEL
        return project is not None and (not value or project == value)

    def _drop_container(self, name: str) -> None:
        self.containers = [c for c in self.containers if c.name != name]

    def _remove(self, name: str, action: object) -> subprocess.CompletedProcess[str]:
        if name in self.fail_rm:
            return _cp(returncode=1, stderr=f"Error: {name} is in use")
        assert callable(action)
        action()
        return _cp(f"{name}\n")


def _orphan_pg(project: str, working_dir: str, port: str = "5434") -> Container:
    return Container(
        name=f"{project}-postgres-1",
        project=project,
        working_dir=working_dir,
        ports={"5432/tcp": [{"HostIp": "", "HostPort": port}]},
    )


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> FakeDocker:
    fake = FakeDocker()
    monkeypatch.setattr(wd, "docker", fake)
    return fake


# ---------------------------------------------------------------------------
# compose_project_name
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("folder", "expected"),
    [
        ("fix-84-worktree-orphan-postgres-port", "fix-84-worktree-orphan-postgres-port"),
        ("restaurant-hub", "restaurant-hub"),
        ("Feat-1-Foo", "feat-1-foo"),
        ("my.project name", "myprojectname"),
        ("_-x_y", "x_y"),
    ],
)
def test_project_name_is_the_one_compose_gives_the_folder(folder: str, expected: str) -> None:
    assert wd.compose_project_name(Path("/repos") / folder) == expected


# ---------------------------------------------------------------------------
# remove_project — o `down -v` pelo rótulo
# ---------------------------------------------------------------------------


def test_remove_project_takes_containers_volumes_and_networks_of_that_project_only(
    fake: FakeDocker,
) -> None:
    fake.containers = [
        _orphan_pg("fix-85-guard", "/w/fix-85-guard"),
        Container("fix-85-guard-app-1", "fix-85-guard", running=False),
        _orphan_pg("restaurant-hub", "/r/restaurant-hub", port="5432"),
    ]
    fake.volumes = {
        "fix-85-guard_pgdata": "fix-85-guard",
        "restaurant-hub_pgdata": "restaurant-hub",
    }
    fake.networks = {
        "fix-85-guard_default": "fix-85-guard",
        "restaurant-hub_default": "restaurant-hub",
    }

    found, failures = wd.remove_project("fix-85-guard")

    assert failures == []
    assert sorted(found.containers) == ["fix-85-guard-app-1", "fix-85-guard-postgres-1"]
    assert found.volumes == ["fix-85-guard_pgdata"]
    assert found.networks == ["fix-85-guard_default"]
    assert [c.name for c in fake.containers] == ["restaurant-hub-postgres-1"]
    assert fake.volumes == {"restaurant-hub_pgdata": "restaurant-hub"}
    assert fake.networks == {"restaurant-hub_default": "restaurant-hub"}


def test_remove_project_removes_containers_before_volumes_and_networks(fake: FakeDocker) -> None:
    """O volume montado num container existente não sai: a ordem é a do `down -v`."""
    fake.containers = [_orphan_pg("fix-1-a", "/w/fix-1-a")]
    fake.volumes = {"fix-1-a_pgdata": "fix-1-a"}
    fake.networks = {"fix-1-a_default": "fix-1-a"}

    wd.remove_project("fix-1-a")

    removals = [c for c in fake.calls if "rm" in c]
    assert removals == [
        ("rm", "-f", "fix-1-a-postgres-1"),
        ("volume", "rm", "fix-1-a_pgdata"),
        ("network", "rm", "fix-1-a_default"),
    ]


def test_remove_project_reports_what_did_not_go(fake: FakeDocker) -> None:
    fake.volumes = {"fix-1-a_pgdata": "fix-1-a", "fix-1-a_app-venv": "fix-1-a"}
    fake.fail_rm = {"fix-1-a_pgdata"}

    found, failures = wd.remove_project("fix-1-a")

    assert sorted(found.volumes) == ["fix-1-a_app-venv", "fix-1-a_pgdata"]
    assert failures == ["volume fix-1-a_pgdata: Error: fix-1-a_pgdata is in use"]
    assert fake.volumes == {"fix-1-a_pgdata": "fix-1-a"}


def test_project_without_resources_is_empty(fake: FakeDocker) -> None:
    assert wd.project_resources("fix-1-a").empty()
    fake.networks = {"fix-1-a_default": "fix-1-a"}
    assert not wd.project_resources("fix-1-a").empty()


# ---------------------------------------------------------------------------
# published_host_ports — inclusive os containers parados
# ---------------------------------------------------------------------------


def test_published_ports_include_stopped_containers(fake: FakeDocker) -> None:
    fake.containers = [
        _orphan_pg("fix-1-a", "/w/fix-1-a", port="5434"),
        Container(
            "stopped",
            "fix-2-b",
            ports={
                "8000/tcp": [{"HostIp": "0.0.0.0", "HostPort": "8003"}],
                "5432/tcp": [{"HostIp": "127.0.0.1", "HostPort": "5436"}],
            },
            running=False,
        ),
        Container("no-ports", None, ports=None),
        Container("expose-only", None, ports={"9000/tcp": [{"HostIp": "", "HostPort": ""}]}),
    ]

    assert wd.published_host_ports() == {5434, 8003, 5436}


def test_no_containers_means_no_ports_and_no_inspect(fake: FakeDocker) -> None:
    assert wd.published_host_ports() == set()
    assert all(call[0] != "inspect" for call in fake.calls)


# ---------------------------------------------------------------------------
# docker() — Docker parado nunca vira "nada encontrado"
# ---------------------------------------------------------------------------


def _patch_run(monkeypatch: pytest.MonkeyPatch, outcome: object) -> None:
    def _run(*_a: object, **_kw: object) -> subprocess.CompletedProcess[str]:
        if isinstance(outcome, BaseException):
            raise outcome
        assert isinstance(outcome, subprocess.CompletedProcess)
        return outcome

    monkeypatch.setattr(wd.subprocess, "run", _run)


@pytest.mark.parametrize(
    "outcome",
    [
        FileNotFoundError("docker"),
        subprocess.TimeoutExpired(["docker"], 30),
        _cp(returncode=1, stderr=DOWN),
        _cp(
            returncode=1,
            stderr="Cannot connect to the Docker daemon at unix:///var/run/docker.sock",
        ),
        _cp(
            returncode=1, stderr="error during connect: Get http://...: open //./pipe/docker_engine"
        ),
    ],
)
def test_docker_down_raises_instead_of_answering_empty(
    monkeypatch: pytest.MonkeyPatch, outcome: object
) -> None:
    _patch_run(monkeypatch, outcome)
    with pytest.raises(wd.DockerUnavailable):
        wd.docker("ps", "-aq")
    with pytest.raises(wd.DockerUnavailable):
        wd.published_host_ports()


def test_command_error_with_daemon_up_goes_back_to_the_caller(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_run(monkeypatch, _cp(returncode=1, stderr="Error: No such volume: x"))
    assert wd.docker("volume", "rm", "x").returncode == 1


def test_published_ports_with_an_unknown_daemon_error_raise_instead_of_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`permission denied` no socket não está nos marcadores de `_daemon_down`: o `ps`
    sairia com 1 e lista vazia, e o picker perderia as portas dos containers parados
    sem avisar (achado da auditoria de testes).
    """
    denied = "permission denied while trying to connect to the Docker daemon socket"
    _patch_run(monkeypatch, _cp(returncode=1, stderr=denied))
    with pytest.raises(wd.DockerUnavailable, match="permission denied"):
        wd.published_host_ports()


def test_ensure_daemon_fails_on_any_info_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_run(monkeypatch, _cp(returncode=1, stderr="permission denied"))
    with pytest.raises(wd.DockerUnavailable, match="permission denied"):
        wd.ensure_daemon()
    _patch_run(monkeypatch, _cp("27.0.0\n"))
    wd.ensure_daemon()


# ---------------------------------------------------------------------------
# find_orphans — de worktree, sem worktree viva
# ---------------------------------------------------------------------------


def _worktrees(tmp_path: Path, *names: str) -> tuple[Path, list[Path], Path]:
    principal = tmp_path / "restaurant-hub"
    parent = tmp_path / "restaurant-hub-worktrees"
    principal.mkdir()
    paths = [principal]
    for name in names:
        (parent / name).mkdir(parents=True)
        paths.append(parent / name)
    return principal, paths, parent


def test_orphans_are_worktree_projects_without_a_live_worktree(tmp_path: Path) -> None:
    principal, worktrees, parent = _worktrees(tmp_path, "fix-84-orphan-port")
    # registrada mas apagada do disco: o projeto dela é órfão
    worktrees.append(parent / "feat-7-gone")
    projects = {
        "restaurant-hub": {str(principal)},
        "fix-84-orphan-port": {str(parent / "fix-84-orphan-port")},
        "fix-84-orphan-port_devcontainer": {str(parent / "fix-84-orphan-port" / ".devcontainer")},
        # pasta sumiu, container ficou — caminho no formato do Docker Desktop
        "fix-85-guard": {str(parent / "fix-85-guard").replace("/", "\\").upper()},
        "feat-7-gone": {str(parent / "feat-7-gone")},
        # só o volume sobrou: sem working_dir, vale o nome no formato de branch
        "feat-47-3-9-staff": set(),
        # outro repositório, fora da pasta de worktrees
        "other-app": {str(tmp_path / "other-app")},
        "fix-9-elsewhere": {str(tmp_path / "elsewhere" / "fix-9-elsewhere")},
        # volume sem container e com nome que não é de branch
        "postgres-data": set(),
    }

    assert wd.find_orphans(projects, worktrees, parent) == [
        "feat-47-3-9-staff",
        "feat-7-gone",
        "fix-85-guard",
    ]


def test_main_checkout_project_is_never_an_orphan(tmp_path: Path) -> None:
    principal, worktrees, parent = _worktrees(tmp_path)
    assert wd.find_orphans({"restaurant-hub": {str(principal)}}, [], parent) == []
    assert wd.find_orphans({"restaurant-hub": set()}, worktrees, parent) == []


def test_sibling_folder_sharing_the_prefix_is_not_inside_the_worktrees_dir(tmp_path: Path) -> None:
    _, worktrees, parent = _worktrees(tmp_path)
    sibling = str(tmp_path / "restaurant-hub-worktrees-old" / "x")
    assert wd.find_orphans({"x": {sibling}}, worktrees, parent) == []


def test_compose_projects_merges_containers_volumes_and_networks(fake: FakeDocker) -> None:
    fake.containers = [
        _orphan_pg("fix-1-a", "/w/fix-1-a"),
        Container("fix-1-a-app-1", "fix-1-a", working_dir="/w/fix-1-a"),
        Container("loose", None),
    ]
    fake.volumes = {"fix-2-b_pgdata": "fix-2-b", "fix-1-a_pgdata": "fix-1-a"}
    fake.networks = {"fix-3-c_default": "fix-3-c"}

    assert wd.compose_projects() == {
        "fix-1-a": {"/w/fix-1-a"},
        "fix-2-b": set(),
        "fix-3-c": set(),
    }


# ---------------------------------------------------------------------------
# main() — `make worktree-orphans`
# ---------------------------------------------------------------------------


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fake: FakeDocker) -> Path:
    principal, worktrees, parent = _worktrees(tmp_path, "fix-84-orphan-port")
    monkeypatch.setattr(wd, "registered_worktrees", lambda: (principal, worktrees))
    fake.containers = [
        _orphan_pg("restaurant-hub", str(principal), port="5432"),
        _orphan_pg("fix-84-orphan-port", str(parent / "fix-84-orphan-port"), port="5434"),
        _orphan_pg("fix-85-guard", str(parent / "fix-85-guard"), port="5435"),
    ]
    fake.volumes = {
        "fix-85-guard_pgdata": "fix-85-guard",
        "restaurant-hub_pgdata": "restaurant-hub",
    }
    return parent


def test_main_lists_orphans_without_touching_them(
    repo: Path, fake: FakeDocker, capsys: pytest.CaptureFixture[str]
) -> None:
    assert wd.main([]) == 0

    out = capsys.readouterr().out
    assert "fix-85-guard" in out
    assert "fix-85-guard-postgres-1" in out
    assert "fix-85-guard_pgdata" in out
    assert "restaurant-hub" not in out
    assert "fix-84-orphan-port" not in out
    assert "ARGS=--prune" in out
    assert [c.project for c in fake.containers] == [
        "restaurant-hub",
        "fix-84-orphan-port",
        "fix-85-guard",
    ]
    assert all("rm" not in call for call in fake.calls)


def test_main_prune_takes_only_the_orphans(
    repo: Path, fake: FakeDocker, capsys: pytest.CaptureFixture[str]
) -> None:
    assert wd.main(["--prune"]) == 0

    assert [c.project for c in fake.containers] == ["restaurant-hub", "fix-84-orphan-port"]
    assert fake.volumes == {"restaurant-hub_pgdata": "restaurant-hub"}
    assert "Órfãos derrubados." in capsys.readouterr().out


def test_main_prune_lists_but_keeps_a_volume_only_project_found_by_name(
    repo: Path, fake: FakeDocker, capsys: pytest.CaptureFixture[str]
) -> None:
    """Só o volume sobrou e o nome tem formato de branch: pode ser de outro
    repositório com a mesma convenção de pasta (ou de uma worktree viva dele que
    fez `docker compose down` sem `-v`). Sem `working_dir`, nada prova a origem —
    o `--prune` lista, não apaga o banco.
    """
    fake.volumes["fix-1-other-repo_pgdata"] = "fix-1-other-repo"
    fake.networks["fix-1-other-repo_default"] = "fix-1-other-repo"

    assert wd.main(["--prune"]) == 0

    assert "fix-1-other-repo_pgdata" in fake.volumes
    assert "fix-1-other-repo_default" in fake.networks
    assert "fix-85-guard_pgdata" not in fake.volumes
    captured = capsys.readouterr()
    assert "fix-1-other-repo_pgdata" in captured.out
    assert "não derrubados" in captured.err
    assert "fix-1-other-repo" in captured.err


def test_main_prune_with_leftovers_exits_2(
    repo: Path, fake: FakeDocker, capsys: pytest.CaptureFixture[str]
) -> None:
    fake.fail_rm = {"fix-85-guard_pgdata"}

    assert wd.main(["--prune"]) == EXIT_LEFTOVERS
    assert "fix-85-guard_pgdata" in capsys.readouterr().err


def test_main_without_orphans_says_so(
    repo: Path, fake: FakeDocker, capsys: pytest.CaptureFixture[str]
) -> None:
    fake.containers = fake.containers[:2]
    fake.volumes = {}

    assert wd.main([]) == 0
    assert "Nenhum projeto compose órfão" in capsys.readouterr().out


def test_main_with_docker_down_exits_1_and_says_nothing_was_checked(
    repo: Path, fake: FakeDocker, capsys: pytest.CaptureFixture[str]
) -> None:
    fake.up = False

    assert wd.main(["--prune"]) == 1
    captured = capsys.readouterr()
    assert "nada foi conferido" in captured.err
    assert "Nenhum projeto" not in captured.out


# ---------------------------------------------------------------------------
# casos pedidos pela auditoria de testes (mutantes sobreviventes)
# ---------------------------------------------------------------------------


def test_stopped_container_of_the_project_is_listed_and_removed(fake: FakeDocker) -> None:
    fake.containers = [Container("fix-1-a-postgres-1", "fix-1-a", running=False)]

    found, failures = wd.remove_project("fix-1-a")

    assert (found.containers, failures) == (["fix-1-a-postgres-1"], [])
    assert fake.containers == []


def test_blank_working_dir_is_not_a_working_dir(fake: FakeDocker) -> None:
    fake.containers = [Container("fix-9-x-db-1", "fix-9-x", working_dir="")]

    assert wd.compose_projects() == {"fix-9-x": set()}


def test_project_rooted_at_the_worktrees_dir_itself_is_inside_it(tmp_path: Path) -> None:
    _, worktrees, parent = _worktrees(tmp_path)
    assert wd.find_orphans({"p": {str(parent)}}, worktrees, parent) == ["p"]


@pytest.mark.parametrize("name", ["fix-tmp", "fix--1-a", "docs-update-readme", "fix-1"])
def test_volume_only_project_needs_a_branch_shaped_name(tmp_path: Path, name: str) -> None:
    _, worktrees, parent = _worktrees(tmp_path)
    assert wd.find_orphans({name: set()}, worktrees, parent) == []


def test_unreadable_inspect_lines_are_skipped_and_the_rest_counted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    outputs = {
        "info": "27.0.0\n",
        "ps": "a\nb\nc\n",
        "inspect": 'not json\n{"5432/tcp": null}\n{"8000/tcp": [{"HostPort": "8004"}]}\n',
    }
    monkeypatch.setattr(wd, "docker", lambda *args: _cp(outputs[args[0]]))

    assert wd.published_host_ports() == {8004}


def test_main_with_a_refusing_daemon_exits_1_instead_of_no_orphans(
    repo: Path, fake: FakeDocker, capsys: pytest.CaptureFixture[str]
) -> None:
    fake.info_error = "permission denied while trying to connect to the Docker daemon socket"
    fake.containers, fake.volumes = [], {}

    assert wd.main([]) == 1
    captured = capsys.readouterr()
    assert "permission denied" in captured.err
    assert "Nenhum projeto" not in captured.out


def test_registered_worktrees_reads_the_main_checkout_first(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    main = tmp_path / "restaurant-hub"
    other = tmp_path / "restaurant-hub-worktrees" / "fix-1-a"
    porcelain = f"worktree {main}\nHEAD 1\nbranch refs/heads/develop\n\nworktree {other}\nHEAD 2\n"
    monkeypatch.setattr(wd.subprocess, "run", lambda *_a, **_kw: _cp(porcelain))

    assert wd.registered_worktrees() == (main, [main, other])


def test_main_looks_for_orphans_only_inside_the_worktrees_dir(
    repo: Path, fake: FakeDocker, capsys: pytest.CaptureFixture[str]
) -> None:
    """Projeto de outro repositório, ao lado do checkout principal, não é órfão."""
    fake.containers.append(_orphan_pg("other-app", str(repo.parent / "other-app"), port="5440"))

    assert wd.main([]) == 0
    out = capsys.readouterr().out
    assert "fix-85-guard" in out
    assert "other-app" not in out
