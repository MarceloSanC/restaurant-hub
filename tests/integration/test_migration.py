"""A migration inicial cria e reverte o schema do BC identity — CA1.

O comando `alembic upgrade head` sozinho só prova que **nada explodiu**. Estes
testes provam o que interessa: que as tabelas certas existem, que as constraints
que carregam invariante de domínio chegaram ao banco, e que o `downgrade` limpa o
que o `upgrade` criou.

O `downgrade` importa mais do que costuma parecer: é o caminho de rollback de um
deploy que deu errado, e é justamente o que ninguém exercita até precisar dele às
três da manhã.

A Stage 3.3 acrescentou a `0003_staff` e, com ela, a metade **staff** do mesmo
par (CA13): as cinco tabelas do BC existem após o `upgrade` e **nenhuma**
sobrevive ao `downgrade base`. O detalhe de constraint, índice e tipo daquele
schema fica em `features/staff/adapters/out/postgres/test_schema.py`; aqui só a
existência e a reversibilidade.
"""

import logging

import pytest
from alembic import command
from sqlalchemy import Engine, text

from tests.conftest import alembic_config

pytestmark = [pytest.mark.integration]

_TABELAS_ESPERADAS = {
    "restaurants",
    "units",
    "users",
    "unit_memberships",
    "sessions",
}

# Stage 3.3 — as cinco do BC staff, criadas pela `0003_staff`.
_TABELAS_DE_STAFF = {
    "job_functions",
    "employees",
    "employee_job_functions",
    "employee_unavailabilities",
    "employee_shift_preferences",
}


def _tabelas(engine: Engine) -> set[str]:
    with engine.connect() as conexao:
        linhas = conexao.execute(
            text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
        )
        return {linha[0] for linha in linhas}


def test_migration_criou_as_cinco_tabelas(engine: Engine) -> None:
    """A fixture de sessão aplica a migration; aqui só conferimos o resultado."""
    assert _tabelas(engine) >= _TABELAS_ESPERADAS


def test_migration_criou_as_cinco_tabelas_de_staff(engine: Engine) -> None:
    """CA13, metade do `upgrade` — a `0003_staff` chegou ao banco.

    A cadeia inteira é exercitada a cada sessão de pytest (`_recriar_schema` faz
    `downgrade base` + `upgrade head`), então uma `0003` com `down_revision`
    errado ou ordem de `create_table` inválida falha aqui, e não em quem clonar
    o repo depois.
    """
    assert _tabelas(engine) >= _TABELAS_DE_STAFF


def test_sessions_nao_tem_coluna_para_o_valor_do_refresh_token(engine: Engine) -> None:
    """I5 / CA9 contra o **banco real**, não contra a declaração em Python.

    A asserção é de igualdade de conjunto: qualquer coluna nova em `sessions`
    quebra o teste, inclusive uma chamada `token`, `secret` ou `raw_value`. Um
    dump deste banco não pode devolver refresh token utilizável (ADR 2.2.0001), e
    a garantia só vale se ninguém acrescentar a coluna sem perceber.
    """
    with engine.connect() as conexao:
        colunas = {
            linha[0]
            for linha in conexao.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'sessions'"
                )
            )
        }
    assert colunas == {
        "id",
        "user_id",
        "refresh_token_fingerprint",
        "issued_at",
        "expires_at",
        "revoked_at",
    }


def test_constraints_de_invariante_existem_no_banco(engine: Engine) -> None:
    """As constraints nomeadas chegaram ao banco com os nomes que o adapter espera.

    O adapter traduz `IntegrityError` → exceção de domínio identificando a regra
    **pelo nome da constraint**. Se um nome divergir entre `tables.py`, a migration
    e o banco, a tradução falha só em produção, no primeiro conflito real.
    """
    with engine.connect() as conexao:
        nomes = {linha[0] for linha in conexao.execute(text("SELECT conname FROM pg_constraint"))}

    esperadas = {
        "pk_restaurants",
        "pk_units",
        "fk_units_restaurant",
        "uq_units_id_restaurant",
        "pk_users",
        "uq_users_email",
        "ck_users_email_normalized",
        "ck_users_role_known",
        "ck_users_tenant_iff_platform_admin",
        "fk_users_tenant",
        "uq_users_id_tenant",
        "pk_unit_memberships",
        "fk_memberships_unit",
        "fk_memberships_user",
        "pk_sessions",
        "uq_sessions_fingerprint",
        "fk_sessions_user",
    }
    assert nomes >= esperadas, f"faltando no banco: {sorted(esperadas - nomes)}"


def test_indices_de_sessions_existem(engine: Engine) -> None:
    """Sem eles, `revoke_all_for_user` e `purge_expired` viram varredura sequencial."""
    with engine.connect() as conexao:
        indices = {
            linha[0]
            for linha in conexao.execute(
                text("SELECT indexname FROM pg_indexes WHERE tablename = 'sessions'")
            )
        }
    assert indices >= {"ix_sessions_user_id", "ix_sessions_expires_at"}


@pytest.mark.slow
def test_downgrade_remove_o_que_o_upgrade_criou(engine: Engine, database_url: str) -> None:
    """CA1, metade do `downgrade` — o caminho de rollback de um deploy que deu errado.

    Este teste existe porque a metade `downgrade` do CA1 estava sendo **afirmada** no
    docstring deste módulo e não verificada por nada: `migrations/` está no `omit` da
    cobertura, então nem o gate de cobertura a alcançava. Um `downgrade` com ordem de
    drop errada passaria despercebido até a madrugada em que alguém precisasse dele.

    O teste devolve o banco ao estado anterior no `finally`, inclusive se a asserção
    falhar — o `engine` é de escopo de sessão e compartilhado com o resto da suíte.
    """
    config = alembic_config(database_url)

    try:
        command.downgrade(config, "base")
        restantes = _tabelas(engine) & (_TABELAS_ESPERADAS | _TABELAS_DE_STAFF)
        assert restantes == set(), f"downgrade deixou tabelas para trás: {sorted(restantes)}"
    finally:
        command.upgrade(config, "head")

    # E o upgrade de volta reconstrói tudo — o par é reversível, não só destrutivo.
    assert _tabelas(engine) >= _TABELAS_ESPERADAS | _TABELAS_DE_STAFF


def _colunas_de_employees(engine: Engine) -> set[str]:
    with engine.connect() as conexao:
        linhas = conexao.execute(
            text(
                "SELECT column_name FROM information_schema.columns WHERE table_name = 'employees'"
            )
        )
        return {linha[0] for linha in linhas}


@pytest.mark.slow
def test_downgrade_da_0004_remove_so_a_coluna_user_id(engine: Engine, database_url: str) -> None:
    """CA19 da Stage 3.5, metade do `downgrade` — descer **até a 0003**, não até `base`.

    Achado do Checkpoint C (bloco 2): `test_downgrade_remove_o_que_o_upgrade_criou`
    desce até `base`, e a `0003.downgrade` derruba a tabela `employees` inteira —
    então uma `0004.downgrade` vazia (`pass`), ou que dropasse a coluna errada,
    sobrevivia a ele e a toda a suíte. O único ponto em que o `downgrade` da `0004`
    é observável isoladamente é o estado `0003`: a tabela **existe** e a coluna
    **não**. É isso que este teste mede, e devolve o banco a `head` no `finally`.
    """
    config = alembic_config(database_url)

    assert "user_id" in _colunas_de_employees(engine)
    try:
        command.downgrade(config, "0003")
        colunas = _colunas_de_employees(engine)
        assert "employees" in _tabelas(engine), "a 0004 não pode derrubar a tabela"
        assert "user_id" not in colunas, "downgrade da 0004 deixou `user_id` para trás"
        assert colunas >= {"id", "tenant_id", "unit_id", "name", "active"}, colunas
    finally:
        command.upgrade(config, "head")

    assert "user_id" in _colunas_de_employees(engine)


def test_rodar_as_migrations_nao_desliga_logger_que_ja_existe(
    engine: Engine, database_url: str
) -> None:
    """Issue #26 (finding F1 da #6) — o Alembic in-process não cega o log da app.

    O `fileConfig` de `migrations/env.py` roda a cada comando do Alembic; com o
    default `disable_existing_loggers=True`, todo `logging.getLogger(__name__)`
    criado antes — na suíte, na coleta — ficava `disabled=True`, e um teste de
    `caplog` só passava se rodasse antes do primeiro uso de `engine`. Aqui o
    logger nasce **antes** de um comando do Alembic e é conferido depois dele, no
    mesmo teste: o resultado não depende da ordem da suíte.

    Desde a #86 o `alembic_config` da suíte pula o `fileConfig`
    (`configure_logger=False`); este teste tira a chave para que o `fileConfig`
    rode de fato — é o caminho de um chamador in-process que não a passa. O
    `fileConfig` troca handlers e nível do root, devolvidos no `finally`.
    """
    logger = logging.getLogger("restaurant_hub.tests.sentinela_do_alembic")
    logger.disabled = False
    config = alembic_config(database_url)
    del config.attributes["configure_logger"]
    root = logging.getLogger()
    handlers, nivel = list(root.handlers), root.level

    try:
        command.upgrade(config, "head")
        assert root.level == logging.WARNING, "o fileConfig não rodou: o teste perdeu o objeto"
    finally:
        root.handlers[:] = handlers
        root.setLevel(nivel)

    assert not logger.disabled
