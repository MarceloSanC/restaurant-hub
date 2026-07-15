"""Testes de build_engine (database/connection.py) e configure_logging (logging/config.py).

build_engine é testado com monkeypatch do create_engine do módulo: o pool que
ele configura (pool_size/max_overflow) exige um banco com pool real (Postgres,
cujo driver não é dependência do scaffold), então o unit valida o CONTRATO da
fábrica — URL resolvida e parâmetros de pool — sem abrir conexão.
"""

import logging

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


def _reset_root_logger() -> None:
    root = logging.getLogger()
    for handler in root.handlers[:]:
        root.removeHandler(handler)


def test_configure_logging_aplica_nivel_valido() -> None:
    _reset_root_logger()
    configure_logging("DEBUG")
    assert logging.getLogger().level == logging.DEBUG


def test_configure_logging_nivel_invalido_cai_para_info() -> None:
    _reset_root_logger()
    configure_logging("NIVEL_INEXISTENTE")
    assert logging.getLogger().level == logging.INFO


def test_configure_logging_reduz_verbosidade_de_libs() -> None:
    _reset_root_logger()
    configure_logging("INFO")
    assert logging.getLogger("sqlalchemy.engine").level == logging.WARNING
    assert logging.getLogger("uvicorn.access").level == logging.INFO
