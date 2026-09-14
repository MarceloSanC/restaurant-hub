"""Testes de Settings e get_settings (shared/infrastructure/config/settings.py)."""

import pytest

from restaurant_hub.shared.infrastructure.config.settings import Settings, get_settings

pytestmark = pytest.mark.unit

DEFAULT_PORT = 8000
ACCESS_TOKEN_TTL_PADRAO = 15
REFRESH_TOKEN_TTL_PADRAO = 14
# Valores arbitrários, só para provar que o ambiente sobrescreve o default.
ACCESS_TOKEN_TTL_DO_AMBIENTE = 5
REFRESH_TOKEN_TTL_DO_AMBIENTE = 30
# RFC 7518 §3.2: a chave HMAC deve ter ao menos o tamanho do digest — 32 bytes
# para SHA-256. O PyJWT avisa abaixo disso.
TAMANHO_MINIMO_DE_CHAVE_HS256 = 32
# Stage 3.5 — o link entregue em mãos vive uma semana; o convite por e-mail, 72h.
HANDOVER_LINK_TTL_PADRAO = 168
HANDOVER_LINK_TTL_DO_AMBIENTE = 24


def _isolate_ambient_env(monkeypatch: pytest.MonkeyPatch) -> None:
    # pydantic-settings é case-insensitive: PORT/HOST/DEBUG etc. da máquina
    # ou do CI vazariam para dentro do teste de defaults.
    for field in (
        "APP_NAME",
        "DEBUG",
        "DATABASE_URL",
        "HOST",
        "PORT",
        "LOG_LEVEL",
        "JWT_SECRET_KEY",
        "JWT_ALGORITHM",
        "ACCESS_TOKEN_TTL_MINUTES",
        "REFRESH_TOKEN_TTL_DAYS",
        "INVITATION_TOKEN_TTL_HOURS",
        "HANDOVER_LINK_TTL_HOURS",
    ):
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


def test_defaults_de_token_existem_para_a_app_subir_sem_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Os quatro campos de token têm default (Stage 2.4).

    O TTL do access token é o número que define a janela de revogação do sistema
    (concept §5 regra 12): revogar a sessão corta o refresh na hora, e o access
    sobrevive no máximo isso. Fixá-lo aqui é o que impede que ele volte a ser
    constante hard-coded dentro de um use case.
    """
    _isolate_ambient_env(monkeypatch)
    settings = Settings(_env_file=None)
    assert settings.jwt_algorithm == "HS256"
    assert settings.access_token_ttl_minutes == ACCESS_TOKEN_TTL_PADRAO
    assert settings.refresh_token_ttl_days == REFRESH_TOKEN_TTL_PADRAO
    # O default é inseguro DE PROPÓSITO e precisa continuar óbvio: um segredo que
    # parecesse plausível passaria despercebido numa revisão e iria para
    # produção. O fail-fast de boot está escalado para a Stage 6.2.
    assert settings.jwt_secret_key.startswith("dev-insecure-change-me")
    # >= 32 bytes: HS256 usa a chave como chave HMAC-SHA256 (RFC 7518 §3.2).
    # Um default curto ensinaria o formato errado a quem copiasse o .env.example.
    assert len(settings.jwt_secret_key) >= TAMANHO_MINIMO_DE_CHAVE_HS256


def test_configuracao_de_token_vem_do_ambiente(monkeypatch: pytest.MonkeyPatch) -> None:
    """TTL e segredo são configuração, não constante — decisão do sponsor."""
    monkeypatch.setenv("JWT_SECRET_KEY", "segredo-de-verdade")
    monkeypatch.setenv("JWT_ALGORITHM", "HS512")
    monkeypatch.setenv("ACCESS_TOKEN_TTL_MINUTES", str(ACCESS_TOKEN_TTL_DO_AMBIENTE))
    monkeypatch.setenv("REFRESH_TOKEN_TTL_DAYS", str(REFRESH_TOKEN_TTL_DO_AMBIENTE))
    settings = Settings(_env_file=None)
    assert settings.jwt_secret_key == "segredo-de-verdade"
    assert settings.jwt_algorithm == "HS512"
    assert settings.access_token_ttl_minutes == ACCESS_TOKEN_TTL_DO_AMBIENTE
    assert settings.refresh_token_ttl_days == REFRESH_TOKEN_TTL_DO_AMBIENTE


def test_prazo_do_link_em_maos_tem_default_maior_que_o_do_convite(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Stage 3.5 — `handover_link_ttl_hours` existe, tem default e é mais longo.

    O link em mãos não chega em minutos como um e-mail: o gestor imprime hoje e
    a pessoa começa segunda. A relação "maior que o convite" é a razão de o
    campo existir (ADR 3.5.0002, alternativa à reemissão); se um dia os dois
    empatarem, o campo virou redundante e este teste é quem avisa.
    """
    _isolate_ambient_env(monkeypatch)
    settings = Settings(_env_file=None)

    assert settings.handover_link_ttl_hours == HANDOVER_LINK_TTL_PADRAO
    assert settings.handover_link_ttl_hours > settings.invitation_token_ttl_hours


def test_prazo_do_link_em_maos_vem_do_ambiente(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HANDOVER_LINK_TTL_HOURS", str(HANDOVER_LINK_TTL_DO_AMBIENTE))
    settings = Settings(_env_file=None)
    assert settings.handover_link_ttl_hours == HANDOVER_LINK_TTL_DO_AMBIENTE


def test_get_settings_e_singleton_cacheado() -> None:
    get_settings.cache_clear()
    try:
        first = get_settings()
        second = get_settings()
        assert first is second
        assert isinstance(first, Settings)
    finally:
        get_settings.cache_clear()
