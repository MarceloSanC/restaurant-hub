"""Testes do schema declarado em `tables.py` — sem banco.

Estes testes não substituem os de integração (que exercitam as constraints contra
o Postgres de verdade); eles guardam as propriedades do schema que são **fáceis de
quebrar por edição descuidada e caras de descobrir em produção**:

- um nome de constraint alterado quebra a tradução de `IntegrityError` → exceção
  de domínio, e o efeito só aparece como 500 no primeiro conflito real;
- uma coluna nova em `sessions` pode reintroduzir a possibilidade de persistir o
  valor do refresh token, que o ADR 2.2.0001 proíbe;
- perder o `NOT NULL` de `users.role` reabre o buraco de lógica ternária da CHECK
  de tenancy, sem quebrar nenhum teste de caminho feliz.
"""

import pytest
from sqlalchemy import CheckConstraint, UniqueConstraint

from restaurant_hub.features.identity.adapters.out.postgres.tables import (
    identity_metadata,
    password_setup_tokens,
    sessions,
    unit_memberships,
    units,
    users,
)
from restaurant_hub.features.identity.application.dtos.setup_tokens import (
    SetupTokenPurpose,
)
from restaurant_hub.features.identity.domain.value_objects.role import Role

pytestmark = pytest.mark.unit


def _constraint_names(table: object) -> set[str]:
    return {c.name for c in table.constraints if c.name is not None}  # type: ignore[attr-defined]


def test_metadata_declara_exatamente_as_seis_tabelas() -> None:
    """Tabela nova ou removida força revisão consciente — e da migration junto."""
    assert set(identity_metadata.tables) == {
        "restaurants",
        "units",
        "users",
        "unit_memberships",
        "sessions",
        # Stage 2.5 — o registro que torna o uso único do token de definição de
        # senha uma garantia do banco (ADR 2.5.0002).
        "password_setup_tokens",
    }


def test_setup_tokens_nao_tem_coluna_capaz_de_guardar_o_valor_do_token() -> None:
    """Mesma disciplina de `sessions`: só o fingerprint é persistido.

    Igualdade de conjunto, e não ausência de um nome específico: uma coluna nova
    chamada qualquer coisa (`token`, `secret`, `raw_value`) quebra o teste, que é
    o ponto. Um dump deste banco não pode devolver link de convite utilizável.
    """
    assert {c.name for c in password_setup_tokens.columns} == {
        "id",
        "user_id",
        "purpose",
        "token_fingerprint",
        "issued_at",
        "expires_at",
        "consumed_at",
    }


def test_check_de_proposito_deriva_do_enum() -> None:
    """Repetir a lista à mão criaria duas fontes de verdade que divergem.

    Um propósito novo em `SetupTokenPurpose` sem entrada na CHECK só apareceria
    como `IntegrityError` em produção.
    """
    checks = [c for c in password_setup_tokens.constraints if isinstance(c, CheckConstraint)]
    texto = " ".join(str(c.sqltext) for c in checks)

    for purpose in SetupTokenPurpose:
        assert f"'{purpose.value}'" in texto


def test_sessions_nao_tem_coluna_capaz_de_guardar_o_valor_do_refresh_token() -> None:
    """Invariante I5 / CA9: só o fingerprint é persistido (ADR 2.2.0001).

    A asserção é de **igualdade de conjunto**, não de ausência de um nome
    específico: uma coluna nova chamada qualquer coisa (`token`, `secret`,
    `raw_value`) quebra o teste, que é o ponto. Verificar `"value" not in colunas`
    protegeria contra um nome e nenhum outro.
    """
    assert {c.name for c in sessions.columns} == {
        "id",
        "user_id",
        "refresh_token_fingerprint",
        "issued_at",
        "expires_at",
        "revoked_at",
    }


def test_sessions_nao_tem_tenant_id() -> None:
    """Decisão 2 do concept: a coluna seria inatingível pelo port e pelo fake.

    O tenant de uma sessão vem de `users.tenant_id`, que é a fonte. Reintroduzir
    a coluna aqui traria de volta a FK composta sobre coluna anulável — inerte por
    MATCH SIMPLE exatamente para `platform_admin`.
    """
    assert "tenant_id" not in {c.name for c in sessions.columns}


def test_email_tem_unicidade_global_sem_tenant_na_chave() -> None:
    """Kickoff #2 / I2: um índice `(tenant_id, email)` deixaria o mesmo login
    existir em dois restaurantes, e passaria em qualquer teste de caminho feliz."""
    uniques = [c for c in users.constraints if isinstance(c, UniqueConstraint)]
    email_unique = [c for c in uniques if c.name == "uq_users_email"]
    assert len(email_unique) == 1
    assert [col.name for col in email_unique[0].columns] == ["email"]


def test_users_role_e_not_null() -> None:
    """O `NOT NULL` é load-bearing, não decoração.

    Uma CHECK em Postgres só rejeita em `FALSE`. Com `role` nulo,
    `(role = 'platform_admin') = (tenant_id IS NULL)` avalia `NULL` e a linha
    **passa** — um `owner` sem tenant entraria pela porta dos fundos.
    """
    assert users.c.role.nullable is False


def test_users_tem_as_tres_checks_de_invariante() -> None:
    nomes = {c.name for c in users.constraints if isinstance(c, CheckConstraint)}
    assert nomes == {
        "ck_users_email_normalized",
        "ck_users_role_known",
        "ck_users_tenant_iff_platform_admin",
    }


def test_check_de_papel_cobre_exatamente_o_enum_de_dominio() -> None:
    """Derivar do enum evita duas fontes de verdade.

    Se a lista fosse repetida à mão, um papel novo em `Role` divergiria do banco e
    a divergência só apareceria como `IntegrityError` em produção.
    """
    check = next(
        c
        for c in users.constraints
        if isinstance(c, CheckConstraint) and c.name == "ck_users_role_known"
    )
    sql = str(check.sqltext)
    for role in Role:
        assert f"'{role.value}'" in sql


def test_tenant_id_e_anulavel_apenas_em_users() -> None:
    """`platform_admin` vive fora de tenant; vínculo, não (senão a FK fica inerte)."""
    assert users.c.tenant_id.nullable is True
    assert unit_memberships.c.tenant_id.nullable is False


def test_unit_memberships_tem_pk_composta_e_as_duas_fks_de_tenant() -> None:
    """I4: as duas FKs juntas tornam vínculo cross-tenant irrepresentável.

    Uma só deixaria o outro lado livre — metade do cerco e nenhuma garantia.
    """
    assert [col.name for col in unit_memberships.primary_key.columns] == [
        "user_id",
        "unit_id",
    ]
    fk_names = {fk.constraint.name for fk in unit_memberships.foreign_keys}
    assert fk_names == {"fk_memberships_unit", "fk_memberships_user"}


def test_ancoras_das_fks_compostas_existem() -> None:
    """Sem estes `UNIQUE` o Postgres recusa criar as FKs compostas.

    Não é redundância com a PK: o Postgres exige índice único cobrindo exatamente
    as colunas referenciadas. Removê-los quebra `alembic upgrade head`, não algum
    teste sutil.
    """
    assert "uq_units_id_restaurant" in _constraint_names(units)
    assert "uq_users_id_tenant" in _constraint_names(users)


def test_toda_constraint_tem_nome_explicito() -> None:
    """A tradução `IntegrityError` → domínio identifica a regra pelo NOME.

    Nome autogerado varia entre ambientes e faria a tradução funcionar em teste e
    falhar em produção.
    """
    for table in identity_metadata.tables.values():
        for constraint in table.constraints:
            assert constraint.name is not None, f"constraint sem nome em {table.name}"
            assert not str(constraint.name).startswith("_unnamed_"), (
                f"constraint autogerada em {table.name}"
            )
        for index in table.indexes:
            assert index.name is not None


def test_colunas_de_tempo_sao_timestamptz() -> None:
    """Fuso é parte do dado (I10).

    Um `TIMESTAMP` sem fuso guardaria o instante errado assim que a sessão do
    banco não estivesse em UTC.
    """
    for coluna in (sessions.c.issued_at, sessions.c.expires_at, sessions.c.revoked_at):
        assert coluna.type.timezone is True  # type: ignore[attr-defined]


def test_sessions_indexa_o_que_os_metodos_do_port_varrem() -> None:
    """`revoke_all_for_user` varre por usuário; `purge_expired`, por expiração."""
    assert {i.name for i in sessions.indexes} == {
        "ix_sessions_user_id",
        "ix_sessions_expires_at",
    }
