"""O banco do worker do mutmut existe durante a sessão e some no fim — issue #132.

Medido contra o Postgres da suíte. O banco base dos testes é o `database_url`
da sessão: sob o próprio mutmut ele já é o do worker, e os nomes derivados dele
continuam únicos por processo.
"""

from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, create_engine, make_url, text

from tests.conftest import fresh_database, suite_database

pytestmark = [pytest.mark.integration]

# PID fictício: nenhum processo da suíte nomeia o seu banco por ele.
_FAKE_PID = 999_999


def _exists(engine: Engine, name: str) -> bool:
    with engine.connect() as connection:
        found = connection.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": name}
        ).scalar()
    return found is not None


@pytest.fixture
def scratch_name(engine: Engine, database_url: str) -> Iterator[str]:
    """Nome de banco descartável ao lado do da sessão, dropado no teardown de todo jeito."""
    name = f"{make_url(database_url).database}_mutmut_{_FAKE_PID}"
    yield name
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        connection.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))


def test_fora_do_mutmut_devolve_o_banco_da_guarda_sem_criar_nada(
    engine: Engine, database_url: str, scratch_name: str
) -> None:
    with suite_database(database_url, "", _FAKE_PID) as url:
        assert url == database_url
        assert not _exists(engine, scratch_name)


def test_sob_o_mutmut_o_banco_do_worker_existe_e_some_no_fim(
    engine: Engine, database_url: str, scratch_name: str
) -> None:
    with suite_database(database_url, "m__mutmut_1", _FAKE_PID) as url:
        assert make_url(url).database == scratch_name
        assert _exists(engine, scratch_name)
        # Conecta de verdade: é um banco utilizável, não só uma linha no catálogo.
        worker = create_engine(url)
        try:
            with worker.connect() as connection:
                assert (
                    connection.execute(text("SELECT current_database()")).scalar() == scratch_name
                )
        finally:
            worker.dispose()

    assert not _exists(engine, scratch_name)


def test_banco_orfao_de_worker_morto_e_substituido_por_um_vazio(
    engine: Engine, database_url: str, scratch_name: str
) -> None:
    """Worker morto por timeout não dropa o seu banco, e o PID volta a ser usado."""
    worker_url = (
        make_url(database_url).set(database=scratch_name).render_as_string(hide_password=False)
    )
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        connection.execute(text(f'CREATE DATABASE "{scratch_name}"'))
    orphan = create_engine(worker_url)
    try:
        with orphan.begin() as connection:
            connection.execute(text("CREATE TABLE leftover (id int)"))
    finally:
        orphan.dispose()

    with fresh_database(database_url, worker_url):
        fresh = create_engine(worker_url)
        try:
            with fresh.connect() as connection:
                assert connection.execute(text("SELECT to_regclass('leftover')")).scalar() is None
        finally:
            fresh.dispose()


def test_o_banco_some_mesmo_quando_a_sessao_falha(
    engine: Engine, database_url: str, scratch_name: str
) -> None:
    worker_url = (
        make_url(database_url).set(database=scratch_name).render_as_string(hide_password=False)
    )

    with pytest.raises(RuntimeError), fresh_database(database_url, worker_url):
        assert _exists(engine, scratch_name)
        raise RuntimeError

    assert not _exists(engine, scratch_name)


def test_conexao_esquecida_aberta_nao_impede_o_drop(
    engine: Engine, database_url: str, scratch_name: str
) -> None:
    worker_url = (
        make_url(database_url).set(database=scratch_name).render_as_string(hide_password=False)
    )
    forgotten = create_engine(worker_url)
    try:
        with fresh_database(database_url, worker_url):
            connection = forgotten.connect()
            connection.execute(text("SELECT 1"))
        assert not _exists(engine, scratch_name)
    finally:
        forgotten.dispose()
