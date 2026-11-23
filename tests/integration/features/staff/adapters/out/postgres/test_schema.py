"""O schema de staff **no catálogo do Postgres** — CA14 e CA15.

`test_tables.py` (unitário) assere o que `tables.py` **declara**; este módulo
assere o que o banco **tem**. A distinção não é redundância: entre a declaração e
o banco existe a migration, escrita à mão de propósito (registro histórico
congelado), e é exatamente aí que uma divergência se instala sem que nenhum teste
unitário note.

Três coisas só o catálogo confirma:

1. **Os dois índices não-únicos.** Eles não aparecem em `pg_constraint` — uma
   verificação que consultasse só aquela view daria verde com os dois ausentes, e
   o `RESTRICT` da FK passaria a varrer a tabela inteira a cada remoção de
   função.
2. **O `confdeltype` de cada FK.** `CASCADE` e `RESTRICT` são invariantes de
   negócio aqui (os filhos somem com o agregado; a função referenciada não é
   apagável), e trocá-los não quebra nenhum caminho feliz.
3. **Os tipos de coluna.** Em especial `weekly_hours`: `numeric` **sem**
   precisão. Uma `NUMERIC(5,2)` gravaria e leria sem erro — arredondando em
   silêncio.

E CA15: as linhas ilegais são recusadas **pelo banco**, por `INSERT` direto, sem
passar por mapper nem por entidade. É a prova de que a guarda existe onde ela
sobrevive a um bug de código.
"""

from decimal import Decimal

import pytest
from sqlalchemy import Connection, Engine, text
from sqlalchemy.exc import IntegrityError

from restaurant_hub.features.staff.adapters.out.postgres.tables import (
    WORKLOAD_KIND_FIXED,
    WORKLOAD_KINDS,
)
from restaurant_hub.features.staff.domain.value_objects.shift_preference import DayPeriod

pytestmark = [pytest.mark.integration]

_TABELAS_DE_STAFF = (
    "job_functions",
    "job_function_units",
    "employees",
    "employee_job_functions",
    "employee_unavailabilities",
    "employee_shift_preferences",
)

_CONSTRAINTS_ESPERADAS = {
    "pk_job_functions",
    "uq_job_functions_tenant_name",
    "uq_job_functions_id_tenant",
    "pk_job_function_units",
    "fk_job_function_units_job_function",
    "pk_employees",
    "uq_employees_id_tenant",
    "ck_employees_workload_kind_known",
    "ck_employees_workload_iff_hours",
    "ck_employees_weekly_hours_positive",
    "pk_employee_job_functions",
    "fk_employee_job_functions_employee",
    "fk_employee_job_functions_job_function",
    "pk_employee_unavailabilities",
    "fk_employee_unavailabilities_employee",
    "ck_employee_unavailabilities_period",
    "pk_employee_shift_preferences",
    "fk_employee_shift_preferences_employee",
    "ck_employee_shift_preferences_period_known",
}


def _nome_da_constraint(erro: IntegrityError) -> str | None:
    """O mesmo caminho estruturado que o tradutor usa — nunca texto de mensagem."""
    original = getattr(erro, "orig", None)
    diag = getattr(original, "diag", None)
    nome = getattr(diag, "constraint_name", None)
    return str(nome) if nome else None


def _semear_funcao_e_funcionario(engine: Engine) -> None:
    """Uma função e um funcionário legais, para as filhas terem pai."""
    with engine.begin() as conexao:
        conexao.execute(
            text(
                "INSERT INTO job_functions (id, tenant_id, name) VALUES ('f1', 't1', 'Cozinheiro')"
            )
        )
        conexao.execute(
            text(
                "INSERT INTO employees "
                "(id, tenant_id, unit_id, name, workload_kind, weekly_hours, active) "
                "VALUES ('e1', 't1', 'u1', 'Ana', 'on_demand', NULL, true)"
            )
        )


# ---------------------------------------------------------------------------
# CA14 — o catálogo confirma nomes, tipos, índices e ações de FK
# ---------------------------------------------------------------------------


def test_constraints_de_staff_existem_no_banco_com_os_nomes_esperados(engine: Engine) -> None:
    """O tradutor identifica a regra **pelo nome** (ADR 3.3.0004).

    Um nome divergente entre `tables.py`, a migration e o banco só apareceria em
    produção, no primeiro conflito real — como 500, não como teste vermelho.
    """
    with engine.connect() as conexao:
        nomes = {
            linha[0]
            for linha in conexao.execute(
                text(
                    "SELECT c.conname FROM pg_constraint c "
                    "JOIN pg_class t ON t.oid = c.conrelid "
                    "WHERE t.relname = ANY(:tabelas)"
                ),
                {"tabelas": list(_TABELAS_DE_STAFF)},
            )
        }
    # **Igualdade, não subconjunto** — espelha o gêmeo unitário
    # (`test_nomes_de_constraint_de_cada_tabela`). Com `>=`, uma constraint que
    # existisse só na migration e não em `tables.py` passaria despercebida, que
    # é justamente a divergência que este módulo existe para pegar: entre a
    # declaração e o banco existe a migration, escrita à mão.
    assert nomes == _CONSTRAINTS_ESPERADAS, (
        f"faltando: {sorted(_CONSTRAINTS_ESPERADAS - nomes)}; "
        f"sobrando: {sorted(nomes - _CONSTRAINTS_ESPERADAS)}"
    )


def test_os_dois_indices_nao_unicos_existem(engine: Engine) -> None:
    """Eles **não** aparecem em `pg_constraint` — escapariam de uma consulta só.

    Sem `ix_employee_job_functions_function`, o `RESTRICT` da FK varre a tabela
    inteira a cada remoção de função; sem `ix_employees_tenant_unit`,
    `list_by_unit` faz o mesmo. Nenhum dos dois quebra teste de resultado.
    """
    with engine.connect() as conexao:
        indices = {
            linha[0]
            for linha in conexao.execute(
                text("SELECT indexname FROM pg_indexes WHERE tablename = ANY(:tabelas)"),
                {"tabelas": list(_TABELAS_DE_STAFF)},
            )
        }
    assert {
        "ix_employees_tenant_unit",
        "ix_employee_job_functions_function",
        "ix_job_function_units_tenant_unit",
        "uq_employees_tenant_unit_user",
    } <= indices


def test_confdeltype_de_cada_fk(engine: Engine) -> None:
    """`r` (RESTRICT) na FK da função; `c` (CASCADE) nas três de filha para pai.

    Trocar os dois é a mutação mais barata e mais destrutiva do schema: com
    `CASCADE` na função, apagá-la apagaria os vínculos em silêncio, deixando
    funcionário sem nenhuma função — estado que a 3.1 declara impossível e que
    `find_by_id` passaria a rejeitar ao ler.
    """
    with engine.connect() as conexao:
        acoes = {
            linha[0]: linha[1]
            for linha in conexao.execute(
                text(
                    "SELECT c.conname, c.confdeltype FROM pg_constraint c "
                    "JOIN pg_class t ON t.oid = c.conrelid "
                    "WHERE c.contype = 'f' AND t.relname = ANY(:tabelas)"
                ),
                {"tabelas": list(_TABELAS_DE_STAFF)},
            )
        }
    assert acoes == {
        "fk_employee_job_functions_job_function": "r",
        "fk_employee_job_functions_employee": "c",
        "fk_employee_unavailabilities_employee": "c",
        "fk_employee_shift_preferences_employee": "c",
        "fk_job_function_units_job_function": "c",
    }


def test_nenhuma_fk_de_staff_aponta_para_tabela_de_identity(engine: Engine) -> None:
    """ADR 3.3.0002 verificado **no catálogo**, não só no `MetaData`.

    Os dois BCs compartilham o mesmo banco nesta fase, então nada além desta
    asserção impede uma FK de `employees.tenant_id` para `restaurants.id` — que
    amarraria os dois ao mesmo banco para sempre e faria a suíte de contrato de
    staff precisar semear identity para provar staff.
    """
    with engine.connect() as conexao:
        alvos = {
            (linha[0], linha[1])
            for linha in conexao.execute(
                text(
                    "SELECT c.conname, alvo.relname FROM pg_constraint c "
                    "JOIN pg_class t ON t.oid = c.conrelid "
                    "JOIN pg_class alvo ON alvo.oid = c.confrelid "
                    "WHERE c.contype = 'f' AND t.relname = ANY(:tabelas)"
                ),
                {"tabelas": list(_TABELAS_DE_STAFF)},
            )
        }
    fora = {(nome, alvo) for nome, alvo in alvos if alvo not in _TABELAS_DE_STAFF}
    assert fora == set(), f"FK de staff atravessando o BC: {sorted(fora)}"


# Contagem transcrita (concept 3.5 §9): as sete da 3.3 mais `user_id`.
_COLUNAS_DE_EMPLOYEES = 8


def test_tipos_de_coluna_de_employees(engine: Engine) -> None:
    """`weekly_hours` é `numeric` **sem** precisão — tipo é contrato (§9).

    `NUMERIC(5,2)` gravaria e leria sem erro nenhum, arredondando em silêncio
    (`22.555 → 22.56`, `0.001 → 0.00`), o que passa em qualquer asserção sobre
    "gravou e leu" e corrompe o dado contra a disciplina verbatim do projeto.
    """
    with engine.connect() as conexao:
        colunas = {
            linha[0]: (linha[1], linha[2], linha[3], linha[4])
            for linha in conexao.execute(
                text(
                    "SELECT column_name, data_type, numeric_precision, numeric_scale, is_nullable "
                    "FROM information_schema.columns WHERE table_name = 'employees'"
                )
            )
        }

    assert colunas["weekly_hours"] == ("numeric", None, None, "YES")
    assert colunas["workload_kind"] == ("text", None, None, "NO")
    assert colunas["active"] == ("boolean", None, None, "NO")
    for texto in ("id", "tenant_id", "unit_id", "name"):
        assert colunas[texto] == ("text", None, None, "NO"), texto
    # Stage 3.5 — o vínculo de login: texto opaco e **anulável** (ADR 3.5.0004).
    assert colunas["user_id"] == ("text", None, None, "YES")
    assert len(colunas) == _COLUNAS_DE_EMPLOYEES


def test_user_id_nao_tem_fk_nem_constraint_e_so_o_indice_de_um_por_unidade(
    engine: Engine,
) -> None:
    """As ausências que ficam do ADR 3.5.0004 §3, e o índice da issue #241, no catálogo.

    Este teste olha só o estado `head`. O `downgrade` da `0004` **não** é
    provado pelo `downgrade base` da fixture (a `0003` derruba `employees`
    inteira, o que mascararia uma `0004.downgrade` vazia); quem o prova é
    `tests/integration/test_migration.py::test_downgrade_da_0004_remove_so_a_coluna_user_id`,
    descendo até `0003` e olhando o catálogo. O da `0008` é provado lá também.
    """
    with engine.connect() as conexao:
        constraints_sobre_user_id = conexao.execute(
            text(
                "SELECT c.conname, c.contype FROM pg_constraint c "
                "JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = ANY(c.conkey) "
                "WHERE c.conrelid = 'employees'::regclass AND a.attname = 'user_id'"
            )
        ).all()
        indices_sobre_user_id = conexao.execute(
            text(
                "SELECT i.relname, x.indisunique, pg_get_indexdef(x.indexrelid) FROM pg_index x "
                "JOIN pg_class i ON i.oid = x.indexrelid "
                "JOIN pg_attribute a ON a.attrelid = x.indrelid AND a.attnum = ANY(x.indkey) "
                "WHERE x.indrelid = 'employees'::regclass AND a.attname = 'user_id'"
            )
        ).all()

    assert constraints_sobre_user_id == []
    assert len(indices_sobre_user_id) == 1, indices_sobre_user_id
    nome, unico, definicao = indices_sobre_user_id[0]
    assert (nome, unico) == ("uq_employees_tenant_unit_user", True)
    assert "(tenant_id, unit_id, user_id)" in definicao, definicao
    assert definicao.endswith("WHERE (user_id IS NOT NULL)"), definicao


# ---------------------------------------------------------------------------
# Issue #241 — um login por unidade, recusado pelo banco (ADR 0.0.0025)
# ---------------------------------------------------------------------------


def _registro(
    conexao: Connection, id_: str, *, tenant: str = "t1", unidade: str = "u1", ativo: bool = True
) -> None:
    conexao.execute(
        text(
            "INSERT INTO employees "
            "(id, tenant_id, unit_id, name, workload_kind, weekly_hours, active) "
            "VALUES (:id, :t, :u, 'Ana', 'on_demand', NULL, :a)"
        ),
        {"id": id_, "t": tenant, "u": unidade, "a": ativo},
    )


def _vincular(conexao: Connection, id_: str, login: str) -> None:
    conexao.execute(
        text("UPDATE employees SET user_id = :login WHERE id = :id"), {"login": login, "id": id_}
    )


@pytest.mark.parametrize("segundo_ativo", [True, False], ids=["ativo", "desligado"])
def test_segundo_registro_da_unidade_com_o_mesmo_login_e_recusado(
    banco_limpo: Engine, segundo_ativo: bool
) -> None:
    """Por `UPDATE` direto, sem mapper nem port: a guarda existe onde sobrevive a um bug.

    O desligado conta, como na regra (ADR 3.10.0001 §6). O nome da violação é o do
    índice — é por ele que o tradutor de `link_login`/`relink_login` a reconhece.
    """
    with banco_limpo.begin() as conexao:
        _registro(conexao, "e1")
        _registro(conexao, "e2", ativo=segundo_ativo)
        _vincular(conexao, "e1", "login-1")

    with pytest.raises(IntegrityError) as excecao, banco_limpo.begin() as conexao:
        _vincular(conexao, "e2", "login-1")

    assert _nome_da_constraint(excecao.value) == "uq_employees_tenant_unit_user"


def test_o_mesmo_login_em_outra_unidade_ou_outro_tenant_e_varios_sem_login_sao_aceitos(
    banco_limpo: Engine,
) -> None:
    """O índice é por unidade (workforce §3.7) e parcial: `NULL` não limita ninguém."""
    with banco_limpo.begin() as conexao:
        _registro(conexao, "e1")
        _registro(conexao, "e-u2", unidade="u2")
        _registro(conexao, "e-t2", tenant="t2")
        _registro(conexao, "e-sem-1")
        _registro(conexao, "e-sem-2")
        for id_ in ("e1", "e-u2", "e-t2"):
            _vincular(conexao, id_, "login-1")

    with banco_limpo.connect() as conexao:
        vinculados = conexao.execute(
            text("SELECT count(*) FROM employees WHERE user_id = 'login-1'")
        ).scalar_one()
        sem_login = conexao.execute(
            text("SELECT count(*) FROM employees WHERE user_id IS NULL")
        ).scalar_one()
    assert (vinculados, sem_login) == (3, 2)


def test_instantes_sao_timestamp_sem_fuso_no_banco(engine: Engine) -> None:
    """O oposto de identity, e deliberado (ADR 3.1.0005).

    Um `timestamp with time zone` aqui faria o psycopg devolver aware, e
    `UnavailabilityPeriod` **rejeita** aware — a reidratação levantaria
    `InvalidUnavailabilityPeriodError` sobre dado perfeitamente válido.
    """
    with engine.connect() as conexao:
        tipos = {
            linha[0]: linha[1]
            for linha in conexao.execute(
                text(
                    "SELECT column_name, data_type FROM information_schema.columns "
                    "WHERE table_name = 'employee_unavailabilities'"
                )
            )
        }
    assert tipos["start_at"] == "timestamp without time zone"
    assert tipos["end_at"] == "timestamp without time zone"


def test_tenant_id_existe_apenas_onde_ancora_um_cerco(engine: Engine) -> None:
    """D2 — a coluna existe onde ancora um cerco, e só ali.

    A asserção tem os dois lados de propósito: a **ausência** nas duas filhas
    sem cerco (onde seria denormalização sem FK composta a sustentar) e a
    **presença, `NOT NULL`,** em `employee_job_functions` — que é o que mantém
    as FKs compostas ativas, já que MATCH SIMPLE ignora a FK inteira quando
    qualquer coluna referenciante é nula.
    """
    with engine.connect() as conexao:
        colunas = {
            (linha[0], linha[1]): linha[2]
            for linha in conexao.execute(
                text(
                    "SELECT table_name, column_name, is_nullable "
                    "FROM information_schema.columns WHERE table_name = ANY(:tabelas)"
                ),
                {"tabelas": list(_TABELAS_DE_STAFF)},
            )
        }

    assert ("employee_unavailabilities", "tenant_id") not in colunas
    assert ("employee_shift_preferences", "tenant_id") not in colunas
    assert colunas[("employee_job_functions", "tenant_id")] == "NO"
    assert colunas[("job_function_units", "tenant_id")] == "NO"


# ---------------------------------------------------------------------------
# A concordância enum↔banco — o lado positivo, que CA15 não pede
# ---------------------------------------------------------------------------
#
# CA15, como escrito, só exige que a **linha ilegal** seja recusada, e um único
# caso negativo (`'dawn'`) satisfaz a letra. Mas a propriedade que importa é a
# **concordância**: todo valor que o domínio considera legal tem de ser aceito
# pelo banco. Medido no Checkpoint C — removendo `"overnight"` da lista congelada
# da migration, a suíte inteira continuava verde, e uma preferência de turno
# legítima passaria a ser recusada em runtime sem nenhum gate notar. A derivação
# assertada em `test_tables.py` fecha só o lado da declaração; a migration é
# congelada de propósito e não deriva de nada.


@pytest.mark.parametrize("periodo", list(DayPeriod), ids=[p.value for p in DayPeriod])
def test_cada_periodo_do_enum_e_aceito_pelo_banco(banco_limpo: Engine, periodo: DayPeriod) -> None:
    """Um caso positivo por valor corrente de `DayPeriod` — o teste que morde.

    É o contrário do teste de `'dawn'`: aquele prova que o conjunto é **fechado**,
    este prova que ele é **completo**. Só os dois juntos travam a concordância.
    """
    _semear_funcao_e_funcionario(banco_limpo)
    with banco_limpo.begin() as conexao:
        conexao.execute(
            text(
                "INSERT INTO employee_shift_preferences (employee_id, period) "
                "VALUES ('e1', :periodo)"
            ),
            {"periodo": periodo.value},
        )
        gravado = conexao.execute(
            text("SELECT period FROM employee_shift_preferences WHERE employee_id = 'e1'")
        ).scalar_one()
    assert gravado == periodo.value


@pytest.mark.parametrize("kind", WORKLOAD_KINDS)
def test_cada_tipo_de_jornada_conhecido_e_aceito_pelo_banco(banco_limpo: Engine, kind: str) -> None:
    """Mesma propriedade para `WORKLOAD_KINDS`, e pela mesma razão.

    A lista da migration é congelada e não deriva das constantes de `tables.py`;
    sem este caso positivo, apagar `'fixed'` de lá sobreviveria à suíte — os
    outros testes ou inserem `on_demand`, ou esperam recusa.

    As horas acompanham o discriminador porque o **iff** as amarra: é o mesmo
    par que `workload_profile_to_columns` produz.
    """
    horas = Decimal("22.50") if kind == WORKLOAD_KIND_FIXED else None
    with banco_limpo.begin() as conexao:
        conexao.execute(
            text(
                "INSERT INTO employees "
                "(id, tenant_id, unit_id, name, workload_kind, weekly_hours, active) "
                "VALUES ('e1', 't1', 'u1', 'Ana', :kind, :horas, true)"
            ),
            {"kind": kind, "horas": horas},
        )
        gravado = conexao.execute(
            text("SELECT workload_kind, weekly_hours FROM employees WHERE id = 'e1'")
        ).one()
    assert gravado[0] == kind
    # CA17 de passagem: a escala do `Decimal` sobrevive à `NUMERIC` sem precisão.
    assert gravado[1] == horas
    if horas is not None:
        assert str(gravado[1]) == "22.50"


# ---------------------------------------------------------------------------
# CA15 — o banco recusa a linha ilegal, por `INSERT` direto
# ---------------------------------------------------------------------------


def test_jornada_fixa_sem_horas_e_recusada(banco_limpo: Engine) -> None:
    """Metade do **iff**: `fixed` sem carga é `FixedSchedule` impossível."""
    with pytest.raises(IntegrityError) as capturado, banco_limpo.begin() as conexao:
        conexao.execute(
            text(
                "INSERT INTO employees "
                "(id, tenant_id, unit_id, name, workload_kind, weekly_hours, active) "
                "VALUES ('e1', 't1', 'u1', 'Ana', 'fixed', NULL, true)"
            )
        )
    assert _nome_da_constraint(capturado.value) == "ck_employees_workload_iff_hours"


def test_jornada_sob_demanda_com_horas_e_recusada(banco_limpo: Engine) -> None:
    """A outra metade do iff — a que uma CHECK "permissiva" deixaria passar.

    `weekly_hours IS NOT NULL OR workload_kind = 'on_demand'` parece equivalente
    e aceita esta linha, que reidrataria para um `OnDemand` com carga — estado
    que a união de tipos torna irrepresentável no domínio.
    """
    with pytest.raises(IntegrityError) as capturado, banco_limpo.begin() as conexao:
        conexao.execute(
            text(
                "INSERT INTO employees "
                "(id, tenant_id, unit_id, name, workload_kind, weekly_hours, active) "
                "VALUES ('e1', 't1', 'u1', 'Ana', 'on_demand', 40, true)"
            )
        )
    assert _nome_da_constraint(capturado.value) == "ck_employees_workload_iff_hours"


def test_carga_semanal_nao_positiva_e_recusada(banco_limpo: Engine) -> None:
    """`FixedSchedule` exige carga positiva; o banco impõe a metade que expressa."""
    with pytest.raises(IntegrityError) as capturado, banco_limpo.begin() as conexao:
        conexao.execute(
            text(
                "INSERT INTO employees "
                "(id, tenant_id, unit_id, name, workload_kind, weekly_hours, active) "
                "VALUES ('e1', 't1', 'u1', 'Ana', 'fixed', :horas, true)"
            ),
            {"horas": Decimal("0")},
        )
    assert _nome_da_constraint(capturado.value) == "ck_employees_weekly_hours_positive"


def test_periodo_com_inicio_apos_o_fim_e_recusado(banco_limpo: Engine) -> None:
    """Semi-aberto `[start, end)`: `start >= end` é intervalo vazio."""
    _semear_funcao_e_funcionario(banco_limpo)
    with pytest.raises(IntegrityError) as capturado, banco_limpo.begin() as conexao:
        conexao.execute(
            text(
                "INSERT INTO employee_unavailabilities (employee_id, start_at, end_at) "
                "VALUES ('e1', TIMESTAMP '2026-08-10 12:00:00', "
                "TIMESTAMP '2026-08-10 08:00:00')"
            )
        )
    assert _nome_da_constraint(capturado.value) == "ck_employee_unavailabilities_period"


def test_periodo_do_dia_desconhecido_e_recusado(banco_limpo: Engine) -> None:
    """A CHECK deriva de `DayPeriod`: valor fora do enum não entra.

    É a contrapartida no banco da derivação assertada em `test_tables.py` — sem
    ela, um período novo no enum viraria linha aceita que reidrata levantando
    `ValueError` na leitura.
    """
    _semear_funcao_e_funcionario(banco_limpo)
    with pytest.raises(IntegrityError) as capturado, banco_limpo.begin() as conexao:
        conexao.execute(
            text(
                "INSERT INTO employee_shift_preferences (employee_id, period) VALUES ('e1', 'dawn')"
            )
        )
    assert _nome_da_constraint(capturado.value) == "ck_employee_shift_preferences_period_known"


def test_jornada_desconhecida_e_recusada(banco_limpo: Engine) -> None:
    """O discriminador vive num conjunto fechado — `WORKLOAD_KINDS`.

    Um terceiro perfil acrescentado ao domínio sem entrar em `WORKLOAD_KINDS`
    para aqui, que é onde se quer que pare: em `INSERT` recusado, e não em
    entidade meio-construída lida do banco.
    """
    with pytest.raises(IntegrityError) as capturado, banco_limpo.begin() as conexao:
        conexao.execute(
            text(
                "INSERT INTO employees "
                "(id, tenant_id, unit_id, name, workload_kind, weekly_hours, active) "
                "VALUES ('e1', 't1', 'u1', 'Ana', 'freelance', NULL, true)"
            )
        )
    assert _nome_da_constraint(capturado.value) == "ck_employees_workload_kind_known"


def test_vinculo_com_funcao_de_outro_tenant_e_recusado(banco_limpo: Engine) -> None:
    """O cerco composto, contra o banco — ADR 3.3.0001, medido no probe.

    O `INSERT` é legal em cada coluna isolada (a função existe, o funcionário
    existe); é a **composição** `(job_function_id, tenant_id)` que não casa.
    """
    _semear_funcao_e_funcionario(banco_limpo)
    with banco_limpo.begin() as conexao:
        conexao.execute(
            text("INSERT INTO job_functions (id, tenant_id, name) VALUES ('f9', 't2', 'Garçom')")
        )

    with pytest.raises(IntegrityError) as capturado, banco_limpo.begin() as conexao:
        conexao.execute(
            text(
                "INSERT INTO employee_job_functions (employee_id, job_function_id, tenant_id) "
                "VALUES ('e1', 'f9', 't1')"
            )
        )
    assert _nome_da_constraint(capturado.value) == "fk_employee_job_functions_job_function"
