"""O schema de scheduling **no catálogo do Postgres** e as garantias do banco — CA09 e CA10.

`test_tables.py` (unitário) assere o que `tables.py` **declara**; este módulo assere o que o
banco **tem** depois da migration, escrita à mão. Entre as duas existe a migration, e é ali
que uma divergência se instala sem que nenhum teste unitário a note.

CA09: as garantias valem **sem o adapter**, por `INSERT` direto — dias disjuntos por
unidade, ids internos únicos na unidade, o cerco das FKs compostas e as bordas de cada
`CHECK`. É a prova de que a garantia existe onde sobrevive a um bug de código, inclusive a
um escritor que não tome o lock da unidade (ADR 4.4.0003).

CA10: os nomes de constraint e de índice do schema migrado são **os de `tables.py`** — o
tradutor de integridade identifica a regra pelo nome (ADR 3.3.0004).
"""

from collections.abc import Callable, Iterator
from datetime import date, datetime, time
from typing import Any

import pytest
from sqlalchemy import Connection, Engine, Table, text
from sqlalchemy.exc import IntegrityError

from restaurant_hub.features.scheduling.adapters.out.postgres.tables import (
    EX_SCHEDULES_UNIT_DAYS_DISJOINT,
    LIMIT_CHECKS,
    POLICY_FIELDS,
    schedule_assignments,
    schedule_bands,
    schedule_changes,
    schedule_demands,
    schedules,
    scheduling_metadata,
    scheduling_settings,
)
from restaurant_hub.features.scheduling.domain.value_objects.operational_calendar import Weekday
from restaurant_hub.features.scheduling.domain.value_objects.validation_config import (
    EnforcementMode,
    WorkloadDirection,
)

pytestmark = [pytest.mark.integration]

_TABELAS = tuple(scheduling_metadata.tables)
_SEG = date(2026, 11, 2)


def _nome_da_constraint(erro: IntegrityError) -> str | None:
    """O mesmo caminho estruturado que o tradutor usa — nunca texto de mensagem."""
    diag = getattr(getattr(erro, "orig", None), "diag", None)
    nome = getattr(diag, "constraint_name", None)
    return str(nome) if nome else None


# --- linhas legais, por `INSERT` direto (sem mapper, sem entidade) -------------------------


def _escala(conexao: Connection, sid: str, **campos: object) -> None:
    linha: dict[str, Any] = {
        "id": sid,
        "tenant_id": "t1",
        "unit_id": "u1",
        "first_day": _SEG,
        "days": 7,
        "week_start": "monday",
        "day_cutoff": time(5),
        "version": 1,
    }
    conexao.execute(schedules.insert().values({**linha, **campos}))


def _faixa(conexao: Connection, bid: str, sid: str, **campos: object) -> None:
    linha: dict[str, Any] = {
        "tenant_id": "t1",
        "unit_id": "u1",
        "id": bid,
        "schedule_id": sid,
        "position": 0,
        "start_at": datetime(2026, 11, 2, 10),
        "end_at": datetime(2026, 11, 2, 14),
        "break_minutes": 0,
    }
    conexao.execute(schedule_bands.insert().values({**linha, **campos}))


def _demanda(conexao: Connection, did: str, sid: str, bid: str, **campos: object) -> None:
    linha: dict[str, Any] = {
        "tenant_id": "t1",
        "unit_id": "u1",
        "id": did,
        "schedule_id": sid,
        "band_id": bid,
        "position": 0,
        "job_function_id": "cozinheiro",
        "quantity": 1,
    }
    conexao.execute(schedule_demands.insert().values({**linha, **campos}))


def _alocacao(conexao: Connection, aid: str, sid: str, did: str, **campos: object) -> None:
    linha: dict[str, Any] = {
        "tenant_id": "t1",
        "unit_id": "u1",
        "id": aid,
        "schedule_id": sid,
        "demand_id": did,
        "position": 0,
        "employee_id": "ana",
        "counts_toward_workload": True,
        "function_exception": False,
        "break_minutes": None,
    }
    conexao.execute(schedule_assignments.insert().values({**linha, **campos}))


def _mudanca(conexao: Connection, sid: str, **campos: object) -> None:
    linha: dict[str, Any] = {
        "schedule_id": sid,
        "seq": 1,
        "author_user_id": "user-ger",
        "occurred_at": datetime.fromisoformat("2026-11-01T12:00:00+00:00"),
        "previous_version": None,
        "resulting_version": 1,
        "operations": [],
        "acknowledged": [],
    }
    conexao.execute(schedule_changes.insert().values({**linha, **campos}))


def _configuracao(conexao: Connection, **campos: object) -> None:
    linha: dict[str, Any] = {
        "tenant_id": "t1",
        "week_start": "monday",
        "day_cutoff": time(5),
        "min_rest_minutes": 660,
        "daily_cap_minutes": 600,
        "weekly_cap_minutes": 2640,
        "workload_tolerance_minutes": 0,
        "workload_direction": "excess",
    }
    for policy in POLICY_FIELDS:
        linha[f"{policy}_enabled"] = True
        linha[f"{policy}_mode"] = "warn"
    conexao.execute(scheduling_settings.insert().values({**linha, **campos}))


@pytest.fixture
def banco(banco_limpo: Engine) -> Iterator[Engine]:
    """O banco limpo com a escala `s1` (faixa `f1`, demanda `d1`, alocação `a1`) gravada."""
    with banco_limpo.begin() as conexao:
        _escala(conexao, "s1")
        _faixa(conexao, "f1", "s1")
        _demanda(conexao, "d1", "s1", "f1")
        _alocacao(conexao, "a1", "s1", "d1")
    yield banco_limpo


def _recusa(engine: Engine, escrita: Callable[[Connection], object]) -> str | None:
    """Roda a escrita numa transação própria e devolve o nome da constraint que a recusou."""
    with pytest.raises(IntegrityError) as capturado, engine.begin() as conexao:
        escrita(conexao)
    return _nome_da_constraint(capturado.value)


# ---------------------------------------------------------------------------
# CA10 — o catálogo tem os nomes de `tables.py`
# ---------------------------------------------------------------------------


def _nomes_declarados(tabela: Table) -> set[str]:
    return {str(c.name) for c in tabela.constraints if c.name is not None}


def test_constraints_do_banco_sao_as_de_tables_py(engine: Engine) -> None:
    """Igualdade, não subconjunto: constraint só na migration também é divergência."""
    with engine.connect() as conexao:
        nomes = {
            linha[0]
            for linha in conexao.execute(
                text(
                    "SELECT c.conname FROM pg_constraint c "
                    "JOIN pg_class t ON t.oid = c.conrelid WHERE t.relname = ANY(:tabelas)"
                ),
                {"tabelas": list(_TABELAS)},
            )
        }
    declarados = {
        nome for tabela in scheduling_metadata.tables.values() for nome in _nomes_declarados(tabela)
    }
    assert nomes == declarados, (
        f"faltando: {sorted(declarados - nomes)}; sobrando: {sorted(nomes - declarados)}"
    )


def test_indices_nao_unicos_do_banco_sao_os_de_tables_py(engine: Engine) -> None:
    """Os índices sem constraint não aparecem em `pg_constraint` — só no catálogo de índices."""
    with engine.connect() as conexao:
        indices = {
            linha[0]
            for linha in conexao.execute(
                text(
                    "SELECT i.relname FROM pg_index x "
                    "JOIN pg_class i ON i.oid = x.indexrelid "
                    "JOIN pg_class t ON t.oid = x.indrelid "
                    "LEFT JOIN pg_constraint c ON c.conindid = x.indexrelid "
                    "WHERE t.relname = ANY(:tabelas) AND c.oid IS NULL"
                ),
                {"tabelas": list(_TABELAS)},
            )
        }
    declarados = {
        str(index.name)
        for tabela in scheduling_metadata.tables.values()
        for index in tabela.indexes
    }
    assert indices == declarados


def test_confdeltype_de_cada_fk(engine: Engine) -> None:
    """`c` (CASCADE) nas filhas do agregado; `r` (RESTRICT) na trilha."""
    with engine.connect() as conexao:
        acoes = {
            linha[0]: linha[1]
            for linha in conexao.execute(
                text(
                    "SELECT c.conname, c.confdeltype FROM pg_constraint c "
                    "JOIN pg_class t ON t.oid = c.conrelid "
                    "WHERE c.contype = 'f' AND t.relname = ANY(:tabelas)"
                ),
                {"tabelas": list(_TABELAS)},
            )
        }
    assert acoes == {
        "fk_schedule_bands_schedule": "c",
        "fk_schedule_demands_band": "c",
        "fk_schedule_assignments_demand": "c",
        "fk_schedule_changes_schedule": "r",
    }


def test_tipos_dos_dois_regimes_de_tempo_no_banco(engine: Engine) -> None:
    with engine.connect() as conexao:
        tipos = {
            (linha[0], linha[1]): linha[2]
            for linha in conexao.execute(
                text(
                    "SELECT table_name, column_name, data_type FROM information_schema.columns "
                    "WHERE table_name = ANY(:tabelas)"
                ),
                {"tabelas": list(_TABELAS)},
            )
        }
    assert tipos[("schedule_bands", "start_at")] == "timestamp without time zone"
    assert tipos[("schedule_bands", "end_at")] == "timestamp without time zone"
    assert tipos[("schedule_changes", "occurred_at")] == "timestamp with time zone"
    assert tipos[("schedules", "first_day")] == "date"
    assert tipos[("schedules", "day_cutoff")] == "time without time zone"
    assert tipos[("scheduling_settings", "day_cutoff")] == "time without time zone"
    assert tipos[("schedule_changes", "operations")] == "jsonb"
    assert tipos[("schedule_changes", "acknowledged")] == "jsonb"


def test_colunas_do_banco_sao_as_de_tables_py_com_a_mesma_nulabilidade(engine: Engine) -> None:
    with engine.connect() as conexao:
        colunas = {
            (linha[0], linha[1]): linha[2] == "YES"
            for linha in conexao.execute(
                text(
                    "SELECT table_name, column_name, is_nullable FROM information_schema.columns "
                    "WHERE table_name = ANY(:tabelas)"
                ),
                {"tabelas": list(_TABELAS)},
            )
        }
    declaradas = {
        (tabela.name, coluna.name): bool(coluna.nullable)
        for tabela in scheduling_metadata.tables.values()
        for coluna in tabela.columns
    }
    assert colunas == declaradas


# ---------------------------------------------------------------------------
# CA09 — dias disjuntos por unidade (L-SC2), por `INSERT` direto
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("primeiro_dia", "dias"),
    [(_SEG, 7), (date(2026, 11, 8), 1), (date(2026, 10, 27), 7), (date(2026, 10, 1), 31)],
    ids=["mesmo-periodo", "ultimo-dia", "primeiro-dia", "envolve"],
)
def test_periodo_que_cruza_outra_escala_da_unidade_e_recusado(
    banco: Engine, primeiro_dia: date, dias: int
) -> None:
    nome = _recusa(banco, lambda c: _escala(c, "s2", first_day=primeiro_dia, days=dias))
    assert nome == EX_SCHEDULES_UNIT_DAYS_DISJOINT


def test_periodo_adjacente_outra_unidade_e_outro_tenant_passam(banco: Engine) -> None:
    """`[)`: o dia seguinte ao último é livre; e a exclusão é por (tenant, unidade)."""
    with banco.begin() as conexao:
        _escala(conexao, "s2", first_day=date(2026, 11, 9))
        _escala(conexao, "s3", first_day=date(2026, 10, 26))
        _escala(conexao, "s4", unit_id="u2")
        _escala(conexao, "s5", tenant_id="t2")
        total = conexao.execute(text("SELECT count(*) FROM schedules")).scalar_one()
    assert total == 5  # noqa: PLR2004


# ---------------------------------------------------------------------------
# CA09 — ids e o cerco
# ---------------------------------------------------------------------------


def test_id_de_escala_colide_em_qualquer_tenant(banco: Engine) -> None:
    nome = _recusa(banco, lambda c: _escala(c, "s1", tenant_id="t2", first_day=date(2026, 12, 7)))
    assert nome == "pk_schedules"


def test_id_interno_repetido_na_unidade_e_recusado_e_em_outra_unidade_passa(banco: Engine) -> None:
    with banco.begin() as conexao:
        _escala(conexao, "s2", first_day=date(2026, 11, 9))
    assert _recusa(banco, lambda c: _faixa(c, "f1", "s2")) == "pk_schedule_bands"
    with banco.begin() as conexao:
        _faixa(
            conexao,
            "f2",
            "s2",
            start_at=datetime(2026, 11, 9, 10),
            end_at=datetime(2026, 11, 9, 14),
        )
    assert _recusa(banco, lambda c: _demanda(c, "d1", "s2", "f2")) == "pk_schedule_demands"
    with banco.begin() as conexao:
        _demanda(conexao, "d2", "s2", "f2")
    assert _recusa(banco, lambda c: _alocacao(c, "a1", "s2", "d2")) == "pk_schedule_assignments"
    with banco.begin() as conexao:
        _escala(conexao, "s3", unit_id="u2")
        _faixa(conexao, "f1", "s3", unit_id="u2")


def test_filha_presa_ao_pai_de_outra_escala_viola_o_cerco(banco: Engine) -> None:
    """A demanda da escala `s2` não pode pendurar-se na faixa `f1`, que é da `s1`."""
    with banco.begin() as conexao:
        _escala(conexao, "s2", first_day=date(2026, 11, 9))
        _faixa(
            conexao,
            "f2",
            "s2",
            start_at=datetime(2026, 11, 9, 10),
            end_at=datetime(2026, 11, 9, 14),
        )
        _demanda(conexao, "d2", "s2", "f2")
    assert _recusa(banco, lambda c: _demanda(c, "d9", "s2", "f1")) == "fk_schedule_demands_band"
    assert _recusa(banco, lambda c: _alocacao(c, "a9", "s2", "d1")) == (
        "fk_schedule_assignments_demand"
    )
    assert _recusa(banco, lambda c: _faixa(c, "f9", "s1", unit_id="u2")) == (
        "fk_schedule_bands_schedule"
    )


def test_as_filhas_caem_em_cascata_e_a_trilha_impede_apagar_a_escala(banco: Engine) -> None:
    with banco.begin() as conexao:
        conexao.execute(text("DELETE FROM schedule_bands WHERE id = 'f1'"))
        restantes = conexao.execute(
            text(
                "SELECT (SELECT count(*) FROM schedule_demands)"
                " + (SELECT count(*) FROM schedule_assignments)"
            )
        ).scalar_one()
        _mudanca(conexao, "s1")
    assert restantes == 0
    nome = _recusa(banco, lambda c: c.execute(text("DELETE FROM schedules WHERE id = 's1'")))
    assert nome == "fk_schedule_changes_schedule"


# ---------------------------------------------------------------------------
# CA09 — as bordas de cada `CHECK`
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("dias", "aceito"), [(0, False), (1, True), (31, True), (32, False)])
def test_borda_de_days(banco_limpo: Engine, dias: int, aceito: bool) -> None:
    if aceito:
        with banco_limpo.begin() as conexao:
            _escala(conexao, "s1", days=dias)
    else:
        assert _recusa(banco_limpo, lambda c: _escala(c, "s1", days=dias)) == (
            "ck_schedules_days_range"
        )


def test_borda_de_version(banco_limpo: Engine) -> None:
    assert _recusa(banco_limpo, lambda c: _escala(c, "s1", version=0)) == (
        "ck_schedules_version_positive"
    )
    with banco_limpo.begin() as conexao:
        _escala(conexao, "s1", version=1)


@pytest.mark.parametrize("dia", list(Weekday), ids=[w.value for w in Weekday])
def test_cada_dia_da_semana_do_enum_e_aceito(banco_limpo: Engine, dia: Weekday) -> None:
    """O lado positivo da concordância: a lista da migration é congelada, não derivada."""
    with banco_limpo.begin() as conexao:
        _escala(conexao, "s1", week_start=dia.value)
        _configuracao(conexao, week_start=dia.value)


def test_dia_da_semana_desconhecido_e_recusado(banco_limpo: Engine) -> None:
    assert _recusa(banco_limpo, lambda c: _escala(c, "s1", week_start="Monday")) == (
        "ck_schedules_week_start_known"
    )
    assert _recusa(banco_limpo, lambda c: _configuracao(c, week_start="feriado")) == (
        "ck_scheduling_settings_week_start_known"
    )


def test_bordas_da_faixa(banco: Engine) -> None:
    with banco.begin() as conexao:
        _escala(conexao, "s2", first_day=date(2026, 11, 9))
    instante = datetime(2026, 11, 9, 10)
    assert _recusa(banco, lambda c: _faixa(c, "f2", "s2", start_at=instante, end_at=instante)) == (
        "ck_schedule_bands_period"
    )
    fim = datetime(2026, 11, 9, 14)
    assert _recusa(
        banco, lambda c: _faixa(c, "f2", "s2", start_at=instante, end_at=fim, break_minutes=-1)
    ) == ("ck_schedule_bands_break_non_negative")
    with banco.begin() as conexao:
        _faixa(conexao, "f2", "s2", start_at=instante, end_at=fim, break_minutes=0)


def test_bordas_da_demanda(banco: Engine) -> None:
    assert _recusa(banco, lambda c: _demanda(c, "d2", "s1", "f1", quantity=-1)) == (
        "ck_schedule_demands_quantity_non_negative"
    )
    with banco.begin() as conexao:
        _demanda(conexao, "d2", "s1", "f1", job_function_id="atendente", quantity=0)


def test_bordas_da_alocacao(banco: Engine) -> None:
    """`NULL` (herda) e `0` (intervalo próprio zero) são dois estados aceitos; `-1` não."""
    assert _recusa(banco, lambda c: _alocacao(c, "a2", "s1", "d1", break_minutes=-1)) == (
        "ck_schedule_assignments_break_non_negative"
    )
    with banco.begin() as conexao:
        _alocacao(conexao, "a2", "s1", "d1", employee_id="bia", break_minutes=0)
        _alocacao(conexao, "a3", "s1", "d1", employee_id="caio", break_minutes=None)
        intervalos = {
            linha[0]: linha[1]
            for linha in conexao.execute(text("SELECT id, break_minutes FROM schedule_assignments"))
        }
    assert intervalos == {"a1": None, "a2": 0, "a3": None}


def test_bordas_da_trilha(banco: Engine) -> None:
    assert _recusa(banco, lambda c: _mudanca(c, "s1", seq=0)) == "ck_schedule_changes_seq_positive"
    assert _recusa(banco, lambda c: _mudanca(c, "s1", operations={"kind": "x"})) == (
        "ck_schedule_changes_operations_is_array"
    )
    assert _recusa(banco, lambda c: _mudanca(c, "s1", acknowledged="nada")) == (
        "ck_schedule_changes_acknowledged_is_array"
    )
    assert _recusa(banco, lambda c: _mudanca(c, "s9")) == "fk_schedule_changes_schedule"
    with banco.begin() as conexao:
        _mudanca(conexao, "s1", seq=1)
    assert _recusa(banco, lambda c: _mudanca(c, "s1", seq=1)) == "pk_schedule_changes"


@pytest.mark.parametrize("modo", list(EnforcementMode), ids=[m.value for m in EnforcementMode])
def test_cada_modo_do_enum_e_aceito_em_cada_politica(
    banco_limpo: Engine, modo: EnforcementMode
) -> None:
    with banco_limpo.begin() as conexao:
        _configuracao(conexao, **{f"{policy}_mode": modo.value for policy in POLICY_FIELDS})


@pytest.mark.parametrize("politica", POLICY_FIELDS)
def test_modo_desconhecido_e_recusado_em_cada_politica(banco_limpo: Engine, politica: str) -> None:
    nome = _recusa(banco_limpo, lambda c: _configuracao(c, **{f"{politica}_mode": "BLOCK"}))
    assert nome == f"ck_scheduling_settings_{politica}_mode_known"


@pytest.mark.parametrize(
    "direcao", list(WorkloadDirection), ids=[d.value for d in WorkloadDirection]
)
def test_cada_direcao_do_enum_e_aceita(banco_limpo: Engine, direcao: WorkloadDirection) -> None:
    with banco_limpo.begin() as conexao:
        _configuracao(conexao, workload_direction=direcao.value)


def test_direcao_desconhecida_e_recusada(banco_limpo: Engine) -> None:
    assert _recusa(banco_limpo, lambda c: _configuracao(c, workload_direction="deficit")) == (
        "ck_scheduling_settings_workload_direction_known"
    )


# Para cada limite: o menor valor aceito e o maior recusado (`>= 0` → 0 e -1; `> 0` → 1 e 0).
_BORDAS_DOS_LIMITES = {
    ">= 0": (0, -1),
    "> 0": (1, 0),
}


@pytest.mark.parametrize(("limite", "faixa"), LIMIT_CHECKS)
def test_bordas_de_cada_limite(banco_limpo: Engine, limite: str, faixa: str) -> None:
    aceito, recusado = _BORDAS_DOS_LIMITES[faixa]
    nome = _recusa(banco_limpo, lambda c: _configuracao(c, **{limite: recusado}))
    assert nome == f"ck_scheduling_settings_{limite}_range"
    with banco_limpo.begin() as conexao:
        _configuracao(conexao, **{limite: aceito})


def test_configuracao_e_uma_linha_por_tenant(banco_limpo: Engine) -> None:
    with banco_limpo.begin() as conexao:
        _configuracao(conexao, tenant_id="t1")
        _configuracao(conexao, tenant_id="t2")
    assert (
        _recusa(banco_limpo, lambda c: _configuracao(c, tenant_id="t1")) == "pk_scheduling_settings"
    )


def test_toda_coluna_da_configuracao_e_obrigatoria(banco_limpo: Engine) -> None:
    """Nenhum default de servidor completa uma linha: omitir uma coluna é `NOT NULL` violado."""
    colunas = [coluna.name for coluna in scheduling_settings.columns if coluna.name != "tenant_id"]
    for coluna in colunas:
        with pytest.raises(IntegrityError) as capturado, banco_limpo.begin() as conexao:
            _configuracao(conexao, **{coluna: None})
        assert getattr(capturado.value.orig, "sqlstate", None) == "23502", coluna
