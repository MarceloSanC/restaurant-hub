"""`PostgresUnitOfWork` contra PostgreSQL real — o que a suíte de contrato não alcança.

O contrato fixa as leis L1 a L6 no fake e no Postgres. Aqui ficam as propriedades
que só existem no Postgres: o pool de conexões (L5 "antes de tocar em qualquer
coisa"; conexão devolvida depois de exceção), duas threads com unidades
simultâneas (a `ContextVar` não vaza), e a armadilha declarada do concept 2.6 R7 —
repositório montado sobre **outro** engine não entra na unidade.
"""

import threading
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.exc import DBAPIError

from restaurant_hub.features.identity.adapters.out.postgres.restaurant_repository import (
    PostgresRestaurantRepository,
)
from restaurant_hub.features.identity.adapters.out.postgres.session_repository import (
    PostgresSessionRepository,
)
from restaurant_hub.features.identity.adapters.out.postgres.unit_connection import (
    for_read,
)
from restaurant_hub.features.identity.adapters.out.postgres.unit_of_work import (
    PostgresUnitOfWork,
)
from restaurant_hub.features.identity.adapters.out.postgres.user_repository import (
    PostgresUserRepository,
)
from restaurant_hub.features.identity.application.dtos.identifiers import (
    PasswordHash,
    SessionId,
)
from restaurant_hub.features.identity.application.dtos.session import Session
from restaurant_hub.features.identity.domain.entities.restaurant import Restaurant
from restaurant_hub.features.identity.domain.entities.user import User
from restaurant_hub.features.identity.domain.value_objects.email import Email
from restaurant_hub.features.identity.domain.value_objects.identifiers import (
    RestaurantId,
    UserId,
)
from restaurant_hub.features.identity.domain.value_objects.role import Role

pytestmark = pytest.mark.integration

_AGORA = datetime(2026, 10, 19, 12, 0, tzinfo=UTC)
_ESPERA = 10  # segundos — teto para a barreira, para o teste falhar em vez de travar


class _Falha(Exception):
    pass


def _sessao(n: str) -> Session:
    return Session(
        id=SessionId(f"sess-{n}"),
        user_id=UserId("user-1"),
        refresh_token_fingerprint=f"fp::{n}",
        issued_at=_AGORA,
        expires_at=_AGORA + timedelta(days=1),
    )


@pytest.fixture
def com_usuario(banco_limpo: Engine) -> Engine:
    PostgresRestaurantRepository(banco_limpo).add(
        Restaurant(id=RestaurantId("rest-a"), name="Cantina")
    )
    PostgresUserRepository(banco_limpo).add(
        User(
            id=UserId("user-1"),
            email=Email("um@x.com"),
            role=Role.OWNER,
            tenant_id=RestaurantId("rest-a"),
        ),
        PasswordHash("hashed::um"),
    )
    return banco_limpo


def test_l5_unidade_aninhada_nao_retira_conexao_do_pool(com_usuario: Engine) -> None:
    """Conta os checkouts **durante** a tentativa aninhada.

    Comparar `pool.checkedout()` depois não serve: uma unidade que retirasse a
    conexão e só então recusasse a devolveria ao sair, e a contagem voltaria ao
    valor de antes — o mutante passaria.
    """
    unidade = PostgresUnitOfWork(com_usuario)
    checkouts: list[object] = []

    def contar(*_: object) -> None:
        checkouts.append(object())

    with unidade.transaction():
        event.listen(com_usuario.pool, "checkout", contar)
        try:
            with pytest.raises(RuntimeError, match="L5"), unidade.transaction():
                pass  # pragma: no cover — nunca abre
        finally:
            event.remove(com_usuario.pool, "checkout", contar)

    assert checkouts == []


def test_conexao_volta_ao_pool_depois_de_excecao(com_usuario: Engine) -> None:
    antes = com_usuario.pool.checkedout()  # type: ignore[attr-defined]
    sessoes = PostgresSessionRepository(com_usuario)

    with pytest.raises(_Falha), PostgresUnitOfWork(com_usuario).transaction():
        sessoes.add(_sessao("1"))
        raise _Falha

    assert com_usuario.pool.checkedout() == antes  # type: ignore[attr-defined]
    assert sessoes.find_by_fingerprint("fp::1") is None


def test_duas_threads_com_unidades_simultaneas_nao_se_enxergam(com_usuario: Engine) -> None:
    """Se a `ContextVar` vazasse entre threads, uma escreveria na conexão da outra."""
    unidade = PostgresUnitOfWork(com_usuario)
    sessoes = PostgresSessionRepository(com_usuario)
    ambas_escreveram = threading.Barrier(2, timeout=_ESPERA)
    viu_a_outra: dict[str, bool] = {}
    erros: list[BaseException] = []

    def trabalhar(minha: str, outra: str) -> None:
        try:
            with unidade.transaction():
                sessoes.add(_sessao(minha))
                ambas_escreveram.wait()
                viu_a_outra[minha] = sessoes.find_by_fingerprint(f"fp::{outra}") is not None
                ambas_escreveram.wait()
        except BaseException as erro:
            erros.append(erro)

    threads = [
        threading.Thread(target=trabalhar, args=("a", "b")),
        threading.Thread(target=trabalhar, args=("b", "a")),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=_ESPERA)

    assert erros == []
    assert viu_a_outra == {"a": False, "b": False}
    assert sessoes.find_by_fingerprint("fp::a") is not None
    assert sessoes.find_by_fingerprint("fp::b") is not None


def test_repositorio_de_outro_engine_nao_entra_na_unidade(
    com_usuario: Engine, database_url: str
) -> None:
    """A armadilha que o concept 2.6 R7 declara e o teste de bootstrap fecha na fiação.

    A unidade é chaveada pelo engine: um repositório montado sobre outro engine —
    mesmo apontando para o mesmo banco — escreve na própria transação e comita
    sozinho, ainda que a unidade desfaça.
    """
    outro = create_engine(database_url, connect_args={"options": "-c timezone=UTC"})
    try:
        sessoes_de_outro_engine = PostgresSessionRepository(outro)

        with pytest.raises(_Falha), PostgresUnitOfWork(com_usuario).transaction():
            sessoes_de_outro_engine.add(_sessao("1"))
            raise _Falha

        assert PostgresSessionRepository(com_usuario).find_by_fingerprint("fp::1") is not None
    finally:
        outro.dispose()


def test_leitura_que_falha_dentro_da_unidade_nao_envenena_a_unidade(com_usuario: Engine) -> None:
    """L3 do lado da leitura: o savepoint de `for_read` é o que segura o aborto.

    Sem ele, o erro da consulta abortaria a transação da unidade, a escrita seguinte
    falharia e o commit viraria um `ROLLBACK` silencioso.
    """
    sessoes = PostgresSessionRepository(com_usuario)

    with PostgresUnitOfWork(com_usuario).transaction():
        sessoes.add(_sessao("1"))
        with pytest.raises(DBAPIError), for_read(com_usuario) as conexao:
            conexao.execute(text("SELECT 1 / 0"))
        sessoes.add(_sessao("2"))

    assert sessoes.find_by_fingerprint("fp::1") is not None
    assert sessoes.find_by_fingerprint("fp::2") is not None
