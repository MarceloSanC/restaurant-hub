"""Fake `InMemoryUnitOfWork` — o rollback devolve só o estado persistido (ADR 2.6.0001 §4).

As leis comuns ao fake e ao Postgres vivem na suíte de contrato; aqui ficam as
propriedades que só o fake precisa provar: a tabela de estado persistido, a
restauração no lugar e a sobrevivência do que **não** é estado (contadores, logs
de injetor) — que é o que permite a um teste de use case afirmar em qual escrita
a falha disparou.
"""

from datetime import UTC, datetime, timedelta

import pytest

from restaurant_hub.features.identity.application.dtos.identifiers import (
    SessionId,
    SetupTokenId,
)
from restaurant_hub.features.identity.application.dtos.session import Session
from restaurant_hub.features.identity.application.dtos.setup_tokens import (
    PasswordSetupToken,
    SetupTokenPurpose,
)
from restaurant_hub.features.identity.application.ports.out.unit_of_work import UnitOfWork
from restaurant_hub.features.identity.domain.value_objects.identifiers import (
    UnitId,
    UserId,
)
from tests.fakes.features.identity.in_memory_password_setup_token_repository import (
    InMemoryPasswordSetupTokenRepository,
)
from tests.fakes.features.identity.in_memory_session_repository import (
    InMemorySessionRepository,
)
from tests.fakes.features.identity.in_memory_unit_of_work import InMemoryUnitOfWork
from tests.fakes.features.identity.in_memory_unit_repository import InMemoryUnitRepository

_AGORA = datetime(2026, 10, 19, 12, 0, tzinfo=UTC)


def _sessao(n: int) -> Session:
    return Session(
        id=SessionId(f"sess-{n}"),
        user_id=UserId("user-1"),
        refresh_token_fingerprint=f"fp-{n}",
        issued_at=_AGORA,
        expires_at=_AGORA + timedelta(days=1),
    )


def _token(n: int) -> PasswordSetupToken:
    return PasswordSetupToken(
        id=SetupTokenId(f"tok-{n}"),
        user_id=UserId("user-1"),
        purpose=SetupTokenPurpose.INVITATION,
        token_fingerprint=f"tfp-{n}",
        issued_at=_AGORA,
        expires_at=_AGORA + timedelta(days=1),
    )


class _Falha(Exception):
    pass


class _SessoesQueRegistram(InMemorySessionRepository):
    """Injetor típico: guarda um log de chamadas no próprio repositório."""

    def __init__(self) -> None:
        super().__init__()
        self.chamadas: list[str] = []

    def add(self, session: Session) -> None:
        self.chamadas.append(f"add:{session.id}")
        super().add(session)


def test_satisfaz_o_port() -> None:
    """Uso pelo tipo do port; a conformidade estática é o `_conforms` do módulo do fake."""
    unidade: UnitOfWork = InMemoryUnitOfWork()
    with unidade.transaction():
        pass


def test_saida_normal_mantem_as_escritas_dos_dois_repositorios() -> None:
    sessoes, tokens = InMemorySessionRepository(), InMemoryPasswordSetupTokenRepository()
    unidade = InMemoryUnitOfWork(sessoes, tokens)

    with unidade.transaction():
        sessoes.add(_sessao(1))
        tokens.add(_token(1))

    assert set(sessoes.sessions) == {SessionId("sess-1")}
    assert set(tokens.tokens) == {SetupTokenId("tok-1")}
    assert (unidade.aberturas, unidade.commits, unidade.rollbacks) == (1, 1, 0)


def test_excecao_desfaz_as_escritas_dos_dois_repositorios_e_sobe_o_mesmo_objeto() -> None:
    sessoes, tokens = InMemorySessionRepository(), InMemoryPasswordSetupTokenRepository()
    sessoes.add(_sessao(0))
    unidade = InMemoryUnitOfWork(sessoes, tokens)
    falha = _Falha()

    with pytest.raises(_Falha) as capturada, unidade.transaction():
        sessoes.add(_sessao(1))
        tokens.add(_token(1))
        raise falha

    assert capturada.value is falha
    assert set(sessoes.sessions) == {SessionId("sess-0")}
    assert tokens.tokens == {}
    assert (unidade.commits, unidade.rollbacks) == (0, 1)


def test_restaura_no_lugar_e_a_referencia_tomada_antes_continua_valida() -> None:
    sessoes = InMemorySessionRepository()
    referencia = sessoes.sessions
    unidade = InMemoryUnitOfWork(sessoes)

    with pytest.raises(_Falha), unidade.transaction():
        sessoes.add(_sessao(1))
        raise _Falha

    assert sessoes.sessions is referencia
    assert referencia == {}


def test_log_do_injetor_sobrevive_ao_rollback() -> None:
    sessoes = _SessoesQueRegistram()
    unidade = InMemoryUnitOfWork(sessoes)

    with pytest.raises(_Falha), unidade.transaction():
        sessoes.add(_sessao(1))
        raise _Falha

    assert sessoes.sessions == {}
    assert sessoes.chamadas == ["add:sess-1"]


def test_contador_de_chamadas_da_classe_base_sobrevive_ao_rollback() -> None:
    """`find_calls` não é estado persistido — se voltasse, a tabela estaria errada."""
    unidades = InMemoryUnitRepository()
    unidade = InMemoryUnitOfWork(unidades)

    with pytest.raises(_Falha), unidade.transaction():
        unidades.find_by_id(UnitId("unit-x"))
        raise _Falha

    assert unidades.find_calls == 1


def test_aninhar_duas_unidades_distintas_levanta_sem_tocar_no_estado() -> None:
    sessoes = InMemorySessionRepository()
    externa, interna = InMemoryUnitOfWork(sessoes), InMemoryUnitOfWork(sessoes)

    with externa.transaction():
        sessoes.add(_sessao(1))
        with pytest.raises(RuntimeError, match="L5"), interna.transaction():
            pass  # pragma: no cover — a unidade interna nunca abre
        assert interna.aberturas == 0

    assert set(sessoes.sessions) == {SessionId("sess-1")}
    assert externa.commits == 1


def test_unidade_fechada_libera_a_proxima() -> None:
    unidade = InMemoryUnitOfWork()

    with unidade.transaction():
        pass
    with pytest.raises(_Falha), unidade.transaction():
        raise _Falha
    with unidade.transaction():
        pass

    assert (unidade.aberturas, unidade.commits, unidade.rollbacks) == (3, 2, 1)


def test_repositorio_sem_estado_declarado_reprova_na_construcao() -> None:
    class _Desconhecido:
        pass

    with pytest.raises(TypeError, match="_ESTADO_PERSISTIDO"):
        InMemoryUnitOfWork(_Desconhecido())
