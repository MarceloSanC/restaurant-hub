"""Configuração de ambiente do Alembic.

Este arquivo é executado pelo Alembic em todas as operações (migrate, revision, etc.).
Lê a DATABASE_URL das Settings do projeto em vez do alembic.ini, garantindo que
o mesmo arquivo .env usado pela aplicação seja usado pelas migrations. Suporta
tanto o modo offline (gera SQL sem conectar) quanto o modo online (executa no banco).
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# Importa as Settings do projeto para ler DATABASE_URL do .env
from restaurant_hub.features.identity.adapters.out.postgres.tables import (
    identity_metadata,
)
from restaurant_hub.features.staff.adapters.out.postgres.tables import (
    staff_metadata,
)
from restaurant_hub.shared.infrastructure.config.settings import get_settings

# Objeto de configuração do Alembic — acessa valores do alembic.ini
config = context.config

# Sobrescreve sqlalchemy.url com o valor real das Settings
# Garante que o mesmo .env da aplicação é usado nas migrations
settings = get_settings()
config.set_main_option("sqlalchemy.url", settings.database_url)

# Configura logging conforme definido no alembic.ini.
#
# `disable_existing_loggers=False` (a mesma escolha do uvicorn): o default `True`
# desliga todo logger que já existe quando o Alembic roda. Na suíte, a fixture de
# sessão `engine` roda as migrations **in-process**, depois da coleta — e cada
# `logging.getLogger(__name__)` de módulo de `src/` ficava `disabled=True` dali em
# diante, cegando os testes de `caplog` conforme a ordem de execução (issue #26,
# finding F1 da #6). Num `alembic upgrade` de linha de comando não muda nada.
if config.config_file_name is not None:
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
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
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
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

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
