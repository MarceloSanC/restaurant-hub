"""Remove uma worktree paralela e todos os seus artefatos Docker/VS Code.

Verifica sincronização com o remoto antes de apagar qualquer coisa:
  - nenhum commit local à frente de origin/<branch>
  - worktree sem alterações não commitadas

Em seguida, em ordem segura:
  1. Derruba o projeto compose da worktree — o `docker compose down -v` dela,
     pelo rótulo `com.docker.compose.project`: containers, volumes (o banco) e
     redes, sem precisar do arquivo do compose (issue #84). Com o Docker parado,
     avisa: o Postgres segue segurando a `POSTGRES_PORT`, e quem o derruba depois
     é o `make worktree-orphans ARGS=--prune`.
  2. Para e remove containers do devcontainer da worktree (via label
     vsch.local.folder / devcontainer.local_folder) e, com confirmação, os volumes deles.
  3. `git worktree remove <path>`
  4. `git branch -d <branch>` (safe-delete: só remove se mergeada)
  5. `git remote prune origin`
  6. Confere os hooks do git (`pre-commit`/`commit-msg`, um só para todas as
     worktrees): se apontavam para o venv da worktree que saiu, ou para um
     python que não existe mais, religa a partir do checkout principal com
     `scripts/install_hooks.py` (issue #100).

A imagem Docker (`restaurant_hub-app:dev`) é compartilhada entre worktrees.
O script pergunta interativamente se deseja removê-la.

A worktree é achada pela branch checada nela (`git worktree list --porcelain`),
não pelo nome da pasta: pasta criada com slug diferente do da branch não exige
`--path` (issue #81). Sem worktree com a branch, cai no caminho-padrão
`../<repo>-worktrees/<slug>`; `--path` continua forçando o caminho.

Rode do checkout principal, depois do `git pull origin develop`: o `git branch -d`
só apaga a branch que já está mergeada no `develop` local (ou no upstream dela).
Sequência completa de merge e limpeza: docs/GIT-WORKFLOW.md §"Merge e limpeza
da worktree".

Uso:
    uv run python scripts/worktree-rm.py feat/42-add-google-login
    uv run python scripts/worktree-rm.py feat/42-add-google-login --dry-run
    uv run python scripts/worktree-rm.py feat/42-add-google-login --force
    uv run python scripts/worktree-rm.py feat/42-add-google-login --delete-remote

Exit codes:
  0  limpeza concluída com sucesso
  1  verificação falhou (não sincronizado, worktree não encontrada, etc.)
  2  erro de subprocess (docker/git), worktree que o `--force` não conseguiu remover,
     recurso do projeto compose que não saiu, ou hooks do git sem python depois
     do religamento

Recusa (exit 1) a branch checada no checkout principal: o projeto compose dele é
o banco de quem não está saindo.
"""

from __future__ import annotations

import argparse
import contextlib
import importlib.util
import io
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, NoReturn

ROOT = Path(__file__).resolve().parent.parent


def _load_install_hooks() -> ModuleType:
    """`scripts/install_hooks.py`, carregado pelo caminho — é quem sabe ler os hooks."""
    path = Path(__file__).resolve().with_name("install_hooks.py")
    spec = importlib.util.spec_from_file_location("install_hooks", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


install_hooks = _load_install_hooks()

# `python scripts/worktree-rm.py` já põe `scripts/` no `sys.path`; carregado pelo
# caminho (os testes), não — daí a linha. O `worktree_docker` é biblioteca padrão.
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))
import worktree_docker  # noqa: E402

# Git e docker escrevem UTF-8; `text=True` sem `encoding` decodifica pelo locale —
# no Windows, cp1252 —, e a worktree em caminho com acento saía com o caminho
# corrompido (issue #143). Mesmo critério do `worktree-new.py`.
GIT_ENCODING = "utf-8"

# ---------------------------------------------------------------------------
# helpers de IO / processo
# ---------------------------------------------------------------------------


def _force_utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        if stream.encoding and stream.encoding.lower() == "utf-8":
            continue
        # `sys.stdout` é `TextIO` no typeshed; só o `TextIOWrapper` tem `reconfigure`
        # (sob captura do pytest, o stream é outro objeto e fica como está).
        if isinstance(stream, io.TextIOWrapper):
            with contextlib.suppress(OSError):
                stream.reconfigure(encoding="utf-8")


def _run(
    cmd: list[str], *, cwd: Path | None = None, check: bool = True, capture: bool = False
) -> subprocess.CompletedProcess[str]:
    printable = " ".join(cmd)
    if not capture:
        print(f"  $ {printable}")
    try:
        return subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            check=check,
            text=True,
            encoding=GIT_ENCODING,
            errors="replace",
            capture_output=capture,
        )
    except FileNotFoundError as e:
        print(f"ERRO: executável não encontrado: {cmd[0]} ({e})", file=sys.stderr)
        sys.exit(2)
    except subprocess.CalledProcessError as e:
        print(f"ERRO: comando falhou (exit {e.returncode}): {printable}", file=sys.stderr)
        if capture and e.stdout:
            print(e.stdout, file=sys.stderr)
        if capture and e.stderr:
            print(e.stderr, file=sys.stderr)
        sys.exit(2)


def _info(msg: str) -> None:
    print(f"  • {msg}")


def _section(title: str) -> None:
    print()
    print(f"== {title} ==")


def _fail(msg: str, *, exit_code: int = 1) -> NoReturn:
    print(f"ERRO: {msg}", file=sys.stderr)
    sys.exit(exit_code)


def _warn(msg: str) -> None:
    print(f"  AVISO: {msg}", file=sys.stderr)


# ---------------------------------------------------------------------------
# git helpers
# ---------------------------------------------------------------------------


def compute_worktree_path(repo_root: Path, branch: str, override: str | None) -> Path:
    if override:
        return Path(override).resolve()
    slug = branch.replace("/", "-")
    parent = repo_root.parent / f"{repo_root.name}-worktrees"
    return (parent / slug).resolve()


def worktree_list_porcelain() -> str:
    cp = subprocess.run(
        ["git", "worktree", "list", "--porcelain"],
        capture_output=True,
        text=True,
        encoding=GIT_ENCODING,
        errors="replace",
        check=False,
    )
    return cp.stdout


def find_worktree_by_branch(porcelain: str, branch: str) -> Path | None:
    """Caminho da worktree que tem `branch` checada, lido do `--porcelain`.

    Cada bloco do porcelain abre com `worktree <path>` e, se houver branch checada,
    traz `branch refs/heads/<nome>`. A comparação é pelo nome inteiro: `feat/4-x`
    não casa `feat/4-x-y`.
    """
    current: str | None = None
    wanted = f"branch refs/heads/{branch}"
    for line in porcelain.splitlines():
        if line.startswith("worktree "):
            current = line.split(" ", 1)[1]
        elif line == wanted and current is not None:
            return Path(current).resolve()
    return None


def resolve_worktree_path(
    repo_root: Path, branch: str, override: str | None, porcelain: str
) -> Path:
    """`--path` vence; senão a worktree da branch; senão o caminho-padrão do slug."""
    if override:
        return Path(override).resolve()
    found = find_worktree_by_branch(porcelain, branch)
    if found is not None:
        return found
    return compute_worktree_path(repo_root, branch, None)


def check_worktree_registered(wt_path: Path) -> bool:
    cp = subprocess.run(
        ["git", "worktree", "list", "--porcelain"],
        capture_output=True,
        text=True,
        encoding=GIT_ENCODING,
        errors="replace",
        check=False,
    )
    for line in cp.stdout.splitlines():
        if not line.startswith("worktree "):
            continue
        if Path(line.split(" ", 1)[1]).resolve() == wt_path.resolve():
            return True
    return False


def check_sync(wt_path: Path, branch: str) -> None:
    """Falha se a worktree tiver commits não pushados ou arquivos sujos."""
    cp = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=str(wt_path),
        capture_output=True,
        text=True,
        encoding=GIT_ENCODING,
        errors="replace",
        check=False,
    )
    if cp.stdout.strip():
        _fail(
            f"worktree tem alterações não commitadas:\n{cp.stdout.rstrip()}\n"
            "Commite ou descarte antes de remover. Use --force para pular."
        )

    # Verifica se a branch remota existe antes de checar divergência.
    remote_exists = (
        subprocess.run(
            ["git", "show-ref", "--verify", "--quiet", f"refs/remotes/origin/{branch}"],
            check=False,
        ).returncode
        == 0
    )

    if not remote_exists:
        _warn(
            f"origin/{branch} não encontrada — branch nunca publicada ou já deletada "
            "no remoto. Verifique manualmente antes de prosseguir."
        )
        return

    cp = subprocess.run(
        ["git", "log", f"origin/{branch}..HEAD", "--oneline"],
        cwd=str(wt_path),
        capture_output=True,
        text=True,
        encoding=GIT_ENCODING,
        errors="replace",
        check=False,
    )
    if cp.stdout.strip():
        _fail(
            f"branch tem commits não enviados ao remoto:\n{cp.stdout.rstrip()}\n"
            "Faça `git push` ou use --force para pular."
        )

    _info(f"branch {branch} em dia com origin ✓")


# ---------------------------------------------------------------------------
# docker helpers
# ---------------------------------------------------------------------------


def _docker_available() -> bool:
    return (
        subprocess.run(
            ["docker", "info"],
            capture_output=True,
            check=False,
        ).returncode
        == 0
    )


def _path_variants(p: Path) -> list[str]:
    """Retorna variantes de caminho (forward slash e backslash) para filtros Docker."""
    variants: list[str] = []
    for s in (str(p), str(p).replace("\\", "/")):
        if s not in variants:
            variants.append(s)
    try:
        resolved = p.resolve()
        for s in (str(resolved), str(resolved).replace("\\", "/")):
            if s not in variants:
                variants.append(s)
    except OSError:
        pass
    return variants


def find_containers_for_worktree(wt_path: Path) -> list[dict[str, Any]]:
    """Busca containers via labels que o VS Code Dev Containers injeta."""
    found: dict[str, dict[str, Any]] = {}
    label_keys = ("vsch.local.folder", "devcontainer.local_folder")

    for label_key in label_keys:
        for path_variant in _path_variants(wt_path):
            cp = subprocess.run(
                [
                    "docker",
                    "ps",
                    "-a",
                    "--filter",
                    f"label={label_key}={path_variant}",
                    "--format",
                    "{{json .}}",
                ],
                capture_output=True,
                text=True,
                encoding=GIT_ENCODING,
                errors="replace",
                check=False,
            )
            for raw_line in cp.stdout.splitlines():
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue
                cid = data.get("ID") or data.get("Id") or ""
                if cid and cid not in found:
                    found[cid] = data

    return list(found.values())


def get_container_volumes(container_id: str) -> list[str]:
    """Retorna nomes de volumes nomeados montados no container."""
    cp = subprocess.run(
        [
            "docker",
            "inspect",
            container_id,
            "--format",
            '{{range .Mounts}}{{if eq .Type "volume"}}{{.Name}}\n{{end}}{{end}}',
        ],
        capture_output=True,
        text=True,
        encoding=GIT_ENCODING,
        errors="replace",
        check=False,
    )
    return [v.strip() for v in cp.stdout.splitlines() if v.strip()]


def _confirm(prompt: str, expected: str) -> bool:
    """Exibe `prompt`, aguarda input e retorna True só se o usuário digitou `expected`."""
    print()
    print(f"  {prompt}")
    print(f'  Digite exatamente  "{expected}"  para confirmar, ou Enter para pular:')
    try:
        answer = input("  > ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return False
    return answer == expected


def compose_cleanup(wt_path: Path, *, dry_run: bool) -> bool | None:
    """O `docker compose down -v` da worktree, pelo rótulo do projeto (issue #84).

    O `docker compose up -d postgres` dentro da worktree cria o projeto com o nome
    da pasta; sem este passo, o Postgres dele seguia publicando a `POSTGRES_PORT`
    depois da remoção, e a worktree seguinte podia herdar a porta. O rótulo
    dispensa o arquivo do compose e a pasta: vale para a worktree já apagada do
    disco. True = projeto limpo; False = algum recurso não saiu; None = Docker
    indisponível (avisado — nada foi conferido).
    """
    project = worktree_docker.compose_project_name(wt_path)
    try:
        worktree_docker.ensure_daemon()
        if dry_run:
            found = worktree_docker.project_resources(project)
            failures: list[str] = []
        else:
            found, failures = worktree_docker.remove_project(project)
    except worktree_docker.DockerUnavailable as e:
        _warn(
            f"Docker indisponível ({e}).\n"
            f"  O projeto compose `{project}` (o Postgres da worktree e o volume do banco)\n"
            "  NÃO foi derrubado: se existir, segue segurando a POSTGRES_PORT no host.\n"
            "  Quando o Docker voltar, no checkout principal:\n"
            "    make worktree-orphans ARGS=--prune"
        )
        return None
    if found.empty():
        _info(f"projeto compose {project}: nada no Docker")
        return True
    verb = "[dry-run] seria derrubado" if dry_run else "derrubado"
    _info(f"projeto compose {verb}:")
    for line in worktree_docker.describe(project, found):
        print(f"  {line}")
    for failure in failures:
        _warn(f"não saiu — {failure}")
    return not failures


def docker_cleanup(wt_path: Path, *, dry_run: bool) -> bool:  # noqa: PLR0912, PLR0915
    """Projeto compose e devcontainer da worktree; False se algo do compose ficou."""
    compose = compose_cleanup(wt_path, dry_run=dry_run)
    if compose is None:
        return True  # Docker indisponível: já avisado, nada mais a conferir
    if not _docker_available():
        return compose

    # Sem ID, `docker inspect ""`/`docker rm ""` não miram nada; o
    # `find_containers_for_worktree` já descarta esses, e a guarda vale para
    # quem o trocar (issue #143).
    containers: list[dict[str, Any]] = []
    for c in find_containers_for_worktree(wt_path):
        if c.get("ID") or c.get("Id"):
            containers.append(c)
        else:
            _warn(f"container sem ID ignorado: {c.get('Names') or c.get('Name') or '?'}")

    if not containers:
        _info("nenhum container Docker encontrado para esta worktree")
        _info("(se o devcontainer nunca foi aberto para esta worktree, é normal)")
    else:
        # Coleta volumes ANTES de remover os containers.
        all_volumes: set[str] = set()
        for c in containers:
            cid = c.get("ID") or c.get("Id", "")
            all_volumes.update(get_container_volumes(cid))

        # Para e remove containers (sem confirmação — containers são descartáveis).
        for c in containers:
            cid = c.get("ID") or c.get("Id", "")
            name = c.get("Names") or c.get("Name") or cid
            state = c.get("State") or c.get("Status") or ""
            _info(f"container: {name} ({cid[:12]}) [{state}]")
            if not dry_run:
                if "running" in state.lower() or state.lower().startswith("up"):
                    subprocess.run(["docker", "stop", cid], capture_output=True, check=False)
                cp = subprocess.run(
                    ["docker", "rm", cid],
                    capture_output=True,
                    text=True,
                    check=False,
                    encoding=GIT_ENCODING,
                    errors="replace",
                )
                if cp.returncode == 0:
                    _info(f"  → removido: {name}")
                else:
                    _warn(f"  falha ao remover {name}: {cp.stderr.strip()}")

        # Volumes — requer confirmação explícita.
        if all_volumes:
            print()
            print(f"  Volumes encontrados ({len(all_volumes)}):")
            for vol in sorted(all_volumes):
                print(f"    - {vol}")

            if dry_run:
                _info(f"[dry-run] {len(all_volumes)} volume(s) seriam removidos após confirmação")
            elif _confirm(
                "ATENÇÃO: volumes contêm dados persistentes (banco, venv, etc.).\n"
                "  Apagar é irreversível.",
                "apagar volumes",
            ):
                for vol in sorted(all_volumes):
                    cp = subprocess.run(
                        ["docker", "volume", "rm", vol],
                        capture_output=True,
                        text=True,
                        encoding=GIT_ENCODING,
                        errors="replace",
                        check=False,
                    )
                    if cp.returncode == 0:
                        _info(f"volume removido: {vol}")
                    else:
                        _warn(f"falha ao remover {vol}: {cp.stderr.strip()}")
            else:
                _info("volumes mantidos (confirmação não fornecida)")

    # Imagem — requer confirmação explícita.
    image = "restaurant_hub-app:dev"
    cp_img = subprocess.run(
        ["docker", "image", "inspect", image],
        capture_output=True,
        check=False,
    )
    if cp_img.returncode == 0:
        print()
        print(f"  Imagem encontrada: {image}")
        print("  (compartilhada com o checkout principal — só remova se não usar mais)")

        if dry_run:
            _info(f"[dry-run] imagem {image} seria removida após confirmação")
        elif _confirm(
            "Deseja remover a imagem Docker? Precisará rebuildar na próxima vez.",
            "apagar imagens",
        ):
            cp = subprocess.run(
                ["docker", "rmi", image],
                capture_output=True,
                text=True,
                encoding=GIT_ENCODING,
                errors="replace",
                check=False,
            )
            if cp.returncode == 0:
                _info(f"imagem removida: {image}")
            else:
                _warn(f"falha ao remover imagem (em uso?): {cp.stderr.strip()}")
        else:
            _info("imagem mantida (confirmação não fornecida)")
    return compose


# ---------------------------------------------------------------------------
# git cleanup
# ---------------------------------------------------------------------------


def _remove_worktree_dir(wt_path: Path, *, force: bool) -> bool:
    """`git worktree remove` (e, com `force`, a segunda tentativa com `--force`).

    True se a worktree saiu. Sem `force`, a falha aborta o script (exit 1). Com
    `force`, a segunda tentativa pode falhar também — no Windows, "Filename too
    long" apaga a pasta só em parte (medido na prova da issue #100) — e então
    devolve False, para o `main()` não anunciar sucesso.
    """
    cp = subprocess.run(
        ["git", "worktree", "remove", str(wt_path)],
        capture_output=True,
        text=True,
        encoding=GIT_ENCODING,
        errors="replace",
        check=False,
    )
    if cp.returncode == 0:
        _info(f"worktree removida: {wt_path}")
        return True
    if not force:
        _fail(
            f"git worktree remove falhou: {cp.stderr.strip()}\nUse --force para forçar a remoção."
        )
    _warn(f"git worktree remove falhou — tentando --force: {cp.stderr.strip()}")
    forced = subprocess.run(["git", "worktree", "remove", "--force", str(wt_path)], check=False)
    if forced.returncode == 0 and not wt_path.exists():
        _info(f"worktree removida (--force): {wt_path}")
        return True
    _warn(
        f"git worktree remove --force falhou; a pasta ficou no disco: {wt_path}\n"
        "  Caminho longo no Windows: `git config --global core.longpaths true` e\n"
        "  rode de novo, ou apague a pasta à mão e rode `git worktree prune`."
    )
    return False


def remove_worktree_git(
    wt_path: Path,
    branch: str,
    *,
    dry_run: bool,
    delete_remote: bool,
    force: bool,
) -> bool:
    """Remove a worktree e a branch; False se a pasta da worktree ficou no disco.

    Mesmo com a pasta no disco, segue para a branch e o prune; o `main()` confere
    os hooks e sai com 2.
    """
    if dry_run:
        _info(f"[dry-run] git worktree remove {wt_path}")
        _info(f"[dry-run] git branch -d {branch}")
        if delete_remote:
            _info(f"[dry-run] git push origin --delete {branch}")
        _info("[dry-run] git remote prune origin")
        return True

    removed = _remove_worktree_dir(wt_path, force=force)

    # Deleta branch local (safe: -d não remove branch não mergeada).
    cp = subprocess.run(
        ["git", "branch", "-d", branch],
        capture_output=True,
        text=True,
        encoding=GIT_ENCODING,
        errors="replace",
        check=False,
    )
    if cp.returncode != 0:
        _warn(
            f"git branch -d falhou (branch não mergeada localmente?): {cp.stderr.strip()}\n"
            "  Use --force para deletar via `git branch -D`."
        )
        if force:
            subprocess.run(["git", "branch", "-D", branch], check=False)
            _info(f"branch local {branch} deletada (--force)")
    else:
        _info(f"branch local {branch} deletada")

    if delete_remote:
        cp = subprocess.run(
            ["git", "push", "origin", "--delete", branch],
            capture_output=True,
            text=True,
            encoding=GIT_ENCODING,
            errors="replace",
            check=False,
        )
        if cp.returncode == 0:
            _info(f"branch remota origin/{branch} deletada")
        else:
            _warn(f"falha ao deletar branch remota: {cp.stderr.strip()}")

    subprocess.run(
        ["git", "remote", "prune", "origin"],
        capture_output=True,
        text=True,
        encoding=GIT_ENCODING,
        errors="replace",
        check=False,
    )
    _info("refs remotas obsoletas prunadas")
    return removed


# ---------------------------------------------------------------------------
# hooks do git (issue #100)
# ---------------------------------------------------------------------------


def hooks_inside(common_dir: Path, wt_path: Path) -> list[str]:
    """Tipos de hook cujo `INSTALL_PYTHON` mora dentro de `wt_path`."""
    inside: list[str] = []
    root = wt_path.resolve()
    for hook_type in install_hooks.HOOK_TYPES:
        python = install_hooks.hook_python(common_dir / "hooks" / hook_type)
        if python is not None and python.resolve().is_relative_to(root):
            inside.append(hook_type)
    return inside


def run_install_hooks(principal: Path) -> None:
    """`scripts/install_hooks.py` no checkout principal, com o venv dele (`uv run`).

    `--extra dev` porque o `pre-commit` é dependência de dev: sem o `.venv` no
    principal, o `uv run` o cria, e sem o extra ele nasceria sem o pre-commit.
    """
    _run(
        ["uv", "run", "--extra", "dev", "python", "scripts/install_hooks.py"],
        cwd=principal,
        check=False,
    )


def relink_hooks(common_dir: Path, wt_path: Path, inside: list[str], *, dry_run: bool) -> bool:
    """Religa os hooks no checkout principal se dependiam da worktree que saiu.

    Os hooks moram no diretório comum e valem para todas as worktrees. Se o
    `pre-commit install` foi rodado de dentro da worktree que saiu, o
    `INSTALL_PYTHON` aponta para o venv dela, e todo commit de toda worktree
    falha. O critério é o caminho (`inside`), não só a existência do python:
    no Windows o `git worktree remove` pode apagar a pasta só em parte
    ("Filename too long", medido na prova da issue), deixando o `python.exe`
    sem as dependências do pre-commit. Também religa hook cujo python já não
    existia (outra worktree removida antes). Retorna False se, depois de religar, ainda sobrar hook
    morto ou dentro da worktree.
    """
    principal = install_hooks.main_checkout(common_dir)
    if dry_run:
        if inside:
            _info(f"[dry-run] hooks {', '.join(inside)} apontam para dentro da worktree;")
            _info(f"[dry-run] seriam religados em {principal} (scripts/install_hooks.py)")
        else:
            _info("[dry-run] hooks do git não dependem desta worktree")
        return True

    dead = install_hooks.dead_hooks(common_dir)
    if not dead and not inside:
        _info("hooks do git não dependem da worktree removida ✓")
        return True

    for hook_type in inside:
        _warn(f"hook {hook_type} apontava para o venv da worktree removida")
    for hook_type, python in dead:
        _warn(f"hook {hook_type} aponta para {python}, que não existe mais")
    _info(f"religando os hooks a partir do checkout principal ({principal})")
    run_install_hooks(principal)
    still_dead = install_hooks.dead_hooks(common_dir) or hooks_inside(common_dir, wt_path)
    if still_dead:
        _warn(
            "os hooks continuam sem python. Religue à mão no checkout principal:\n"
            f"    cd {principal}\n    {install_hooks.RELINK_HINT}"
        )
        return False
    _info("hooks do git religados ✓")
    return True


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "branch",
        help="Nome completo da branch (ex.: feat/42-add-google-login).",
    )
    parser.add_argument(
        "--path",
        default=None,
        help=(
            "Override do path da worktree (default: a worktree com a branch checada; "
            "sem ela, ../<repo>-worktrees/<slug>)."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Mostra o que seria feito sem executar nenhuma ação.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Pula verificações de sync e força remoção mesmo se não mergeada.",
    )
    parser.add_argument(
        "--delete-remote",
        action="store_true",
        help="Deleta também a branch em origin (git push origin --delete).",
    )
    parser.add_argument(
        "--no-docker",
        action="store_true",
        help="Pula limpeza de containers e volumes Docker.",
    )
    return parser


def main() -> int:
    _force_utf8_stdio()
    args = _build_parser().parse_args()

    # Medido uma vez, antes de remover: o mesmo resultado serve ao dry-run e à remoção.
    _, common_dir = install_hooks.git_dirs()
    # A raiz do checkout principal, não a da worktree de onde rodou (issue #143): é
    # dela que sai o caminho-padrão `../<repo>-worktrees/<slug>`.
    principal = install_hooks.main_checkout(common_dir)
    wt_path = resolve_worktree_path(principal, args.branch, args.path, worktree_list_porcelain())

    _section("1. Localizando worktree")
    if not check_worktree_registered(wt_path):
        _fail(f"worktree não registrada no git: {wt_path}\nVerifique com `git worktree list`.")
    if wt_path.resolve() == principal.resolve():
        _fail(
            f"{args.branch} está no checkout principal ({wt_path}), não numa worktree.\n"
            "O projeto compose dele é o banco do checkout principal — nada foi removido."
        )
    # O compose dá à pasta o nome do projeto; worktree criada à mão numa pasta com o
    # nome do checkout principal (`../x/restaurant-hub`) teria o mesmo projeto, e
    # derrubá-lo apagaria o banco de quem fica.
    project = worktree_docker.compose_project_name(wt_path)
    if not args.no_docker and project == worktree_docker.compose_project_name(principal):
        _fail(
            f"o projeto compose da worktree ({project}) tem o nome do do checkout principal:\n"
            "derrubá-lo apagaria o banco dele — nada foi removido. Para remover só a\n"
            "worktree, rode com --no-docker."
        )
    _info(f"worktree: {wt_path}")
    _info(f"branch:   {args.branch}")
    if args.dry_run:
        print("  [modo dry-run — nenhuma alteração será feita]")

    _section("2. Verificando sincronização com o remoto")
    if args.force:
        _info("--force: verificação de sync pulada")
    elif not wt_path.exists():
        _info("diretório não existe no disco — pulando check de sync")
    else:
        check_sync(wt_path, args.branch)

    docker_ok = True
    if not args.no_docker:
        _section("3. Derrubando o compose da worktree e limpando o devcontainer")
        docker_ok = docker_cleanup(wt_path, dry_run=args.dry_run)

    hooks_in_worktree = hooks_inside(common_dir, wt_path)

    _section("4. Removendo worktree e branch git")
    removed = remove_worktree_git(
        wt_path,
        args.branch,
        dry_run=args.dry_run,
        delete_remote=args.delete_remote,
        force=args.force,
    )

    _section("5. Conferindo os hooks do git")
    hooks_ok = relink_hooks(common_dir, wt_path, hooks_in_worktree, dry_run=args.dry_run)

    print()
    print("=" * 60)
    if args.dry_run:
        print("  [dry-run] nenhuma alteração foi feita")
        print("  Revise acima e rode sem --dry-run quando estiver pronto.")
    elif removed:
        print(f"  ✓ Worktree {args.branch} removida")
        print(f"  ✓ Path: {wt_path}")
    else:
        print(f"  ✗ Worktree {args.branch} NÃO removida — a pasta ficou no disco")
        print(f"  ✗ Path: {wt_path}")
    print("=" * 60)
    print()
    return 0 if hooks_ok and removed and docker_ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
