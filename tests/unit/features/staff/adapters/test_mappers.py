"""Mapeamento domínio↔linha do BC staff — metade unitária de CA8b/CA15b e CA17.

Sem banco: as funções são puras, e é isso que permite travar aqui as duas regras
que a Stage inteira depende de não errar.

**A asserção de `tzinfo is None` é a mais importante deste arquivo.** O erro mais
provável desta Stage é normalizar o `datetime` para UTC por analogia com o mapper
de identity — onde é **certo** fazê-lo. Aqui é o oposto:
`UnavailabilityPeriod` rejeita tz-aware (ADR 3.1.0005), então um
`.astimezone(UTC)` escrito por reflexo faria a reidratação levantar sobre dado
válido. Um round-trip que só comparasse `start`/`end` por igualdade **não**
pegaria a inversão, porque a construção já teria explodido — a asserção precisa
existir de propósito.

A segunda é a reidratação **pelo construtor**: as três invariantes que o schema
não impõe (§5.19) levantam ao ler, e é aqui que isso é verificável sem banco.
"""

from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest

from restaurant_hub.features.staff.adapters.out.postgres import mappers
from restaurant_hub.features.staff.adapters.out.postgres.tables import (
    WORKLOAD_KIND_FIXED,
    WORKLOAD_KIND_ON_DEMAND,
)
from restaurant_hub.features.staff.domain.entities.employee import Employee
from restaurant_hub.features.staff.domain.entities.job_function import JobFunction
from restaurant_hub.features.staff.domain.exceptions.errors import (
    EmptyJobFunctionsError,
    InvalidNameError,
    InvalidUnavailabilityPeriodError,
    OverlappingUnavailabilityError,
)
from restaurant_hub.features.staff.domain.value_objects.identifiers import (
    EmployeeId,
    JobFunctionId,
    TenantId,
    UnitId,
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
)

pytestmark = pytest.mark.unit

# Microssegundos entram na asserção de propósito: uma conversão de fuso mal
# feita costuma vir acompanhada de truncamento de precisão.
_MICROSSEGUNDOS = 123456
_PERIODOS_ESPERADOS = 2


def _linha(**colunas: object) -> SimpleNamespace:
    """Linha do driver — acesso por atributo, como `Row` do SQLAlchemy."""
    return SimpleNamespace(**colunas)


def _linha_de_funcionario(**sobrescritas: object) -> SimpleNamespace:
    colunas: dict[str, Any] = {
        "id": "e1",
        "tenant_id": "t1",
        "unit_id": "u1",
        "name": "Ana",
        "workload_kind": WORKLOAD_KIND_ON_DEMAND,
        "weekly_hours": None,
        "active": True,
    }
    colunas.update(sobrescritas)
    return _linha(**colunas)


def _funcionario(**sobrescritas: object) -> Employee:
    campos: dict[str, Any] = {
        "id": EmployeeId("e1"),
        "tenant_id": TenantId("t1"),
        "unit_id": UnitId("u1"),
        "name": "Ana",
        "workload_profile": OnDemand(),
        "shift_preference": None,
        "job_function_ids": frozenset({JobFunctionId("f1")}),
    }
    campos.update(sobrescritas)
    return Employee(**campos)


# ---------------------------------------------------------------------------
# JobFunction
# ---------------------------------------------------------------------------


def test_round_trip_de_funcao_preserva_o_nome_verbatim() -> None:
    """Nome com espaço à direita e case misto atravessa intacto (ADR 3.1.0002).

    Um `strip()`/`lower()` em qualquer ponta faria `'cozinheiro '` e
    `'Cozinheiro'` colidirem no índice único — e CA9 exige que convivam.
    """
    funcao = JobFunction(id=JobFunctionId("f1"), tenant_id=TenantId("t1"), name="cozinheiro ")

    linha = mappers.job_function_to_row(funcao)
    assert linha == {"id": "f1", "tenant_id": "t1", "name": "cozinheiro "}

    de_volta = mappers.row_to_job_function(_linha(**linha))
    assert de_volta.id == "f1"
    assert de_volta.tenant_id == "t1"
    assert de_volta.name == "cozinheiro "


def test_funcao_com_nome_vazio_na_linha_levanta_ao_ser_lida() -> None:
    """Reidratação pelo construtor: linha corrompida não vira entidade inválida."""
    with pytest.raises(InvalidNameError):
        mappers.row_to_job_function(_linha(id="f1", tenant_id="t1", name="   "))


# ---------------------------------------------------------------------------
# WorkloadProfile — a união e o discriminador persistido
# ---------------------------------------------------------------------------


def test_jornada_fixa_vira_par_de_colunas_e_volta() -> None:
    """CA17, metade `Decimal`: valor **e escala** preservados.

    `Decimal("22.50")` não pode voltar `Decimal("22.5")`: a escala é dado, e é
    ela que a coluna `NUMERIC` sem precisão existe para preservar.
    """
    kind, horas = mappers.workload_profile_to_columns(FixedSchedule(weekly_hours=Decimal("22.50")))
    assert kind == WORKLOAD_KIND_FIXED
    assert horas == Decimal("22.50")

    de_volta = mappers.columns_to_workload_profile(kind, horas)
    assert de_volta == FixedSchedule(weekly_hours=Decimal("22.50"))
    assert isinstance(de_volta, FixedSchedule)
    assert str(de_volta.weekly_hours) == "22.50"


def test_jornada_sob_demanda_vira_par_de_colunas_e_volta() -> None:
    """`OnDemand` não carrega carga — a coluna vai `NULL`, e o iff depende disso."""
    kind, horas = mappers.workload_profile_to_columns(OnDemand())
    assert (kind, horas) == (WORKLOAD_KIND_ON_DEMAND, None)
    assert mappers.columns_to_workload_profile(kind, horas) == OnDemand()


def test_o_mapper_consome_os_literais_de_tables_e_nao_os_repete() -> None:
    """Fonte única: o par de constantes de `tables.py` governa as duas direções.

    Se alguém trocar o literal aqui sem trocar a `CHECK`, a divergência só
    apareceria como `ck_employees_workload_kind_known` violada em produção.
    """
    kind, _ = mappers.workload_profile_to_columns(FixedSchedule(weekly_hours=Decimal("40")))
    assert kind is WORKLOAD_KIND_FIXED
    kind_sob_demanda, _ = mappers.workload_profile_to_columns(OnDemand())
    assert kind_sob_demanda is WORKLOAD_KIND_ON_DEMAND


@pytest.mark.parametrize(
    ("kind", "horas"),
    [
        (WORKLOAD_KIND_FIXED, None),
        (WORKLOAD_KIND_ON_DEMAND, Decimal("40")),
        ("freelance", None),
    ],
    ids=["fixa_sem_horas", "sob_demanda_com_horas", "tipo_desconhecido"],
)
def test_combinacao_que_a_check_proibe_levanta_ao_ser_lida(
    kind: str, horas: Decimal | None
) -> None:
    """Linha fora do que a `CHECK` aceita significa schema divergente do código.

    Estourar alto é o desejado — mesmo motivo do `SetupTokenPurpose(row.purpose)`
    de identity. Silenciar produziria um perfil de jornada inventado pelo mapper.
    """
    with pytest.raises(ValueError):
        mappers.columns_to_workload_profile(kind, horas)


# ---------------------------------------------------------------------------
# Tabelas-filhas
# ---------------------------------------------------------------------------


def test_vinculos_saem_em_ordem_deterministica_com_o_tenant_denormalizado() -> None:
    """`sorted()` sobre o `frozenset` — §5.15 e ordem de lock estável (§5.20).

    Sem ele a ordem de inserção depende de `PYTHONHASHSEED`, e ordem de aquisição
    de lock variável entre execuções é como um deadlock vira "flakiness" em vez
    de bug.
    """
    funcionario = _funcionario(
        job_function_ids=frozenset({JobFunctionId("f99"), JobFunctionId("f1"), JobFunctionId("f7")})
    )
    assert mappers.job_function_link_rows(funcionario) == [
        {"employee_id": "e1", "job_function_id": "f1", "tenant_id": "t1"},
        {"employee_id": "e1", "job_function_id": "f7", "tenant_id": "t1"},
        {"employee_id": "e1", "job_function_id": "f99", "tenant_id": "t1"},
    ]


def test_sem_preferencia_declarada_nao_ha_linha_alguma() -> None:
    """Regra 4: "nenhuma linha" e "preferência vazia" são o mesmo estado."""
    assert mappers.shift_preference_rows(_funcionario(shift_preference=None)) == []


def test_preferencia_declarada_vira_uma_linha_por_periodo() -> None:
    funcionario = _funcionario(
        shift_preference=ShiftPreference(periods=frozenset({DayPeriod.NIGHT, DayPeriod.MORNING}))
    )
    linhas = mappers.shift_preference_rows(funcionario)
    assert {linha["period"] for linha in linhas} == {"morning", "night"}
    assert {linha["employee_id"] for linha in linhas} == {"e1"}


def test_periodos_sem_linha_reidratam_para_none() -> None:
    assert mappers.periods_to_shift_preference([]) is None


def test_periodos_com_linha_reidratam_para_shift_preference_nao_vazia() -> None:
    """ADR 3.1.0004: preferência declarada nunca é vazia."""
    preferencia = mappers.periods_to_shift_preference(["overnight", "morning"])
    assert preferencia == ShiftPreference(
        periods=frozenset({DayPeriod.OVERNIGHT, DayPeriod.MORNING})
    )


def test_periodo_fora_do_enum_levanta_ao_ser_lido() -> None:
    """A `CHECK` deriva do enum; uma linha fora dele é schema divergente."""
    with pytest.raises(ValueError):
        mappers.periods_to_shift_preference(["dawn"])


def test_indisponibilidades_atravessam_ingenuas_e_na_ordem_recebida() -> None:
    """A asserção central deste arquivo — Regra 2, o oposto de identity.

    `tzinfo is None` explícito: um `.astimezone(UTC)` escrito por analogia com o
    mapper de identity faria a construção de `UnavailabilityPeriod` levantar
    sobre dado válido. E os microssegundos entram na asserção porque uma
    conversão de fuso mal feita costuma vir acompanhada de truncamento.
    """
    linhas = [
        _linha(
            start_at=datetime(2026, 8, 10, 8, 0, 0, _MICROSSEGUNDOS),
            end_at=datetime(2026, 8, 10, 12, 0, 0),
        ),
        _linha(start_at=datetime(2026, 8, 11, 8, 0), end_at=datetime(2026, 8, 11, 12, 0)),
    ]

    periodos = mappers.rows_to_unavailabilities(linhas)

    assert len(periodos) == _PERIODOS_ESPERADOS
    assert periodos[0].start == datetime(2026, 8, 10, 8, 0, 0, _MICROSSEGUNDOS)
    assert periodos[0].start.microsecond == _MICROSSEGUNDOS
    for periodo in periodos:
        assert periodo.start.tzinfo is None
        assert periodo.end.tzinfo is None
    # A ordem recebida (o `ORDER BY start_at` do adapter) é preservada.
    assert [p.start for p in periodos] == sorted(p.start for p in periodos)


def test_periodos_do_funcionario_viram_linhas_sem_conversao_de_fuso() -> None:
    """A mesma regra na direção da escrita: nada de `.astimezone` na ida."""
    periodo = UnavailabilityPeriod(
        start=datetime(2026, 8, 10, 8, 0, 0, _MICROSSEGUNDOS), end=datetime(2026, 8, 10, 12, 0)
    )
    funcionario = _funcionario(unavailabilities=(periodo,))

    linhas = mappers.unavailability_rows(funcionario)

    assert linhas == [
        {
            "employee_id": "e1",
            "start_at": datetime(2026, 8, 10, 8, 0, 0, _MICROSSEGUNDOS),
            "end_at": datetime(2026, 8, 10, 12, 0),
        }
    ]
    assert linhas[0]["start_at"].tzinfo is None


# ---------------------------------------------------------------------------
# Employee — o agregado de quatro tabelas
# ---------------------------------------------------------------------------


def test_round_trip_de_funcionario_sob_demanda_sem_preferencia() -> None:
    """O caso mínimo: `OnDemand`, sem preferência, sem período."""
    funcionario = _funcionario()

    linha = mappers.employee_to_row(funcionario)
    assert linha == {
        "id": "e1",
        "tenant_id": "t1",
        "unit_id": "u1",
        "name": "Ana",
        "workload_kind": WORKLOAD_KIND_ON_DEMAND,
        "weekly_hours": None,
        "active": True,
    }

    de_volta = mappers.row_to_employee(
        _linha(**linha),
        job_function_ids=["f1"],
        unavailabilities=[],
        shift_periods=[],
    )
    assert de_volta.id == "e1"
    assert de_volta.workload_profile == OnDemand()
    assert de_volta.shift_preference is None
    assert de_volta.unavailabilities == ()
    assert de_volta.job_function_ids == frozenset({"f1"})
    assert de_volta.active is True


def test_round_trip_de_funcionario_completo() -> None:
    """CA17: `Decimal` com escala, `datetime` ingênuo com microssegundos.

    O agregado inteiro — jornada fixa, preferência declarada, dois períodos e
    duas funções — sai para as quatro tabelas e volta idêntico.
    """
    periodos = (
        UnavailabilityPeriod(
            start=datetime(2026, 8, 10, 8, 0, 0, _MICROSSEGUNDOS), end=datetime(2026, 8, 10, 12, 0)
        ),
        UnavailabilityPeriod(start=datetime(2026, 8, 12, 8, 0), end=datetime(2026, 8, 12, 12, 0)),
    )
    funcionario = _funcionario(
        name="Ana Maria",
        workload_profile=FixedSchedule(weekly_hours=Decimal("22.50")),
        shift_preference=ShiftPreference(periods=frozenset({DayPeriod.AFTERNOON})),
        job_function_ids=frozenset({JobFunctionId("f1"), JobFunctionId("f2")}),
        unavailabilities=periodos,
        active=False,
    )

    linha = mappers.employee_to_row(funcionario)
    de_volta = mappers.row_to_employee(
        _linha(**linha),
        job_function_ids=[
            r["job_function_id"] for r in mappers.job_function_link_rows(funcionario)
        ],
        unavailabilities=[_linha(**r) for r in mappers.unavailability_rows(funcionario)],
        shift_periods=[r["period"] for r in mappers.shift_preference_rows(funcionario)],
    )

    assert de_volta.name == "Ana Maria"
    assert de_volta.workload_profile == FixedSchedule(weekly_hours=Decimal("22.50"))
    assert isinstance(de_volta.workload_profile, FixedSchedule)
    assert str(de_volta.workload_profile.weekly_hours) == "22.50"
    assert de_volta.shift_preference == ShiftPreference(periods=frozenset({DayPeriod.AFTERNOON}))
    assert de_volta.job_function_ids == frozenset({"f1", "f2"})
    assert de_volta.unavailabilities == periodos
    assert de_volta.unavailabilities[0].start.microsecond == _MICROSSEGUNDOS
    assert de_volta.active is False


@pytest.mark.parametrize(
    ("sobrescritas", "extras", "esperado"),
    [
        ({}, {"job_function_ids": []}, EmptyJobFunctionsError),
        ({"name": "   "}, {}, InvalidNameError),
        (
            {},
            {
                "unavailabilities": [
                    _linha(
                        start_at=datetime(2026, 8, 10, 8, 0), end_at=datetime(2026, 8, 10, 12, 0)
                    ),
                    _linha(
                        start_at=datetime(2026, 8, 10, 10, 0), end_at=datetime(2026, 8, 10, 14, 0)
                    ),
                ]
            },
            OverlappingUnavailabilityError,
        ),
    ],
    ids=["sem_funcao", "nome_vazio", "periodos_sobrepostos"],
)
def test_as_tres_invariantes_que_o_schema_nao_impoe_levantam_ao_ser_lidas(
    sobrescritas: dict[str, Any], extras: dict[str, Any], esperado: type[Exception]
) -> None:
    """§5.19 / CA16, metade unitária — é o construtor que as impõe, e só ele.

    O probe mediu que o banco **aceita** as três linhas. Sem a Regra 1, cada uma
    viraria uma entidade inválida em circulação, que o resto do sistema trataria
    como legítima. Um `object.__setattr__` no lugar do construtor apagaria estas
    três garantias sem quebrar nenhum outro teste desta Stage.
    """
    argumentos: dict[str, Any] = {
        "job_function_ids": ["f1"],
        "unavailabilities": [],
        "shift_periods": [],
    }
    argumentos.update(extras)

    with pytest.raises(esperado):
        mappers.row_to_employee(_linha_de_funcionario(**sobrescritas), **argumentos)


# ---------------------------------------------------------------------------
# A precedência entre as conversões de `row_to_employee`
# ---------------------------------------------------------------------------
#
# **Por que estes três testes existem.** O docstring de `row_to_employee` afirma
# que as três conversões saem para variáveis locais **de propósito**, porque
# Python avalia argumentos na ordem da fonte e um reorder — de um formatter, ou
# de quem só quis alinhar com a assinatura de `Employee` — "inverteria em
# silêncio qual exceção o dado corrompido produz".
#
# A afirmação é verdadeira, e até aqui **nada a prendia**: reordenar as três
# linhas passava na suíte inteira. Um docstring que afirma o que nenhum gate
# confere é exatamente a classe de asserção aspiracional que este projeto já
# catalogou — ou se trava, ou se rebaixa a prosa. Aqui se trava.
#
# A ordem travada é a da fonte: jornada → preferência → períodos → construtor.
# Cada teste corrompe **duas** coisas ao mesmo tempo e exige a exceção da
# **primeira**; com uma corrupção só, toda ordem responde igual e o teste não
# discriminaria nada.


def test_precedencia_jornada_invalida_vence_periodo_de_preferencia_invalido() -> None:
    """1º `columns_to_workload_profile`, 2º `periods_to_shift_preference`.

    As duas levantam `ValueError`, então a discriminação é pela **mensagem** — é
    o preço de a segunda vir de `DayPeriod(...)`, do enum, cuja exceção não é
    nossa para tipar.
    """
    with pytest.raises(ValueError, match="tipo de jornada desconhecido") as excecao:
        mappers.row_to_employee(
            _linha_de_funcionario(workload_kind="jornada-que-nao-existe"),
            job_function_ids=["f1"],
            unavailabilities=[],
            shift_periods=["periodo-que-nao-existe"],
        )
    assert "DayPeriod" not in str(excecao.value)


def test_precedencia_periodo_de_preferencia_invalido_vence_indisponibilidade_invalida() -> None:
    """2º `periods_to_shift_preference`, 3º `rows_to_unavailabilities`."""
    with pytest.raises(ValueError, match="DayPeriod"):
        mappers.row_to_employee(
            _linha_de_funcionario(),
            job_function_ids=["f1"],
            # `start >= end` faria `UnavailabilityPeriod` recusar — mas só depois.
            unavailabilities=[
                _linha(start_at=datetime(2026, 8, 10, 12, 0), end_at=datetime(2026, 8, 10, 8, 0))
            ],
            shift_periods=["periodo-que-nao-existe"],
        )


def test_precedencia_indisponibilidade_invalida_vence_invariante_da_entidade() -> None:
    """3º `rows_to_unavailabilities`, 4º o construtor de `Employee`.

    O nome vazio só é avaliado dentro do `__post_init__`, que roda por último —
    então a linha com **os dois** defeitos responde pelo período, não pelo nome.
    """
    with pytest.raises(InvalidUnavailabilityPeriodError):
        mappers.row_to_employee(
            _linha_de_funcionario(name="   "),
            job_function_ids=["f1"],
            unavailabilities=[
                _linha(start_at=datetime(2026, 8, 10, 12, 0), end_at=datetime(2026, 8, 10, 8, 0))
            ],
            shift_periods=[],
        )
