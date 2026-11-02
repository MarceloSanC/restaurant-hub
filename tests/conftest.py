"""Fixtures globais de teste.

Fixtures de escopo `session` são criadas uma vez por execução do pytest — ideal
para recursos caros como engines de banco de dados. Fixtures de escopo padrão
(function) são recriadas a cada teste — ideal para estado que deve ser isolado
entre testes (ex: client HTTP). Use pytest.mark para filtrar suites no CI.

**Fixtures de banco (Stage 2.3).** `database_url` e `engine` vivem aqui, e não em
`tests/integration/conftest.py`, porque as suítes de **integração** e de
**contrato** precisam do mesmo `Engine` — o contrato roda o mesmo corpo de teste
contra o fake e contra o Postgres. Duplicá-las criaria duas conexões e duas
verdades sobre o que é "o banco de teste". São lazy: um teste unitário que não as
pede nunca abre conexão.

A fixture `test_engine` (SQLite in-memory), herdada do template, foi removida na
Stage 2.3 — sem substituto. Ela nunca chegou a ser usada por teste nenhum, e
mantê-la seria pior que não tê-la: o schema desta Stage carrega as invariantes
**no banco** (FKs compostas, a `CHECK` do iff de tenancy, `TIMESTAMPTZ`,
constraints nomeadas que o adapter lê para traduzir erro), e o SQLite diverge do
Postgres em todos esses pontos. Uma suíte verde contra SQLite valeria menos que
suíte nenhuma, porque inspiraria confiança no que não foi verificado.
"""

import ipaddress
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import Engine, create_engine, make_url, text
from sqlalchemy.exc import OperationalError

from restaurant_hub.shared.infrastructure.config.settings import Settings
from restaurant_hub.shared.infrastructure.http.app import create_app

_REPO_ROOT = Path(__file__).resolve().parents[1]
_ALEMBIC_INI = _REPO_ROOT / "migrations" / "alembic.ini"

# Ordem de truncamento: filhas antes das mães. `CASCADE` resolveria sozinho, mas a
# ordem explícita documenta o grafo de dependências.
#
# Fonte ÚNICA: as suítes de integração e de contrato truncam as mesmas tabelas, e
# duas listas separadas divergiriam no dia em que uma tabela nova entrasse só numa
# delas — o sintoma seria um erro de FK confuso numa suíte e não na outra.
TABELAS_EM_ORDEM_DE_LIMPEZA = (
    # Stage 2.5 — antes de `users`, que é o alvo da sua FK.
    "password_setup_tokens",
    "sessions",
    "unit_memberships",
    "users",
    "units",
    "restaurants",
    # Stage 3.3 — BC staff, na mesma disciplina: filhas antes das mães, e
    # `employee_job_functions` antes de `job_functions`, que ela referencia com
    # `RESTRICT`.
    #
    # **A ordem aqui é documentação, não necessidade** — medido contra o banco
    # real: um `TRUNCATE a, b, c CASCADE` único trata as tabelas como **uma**
    # operação, e a lista invertida funciona igual, inclusive com o `RESTRICT`
    # ativo. O que a ordem entrega é o grafo de dependências legível para quem
    # acrescentar a próxima tabela, exatamente como o comentário de identity
    # acima já dizia.
    "employee_shift_preferences",
    "employee_unavailabilities",
    "employee_job_functions",
    "employees",
    "job_functions",
)


def truncar_tudo(engine: Engine) -> None:
    """Esvazia todas as tabelas dos BCs identity e staff."""
    with engine.begin() as conexao:
        conexao.execute(text(f"TRUNCATE {', '.join(TABELAS_EM_ORDEM_DE_LIMPEZA)} CASCADE"))


@pytest.fixture
async def client() -> AsyncClient:
    """Cliente HTTP assíncrono apontando para a aplicação FastAPI em memória.

    Usa ASGITransport do httpx para fazer requisições sem abrir porta TCP.
    Ideal para testes e2e que precisam testar o ciclo completo HTTP.
    """
    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as c:
        yield c


# ---------------------------------------------------------------------------
# Banco real — sem caminho de skip (ADR 2.3.0001)
# ---------------------------------------------------------------------------


# A porta em que o compose publica o Postgres quando a `POSTGRES_PORT` falta ou
# está vazia — o `${POSTGRES_PORT:-5432}` do docker-compose.yml, que
# `tests/unit/test_database_url_guard.py` cobra contra o arquivo.
COMPOSE_DEFAULT_POSTGRES_PORT = 5432
# Porta em que a libpq conecta quando a URL não declara nenhuma — medido com o
# psycopg 3.3.4: `localhost` sem porta devolve "port 5432 failed".
_LIBPQ_DEFAULT_PORT = 5432


class _ComposePostgresPort(BaseSettings):
    """A `POSTGRES_PORT` como o compose a resolve: ambiente primeiro, depois o `.env`.

    O `.env` que conta é o do **projeto** do compose — a pasta do
    `docker-compose.yml`, a raiz do checkout —, qualquer que seja o diretório
    corrente: medido, `docker compose config` rodado de `tests/unit` publica a
    porta do `.env` da raiz. O valor vazio conta como ausente, como no `:-` do
    compose; e a ordem ambiente → `.env` é a mesma do pydantic-settings.
    """

    model_config = SettingsConfigDict(
        env_file_encoding="utf-8", extra="ignore", env_ignore_empty=True
    )

    postgres_port: int | None = None


def published_postgres_port(compose_dir: Path = _REPO_ROOT) -> int:
    """A porta em que o compose deste checkout publica o Postgres no host."""
    declared = _ComposePostgresPort(_env_file=compose_dir / ".env").postgres_port
    return COMPOSE_DEFAULT_POSTGRES_PORT if declared is None else declared


def is_loopback(host: str | None) -> bool:
    """`localhost`, 127.0.0.0/8 ou `::1` — o critério do `scripts/worktree-new.py`.

    `tests/unit/test_database_url_guard.py` cobra que os dois lados concordam.
    """
    if not host:
        return False
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def database_port_mismatch(database_url: str, published_port: int) -> str | None:
    """Por que `database_url` não alcança o Postgres deste checkout, ou None se alcança.

    Com host loopback, a porta da URL tem de ser a que o compose publica. Os
    outros hosts não passam por ela — `postgres` é o service dentro da rede do
    compose, que responde na 5432 do contêiner, e um banco remoto não tem
    relação com o mapeamento local —, e para eles a regra não se aplica.

    A mensagem nomeia host e portas, nunca a URL inteira: ela carrega a senha.
    """
    url = make_url(database_url)
    if not is_loopback(url.host):
        return None
    port = _LIBPQ_DEFAULT_PORT if url.port is None else url.port
    if port == published_port:
        return None
    return (
        f"A DATABASE_URL aponta para a porta {port} de {url.host}, mas o compose deste "
        f"checkout publica o Postgres na porta {published_port} (POSTGRES_PORT, ou "
        f"{COMPOSE_DEFAULT_POSTGRES_PORT} sem ela): a suíte rodaria — e recriaria o "
        "schema — no Postgres de outra worktree ou do checkout principal.\n"
        "Alinhe a porta da DATABASE_URL no .env (o scripts/worktree-new.py escreve as "
        "duas coerentes) e suba o banco desta worktree: "
        "`docker compose up -d --wait postgres`."
    )


def resolve_test_database_url(compose_dir: Path = _REPO_ROOT) -> str:
    """A `DATABASE_URL` da suíte, recusada se não alcançar o Postgres deste checkout.

    A URL que o `Settings` lê tem de apontar para a porta que o compose publica
    (`database_port_mismatch`). Ela é a única URL em jogo: o Alembic migra a que
    `_recriar_schema` lhe passa (`config.attributes`, issue #86), sem consultar o
    `get_settings()` em cache — a conferência do cache que a #58 pôs aqui deixou
    de ter objeto.
    """
    database_url = Settings().database_url
    mismatch = database_port_mismatch(database_url, published_postgres_port(compose_dir))
    if mismatch is not None and Path.cwd().resolve() != compose_dir.resolve():
        mismatch += (
            f"\nO Settings lê o .env do diretório corrente ({Path.cwd()}), não da raiz "
            f"({compose_dir}): rode o pytest da raiz do checkout."
        )
    if mismatch is not None:
        pytest.fail(mismatch, pytrace=False)
    return database_url


@pytest.fixture(scope="session")
def database_url() -> str:
    """URL do banco de teste, do ambiente ou do `.env` da worktree.

    O `Settings` tem default (`localhost:5432`), e é ele que uma worktree sem
    `DATABASE_URL` no `.env` recebia: a suíte rodava contra o banco de **outra**
    frente, e a fixture `engine` tentava recriar o schema dele. Na Stage 4.1 a
    tentativa morreu em `ResolutionError: No such revision '0004'` (629 testes em
    `ERROR at setup`, issue #58); com as mesmas migrations, teria derrubado o
    banco alheio. Por isso a URL passa pela guarda antes de qualquer conexão: uma
    URL loopback fora da porta que o compose deste checkout publica reprova a
    sessão inteira, aqui, sem tocar o banco. Toda suíte que fala com o banco —
    integração, contrato e e2e — resolve a URL por esta fixture.
    """
    return resolve_test_database_url()


@pytest.fixture(scope="session")
def engine(database_url: str) -> Iterator[Engine]:
    """Engine de teste contra o Postgres real, com o schema já migrado.

    **Quando o banco não responde, esta fixture FALHA.** Nunca `pytest.skip`, e
    não existe variável de ambiente que desligue a exigência — esta é a decisão de
    gate mais consequente da Stage (ADR 2.3.0001), e ela vive aqui.

    O motivo é o defeito que a Stage 1.2 catalogou: um teste que se pula quando
    falta infraestrutura reporta verde **por não ter olhado** ("a false negative
    wearing a checkmark"). Como o gate deste projeto é o mesmo comando local e no
    runner (`make check`), qualquer válvula de escape aqui acabaria aberta no CI, e
    o gate de persistência inteiro viraria decorativo.

    O custo é real e aceito: `make check` passa a exigir Docker. A alternativa
    ("pular local, exigir no CI") foi medida e rejeitada — com os adapters sem
    cobertura, o `fail_under = 90` reprovaria de todo jeito, então o skip não
    entregaria nem o gate verde que prometia.

    **O schema vem da migration**, não de `metadata.create_all`: assim cada
    execução exercita a migration de verdade, e o schema de teste não diverge do de
    produção. E é **recriado do zero** a cada execução (`_recriar_schema`), porque
    contra um banco persistente `upgrade head` é no-op e a migration editada nunca
    chegaria a ser exercitada — ver o docstring de `_recriar_schema`.

    Escopo `session`: recriar o schema por teste seria lento sem ganho — o
    isolamento fica com o `TRUNCATE` das fixtures que dependem desta.
    """
    engine = create_engine(
        database_url,
        connect_args={
            # O psycopg devolve `timestamptz` no fuso da SESSÃO, não em UTC. Sem
            # fixar, um round-trip volta em horário local e o mesmo teste passa no
            # runner (UTC) e falha numa máquina em America/Sao_Paulo. O mapper
            # ainda normaliza — cinto e suspensório, porque este Engine é o dos
            # testes e não passa pelo composition root.
            "options": "-c timezone=UTC",
            # Falhar rápido faz parte de falhar alto: sem timeout, a tentativa de
            # conexão fica pendurada por dezenas de segundos e o dev lê "a suíte
            # travou" em vez de "falta subir o Postgres".
            "connect_timeout": 5,
        },
    )

    try:
        with engine.connect() as conexao:
            conexao.execute(text("SELECT 1"))
    except OperationalError as exc:
        engine.dispose()
        pytest.fail(
            f"Postgres não está acessível em {database_url!r}.\n"
            f"Suba o banco com `make docker-up`. Os testes de integração desta "
            f"Stage não se pulam (ADR 2.3.0001): um gate que se pula sozinho "
            f"reporta verde por não ter olhado.\n"
            f"Erro original: {exc}",
            pytrace=False,
        )

    _recriar_schema(database_url)
    yield engine
    engine.dispose()


def _recriar_schema(database_url: str) -> None:
    """Recria o schema do zero: `downgrade base` e então `upgrade head`.

    **Por que não basta `upgrade head`.** O banco de teste local é persistente, e
    `upgrade head` é no-op quando o banco já está em `head`. Editar o arquivo de
    migration não reaplica nada: a suíte segue rodando contra o schema **antigo**,
    que continua correto, e o local reporta verde para uma migration quebrada. A
    quebra só apareceria em quem clonasse o repo — ou no CI, cujo Postgres é
    efêmero e sempre parte do zero. Recriar aqui faz o local espelhar o CI.

    Pior que o falso verde: `test_downgrade_remove_o_que_o_upgrade_criou` reaplica a
    migration no fim, então uma migration errada **contamina** o banco de dev e só
    se manifesta na rodada seguinte, longe da edição que a causou.

    **Por que não `compare_metadata()`.** O diff de autogenerate não fecha este
    caso: com a migration editada e não reaplicada, o banco guarda o schema antigo
    (correto) e `tables.py` está intocado — não há diferença a detectar. Some-se a
    isso que o suporte dele a `CHECK` é fraco, e `CHECK` é exatamente a classe de
    invariante em jogo (`ck_users_email_normalized`, `ck_users_role_known`,
    `ck_users_tenant_iff_platform_admin`).

    **Custo.** Roda uma vez por sessão de pytest, não por teste — a fixture que a
    chama tem escopo `session`, e o isolamento entre testes continua sendo o
    `TRUNCATE`. Dropar e recriar cinco tabelas vazias é ruído perto do resto.
    """
    config = alembic_config(database_url)
    command.downgrade(config, "base")
    command.upgrade(config, "head")


def alembic_config(database_url: str) -> Config:
    """O `Config` de um comando do Alembic in-process, apontado para `database_url`.

    A URL vai em `config.attributes["database_url"]`, o canal que
    `migrations/env.py` honra (issue #86) — a `sqlalchemy.url` ele recusa. E
    `configure_logger=False`, para que o `fileConfig(alembic.ini)` não troque os
    handlers nem o nível do root logger da suíte (finding F-A da #26).
    """
    config = Config(str(_ALEMBIC_INI))
    config.set_main_option("script_location", str(_REPO_ROOT / "migrations"))
    config.attributes["database_url"] = database_url
    config.attributes["configure_logger"] = False
    return config
