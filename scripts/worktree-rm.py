"""Remove uma worktree paralela e todos os seus artefatos Docker/VS Code.

Verifica sincronização com o remoto antes de apagar qualquer coisa:
  - nenhum commit local à frente de origin/<branch>
  - worktree sem alterações não commitadas

Em seguida, em ordem segura:
  1. Para e remove containers Docker da worktree
     (via label vsch.local.folder / devcontainer.local_folder).
  2. Remove volumes Docker associados a esses containers.
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
  2  erro de subprocess (docker/git), ou hooks do git sem python depois do religamento
"""

from __future__ import annotations

import argparse
import contextlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType

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


# ---------------------------------------------------------------------------
# helpers de IO / processo
# ---------------------------------------------------------------------------


def _force_utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        if stream.encoding and stream.encoding.lower() == "utf-8":
            continue
        with contextlib.suppress(AttributeError, OSError):
            stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]


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


def _fail(msg: str, *, exit_code: int = 1) -> None:
    print(f"ERRO: {msg}", file=sys.stderr)
    sys.exit(exit_code)


def _warn(msg: str) -> None:
    print(f"  AVISO: {msg}", file=sys.stderr)


# ---------------------------------------------------------------------------
# git helpers
# ---------------------------------------------------------------------------


def git_top() -> Path:
    cp = _run(["git", "rev-parse", "--show-toplevel"], capture=True)
    return Path(cp.stdout.strip()).resolve()


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


def find_containers_for_worktree(wt_path: Path) -> list[dict]:
    """Busca containers via labels que o VS Code Dev Containers injeta."""
    found: dict[str, dict] = {}
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


def docker_cleanup(wt_path: Path, *, dry_run: bool) -> None:  # noqa: PLR0912, PLR0915
    if not _docker_available():
        _warn("Docker não está rodando ou não está instalado — pulando limpeza Docker.")
        return

    containers = find_containers_for_worktree(wt_path)

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
                    ["docker", "rm", cid], capture_output=True, text=True, check=False
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
                check=False,
            )
            if cp.returncode == 0:
                _info(f"imagem removida: {image}")
            else:
                _warn(f"falha ao remover imagem (em uso?): {cp.stderr.strip()}")
        else:
            _info("imagem mantida (confirmação não fornecida)")


# ---------------------------------------------------------------------------
# git cleanup
# ---------------------------------------------------------------------------


def remove_worktree_git(
    wt_path: Path,
    branch: str,
    *,
    dry_run: bool,
    delete_remote: bool,
    force: bool,
) -> None:
    if dry_run:
        _info(f"[dry-run] git worktree remove {wt_path}")
        _info(f"[dry-run] git branch -d {branch}")
        if delete_remote:
            _info(f"[dry-run] git push origin --delete {branch}")
        _info("[dry-run] git remote prune origin")
        return

    # Remove worktree.
    cp = subprocess.run(
        ["git", "worktree", "remove", str(wt_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    if cp.returncode != 0:
        if force:
            _warn(f"git worktree remove falhou — tentando --force: {cp.stderr.strip()}")
            subprocess.run(
                ["git", "worktree", "remove", "--force", str(wt_path)],
                check=False,
            )
        else:
            _fail(
                f"git worktree remove falhou: {cp.stderr.strip()}\n"
                "Use --force para forçar a remoção."
            )
    else:
        _info(f"worktree removida: {wt_path}")

    # Deleta branch local (safe: -d não remove branch não mergeada).
    cp = subprocess.run(
        ["git", "branch", "-d", branch],
        capture_output=True,
        text=True,
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
        check=False,
    )
    _info("refs remotas obsoletas prunadas")


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

    repo_root = git_top()
    wt_path = resolve_worktree_path(repo_root, args.branch, args.path, worktree_list_porcelain())

    _section("1. Localizando worktree")
    if not check_worktree_registered(wt_path):
        _fail(f"worktree não registrada no git: {wt_path}\nVerifique com `git worktree list`.")
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

    if not args.no_docker:
        _section("3. Limpando containers e volumes Docker")
        docker_cleanup(wt_path, dry_run=args.dry_run)

    # Medido uma vez, antes de remover: o mesmo resultado serve ao dry-run e à remoção.
    _, common_dir = install_hooks.git_dirs()
    hooks_in_worktree = hooks_inside(common_dir, wt_path)

    _section("4. Removendo worktree e branch git")
    remove_worktree_git(
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
    else:
        print(f"  ✓ Worktree {args.branch} removida")
        print(f"  ✓ Path: {wt_path}")
    print("=" * 60)
    print()
    return 0 if hooks_ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
