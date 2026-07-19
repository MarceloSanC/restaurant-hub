"""Testes de Settings e get_settings (shared/infrastructure/config/settings.py)."""

import pytest

from restaurant_hub.shared.infrastructure.config.settings import Settings, get_settings

pytestmark = pytest.mark.unit

DEFAULT_PORT = 8000


def _isolate_ambient_env(monkeypatch: pytest.MonkeyPatch) -> None:
    # pydantic-settings é case-insensitive: PORT/HOST/DEBUG etc. da máquina
    # ou do CI vazariam para dentro do teste de defaults.
    for field in ("APP_NAME", "DEBUG", "DATABASE_URL", "HOST", "PORT", "LOG_LEVEL"):
        monkeypatch.delenv(field, raising=False)


def test_defaults_permitem_iniciar_sem_env(monkeypatch: pytest.MonkeyPatch) -> None:
    _isolate_ambient_env(monkeypatch)
    settings = Settings(_env_file=None)
    assert settings.app_name == "restaurant_hub"
    assert settings.debug is False
    assert settings.port == DEFAULT_PORT
    assert settings.log_level == "INFO"
    # O esquema carrega o driver (Stage 2.3). `postgresql://` sozinho resolveria
    # para o psycopg2, que o projeto não declara — a asserção fixa o driver
    # nomeado para que voltar ao esquema genérico quebre aqui, e não em runtime.
    assert settings.database_url.startswith("postgresql+psycopg://")


def test_variavel_de_ambiente_sobrescreve_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_NAME", "from-env")
    monkeypatch.setenv("DEBUG", "true")
    settings = Settings(_env_file=None)
    assert settings.app_name == "from-env"
    assert settings.debug is True


def test_variavel_extra_e_ignorada(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VARIAVEL_QUE_NAO_EXISTE_NO_SCHEMA", "x")
    settings = Settings(_env_file=None)  # extra="ignore" — não levanta
    assert settings.app_name == "restaurant_hub"


def test_get_settings_e_singleton_cacheado() -> None:
    get_settings.cache_clear()
    try:
        first = get_settings()
        second = get_settings()
        assert first is second
        assert isinstance(first, Settings)
    finally:
        get_settings.cache_clear()
