"""Configuração de ambiente do Alembic.

Este arquivo é executado pelo Alembic em todas as operações (migrate, revision, etc.).
Suporta tanto o modo offline (gera SQL sem conectar) quanto o modo online (executa
no banco).

**De onde vem a URL do banco (issue #86).** Duas fontes, numa precedência
explícita, e nenhuma delas é o `alembic.ini`:

1. **O chamador in-process**, por `config.attributes["database_url"]` — o canal
   que o Alembic oferece para passar objetos do código que chama
   `command.upgrade(config, ...)` até este arquivo. É o que a suíte usa para
   migrar o banco que a guarda dela conferiu (`tests/conftest.py`).
2. **A `DATABASE_URL` das Settings** (`Settings().database_url`: ambiente, depois
   `.env`), quando o chamador não passou nada — a CLI, o `make migrate`, o deploy.
   Lida sem o cache do `get_settings()`, para que um cache de outro momento do
   processo não decida qual banco migra.

A CLI não tem como pôr nada em `config.attributes`, então em produção quem decide
é sempre o ambiente — o mesmo `.env` da aplicação. E a `sqlalchemy.url` do
`Config` é **recusada**, não ignorada: ela era o canal antigo (ignorado em
silêncio, a #86) e é o lugar onde um `alembic.ini` de deploy declararia uma URL
que passaria a vencer o ambiente. Nos dois casos, falhar alto é melhor que
migrar um banco que ninguém escolheu.

**Logging.** O `fileConfig(alembic.ini)` reconfigura o root logger (handler de
stderr, nível `WARN`). Pela CLI, é o que se quer. In-process, ele trocaria os
handlers da aplicação que chamou: o chamador desliga com
`config.attributes["configure_logger"] = False` (finding F-A da #26, anexado à
#86).
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from restaurant_hub.features.identity.adapters.out.postgres.tables import (
    identity_metadata,
)
from restaurant_hub.features.staff.adapters.out.postgres.tables import (
    staff_metadata,
)
from restaurant_hub.shared.infrastructure.config.settings import Settings

# Objeto de configuração do Alembic — acessa valores do alembic.ini
config = context.config

# As chaves de `config.attributes` que um chamador in-process pode preencher.
DATABASE_URL_ATTRIBUTE = "database_url"
CONFIGURE_LOGGER_ATTRIBUTE = "configure_logger"


def resolve_database_url() -> str:
    """A URL que esta execução migra: a do chamador, senão a do ambiente.

    Raises:
        RuntimeError: o `Config` traz `sqlalchemy.url` (canal recusado — ver o
            docstring do módulo), ou o atributo do chamador não é uma URL.
    """
    if config.get_main_option("sqlalchemy.url") is not None:
        raise RuntimeError(
            "O Config do Alembic traz `sqlalchemy.url`, e migrations/env.py a recusa "
            "(issue #86): pela CLI a URL vem da DATABASE_URL do ambiente; in-process, "
            f'passe-a em config.attributes["{DATABASE_URL_ATTRIBUTE}"]. Se ela veio de um '
            "alembic.ini, remova a linha."
        )
    caller_url = config.attributes.get(DATABASE_URL_ATTRIBUTE)
    if caller_url is None:
        return Settings().database_url
    if isinstance(caller_url, str) and caller_url:
        return caller_url
    raise RuntimeError(
        f'config.attributes["{DATABASE_URL_ATTRIBUTE}"] tem de ser uma URL não '
        f"vazia (str), veio {type(caller_url).__name__}."
    )


database_url = resolve_database_url()

# Configura logging conforme definido no alembic.ini — só quando o chamador não
# pediu o contrário (ver o docstring do módulo).
#
# `disable_existing_loggers=False` (a mesma escolha do uvicorn): o default `True`
# desliga todo logger que já existe quando o Alembic roda. Na suíte, a fixture de
# sessão `engine` roda as migrations **in-process**, depois da coleta — e cada
# `logging.getLogger(__name__)` de módulo de `src/` ficava `disabled=True` dali em
# diante, cegando os testes de `caplog` conforme a ordem de execução (issue #26,
# finding F1 da #6). Num `alembic upgrade` de linha de comando não muda nada.
if config.config_file_name is not None and config.attributes.get(CONFIGURE_LOGGER_ATTRIBUTE, True):
    fileConfig(config.config_file_name, disable_existing_loggers=False)

# MetaData para autogenerate.
#
# O projeto usa SQLAlchemy **Core** (sem ORM declarativo), então não existe um
# `Base`: cada bounded context descreve o seu schema num `MetaData` próprio, e é
# ele que entra aqui. Um `MetaData` global compartilhado faria o Alembic de um BC
# enxergar as tabelas de outro e propor drops indevidos no autogenerate.
#
# Quando o 2º BC chegar, combine os metadatas em vez de trocar este por aquele —
# `target_metadata` aceita uma lista.
#
# O 2º BC chegou na Stage 3.3 (staff), e a instrução acima foi seguida
# literalmente: **lista**, não substituição. Trocar um pelo outro faria o
# autogenerate deste BC propor o drop das tabelas do outro.
target_metadata = [identity_metadata, staff_metadata]


def run_migrations_offline() -> None:
    """Executa migrations em modo offline (gera SQL sem conexão com o banco).

    Útil para revisar as queries antes de aplicar em produção, ou para
    ambientes sem acesso direto ao banco.
    """
    context.configure(
        url=database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Executa migrations em modo online (conecta ao banco e aplica imediatamente).

    Modo padrão para `alembic upgrade head`. Usa NullPool em vez do pool padrão
    para evitar problemas com migrações em ambientes de CI/CD.
    """
    # A URL vai direto ao `create_engine`, sem passar pelo `Config`: a
    # `set_main_option` interpola `%`, e uma senha com escape de URL (`%40`)
    # quebraria ali.
    connectable = create_engine(database_url, poolclass=pool.NullPool)

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
