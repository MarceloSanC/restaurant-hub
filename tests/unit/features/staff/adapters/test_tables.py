"""Testes do schema declarado em `tables.py` do BC staff — sem banco.

Estes testes não substituem os de integração (que exercitam as constraints contra
o Postgres de verdade); eles guardam as propriedades do schema que são **fáceis
de quebrar por edição descuidada e caras de descobrir em produção**:

- um nome de constraint alterado quebra a tradução de `IntegrityError` → exceção
  de aplicação (ADR 3.3.0004), e o efeito só aparece como 500 no primeiro
  conflito real;
- perder uma das **duas** FKs compostas de `employee_job_functions` deixa metade
  do cerco de tenant e nenhuma garantia — e nenhum teste de caminho feliz nota;
- trocar `NUMERIC` por `NUMERIC(5,2)` em `weekly_hours` arredonda em silêncio
  (`22.555 → 22.56`), o que é corrupção de dado que passa em qualquer asserção
  sobre "gravou e leu";
- acrescentar um período em `DayPeriod` sem acrescentá-lo à `CHECK` só apareceria
  como `IntegrityError` em produção — daí a asserção de **derivação**, e não de
  mera presença.
"""

import re

import pytest
from sqlalchemy import CheckConstraint, ForeignKeyConstraint, Numeric, Table, Text, UniqueConstraint

from restaurant_hub.features.staff.adapters.out.postgres.tables import (
    WORKLOAD_KIND_FIXED,
    WORKLOAD_KIND_ON_DEMAND,
    WORKLOAD_KINDS,
    employee_job_functions,
    employee_shift_preferences,
    employee_unavailabilities,
    employees,
    job_function_units,
    job_functions,
    staff_metadata,
)
from restaurant_hub.features.staff.domain.value_objects.shift_preference import DayPeriod

pytestmark = pytest.mark.unit


def _nomes_de_constraint(table: Table) -> set[str]:
    return {c.name for c in table.constraints if c.name is not None}


def _checks(table: Table) -> dict[str, str]:
    return {
        str(c.name): str(c.sqltext)
        for c in table.constraints
        if isinstance(c, CheckConstraint) and c.name is not None
    }


def _literais(sql: str) -> tuple[str, ...]:
    """Literais de string do texto da CHECK, na ordem em que aparecem."""
    return tuple(re.findall(r"'([^']*)'", sql))


def _normalizado(sql: str) -> str:
    """Texto da CHECK com os brancos colapsados, para comparação por igualdade.

    Igualdade e não substring: uma asserção de substring trava o **caso** e não a
    **propriedade** — `"=" in sql` continua verdadeiro depois de trocar o `=` do
    iff por `OR`, que é exatamente a formulação permissiva que o teste existe
    para reprovar. Só o texto inteiro fecha a operação lógica.
    """
    return " ".join(sql.split())


def _fks(table: Table) -> dict[str, ForeignKeyConstraint]:
    return {
        str(c.name): c for c in table.constraints if isinstance(c, ForeignKeyConstraint) and c.name
    }


def test_metadata_declara_exatamente_as_seis_tabelas() -> None:
    """Tabela nova ou removida força revisão consciente — e da migration junto."""
    assert set(staff_metadata.tables) == {
        "job_functions",
        "job_function_units",
        "employees",
        "employee_job_functions",
        "employee_unavailabilities",
        "employee_shift_preferences",
    }


def test_toda_constraint_tem_nome_explicito() -> None:
    """A tradução `IntegrityError` → aplicação identifica a regra **pelo NOME**.

    Nome autogerado varia entre ambientes e faria a tradução funcionar em teste e
    falhar em produção (ADR 3.3.0004).
    """
    for table in staff_metadata.tables.values():
        for constraint in table.constraints:
            assert constraint.name is not None, f"constraint sem nome em {table.name}"
            assert not str(constraint.name).startswith("_unnamed_"), (
                f"constraint autogerada em {table.name}"
            )
        for index in table.indexes:
            assert index.name is not None


def test_nomes_de_constraint_de_cada_tabela() -> None:
    """Congela o conjunto **inteiro**, não só as que alguém lembrou de citar.

    Igualdade de conjunto (e não `>=`): uma constraint acrescentada em silêncio
    é tão relevante quanto uma removida — a primeira muda o que o banco recusa
    sem que nenhum mapa de tradução saiba dela.
    """
    assert _nomes_de_constraint(job_functions) == {
        "pk_job_functions",
        "uq_job_functions_tenant_name",
        "uq_job_functions_id_tenant",
    }
    assert _nomes_de_constraint(job_function_units) == {
        "pk_job_function_units",
        "fk_job_function_units_job_function",
    }
    assert _nomes_de_constraint(employees) == {
        "pk_employees",
        "uq_employees_id_tenant",
        "ck_employees_workload_kind_known",
        "ck_employees_workload_iff_hours",
        "ck_employees_weekly_hours_positive",
    }
    assert _nomes_de_constraint(employee_job_functions) == {
        "pk_employee_job_functions",
        "fk_employee_job_functions_employee",
        "fk_employee_job_functions_job_function",
    }
    assert _nomes_de_constraint(employee_unavailabilities) == {
        "pk_employee_unavailabilities",
        "fk_employee_unavailabilities_employee",
        "ck_employee_unavailabilities_period",
    }
    assert _nomes_de_constraint(employee_shift_preferences) == {
        "pk_employee_shift_preferences",
        "fk_employee_shift_preferences_employee",
        "ck_employee_shift_preferences_period_known",
    }


def test_os_indices_sao_exatamente_os_declarados() -> None:
    """D5 / ADR 3.3.0005 — índices pelo acesso medido, não por reflexo.

    O `UNIQUE (tenant_id, name)` já serve `find_by_name` e `list_by_tenant`; um
    `(tenant_id, id)` seria redundante com a PK. O de
    `employee_job_functions` **não** é otimização: sem ele o `RESTRICT` varre a
    tabela inteira a cada remoção de função.
    """
    indices = {i.name for table in staff_metadata.tables.values() for i in table.indexes}
    assert indices == {
        "ix_employees_tenant_unit",
        "ix_employee_job_functions_function",
        # Stage 3.11 — serve `list_by_unit` (L-JF6).
        "ix_job_function_units_tenant_unit",
    }
    assert [c.name for c in next(iter(employee_job_functions.indexes)).columns] == [
        "job_function_id",
        "tenant_id",
    ]


def test_ancoras_das_fks_compostas_existem() -> None:
    """Sem estes `UNIQUE` o Postgres recusa criar as FKs compostas.

    Não é redundância com a PK: o Postgres exige índice único cobrindo
    exatamente as colunas referenciadas. Removê-los quebra
    `alembic upgrade head`, não algum teste sutil.
    """
    for table, nome in (
        (job_functions, "uq_job_functions_id_tenant"),
        (employees, "uq_employees_id_tenant"),
    ):
        ancora = next(
            c for c in table.constraints if isinstance(c, UniqueConstraint) and c.name == nome
        )
        assert [col.name for col in ancora.columns] == ["id", "tenant_id"]


def test_unicidade_de_nome_de_funcao_e_por_tenant_e_verbatim() -> None:
    """§5.6 — sem `lower()`, sem `btrim`: a coluna entra crua no índice.

    Uma unicidade normalizada recusaria `'cozinheiro '` ao lado de
    `'Cozinheiro'`, que o probe mediu como **aceito** e que CA9 exige.
    """
    unico = next(
        c
        for c in job_functions.constraints
        if isinstance(c, UniqueConstraint) and c.name == "uq_job_functions_tenant_name"
    )
    assert [col.name for col in unico.columns] == ["tenant_id", "name"]


def test_colisao_de_id_e_global_nas_duas_raizes() -> None:
    """L-JF1/L-E1: a PK **não** inclui o tenant.

    Uma PK `(tenant_id, id)` aceitaria a inserção de id repetido em outro
    restaurante — que é exatamente o que CA5 recusa nas duas implementações.
    """
    assert [c.name for c in job_functions.primary_key.columns] == ["id"]
    assert [c.name for c in employees.primary_key.columns] == ["id"]


def test_employee_job_functions_tem_as_duas_fks_compostas_com_ondelete_distinto() -> None:
    """ADR 3.3.0001 + L-JF3: o cerco inteiro, e a guarda de remoção.

    Uma FK só deixaria o outro lado livre — metade do cerco e nenhuma garantia.
    E os dois `ondelete` são **diferentes de propósito**: o vínculo some com o
    funcionário (`CASCADE`) e **impede** apagar a função (`RESTRICT`). Trocá-los
    apagaria vínculos ao remover a função, furando "ao menos uma função" da 3.1.
    """
    fks = _fks(employee_job_functions)
    assert set(fks) == {
        "fk_employee_job_functions_employee",
        "fk_employee_job_functions_job_function",
    }

    do_funcionario = fks["fk_employee_job_functions_employee"]
    assert [c.name for c in do_funcionario.columns] == ["employee_id", "tenant_id"]
    assert [e.target_fullname for e in do_funcionario.elements] == [
        "employees.id",
        "employees.tenant_id",
    ]
    assert do_funcionario.ondelete == "CASCADE"

    da_funcao = fks["fk_employee_job_functions_job_function"]
    assert [c.name for c in da_funcao.columns] == ["job_function_id", "tenant_id"]
    assert [e.target_fullname for e in da_funcao.elements] == [
        "job_functions.id",
        "job_functions.tenant_id",
    ]
    assert da_funcao.ondelete == "RESTRICT"


def test_tenant_id_do_vinculo_e_not_null() -> None:
    """`NOT NULL` é o que mantém as FKs compostas **ativas**.

    FK composta em Postgres é MATCH SIMPLE por default e é ignorada por inteiro
    quando qualquer coluna referenciante é nula: com a coluna anulável, o cerco
    seria decorativo e nenhum teste de caminho feliz notaria.
    """
    assert employee_job_functions.c.tenant_id.nullable is False


def test_filhas_sem_cerco_nao_tem_tenant_id() -> None:
    """D2: a coluna existe **onde ancora um cerco**, e ali não ancora nenhum.

    A única referência das duas é o próprio `employee_id`; um `tenant_id` ali
    seria denormalização sem FK composta a sustentar — a mesma razão pela qual
    `sessions` não a tem em identity.
    """
    assert {c.name for c in employee_unavailabilities.columns} == {
        "employee_id",
        "start_at",
        "end_at",
    }
    assert {c.name for c in employee_shift_preferences.columns} == {
        "employee_id",
        "period",
    }


def test_as_tres_fks_de_filha_para_pai_sao_cascade() -> None:
    """§5.10 — os filhos do agregado somem com o agregado."""
    for tabela in (
        employee_job_functions,
        employee_unavailabilities,
        employee_shift_preferences,
    ):
        do_funcionario = next(fk for nome, fk in _fks(tabela).items() if nome.endswith("_employee"))
        assert do_funcionario.ondelete == "CASCADE", tabela.name


def test_nenhuma_fk_aponta_para_fora_do_metadata_de_staff() -> None:
    """ADR 3.3.0002 — nenhuma FK atravessa o bounded context.

    `tenant_id` e `unit_id` são strings opacas: uma FK para `restaurants`/`units`
    de identity amarraria os dois BCs ao mesmo banco para sempre e faria a suíte
    de contrato de staff precisar semear identity para provar staff.
    """
    tabelas_do_bc = set(staff_metadata.tables)
    for table in staff_metadata.tables.values():
        for fk in table.foreign_keys:
            alvo = fk.column.table.name
            assert alvo in tabelas_do_bc, f"{table.name} referencia {alvo}, fora do BC staff"


def test_employees_nao_tem_fk_alguma() -> None:
    """Corolário do anterior que merece asserção própria (D1).

    É em `employees` que a FK cross-BC seria tentadora — `tenant_id` aponta para
    `restaurants` e `unit_id` para `units`. Um teste que só olhasse o conjunto de
    alvos passaria se alguém acrescentasse a FK **e** a tabela alvo ao metadata.
    """
    assert set(employees.foreign_keys) == set()


def test_weekly_hours_e_numeric_sem_precisao_e_anulavel() -> None:
    """Tipo é contrato: `NUMERIC(5,2)` arredonda em silêncio (`22.555 → 22.56`).

    `FixedSchedule` aceita qualquer `Decimal` finito positivo, e a disciplina
    verbatim do projeto não sobrevive a um arredondamento que ninguém pediu.
    Anulável porque `OnDemand` não carrega carga — o iff é quem amarra.
    """
    tipo = employees.c.weekly_hours.type
    assert isinstance(tipo, Numeric)
    assert tipo.precision is None
    assert tipo.scale is None
    assert employees.c.weekly_hours.nullable is True


def test_instantes_sao_timestamp_sem_fuso() -> None:
    """O **oposto** de identity, e deliberado (ADR 3.1.0005).

    `UnavailabilityPeriod` guarda wall-clock do fuso da unidade e **rejeita**
    tz-aware: um `TIMESTAMPTZ` aqui faria a reidratação levantar
    `InvalidUnavailabilityPeriodError` sobre dado válido.
    """
    for coluna in (employee_unavailabilities.c.start_at, employee_unavailabilities.c.end_at):
        assert coluna.type.timezone is False  # type: ignore[attr-defined]


def test_workload_kind_e_not_null() -> None:
    """`NOT NULL` load-bearing: uma CHECK em Postgres só rejeita em `FALSE`.

    Com o discriminador nulo, `(workload_kind = 'fixed') = (weekly_hours IS NOT NULL)`
    avalia `NULL` e a linha **passa** — jornada indefinida entrando pela porta
    dos fundos.
    """
    assert employees.c.workload_kind.nullable is False


def test_os_dois_tipos_de_jornada_sao_os_da_uniao_do_dominio() -> None:
    """Fonte única dos literais persistidos (Task 01 do technical).

    `WorkloadProfile = FixedSchedule | OnDemand` **não** tem string
    discriminadora de onde derivar, então os dois valores nascem aqui, com dono.
    O mapper os consome daqui nas duas direções; repetir o literal lá recriaria
    a segunda fonte que estas constantes existem para eliminar.
    """
    assert WORKLOAD_KIND_FIXED == "fixed"
    assert WORKLOAD_KIND_ON_DEMAND == "on_demand"
    assert WORKLOAD_KINDS == ("fixed", "on_demand")


def test_check_de_jornada_cobre_exatamente_as_constantes_do_modulo() -> None:
    """A `CHECK` consome `WORKLOAD_KINDS` — um terceiro perfil entra numa linha só."""
    assert _literais(_checks(employees)["ck_employees_workload_kind_known"]) == WORKLOAD_KINDS


def test_check_de_jornada_e_um_iff_com_as_horas() -> None:
    """Barra `fixed` sem horas **e** `on_demand` com horas (medido no probe).

    Uma formulação "permissiva" que parece equivalente —
    `(workload_kind = 'fixed') OR (weekly_hours IS NOT NULL)` — aceitaria
    `on_demand` com horas, que é justamente o estado que a união de tipos torna
    irrepresentável no domínio.

    **A asserção é de igualdade sobre o texto normalizado, e a versão anterior
    (três substrings) era o defeito que ela agora impede.** Trocar o `=` por
    `OR` deixava `"=" in sql` verdadeiro — o `=` interno de `workload_kind =`
    sobrevive — e a suíte inteira ficava verde sobre um schema permissivo. A
    integração não alcança este caso: o DDL vem da migration, não deste arquivo,
    e `compare_metadata()` foi rejeitado com razão (fixture `_recriar_schema`).
    Aqui é o único lugar onde a operação lógica é verificável.
    """
    sql = _checks(employees)["ck_employees_workload_iff_hours"]
    assert (
        _normalizado(sql)
        == f"(workload_kind = '{WORKLOAD_KIND_FIXED}') = (weekly_hours IS NOT NULL)"
    )


def test_texto_exato_das_outras_quatro_checks() -> None:
    """Mesma disciplina do teste acima, para as CHECK restantes.

    A propriedade que cada uma carrega é a **operação lógica**, não a presença
    dos operandos: `IN` virando `NOT IN`, `>` virando `>=`, `IS NULL OR`
    sumindo — nenhuma dessas mutações move uma asserção de substring. Onde a
    lista de valores é derivada, ela é derivada **aqui também**, senão o teste
    reintroduziria a segunda fonte que a derivação existe para eliminar.
    """
    jornadas = ", ".join(f"'{kind}'" for kind in WORKLOAD_KINDS)
    periodos = ", ".join(f"'{period.value}'" for period in DayPeriod)

    checks_de_employees = _checks(employees)
    assert (
        _normalizado(checks_de_employees["ck_employees_workload_kind_known"])
        == f"workload_kind IN ({jornadas})"
    )
    assert (
        _normalizado(checks_de_employees["ck_employees_weekly_hours_positive"])
        == "weekly_hours IS NULL OR weekly_hours > 0"
    )
    assert (
        _normalizado(_checks(employee_unavailabilities)["ck_employee_unavailabilities_period"])
        == "start_at < end_at"
    )
    assert (
        _normalizado(
            _checks(employee_shift_preferences)["ck_employee_shift_preferences_period_known"]
        )
        == f"period IN ({periodos})"
    )


def test_check_de_periodo_deriva_do_enum_de_dominio() -> None:
    """A asserção que reprova o dia em que um período novo entrar no enum.

    **Igualdade com o `tuple` derivado**, não "cada valor aparece": a segunda
    forma passa com uma lista escrita à mão que por acaso contenha os quatro de
    hoje, e é exatamente ela que ficaria para trás no dia do quinto período. A
    divergência só apareceria como `IntegrityError` em produção.
    """
    sql = _checks(employee_shift_preferences)["ck_employee_shift_preferences_period_known"]
    assert _literais(sql) == tuple(period.value for period in DayPeriod)


def test_check_de_periodo_do_agregado_e_semiaberto() -> None:
    """`start_at < end_at`: intervalo vazio é recusado pelo banco também.

    `<=` aceitaria `start == end`, que `UnavailabilityPeriod.__post_init__`
    recusa — e a divergência produziria linha que levanta ao ser lida.
    """
    sql = _checks(employee_unavailabilities)["ck_employee_unavailabilities_period"]
    assert sql.replace(" ", "") == "start_at<end_at"


def test_pk_de_indisponibilidade_usa_o_inicio() -> None:
    """É o que torna `ORDER BY start_at` uma ordem **total** na reidratação.

    Períodos do mesmo funcionário não se sobrepõem, logo o início é único por
    registro — e `L-ORD` (ADR 3.3.0003) depende disso para não precisar de
    desempate.
    """
    assert [c.name for c in employee_unavailabilities.primary_key.columns] == [
        "employee_id",
        "start_at",
    ]


def test_preferencia_de_turno_e_um_conjunto_por_funcionario() -> None:
    """Sem linha ⇒ `None`; preferência declarada nunca é vazia (ADR 3.1.0004).

    A PK composta impede o mesmo período duas vezes — o campo é um `frozenset`
    no agregado, e um multiconjunto no banco reidrataria com contagem perdida.
    """
    assert [c.name for c in employee_shift_preferences.primary_key.columns] == [
        "employee_id",
        "period",
    ]


# ---------------------------------------------------------------------------
# Stage 3.5 — `employees.user_id` (ADR 3.5.0004)
# ---------------------------------------------------------------------------


def test_employees_tem_oito_colunas_e_user_id_e_a_ultima() -> None:
    """Contagem transcrita: um campo a mais que a 3.3 — e só ele."""
    assert [c.name for c in employees.columns] == [
        "id",
        "tenant_id",
        "unit_id",
        "name",
        "workload_kind",
        "weekly_hours",
        "active",
        "user_id",
    ]


def test_user_id_e_text_anulavel_sem_fk_sem_unique_e_sem_indice() -> None:
    """As quatro ausências são decisão (ADR 3.5.0004 §3), e cada uma é asserida.

    FK: ADR 3.3.0002. UNIQUE: workforce §3.7. Índice: ADR 3.3.0005. Anulável:
    workforce §3.8. Um `UniqueConstraint("user_id")` acrescentado "por
    segurança" reprova aqui — congelaria o contrário do que o doc de domínio
    admite.
    """
    coluna = employees.c.user_id
    assert isinstance(coluna.type, Text)
    assert coluna.nullable is True
    assert set(coluna.foreign_keys) == set()
    colunas_unicas = {
        tuple(c.name for c in constraint.columns)
        for constraint in employees.constraints
        if isinstance(constraint, UniqueConstraint)
    }
    assert ("user_id",) not in colunas_unicas
    assert all("user_id" not in [c.name for c in indice.columns] for indice in employees.indexes)


# ---------------------------------------------------------------------------
# Stage 3.11 — habilitação por unidade (ADR 3.11.0001)
# ---------------------------------------------------------------------------


def test_flag_de_todas_as_unidades_e_not_null_com_default_verdadeiro() -> None:
    """CA4 — o `DEFAULT true` é o que faz as funções anteriores nascerem em todas.

    Sem default, a migration falharia nas linhas existentes; com default falso,
    elas sumiriam de toda listagem de unidade (nenhum vínculo, flag falsa).
    """
    coluna = job_functions.c.enabled_in_all_units
    assert coluna.nullable is False
    assert coluna.server_default is not None
    assert str(coluna.server_default.arg) == "true"  # type: ignore[attr-defined]


def test_vinculo_de_unidade_e_filha_da_funcao_com_cascade_e_cerco_de_tenant() -> None:
    """O vínculo some com a função; a FK composta impede vínculo de outro tenant."""
    fk = _fks(job_function_units)["fk_job_function_units_job_function"]
    assert [c.name for c in fk.columns] == ["job_function_id", "tenant_id"]
    assert [e.target_fullname for e in fk.elements] == [
        "job_functions.id",
        "job_functions.tenant_id",
    ]
    assert fk.ondelete == "CASCADE"
    assert job_function_units.c.tenant_id.nullable is False
    assert [c.name for c in job_function_units.primary_key.columns] == [
        "job_function_id",
        "unit_id",
    ]
    indice = next(iter(job_function_units.indexes))
    assert [c.name for c in indice.columns] == ["tenant_id", "unit_id"]
