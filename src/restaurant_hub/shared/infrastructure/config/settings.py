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
    #
    # O preenchimento até 32+ bytes não é enfeite: HS256 usa a chave como chave
    # HMAC-SHA256, e a RFC 7518 §3.2 exige chave de pelo menos o tamanho do
    # digest (32 bytes). O PyJWT emite `InsecureKeyLengthWarning` abaixo disso —
    # foi assim que se notou. Um default curto ensinaria o formato errado a quem
    # copiasse o `.env.example` e trocasse só as palavras.
    jwt_secret_key: str = "dev-insecure-change-me-0000000000000000"

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
    # Convite e definição de senha (Stage 2.5)
    # ---------------------------------------------------------------------------
    # Base do link que vai no e-mail. É a URL da aplicação **web**, não da API:
    # quem clica é uma pessoa, e o destino é a tela de definir senha.
    app_base_url: str = "http://localhost:8000"

    # Não há `email_from` aqui, e a ausência é deliberada. O `ConsoleSender` não
    # tem remetente (escreve local) e `EmailMessage` não tem campo para ele — a
    # CA1 fixa os três campos do DTO justamente para o port não crescer por
    # antecipação. Um campo de configuração sem leitor é pior que ausência: quem
    # o define no `.env` recebe silêncio. Entra na 6.2, junto com o adapter que
    # vai lê-lo (`[finding]`).

    # TTLs dos tokens de definição de senha, em unidades **diferentes** de
    # propósito, porque os dois prazos não são o mesmo tipo de coisa:
    #
    # - um convite tolera o atraso humano de alguém que só abre o e-mail no dia
    #   seguinte, então conta-se em dias;
    # - uma redefinição de senha é uma emergência — normalmente a pessoa está com
    #   o e-mail aberto agora —, e a janela curta é a própria defesa: reduz o
    #   tempo em que um e-mail interceptado ainda vale.
    #
    # Configuráveis pela mesma razão do TTL do access token: são alavancas de
    # segurança do produto, e fixá-las em código as tornaria inalcançáveis sem
    # deploy.
    invitation_token_ttl_hours: int = 72
    password_reset_token_ttl_minutes: int = 30

    # Stage 3.5 — o prazo do link de definição de senha **entregue em mãos**
    # (canal `link` de R17: impresso, QR, mensagem). Mais longo que o do convite
    # por e-mail porque o link não chega em minutos — o gestor imprime hoje e a
    # pessoa começa segunda. É a alternativa escolhida à reemissão do link
    # (ADR 3.5.0002): o prazo do canal absorve a demora, e o link perdido é
    # recuperado pelo pedido público de redefinição de senha, como qualquer
    # convite. Em horas, como o do convite, porque é o mesmo tipo de coisa.
    handover_link_ttl_hours: int = 168

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
