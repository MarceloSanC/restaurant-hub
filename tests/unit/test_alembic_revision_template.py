"""A revision que o `alembic revision` gera já passa no gate de ruff — issue #99.

Desde a issue #99 o `make check` roda `ruff check` e `ruff format --check` sobre
`migrations/`. A revision recém-gerada nasce do `migrations/script.py.mako` e
passa pelo hook de pós-escrita do `migrations/alembic.ini`; se um dos dois
produzir arquivo fora do padrão, toda migration nova chega reprovada, e o
caminho fácil vira `noqa` em massa. Medido na issue: o hook (`type = exec` com
`entrypoint`) falhava sem formatar — o arquivo ficava com as aspas simples do
`repr` — e o template deixava duas linhas em branco depois dos imports (I001).

O teste gera uma revision vazia com o `alembic.ini`, o template e o hook reais.
Só o diretório das versions muda, para não sujar `migrations/versions/` nem
criar um segundo head; o `pyproject.toml` vai junto, porque o ruff acha a
configuração subindo a partir do arquivo, como acharia em `migrations/versions/`.

O que a revision vazia pode ter de diagnóstico é só o F401 de `sa` e `op`: o
template os importa para o corpo que quem gera vai escrever, e uma migration
commitada sem corpo deve mesmo reprovar no lint.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

pytestmark = pytest.mark.unit

_REPO_ROOT = Path(__file__).resolve().parents[2]
_MIGRATIONS = _REPO_ROOT / "migrations"

# Os únicos diagnósticos aceitos numa revision sem corpo: os imports que o
# template traz para o corpo que ainda não foi escrito.
_EMPTY_BODY_DIAGNOSTICS = {
    ("F401", "`sqlalchemy` imported but unused"),
    ("F401", "`alembic.op` imported but unused"),
}


@pytest.fixture
def revision_file(tmp_path: Path) -> Path:
    """Uma revision gerada pelo `alembic revision`, fora de `migrations/versions/`."""
    shutil.copy(_REPO_ROOT / "pyproject.toml", tmp_path / "pyproject.toml")
    versions = tmp_path / "versions"
    versions.mkdir()

    config = Config(str(_MIGRATIONS / "alembic.ini"))
    config.set_main_option("script_location", str(_MIGRATIONS))
    # Sem ele, o alembic separa `version_locations` em espaço e vírgula, e um
    # `tmp_path` com espaço viraria dois diretórios.
    config.set_main_option("path_separator", "os")
    config.set_main_option("version_locations", str(versions))
    command.revision(config, message="probe")

    [generated] = versions.glob("*.py")
    return generated


def _ruff(*args: str) -> subprocess.CompletedProcess[str]:
    """O ruff do venv, o mesmo que o `uv run ruff` dos targets do Makefile."""
    return subprocess.run(
        [sys.executable, "-m", "ruff", *args],
        capture_output=True,
        text=True,
        check=False,
    )


def test_generated_revision_is_already_formatted(revision_file: Path) -> None:
    """O `make fmt-check` aprova a revision como o alembic a escreveu."""
    result = _ruff("format", "--check", str(revision_file))
    assert result.returncode == 0, (
        f"a revision recém-gerada reprova no `ruff format --check`: o hook de "
        f"pós-escrita do migrations/alembic.ini não a formatou.\n"
        f"{result.stdout}{result.stderr}\n{revision_file.read_text(encoding='utf-8')}"
    )


def test_generated_revision_only_lacks_its_body(revision_file: Path) -> None:
    """O `make lint` só aponta os imports que esperam o corpo da migration."""
    result = _ruff("check", "--output-format", "json", str(revision_file))
    found = {(item["code"], item["message"]) for item in json.loads(result.stdout)}
    assert found == _EMPTY_BODY_DIAGNOSTICS, (
        f"a revision recém-gerada tem diagnósticos além do F401 de `sa`/`op`: "
        f"{sorted(found - _EMPTY_BODY_DIAGNOSTICS)}. O migrations/script.py.mako "
        f"gera arquivo que o `make lint` reprova.\n"
        f"{revision_file.read_text(encoding='utf-8')}"
    )
