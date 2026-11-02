"""A guarda da `DATABASE_URL` deste checkout — fonte única da regra (issue #85).

Numa worktree paralela, o compose publica o Postgres numa porta própria
(`POSTGRES_PORT` do `.env`, `scripts/worktree-new.py`). Uma `DATABASE_URL`
loopback em outra porta fala com o banco de **outra** frente: a suíte recriaria
o schema dele (issue #58), o `make migrate` aplicaria nele as migrations desta
branch e o `make run` leria e escreveria nele. A regra mora aqui, e os pontos
que a aplicam importam daqui:

- a fixture `database_url` de `tests/conftest.py`, antes de qualquer conexão;
- `make migrate` e `make run`, que passam por `main()` antes de chamar o Alembic
  e o uvicorn — com a guarda recusando, nenhum dos dois roda;
- o `scripts/worktree-new.py`, que importa daqui o `is_loopback` — o critério de
  quais URLs ele reescreve é o de quais URLs a guarda confere.

**Por que fora do `Settings`.** O `Settings` é contrato de produção, onde
`POSTGRES_PORT` não existe: a guarda só vale para quem sobe o banco pelo compose
deste checkout. O CI (URL por `env:`, sem `.env` nem `POSTGRES_PORT`) e a
produção (sem `make`) passam por ela sem mudar de comportamento.

**Por que os imports de terceiros ficam dentro das funções.** O topo do módulo
é biblioteca padrão: o `worktree-new.py` roda sem o venv
(`python scripts/worktree-new.py`) e importa daqui o `is_loopback`.
O SQLAlchemy, o pydantic-settings e o `Settings` só entram quando a guarda de
fato roda, sempre dentro do venv.

Uso (pelos alvos do Makefile, da raiz do checkout):
    uv run python scripts/database_url_guard.py migrate
    uv run python scripts/database_url_guard.py run

Exit codes:
  1  a `DATABASE_URL` não alcança o Postgres deste checkout (nada roda)
  *  o do Alembic / uvicorn, quando a guarda passa
"""

from __future__ import annotations

import argparse
import ipaddress
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# A porta em que o compose publica o Postgres quando a `POSTGRES_PORT` falta ou
# está vazia — o `${POSTGRES_PORT:-5432}` do docker-compose.yml, que
# `tests/unit/test_database_url_guard.py` cobra contra o arquivo.
COMPOSE_DEFAULT_POSTGRES_PORT = 5432
# Porta em que a libpq conecta quando a URL não declara nenhuma — medido com o
# psycopg 3.3.4: `localhost` sem porta devolve "port 5432 failed".
LIBPQ_DEFAULT_PORT = 5432


def is_loopback(host: str | None) -> bool:
    """Host que alcança a porta publicada no host: `localhost`, 127.0.0.0/8 ou `::1`.

    Os demais não passam por ela: `postgres` é o service dentro da rede do
    compose, que responde na porta do contêiner (5432), e um banco remoto não
    tem relação com o mapeamento local. `0.0.0.0` também fica de fora: não é
    endereço de destino (RFC 1122 §3.2.1.3).
    """
    if not host:
        return False
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _compose_port(name: str, default: int, compose_dir: Path) -> int:
    """A porta `name` como o compose a resolve: ambiente primeiro, depois o `.env`.

    O `.env` que conta é o do **projeto** do compose — a pasta do
    `docker-compose.yml`, a raiz do checkout —, qualquer que seja o diretório
    corrente: medido, `docker compose config` rodado de `tests/unit` publica a
    porta do `.env` da raiz. O valor vazio conta como ausente, como no `:-` do
    compose; e a ordem ambiente → `.env` é a mesma do pydantic-settings.
    """
    from pydantic_settings import BaseSettings, SettingsConfigDict  # noqa: PLC0415

    class _ComposePorts(BaseSettings):
        model_config = SettingsConfigDict(
            env_file_encoding="utf-8", extra="ignore", env_ignore_empty=True
        )

        postgres_port: int | None = None

    declared: int | None = getattr(_ComposePorts(_env_file=compose_dir / ".env"), name)
    return default if declared is None else declared


def published_postgres_port(compose_dir: Path = ROOT) -> int:
    """A porta em que o compose deste checkout publica o Postgres no host."""
    return _compose_port("postgres_port", COMPOSE_DEFAULT_POSTGRES_PORT, compose_dir)


def database_port_mismatch(database_url: str, published_port: int) -> str | None:
    """Por que `database_url` não alcança o Postgres deste checkout, ou None se alcança.

    Com host loopback, a porta da URL tem de ser a que o compose publica. Os
    outros hosts não passam por ela — `postgres` é o service dentro da rede do
    compose, que responde na 5432 do contêiner, e um banco remoto não tem
    relação com o mapeamento local —, e para eles a regra não se aplica.

    A mensagem nomeia host e portas, nunca a URL inteira: ela carrega a senha.
    """
    from sqlalchemy import make_url  # noqa: PLC0415

    url = make_url(database_url)
    if not is_loopback(url.host):
        return None
    port = LIBPQ_DEFAULT_PORT if url.port is None else url.port
    if port == published_port:
        return None
    return (
        f"A DATABASE_URL aponta para a porta {port} de {url.host}, mas o compose deste "
        f"checkout publica o Postgres na porta {published_port} (POSTGRES_PORT, ou "
        f"{COMPOSE_DEFAULT_POSTGRES_PORT} sem ela): a suíte, as migrations e a app "
        "rodariam no Postgres de outra worktree ou do checkout principal — e a suíte "
        "recriaria o schema dele.\n"
        "Alinhe a porta da DATABASE_URL no .env (o scripts/worktree-new.py escreve as "
        "duas coerentes) e suba o banco desta worktree: "
        "`docker compose up -d --wait postgres`."
    )


def checkout_database_url(compose_dir: Path = ROOT) -> tuple[str, str | None]:
    """A `DATABASE_URL` que a app, o Alembic e a suíte leriam agora, e a recusa dela.

    A URL é a do `Settings` sem o cache do `get_settings()` — ambiente, depois o
    `.env` do diretório corrente —, a mesma que o `migrations/env.py` migra pela
    CLI (issue #86). A recusa é `database_port_mismatch` contra a porta que o
    compose deste checkout publica, ou None se a URL o alcança.
    """
    from restaurant_hub.shared.infrastructure.config.settings import Settings  # noqa: PLC0415

    database_url = Settings().database_url
    mismatch = database_port_mismatch(database_url, published_postgres_port(compose_dir))
    if mismatch is not None and Path.cwd().resolve() != compose_dir.resolve():
        mismatch += (
            f"\nO Settings lê o .env do diretório corrente ({Path.cwd()}), não da raiz "
            f"({compose_dir}): rode o pytest e o make da raiz do checkout."
        )
    return database_url, mismatch


# O que cada alvo do Makefile roda depois da guarda — os comandos de antes da
# #85, pelo python do venv que roda a guarda.
TARGET_COMMANDS: dict[str, list[str]] = {
    # O `-c` é obrigatório: o alembic.ini vive em migrations/, e o alembic só
    # procura `alembic.ini` no diretório corrente (Stage 2.3).
    "migrate": ["-m", "alembic", "-c", "migrations/alembic.ini", "upgrade", "head"],
    "run": [
        "-m",
        "uvicorn",
        "restaurant_hub.main:app",
        "--reload",
        "--host",
        "0.0.0.0",
        "--port",
        "8000",
    ],
}


def main(argv: list[str] | None = None, compose_dir: Path = ROOT) -> int:
    """Confere a `DATABASE_URL` e, se ela alcança o Postgres deste checkout, roda o alvo.

    O comando roda no diretório corrente, como rodava direto do Makefile: o
    Alembic e a app leem o mesmo `.env` que a guarda acabou de conferir.
    """
    parser = argparse.ArgumentParser(
        description="Confere a DATABASE_URL deste checkout e roda o alvo do Makefile."
    )
    parser.add_argument("target", choices=sorted(TARGET_COMMANDS))
    args = parser.parse_args(argv)

    _, mismatch = checkout_database_url(compose_dir)
    if mismatch is not None:
        print(mismatch, file=sys.stderr)
        return 1
    command = [sys.executable, *TARGET_COMMANDS[args.target]]
    try:
        return subprocess.run(command, check=False).returncode
    except KeyboardInterrupt:  # Ctrl+C no `make run`: o filho recebe o mesmo sinal
        return 130


if __name__ == "__main__":
    sys.exit(main())
