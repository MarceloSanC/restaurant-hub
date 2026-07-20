"""`PostgresPasswordSetupTokenRepository` contra PostgreSQL real (CA5, CA9b, CA16).

O teste que justifica este arquivo é `test_consume_concorrente_...`: ele é o
**único** capaz de distinguir o `UPDATE` condicional da implementação
`SELECT`-depois-`UPDATE`. As duas passam em todos os outros testes daqui, e uma
delas define a senha da vítima duas vezes sob concorrência.
"""

import threading
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import Engine, inspect, text
from sqlalchemy.exc import IntegrityError

from restaurant_hub.features.identity.adapters.out.postgres.password_setup_token_repository import (
    PostgresPasswordSetupTokenRepository,
)
from restaurant_hub.features.identity.adapters.out.postgres.restaurant_repository import (
    PostgresRestaurantRepository,
)
from restaurant_hub.features.identity.adapters.out.postgres.tables import (
    identity_metadata,
)
from restaurant_hub.features.identity.adapters.out.postgres.user_repository import (
    PostgresUserRepository,
)
from restaurant_hub.features.identity.application.dtos.identifiers import (
    PasswordHash,
    SetupTokenId,
)
from restaurant_hub.features.identity.application.dtos.setup_tokens import (
    PasswordSetupToken,
    SetupTokenPurpose,
)
from restaurant_hub.features.identity.domain.entities.restaurant import Restaurant
from restaurant_hub.features.identity.domain.entities.user import User
from restaurant_hub.features.identity.domain.value_objects.email import Email
from restaurant_hub.features.identity.domain.value_objects.identifiers import (
    RestaurantId,
    UserId,
)
from restaurant_hub.features.identity.domain.value_objects.role import Role

pytestmark = pytest.mark.integration

_AGORA = datetime(2026, 7, 20, 12, 0, 0, 123456, tzinfo=UTC)
_DEPOIS = _AGORA + timedelta(minutes=5)


@pytest.fixture
def cenario(banco_limpo: Engine) -> Engine:
    """Um restaurante com dois usuários — a FK de `password_setup_tokens` exige."""
    PostgresRestaurantRepository(banco_limpo).add(
        Restaurant(id=RestaurantId("rest-a"), name="Cantina A")
    )
    usuarios = PostgresUserRepository(banco_limpo)
    for indice in (1, 2):
        usuarios.add(
            User(
                id=UserId(f"user-{indice}"),
                email=Email(f"pessoa{indice}@x.com"),
                role=Role.OWNER if indice == 1 else Role.MANAGER,
                tenant_id=RestaurantId("rest-a"),
            ),
            PasswordHash("hashed::inicial"),
        )
    return banco_limpo


# `noqa: PLR0913` — fábrica de fixture: cada parâmetro é uma coluna do registro.
def _token(  # noqa: PLR0913
    token_id: str = "tok-1",
    *,
    user_id: str = "user-1",
    purpose: SetupTokenPurpose = SetupTokenPurpose.INVITATION,
    fingerprint: str | None = None,
    expires_at: datetime | None = None,
    consumed_at: datetime | None = None,
) -> PasswordSetupToken:
    return PasswordSetupToken(
        id=SetupTokenId(token_id),
        user_id=UserId(user_id),
        purpose=purpose,
        token_fingerprint=fingerprint if fingerprint is not None else f"fp-{token_id}",
        issued_at=_AGORA,
        expires_at=expires_at if expires_at is not None else _AGORA + timedelta(hours=72),
        consumed_at=consumed_at,
    )


# ---------------------------------------------------------------------------
# Round-trip e schema
# ---------------------------------------------------------------------------


def test_token_faz_round_trip_campo_a_campo(cenario: Engine) -> None:
    repo = PostgresPasswordSetupTokenRepository(cenario)
    repo.add(_token())

    lido = repo.find_by_fingerprint("fp-tok-1")

    assert lido is not None
    assert lido.id == "tok-1"
    assert lido.user_id == "user-1"
    assert lido.purpose is SetupTokenPurpose.INVITATION
    assert lido.token_fingerprint == "fp-tok-1"
    assert lido.consumed_at is None


def test_timestamps_preservam_microssegundos_e_fuso(cenario: Engine) -> None:
    """Precisão reduzida truncaria em silêncio a fronteira de expiração."""
    repo = PostgresPasswordSetupTokenRepository(cenario)
    repo.add(_token())

    lido = repo.find_by_fingerprint("fp-tok-1")

    assert lido is not None
    assert lido.issued_at == _AGORA
    assert lido.issued_at.tzinfo is not None


def test_tabela_nao_tem_coluna_para_o_valor_do_token(cenario: Engine) -> None:
    """A garantia é estrutural: não há onde gravar o token utilizável.

    Um dump deste banco não devolve nenhum link de convite que funcione, e isso
    não depende de disciplina de quem escreve o mapper — depende de a coluna não
    existir (ADR 2.5.0002).
    """
    colunas = {c["name"] for c in inspect(cenario).get_columns("password_setup_tokens")}

    assert "token_fingerprint" in colunas
    assert not {"token", "value", "token_value", "plain_token"} & colunas


def test_schema_da_migration_bate_com_o_metadata(cenario: Engine) -> None:
    """CA16 — a migration `0002` e `tables.py` descrevem a mesma tabela.

    Compara nome **e nulabilidade**, não só o conjunto de nomes. A migration
    duplica o schema à mão de propósito (é registro histórico congelado), então
    é justamente o artefato que mais tende a divergir — e um `nullable=False`
    perdido em `expires_at` deixaria passar um token sem prazo, isto é, um token
    que a checagem de expiração nunca recusa.
    """
    inspetor = inspect(cenario)
    esperadas = {
        c.name: c.nullable for c in identity_metadata.tables["password_setup_tokens"].columns
    }

    reais = {c["name"]: c["nullable"] for c in inspetor.get_columns("password_setup_tokens")}

    assert reais == esperadas


def test_indices_da_migration_existem_no_banco(cenario: Engine) -> None:
    """Os dois índices servem `invalidate_all_for_user` e `purge_expired`.

    Sem eles as duas operações viram varredura sequencial — não quebra nada, e é
    exatamente por isso que a ausência passaria despercebida até a tabela crescer.
    """
    nomes = {i["name"] for i in inspect(cenario).get_indexes("password_setup_tokens")}

    assert {"ix_setup_tokens_user_id", "ix_setup_tokens_expires_at"} <= nomes


def test_token_de_usuario_inexistente_e_recusado_pela_fk(cenario: Engine) -> None:
    """A FK é o que obriga o use case a criar o usuário **antes** do token.

    Sem este teste, inverter as duas escritas em `invite_user` mantinha a suíte
    inteira verde — o fake in-memory não tem integridade referencial — e todo
    convite quebrava em produção com `IntegrityError` em `fk_setup_tokens_user`.
    """
    repo = PostgresPasswordSetupTokenRepository(cenario)

    with pytest.raises(IntegrityError):
        repo.add(_token("orfao", user_id="usuario-que-nao-existe"))


def test_fingerprint_repetido_e_recusado_pelo_banco(cenario: Engine) -> None:
    repo = PostgresPasswordSetupTokenRepository(cenario)
    repo.add(_token("tok-1", fingerprint="mesmo"))

    with pytest.raises(IntegrityError):
        repo.add(_token("tok-2", fingerprint="mesmo"))


def test_proposito_fora_do_conjunto_e_recusado(cenario: Engine) -> None:
    """A CHECK derivada do enum impede um propósito que o código não conhece."""
    with pytest.raises(IntegrityError), cenario.begin() as conexao:
        conexao.execute(
            text(
                "INSERT INTO password_setup_tokens "
                "(id, user_id, purpose, token_fingerprint, issued_at, expires_at) "
                "VALUES ('x', 'user-1', 'proposito-invalido', 'fp-x', now(), now())"
            )
        )


# ---------------------------------------------------------------------------
# find_by_fingerprint — não filtra
# ---------------------------------------------------------------------------


def test_find_by_fingerprint_encontra_token_consumido(cenario: Engine) -> None:
    """Filtrar tornaria um replay indistinguível de um token forjado."""
    repo = PostgresPasswordSetupTokenRepository(cenario)
    repo.add(_token(consumed_at=_AGORA))

    assert repo.find_by_fingerprint("fp-tok-1") is not None


def test_find_by_fingerprint_encontra_token_expirado(cenario: Engine) -> None:
    repo = PostgresPasswordSetupTokenRepository(cenario)
    repo.add(_token(expires_at=_AGORA - timedelta(days=1)))

    assert repo.find_by_fingerprint("fp-tok-1") is not None


def test_find_by_fingerprint_desconhecido_devolve_none(cenario: Engine) -> None:
    repo = PostgresPasswordSetupTokenRepository(cenario)

    assert repo.find_by_fingerprint("fp-inexistente") is None


# ---------------------------------------------------------------------------
# consume — o contrato de uso único
# ---------------------------------------------------------------------------


def test_consume_devolve_true_e_depois_false(cenario: Engine) -> None:
    """CA5 (Postgres) — a mesma semântica que o fake honra."""
    repo = PostgresPasswordSetupTokenRepository(cenario)
    repo.add(_token())

    primeiro = repo.consume(SetupTokenId("tok-1"), _AGORA)
    segundo = repo.consume(SetupTokenId("tok-1"), _DEPOIS)

    assert primeiro is True
    assert segundo is False


def test_consume_preserva_o_instante_do_primeiro_consumo(cenario: Engine) -> None:
    repo = PostgresPasswordSetupTokenRepository(cenario)
    repo.add(_token())
    repo.consume(SetupTokenId("tok-1"), _AGORA)
    repo.consume(SetupTokenId("tok-1"), _DEPOIS)

    lido = repo.find_by_fingerprint("fp-tok-1")
    assert lido is not None
    assert lido.consumed_at == _AGORA


def test_consume_de_token_inexistente_devolve_false(cenario: Engine) -> None:
    repo = PostgresPasswordSetupTokenRepository(cenario)

    assert repo.consume(SetupTokenId("nao-existe"), _AGORA) is False


def test_consume_concorrente_deixa_exatamente_um_vencedor(cenario: Engine) -> None:
    """CA9b — o teste que distingue o `UPDATE` condicional do check-then-act.

    Duas threads chamam `consume` no **mesmo** token, sincronizadas por uma
    barreira para que ambas cheguem juntas. Com `UPDATE ... WHERE consumed_at IS
    NULL`, o Postgres serializa as duas escritas na mesma linha e exatamente uma
    afeta uma linha. Com `SELECT` seguido de `UPDATE`, ambas leem nulo antes de
    qualquer gravar, ambas devolvem `True` — e, no fluxo real, ambas definem uma
    senha, sendo a segunda a do atacante.

    Todos os outros testes deste arquivo passam nas duas implementações. Este é o
    único que não.
    """
    repo = PostgresPasswordSetupTokenRepository(cenario)
    repo.add(_token())

    concorrentes = 2
    barreira = threading.Barrier(concorrentes)
    resultados: list[bool] = []
    trava = threading.Lock()

    def redimir() -> None:
        barreira.wait()
        venceu = repo.consume(SetupTokenId("tok-1"), _AGORA)
        with trava:
            resultados.append(venceu)

    threads = [threading.Thread(target=redimir) for _ in range(concorrentes)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sorted(resultados) == [False, True]


# ---------------------------------------------------------------------------
# invalidate_all_for_user e purge_expired
# ---------------------------------------------------------------------------


def test_invalidate_com_proposito_nao_toca_no_outro(cenario: Engine) -> None:
    """CA13 — a rota pública de redefinição não mata um convite pendente."""
    repo = PostgresPasswordSetupTokenRepository(cenario)
    repo.add(_token("convite", purpose=SetupTokenPurpose.INVITATION))
    repo.add(_token("reset", purpose=SetupTokenPurpose.PASSWORD_RESET))

    invalidados = repo.invalidate_all_for_user(
        UserId("user-1"), _AGORA, purpose=SetupTokenPurpose.PASSWORD_RESET
    )

    assert invalidados == 1
    convite = repo.find_by_fingerprint("fp-convite")
    assert convite is not None
    assert convite.consumed_at is None


def test_invalidate_sem_proposito_atinge_todos(cenario: Engine) -> None:
    repo = PostgresPasswordSetupTokenRepository(cenario)
    repo.add(_token("convite", purpose=SetupTokenPurpose.INVITATION))
    repo.add(_token("reset", purpose=SetupTokenPurpose.PASSWORD_RESET))

    esperado = 2
    assert repo.invalidate_all_for_user(UserId("user-1"), _AGORA) == esperado


def test_invalidate_alcanca_token_expirado_e_nao_consumido(cenario: Engine) -> None:
    """Regra 4 do port — o predicado é `consumed_at IS NULL`, sem expiração.

    É o caso em que fake e adapter discordariam em silêncio, e a contagem é
    observável (a CA13 assere sobre ela).
    """
    repo = PostgresPasswordSetupTokenRepository(cenario)
    repo.add(_token("expirado", expires_at=_AGORA - timedelta(days=1)))

    assert repo.invalidate_all_for_user(UserId("user-1"), _AGORA) == 1


def test_invalidate_nao_toca_em_token_de_outro_usuario(cenario: Engine) -> None:
    repo = PostgresPasswordSetupTokenRepository(cenario)
    repo.add(_token("meu", user_id="user-1"))
    repo.add(_token("alheio", user_id="user-2"))

    repo.invalidate_all_for_user(UserId("user-1"), _AGORA)

    alheio = repo.find_by_fingerprint("fp-alheio")
    assert alheio is not None
    assert alheio.consumed_at is None


def test_invalidate_nao_reescreve_consumo_ja_gravado(cenario: Engine) -> None:
    repo = PostgresPasswordSetupTokenRepository(cenario)
    repo.add(_token(consumed_at=_AGORA))

    assert repo.invalidate_all_for_user(UserId("user-1"), _DEPOIS) == 0

    lido = repo.find_by_fingerprint("fp-tok-1")
    assert lido is not None
    assert lido.consumed_at == _AGORA


def test_purge_e_inclusivo_na_fronteira(cenario: Engine) -> None:
    """`is_usable` é half-open, então `expires_at == before` já expirou."""
    repo = PostgresPasswordSetupTokenRepository(cenario)
    repo.add(_token(expires_at=_AGORA))

    assert repo.purge_expired(_AGORA) == 1
    assert repo.find_by_fingerprint("fp-tok-1") is None


def test_purge_preserva_token_ainda_valido(cenario: Engine) -> None:
    repo = PostgresPasswordSetupTokenRepository(cenario)
    repo.add(_token(expires_at=_AGORA + timedelta(seconds=1)))

    assert repo.purge_expired(_AGORA) == 0
