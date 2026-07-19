"""Testes de build_engine (database/connection.py) e configure_logging (logging/config.py).

build_engine é testado com monkeypatch do create_engine do módulo: o pool que
ele configura (pool_size/max_overflow) exige um banco com pool real (Postgres,
cujo driver não é dependência do scaffold), então o unit valida o CONTRATO da
fábrica — URL resolvida e parâmetros de pool — sem abrir conexão.
"""

import logging
from collections.abc import Iterator

import pytest

from restaurant_hub.shared.infrastructure.config.settings import get_settings
from restaurant_hub.shared.infrastructure.database import connection
from restaurant_hub.shared.infrastructure.logging.config import configure_logging

pytestmark = pytest.mark.unit

EXPECTED_POOL_SIZE = 5
EXPECTED_MAX_OVERFLOW = 10


def _spy_create_engine(captured: dict[str, object]) -> object:
    def fake_create_engine(url: str, **kwargs: object) -> str:
        captured["url"] = url
        captured.update(kwargs)
        return "engine-sentinel"

    return fake_create_engine


def test_build_engine_usa_url_explicita_e_pool(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}
    monkeypatch.setattr(connection, "create_engine", _spy_create_engine(captured))

    result = connection.build_engine("postgresql://explicit/db")

    assert result == "engine-sentinel"
    assert captured["url"] == "postgresql://explicit/db"
    assert captured["pool_pre_ping"] is True
    assert captured["pool_size"] == EXPECTED_POOL_SIZE
    assert captured["max_overflow"] == EXPECTED_MAX_OVERFLOW


def test_build_engine_cai_para_url_das_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}
    monkeypatch.setattr(connection, "create_engine", _spy_create_engine(captured))
    monkeypatch.setenv("DATABASE_URL", "postgresql://from-settings/db")
    get_settings.cache_clear()
    try:
        connection.build_engine()
        assert captured["url"] == "postgresql://from-settings/db"
    finally:
        get_settings.cache_clear()


@pytest.fixture
def restore_logging_state() -> Iterator[None]:
    """Salva e restaura o estado global de logging mutado por configure_logging.

    A limpeza de handlers acontece DENTRO do corpo de cada teste (helper
    abaixo): o plugin de logging do pytest re-injeta um handler no root entre
    o setup da fixture e a fase de call, o que tornaria basicConfig no-op.
    """
    root = logging.getLogger()
    saved_handlers = root.handlers[:]
    saved_level = root.level
    saved_sqlalchemy = logging.getLogger("sqlalchemy.engine").level
    saved_uvicorn = logging.getLogger("uvicorn.access").level
    yield
    for handler in root.handlers[:]:
        root.removeHandler(handler)
    for handler in saved_handlers:
        root.addHandler(handler)
    root.setLevel(saved_level)
    logging.getLogger("sqlalchemy.engine").setLevel(saved_sqlalchemy)
    logging.getLogger("uvicorn.access").setLevel(saved_uvicorn)


def _clear_root_handlers() -> None:
    root = logging.getLogger()
    for handler in root.handlers[:]:
        root.removeHandler(handler)


@pytest.mark.usefixtures("restore_logging_state")
def test_configure_logging_aplica_nivel_valido() -> None:
    _clear_root_handlers()
    configure_logging("DEBUG")
    assert logging.getLogger().level == logging.DEBUG


@pytest.mark.usefixtures("restore_logging_state")
def test_configure_logging_nivel_invalido_cai_para_info() -> None:
    _clear_root_handlers()
    configure_logging("NIVEL_INEXISTENTE")
    assert logging.getLogger().level == logging.INFO


@pytest.mark.usefixtures("restore_logging_state")
def test_configure_logging_reduz_verbosidade_de_libs() -> None:
    _clear_root_handlers()
    configure_logging("INFO")
    assert logging.getLogger("sqlalchemy.engine").level == logging.WARNING
    assert logging.getLogger("uvicorn.access").level == logging.INFO


def test_build_engine_fixa_a_sessao_em_utc(monkeypatch: pytest.MonkeyPatch) -> None:
    """O `timezone=UTC` da conexão de produção precisa de gate próprio.

    O psycopg devolve `timestamptz` no fuso da SESSÃO. O mapper normaliza, e o
    `Engine` dos testes fixa o fuso por conta própria — de modo que apagar esta
    linha do `build_engine` não quebrava teste nenhum, apesar de mudar o
    comportamento de produção. Só a prosa protegia.
    """
    capturado: dict[str, object] = {}

    def _fake_create_engine(url: str, **kwargs: object) -> object:
        capturado.update(kwargs)
        return object()

    monkeypatch.setattr(connection, "create_engine", _fake_create_engine)
    connection.build_engine("postgresql+psycopg://x/y")

    connect_args = capturado.get("connect_args")
    assert isinstance(connect_args, dict)
    assert "-c timezone=UTC" in str(connect_args.get("options"))
