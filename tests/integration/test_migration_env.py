"""`migrations/env.py` migra o banco que o chamador escolheu — issue #86.

A precedência que o `env.py` documenta, medida contra um Postgres real:

1. `config.attributes["database_url"]` (chamador in-process) vence o ambiente;
2. sem ela, a `DATABASE_URL` do ambiente — lida sem o cache do `get_settings()`
   — e é o que a CLI (`make migrate`, deploy) usa;
3. a `sqlalchemy.url` no `Config`, posta pelo código ou declarada num
   `alembic.ini`, é recusada antes de qualquer conexão.

Cada teste migra um banco **descartável** (`<banco da suíte>_issue86`), criado e
dropado aqui, no mesmo servidor do banco da suíte. Um `env.py` que ignorasse a
URL do chamador migraria o banco da suíte — já em `head`, então no-op — e o
descartável ficaria vazio: é essa diferença que as asserções leem.

E o logging (finding F-A da #26): in-process, com `configure_logger=False`, o
root logger do chamador não muda; pela CLI, o `fileConfig` segue valendo.
"""

import logging
import os
import subprocess
import sys
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, create_engine, make_url, text

from restaurant_hub.shared.infrastructure.config.settings import get_settings
from tests.conftest import _ALEMBIC_INI, _REPO_ROOT, alembic_config

pytestmark = [pytest.mark.integration]


@pytest.fixture
def scratch_url(engine: Engine, database_url: str) -> Iterator[str]:
    """URL de um banco vazio, ao lado do da suíte, dropado no teardown."""
    url = make_url(database_url)
    nome = f"{url.database}_issue86"
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conexao:
        conexao.execute(text(f'DROP DATABASE IF EXISTS "{nome}" WITH (FORCE)'))
        conexao.execute(text(f'CREATE DATABASE "{nome}"'))
    try:
        yield url.set(database=nome).render_as_string(hide_password=False)
    finally:
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conexao:
            conexao.execute(text(f'DROP DATABASE IF EXISTS "{nome}" WITH (FORCE)'))


def _revisao(url: str) -> str | None:
    """A revisão gravada em `alembic_version`, ou `None` se o banco nunca migrou."""
    engine = create_engine(url)
    try:
        with engine.connect() as conexao:
            if conexao.execute(text("SELECT to_regclass('alembic_version')")).scalar() is None:
                return None
            return conexao.execute(text("SELECT version_num FROM alembic_version")).scalar()
    finally:
        engine.dispose()


def _tem_tabela(url: str, tabela: str) -> bool:
    engine = create_engine(url)
    try:
        with engine.connect() as conexao:
            return conexao.execute(text(f"SELECT to_regclass('{tabela}')")).scalar() is not None
    finally:
        engine.dispose()


def _head() -> str:
    head = ScriptDirectory.from_config(Config(str(_ALEMBIC_INI))).get_current_head()
    assert head is not None
    return head


# ---------------------------------------------------------------------------
# 1. A URL do chamador
# ---------------------------------------------------------------------------


@pytest.mark.slow
def test_upgrade_e_downgrade_rodam_na_url_do_chamador(scratch_url: str, database_url: str) -> None:
    """Critério 1 da #86 — o `Config` que traz a URL migra **esse** banco, nos dois sentidos."""
    config = alembic_config(scratch_url)

    command.upgrade(config, "head")
    assert _revisao(scratch_url) == _head()
    assert _tem_tabela(scratch_url, "users")

    command.downgrade(config, "base")
    assert _revisao(scratch_url) is None
    assert not _tem_tabela(scratch_url, "users")

    # O banco da suíte, que é o da `DATABASE_URL`, não foi tocado.
    assert _revisao(database_url) == _head()


def test_url_do_chamador_vence_o_ambiente(
    scratch_url: str, database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Com o ambiente apontando para o banco da suíte, a URL do chamador ainda vence."""
    monkeypatch.setenv("DATABASE_URL", database_url)

    command.upgrade(alembic_config(scratch_url), "head")

    assert _revisao(scratch_url) == _head()


# ---------------------------------------------------------------------------
# 2. Sem URL do chamador: o ambiente, sem cache
# ---------------------------------------------------------------------------


@pytest.fixture
def get_settings_limpo() -> Iterator[None]:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_sem_url_do_chamador_vale_o_ambiente_e_nao_o_cache(
    scratch_url: str,
    database_url: str,
    monkeypatch: pytest.MonkeyPatch,
    get_settings_limpo: None,
) -> None:
    """O fallback lê a `DATABASE_URL` de agora, não a que o `get_settings()` guardou.

    O cache fica com a URL da suíte e o ambiente passa a apontar o descartável: um
    `env.py` que lesse o cache migraria o banco da suíte (no-op) e o descartável
    ficaria vazio.
    """
    monkeypatch.setenv("DATABASE_URL", database_url)
    assert get_settings().database_url == database_url
    monkeypatch.setenv("DATABASE_URL", scratch_url)
    config = alembic_config(scratch_url)
    del config.attributes["database_url"]

    command.upgrade(config, "head")

    assert _revisao(scratch_url) == _head()


@pytest.mark.slow
def test_cli_migra_a_database_url_do_ambiente(scratch_url: str) -> None:
    """Critério 2 da #86 — `alembic -c migrations/alembic.ini upgrade head`, como no deploy.

    E a CLI continua configurando o logging pelo `alembic.ini`: o `INFO` do
    Alembic chega ao stderr pelo handler `console` do `fileConfig`.
    """
    resultado = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "migrations/alembic.ini", "upgrade", "head"],
        cwd=_REPO_ROOT,
        env={**os.environ, "DATABASE_URL": scratch_url},
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )

    assert resultado.returncode == 0, resultado.stderr
    assert _revisao(scratch_url) == _head()
    assert "INFO  [alembic.runtime.migration]" in resultado.stderr


# ---------------------------------------------------------------------------
# 3. A `sqlalchemy.url` do `Config` é recusada
# ---------------------------------------------------------------------------


def _config_com_url_no_ini(tmp_path: Path, url: str) -> Config:
    """Um `alembic.ini` de deploy que declarasse a URL — o risco da "Incerteza" da #86."""
    ini = tmp_path / "alembic.ini"
    original = _ALEMBIC_INI.read_text(encoding="utf-8")
    ini.write_text(
        original.replace(
            "[alembic]\n", f"[alembic]\nsqlalchemy.url = {url.replace('%', '%%')}\n", 1
        ),
        encoding="utf-8",
    )
    config = Config(str(ini))
    config.set_main_option("script_location", str(_REPO_ROOT / "migrations"))
    config.attributes["configure_logger"] = False
    return config


def _config_com_set_main_option(_tmp_path: Path, url: str) -> Config:
    """O canal antigo, que a #86 ignorava em silêncio."""
    config = alembic_config(url)
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return config


@pytest.mark.parametrize(
    "montar", [_config_com_url_no_ini, _config_com_set_main_option], ids=["ini", "set_main_option"]
)
def test_sqlalchemy_url_no_config_e_recusada(
    montar: Callable[[Path, str], Config],
    scratch_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Recusada antes de conectar — nem o banco dela nem o do ambiente migram."""
    monkeypatch.setenv("DATABASE_URL", scratch_url)
    config = montar(tmp_path, scratch_url)

    with pytest.raises(RuntimeError, match=r"sqlalchemy\.url"):
        command.upgrade(config, "head")

    assert _revisao(scratch_url) is None


@pytest.mark.parametrize("invalida", ["", 5432])
def test_url_do_chamador_invalida_e_recusada(invalida: object, scratch_url: str) -> None:
    """Uma URL vazia (ou que não é texto) não cai em silêncio no ambiente."""
    config = alembic_config(scratch_url)
    config.attributes["database_url"] = invalida

    with pytest.raises(RuntimeError, match="database_url"):
        command.upgrade(config, "head")


# ---------------------------------------------------------------------------
# 4. Logging (finding F-A da #26)
# ---------------------------------------------------------------------------


def test_comando_in_process_nao_reconfigura_o_root_logger(scratch_url: str) -> None:
    """Handlers e nível do root logger saem do `command.upgrade` como entraram.

    O `fileConfig(alembic.ini)` trocaria os handlers pelo `console` (stderr) e
    poria o nível em `WARN`. O nível de partida aqui é `DEBUG` — diferente do
    `WARN` do ini — para que a troca seja visível.
    """
    root = logging.getLogger()
    nivel_original = root.level
    root.setLevel(logging.DEBUG)
    try:
        handlers_antes = list(root.handlers)

        command.upgrade(alembic_config(scratch_url), "head")

        assert root.handlers == handlers_antes
        assert root.level == logging.DEBUG
    finally:
        root.setLevel(nivel_original)
