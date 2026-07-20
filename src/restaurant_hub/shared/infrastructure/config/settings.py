"""Configuração da aplicação via pydantic-settings.

Lê variáveis de ambiente e/ou arquivo .env automaticamente. Campos com valores
padrão permitem que a aplicação inicie sem .env (útil em testes). Em produção,
sempre defina DATABASE_URL, SECRET_KEY e DEBUG=false via variáveis de ambiente
— nunca commite um .env com credenciais reais.

Uso em qualquer módulo:
    from restaurant_hub.shared.infrastructure.config.settings import get_settings
    settings = get_settings()
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configurações da aplicação carregadas do ambiente ou do arquivo .env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        # Ignora variáveis de ambiente extras não declaradas aqui
        extra="ignore",
    )

    # ---------------------------------------------------------------------------
    # Application
    # ---------------------------------------------------------------------------
    app_name: str = "restaurant_hub"
    debug: bool = False  # Em produção: DEBUG=false

    # ---------------------------------------------------------------------------
    # Database
    # ---------------------------------------------------------------------------
    # Formato: postgresql+psycopg://usuario:senha@host:porta/banco
    #
    # O esquema nomeia o driver de propósito (Stage 2.3): `postgresql://` sozinho
    # faz o SQLAlchemy procurar o psycopg2, que este projeto não declara. Nomear
    # o driver impede que a escolha dependa de um default silencioso.
    database_url: str = "postgresql+psycopg://user:pass@localhost:5432/restaurant_hub"

    # ---------------------------------------------------------------------------
    # Server
    # ---------------------------------------------------------------------------
    host: str = "0.0.0.0"
    port: int = 8000

    # ---------------------------------------------------------------------------
    # Segurança / tokens (Stage 2.4 — ADR 2.4.0004)
    # ---------------------------------------------------------------------------
    # Segredo de assinatura do access token (HS256).
    #
    # O default é deliberadamente inseguro E deliberadamente óbvio: um valor que
    # parecesse plausível seria pior, porque passaria despercebido em revisão.
    #
    # NÃO há fail-fast de boot quando `debug=false` e o segredo é o default, e a
    # razão é concreta: a suíte de testes sobe com `debug=false` (é o default de
    # `Settings`), então a checagem quebraria os testes em vez da produção.
    # Escalado como `[finding]` para `6.2-deploy-pipeline`, onde um gate de
    # configuração de boot é o lugar certo — concept §10 e §13.
    jwt_secret_key: str = "dev-insecure-change-me"

    # Algoritmo de assinatura. Simétrico porque um único serviço assina e
    # verifica; a troca para RS256 é mudança de configuração + adapter, sem
    # tocar no port (ADR 2.4.0002).
    jwt_algorithm: str = "HS256"

    # TTL do access token, em minutos.
    #
    # **É configuração, não constante** — decisão do sponsor de 2026-07-19. A
    # janela de revogação do sistema é justamente este número: revogar a sessão
    # corta o refresh na hora, e o access sobrevive no máximo este tempo. Fixá-lo
    # em código tornaria a principal alavanca de segurança do sistema
    # inalcançável sem deploy.
    access_token_ttl_minutes: int = 15

    # TTL do refresh token, em dias. Renovado a cada rotação — não há teto
    # absoluto de vida de sessão nesta Stage (`[finding]`, concept §13).
    refresh_token_ttl_days: int = 14

    # ---------------------------------------------------------------------------
    # Logging
    # ---------------------------------------------------------------------------
    log_level: str = "INFO"  # DEBUG, INFO, WARNING, ERROR, CRITICAL


@lru_cache
def get_settings() -> Settings:
    """Retorna a instância singleton de Settings.

    O cache é mantido pelo functools.lru_cache do Python — uma única instância
    por processo. Em testes, sobrescreva via:

        from restaurant_hub.shared.infrastructure.config.settings import get_settings, Settings

        get_settings.cache_clear()
        # então monkeypatch ou substitua via dependency_overrides do FastAPI
    """
    return Settings()
