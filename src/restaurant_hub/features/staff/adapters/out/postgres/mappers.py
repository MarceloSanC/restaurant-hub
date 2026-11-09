"""Mapeamento domínio↔linha do BC staff.

Funções puras: recebem linha, devolvem entidade; recebem entidade, devolvem
`dict` de colunas. Nenhuma consulta, nenhuma sessão, nenhum efeito — o que torna
este módulo testável sem banco e o lugar certo para concentrar as regras
delicadas da persistência deste BC.

**Idioma: inglês**, divergindo do `mappers.py` de identity (que está em PT).
Mesma razão do ADR 3.3.0004 para `integrity_errors.py`: CONVENTIONS §1 é
literal, estes nomes são **API de módulo** (os adapters das Tasks 06/07 os
importam), e a §7 do technical da 3.2 já registrou o `[finding]` cuja direção é
renomear os identificadores PT deste BC. Acrescentá-los em PT aprofundaria uma
dívida já reconhecida.

**Regra 1 — reidratar SEMPRE pelo construtor.**
As entidades da 3.1 são `frozen` e validam as invariantes no `__post_init__`.
Aqui **não** se usa `object.__setattr__`, `__new__`, `dataclasses.fields` nem
qualquer atalho que produza a entidade sem passar pela validação. A consequência
é deliberada e é o que fecha o limite declarado em §5.19: das seis invariantes de
`Employee`, **três** o schema não consegue impor (conjunto de funções não-vazio,
nome não-vazio, não-sobreposição de períodos), e é **só** esta regra que faz uma
linha corrompida **levantar ao ser lida**, em vez de reintroduzir no sistema uma
entidade inválida que o resto do código tratará como legítima.

**Regra 2 — o mapper NÃO normaliza fuso. É o oposto da Regra 2 de identity.**
Lá, `timestamptz` volta no fuso da sessão e o mapper normaliza para UTC aware.
Aqui, `UnavailabilityPeriod` guarda **wall-clock do fuso da unidade** e
**rejeita** tz-aware na construção (ADR 3.1.0005): um `.astimezone(UTC)` ou um
`.replace(tzinfo=UTC)` escrito aqui por analogia com identity faria a reidratação
levantar `InvalidUnavailabilityPeriodError` sobre um dado perfeitamente válido.
O `datetime` atravessa **ingênuo**, exatamente como saiu.

**Regra 3 — o discriminador de jornada vem de `tables.py`.**
`WORKLOAD_KIND_FIXED`/`WORKLOAD_KIND_ON_DEMAND` são consumidos nas **duas**
direções. Repetir os literais `"fixed"`/`"on_demand"` aqui recriaria a segunda
fonte que aquelas constantes existem para eliminar, e a divergência só apareceria
como violação de `ck_employees_workload_kind_known` em produção.

**Regra 4 — sem linha em `employee_shift_preferences` ⇒ `None`.**
Preferência **declarada** nunca é vazia (ADR 3.1.0004), então "nenhuma linha" e
"preferência vazia" não são dois estados: são o mesmo, e é o único que o schema
representa.
"""

from collections.abc import Iterable
from decimal import Decimal
from typing import Any

from restaurant_hub.features.staff.adapters.out.postgres.tables import (
    WORKLOAD_KIND_FIXED,
    WORKLOAD_KIND_ON_DEMAND,
)
from restaurant_hub.features.staff.domain.entities.employee import Employee
from restaurant_hub.features.staff.domain.entities.job_function import JobFunction
from restaurant_hub.features.staff.domain.value_objects.identifiers import (
    EmployeeId,
    JobFunctionId,
    TenantId,
    UnitId,
    UserId,
)
from restaurant_hub.features.staff.domain.value_objects.shift_preference import (
    DayPeriod,
    ShiftPreference,
)
from restaurant_hub.features.staff.domain.value_objects.unavailability_period import (
    UnavailabilityPeriod,
)
from restaurant_hub.features.staff.domain.value_objects.workload_profile import (
    FixedSchedule,
    OnDemand,
    WorkloadProfile,
)

# O único escape de tipagem do módulo, e é limitação da biblioteca, não atalho.
# `sqlalchemy.Row` é genérico sobre a **tupla de colunas** do `select()` que o
# produziu (`Row[tuple[str, str, ...]]`), e o acesso por atributo (`row.name`)
# vive num `__getattr__` que o mypy não resolve: qualquer anotação mais estreita
# que `Any` — inclusive `Row[Any]` — faz `row.<coluna>` virar erro em vez de
# checagem. O preço, assumido: nenhum `row.<coluna>` deste módulo é conferido
# estaticamente, e o que protege contra coluna renomeada é `tables.py` como fonte
# única (Regra 3) mais o teste de integração que lê o schema real. O alias
# nomeado existe para que a fronteira fique **visível** na assinatura, em vez de
# um `Any` solto por parâmetro.
Row = Any


# ---------------------------------------------------------------------------
# JobFunction
# ---------------------------------------------------------------------------


def job_function_to_row(job_function: JobFunction) -> dict[str, Any]:
    """`name` vai **verbatim** — a persistência não normaliza (ADR 3.1.0002)."""
    return {
        "id": job_function.id,
        "tenant_id": job_function.tenant_id,
        "name": job_function.name,
    }


def row_to_job_function(row: Row) -> JobFunction:
    """Reidrata pelo construtor: nome vazio na linha levanta `InvalidNameError`."""
    return JobFunction(
        id=JobFunctionId(row.id),
        tenant_id=TenantId(row.tenant_id),
        name=row.name,
    )


# ---------------------------------------------------------------------------
# WorkloadProfile — a união sem discriminador, e o discriminador persistido
# ---------------------------------------------------------------------------


def workload_profile_to_columns(profile: WorkloadProfile) -> tuple[str, Decimal | None]:
    """Devolve `(workload_kind, weekly_hours)` para as colunas de `employees`.

    O par sai junto de propósito: as duas colunas são amarradas pelo **iff** de
    `ck_employees_workload_iff_hours`, e produzi-las em pontos separados do
    código é o caminho mais curto para gravar `on_demand` com horas.
    """
    if isinstance(profile, FixedSchedule):
        return WORKLOAD_KIND_FIXED, profile.weekly_hours
    return WORKLOAD_KIND_ON_DEMAND, None


def columns_to_workload_profile(
    workload_kind: str, weekly_hours: Decimal | None
) -> WorkloadProfile:
    """Reconstrói a união a partir do discriminador persistido.

    Levanta `ValueError` para discriminador desconhecido ou para a combinação que
    o **iff** proíbe — e levantar é o desejado, pelo mesmo motivo do
    `SetupTokenPurpose(row.purpose)` de identity: a `CHECK` do banco só aceita as
    combinações legais, então uma linha fora delas significa schema divergente do
    código e precisa estourar alto, em vez de virar um perfil de jornada
    silenciosamente errado.
    """
    if workload_kind == WORKLOAD_KIND_FIXED:
        if weekly_hours is None:
            raise ValueError(
                f"jornada {WORKLOAD_KIND_FIXED!r} sem carga semanal — "
                f"linha viola ck_employees_workload_iff_hours"
            )
        return FixedSchedule(weekly_hours=weekly_hours)
    if workload_kind == WORKLOAD_KIND_ON_DEMAND:
        if weekly_hours is not None:
            raise ValueError(
                f"jornada {WORKLOAD_KIND_ON_DEMAND!r} com carga semanal — "
                f"linha viola ck_employees_workload_iff_hours"
            )
        return OnDemand()
    raise ValueError(f"tipo de jornada desconhecido: {workload_kind!r}")


# ---------------------------------------------------------------------------
# Tabelas-filhas de `employees`
# ---------------------------------------------------------------------------


def job_function_link_rows(employee: Employee) -> list[dict[str, Any]]:
    """Linhas de `employee_job_functions` do agregado, em ordem **determinística**.

    `sorted()` sobre o `frozenset`: um `frozenset` itera em ordem dependente de
    `PYTHONHASHSEED`, e ordem de inserção variável entre execuções é ordem de
    aquisição de lock variável entre execuções — que é como um deadlock vira
    "flakiness" em vez de bug.

    O `tenant_id` é denormalizado e ancorado pelas duas FKs compostas: um valor
    errado aqui não passa despercebido, a linha é rejeitada.
    """
    return [
        {
            "employee_id": employee.id,
            "job_function_id": job_function_id,
            "tenant_id": employee.tenant_id,
        }
        for job_function_id in sorted(employee.job_function_ids)
    ]


def unavailability_rows(employee: Employee) -> list[dict[str, Any]]:
    """Linhas de `employee_unavailabilities` — instantes **ingênuos**, sem conversão."""
    return [
        {"employee_id": employee.id, "start_at": period.start, "end_at": period.end}
        for period in employee.unavailabilities
    ]


def shift_preference_rows(employee: Employee) -> list[dict[str, Any]]:
    """Linhas de `employee_shift_preferences`; **lista vazia** quando não há preferência."""
    if employee.shift_preference is None:
        return []
    return [
        {"employee_id": employee.id, "period": period.value}
        for period in sorted(employee.shift_preference.periods)
    ]


def rows_to_unavailabilities(rows: Iterable[Row]) -> tuple[UnavailabilityPeriod, ...]:
    """Reidrata os períodos **preservando a ordem recebida** (o `ORDER BY start_at`).

    E preservando o `tzinfo is None`: ver a Regra 2 do docstring do módulo — é o
    erro mais provável desta camada e o teste o assere explicitamente.
    """
    return tuple(UnavailabilityPeriod(start=row.start_at, end=row.end_at) for row in rows)


def periods_to_shift_preference(periods: Iterable[str]) -> ShiftPreference | None:
    """Sem período ⇒ `None`; com período(s) ⇒ `ShiftPreference`, que nunca é vazia.

    `DayPeriod(valor)` levanta `ValueError` para valor fora do enum — a `CHECK`
    derivada do enum só aceita os correntes, então uma linha fora deles é schema
    divergente do código.
    """
    day_periods = frozenset(DayPeriod(period) for period in periods)
    if not day_periods:
        return None
    return ShiftPreference(periods=day_periods)


# ---------------------------------------------------------------------------
# Employee — o agregado de quatro tabelas
# ---------------------------------------------------------------------------


def employee_to_row(employee: Employee) -> dict[str, Any]:
    """Colunas da tabela `employees`; as filhas saem pelas funções acima."""
    workload_kind, weekly_hours = workload_profile_to_columns(employee.workload_profile)
    return {
        "id": employee.id,
        "tenant_id": employee.tenant_id,
        "unit_id": employee.unit_id,
        "name": employee.name,
        "workload_kind": workload_kind,
        "weekly_hours": weekly_hours,
        "active": employee.active,
        "user_id": employee.user_id,
    }


def row_to_employee(
    row: Row,
    *,
    job_function_ids: Iterable[str],
    unavailabilities: Iterable[Row],
    shift_periods: Iterable[str],
) -> Employee:
    """Reidrata o agregado **pelo construtor**, na ordem especificada em §5.11.

    As três conversões saem para variáveis locais **de propósito** — mesmo
    motivo do `row_to_user` de identity. Avaliá-las inline nos argumentos
    faria a precedência depender da ordem em que os kwargs estão escritos (Python
    avalia argumentos na ordem da fonte), e um reorder futuro — de um formatter,
    ou de quem só quis alinhar com a assinatura de `Employee` — inverteria em
    silêncio qual exceção o dado corrompido produz.

    O `Employee(...)` final é o que impõe as três invariantes que o schema não
    impõe: conjunto de funções vazio ⇒ `EmptyJobFunctionsError`, nome
    vazio/whitespace ⇒ `InvalidNameError`, períodos sobrepostos ⇒
    `OverlappingUnavailabilityError`.
    """
    workload_profile = columns_to_workload_profile(row.workload_kind, row.weekly_hours)
    shift_preference = periods_to_shift_preference(shift_periods)
    periods = rows_to_unavailabilities(unavailabilities)
    return Employee(
        id=EmployeeId(row.id),
        tenant_id=TenantId(row.tenant_id),
        unit_id=UnitId(row.unit_id),
        name=row.name,
        workload_profile=workload_profile,
        shift_preference=shift_preference,
        job_function_ids=frozenset(JobFunctionId(value) for value in job_function_ids),
        unavailabilities=periods,
        active=row.active,
        # Pelo construtor, como os demais: um `""` gravado por fora cairia na
        # validação da entidade (`InvalidIdentifierError`), não num vínculo
        # fantasma (concept 3.5 §4; ADR 3.5.0004 §1).
        user_id=UserId(row.user_id) if row.user_id is not None else None,
    )
