"""Testes da raiz Schedule (entities/schedule.py) — construção, invariantes e leituras.

Fecha CA10 (as sub-checagens da raiz, inclusive o caso discriminante
civil/operacional), CA15, CA16, CA22 e CA24. Parcial de CA12 (as linhas das
leituras na matriz método x exceção da §6) e de CA23 (as leituras em minutos e a
divergência por id).

As varreduras daqui cobram listas escritas no topo **contra a classe**, por
introspecção — a lista sozinha envelhece, a introspecção sozinha concorda com
qualquer coisa.
"""

import dataclasses
import inspect
import typing
from collections.abc import Callable
from datetime import date, datetime, time, timedelta
from typing import Any

import pytest

from restaurant_hub.features.scheduling.domain.entities.assignment import Assignment
from restaurant_hub.features.scheduling.domain.entities.schedule import Schedule
from restaurant_hub.features.scheduling.domain.entities.shift_band import ShiftBand
from restaurant_hub.features.scheduling.domain.entities.shift_demand import ShiftDemand
from restaurant_hub.features.scheduling.domain.exceptions.errors import (
    AssignmentNotFoundError,
    DuplicateEntityIdError,
    DuplicateShiftBandError,
    InvalidIdentifierError,
    InvalidSchedulePeriodError,
    InvalidScheduleVersionError,
    SchedulingError,
    ShiftBandNotFoundError,
    ShiftDemandNotFoundError,
    TimeRangeOutsidePeriodError,
)
from restaurant_hub.features.scheduling.domain.value_objects.demand_quantity import (
    DemandQuantity,
)
from restaurant_hub.features.scheduling.domain.value_objects.identifiers import (
    AssignmentId,
    EmployeeId,
    JobFunctionId,
    ScheduleId,
    ShiftBandId,
    ShiftDemandId,
    TenantId,
    UnitId,
)
from restaurant_hub.features.scheduling.domain.value_objects.operational_calendar import (
    DayCutoff,
    OperationalCalendar,
    Weekday,
)
from restaurant_hub.features.scheduling.domain.value_objects.schedule_period import (
    SchedulePeriod,
)
from restaurant_hub.features.scheduling.domain.value_objects.time_range import TimeRange

pytestmark = pytest.mark.unit

# Período de segunda 2026-09-28 a domingo 2026-10-04; corte 05:00.
_SEGUNDA = date(2026, 9, 28)
_SEXTA = date(2026, 10, 2)
_SABADO = date(2026, 10, 3)
_DOMINGO = date(2026, 10, 4)
_CALENDARIO = OperationalCalendar(week_start=Weekday.MONDAY, day_cutoff=DayCutoff(at=time(5, 0)))
_PERIODO = SchedulePeriod(first_day=_SEGUNDA)
_UMA_HORA = 60

# As 8 leituras de §4 (CA15). Cobrada contra a classe em
# `test_as_leituras_publicas_sao_exatamente_as_oito`.
_LEITURAS = (
    "band",
    "locate_demand",
    "locate_assignment",
    "bands_of",
    "operational_day_of",
    "worked_minutes_of",
    "effective_break_minutes_of",
    "has_break_divergence",
)

# As linhas da matriz §6 (método x exceção) que as leituras ocupam (CA12, parcial).
_MATRIZ_DAS_LEITURAS: tuple[tuple[str, type[SchedulingError]], ...] = (
    ("band", ShiftBandNotFoundError),
    ("locate_demand", ShiftDemandNotFoundError),
    ("locate_assignment", AssignmentNotFoundError),
    ("worked_minutes_of", AssignmentNotFoundError),
    ("effective_break_minutes_of", AssignmentNotFoundError),
    ("has_break_divergence", AssignmentNotFoundError),
)


def _faixa(
    faixa_id: str,
    inicio: datetime,
    horas: int,
    *demandas: ShiftDemand,
    break_minutes: int = 0,
) -> ShiftBand:
    return ShiftBand(
        id=ShiftBandId(faixa_id),
        time_range=TimeRange(
            start=inicio, end=inicio + timedelta(hours=horas), break_minutes=break_minutes
        ),
        demands=demandas,
    )


def _dem(dem: str, funcao: str, *alocacoes: Assignment) -> ShiftDemand:
    return ShiftDemand(
        id=ShiftDemandId(dem),
        job_function_id=JobFunctionId(funcao),
        quantity=DemandQuantity(1),
        assignments=alocacoes,
    )


def _aloc(aloc: str, funcionario: str, break_minutes: int | None = None) -> Assignment:
    return Assignment(
        id=AssignmentId(aloc), employee_id=EmployeeId(funcionario), break_minutes=break_minutes
    )


def _escala(*faixas: ShiftBand, version: int = 1) -> Schedule:
    return Schedule(
        id=ScheduleId("escala-1"),
        tenant_id=TenantId("tenant-1"),
        unit_id=UnitId("unidade-1"),
        period=_PERIODO,
        calendar=_CALENDARIO,
        bands=faixas,
        version=version,
    )


def _as(dia: date, hora: int) -> datetime:
    return datetime(dia.year, dia.month, dia.day, hora, 0)


def _escala_de_duas_faixas() -> Schedule:
    """2 faixas, 2 demandas cada, 1 alocação por demanda — o agregado de CA24."""
    return _escala(
        _faixa(
            "f1",
            _as(_SEXTA, 16),
            8,
            _dem("d1", "cozinheiro", _aloc("a1", "ana", _UMA_HORA)),
            _dem("d2", "atendente", _aloc("a2", "bia")),
        ),
        _faixa(
            "f2",
            _as(_SABADO, 2),
            4,
            _dem("d3", "cozinheiro", _aloc("a3", "caio")),
            _dem("d4", "atendente", _aloc("a4", "dani")),
        ),
    )


# --- CA10 (raiz): invariantes na construção direta ------------------------------------


def test_escala_valida_e_aceita() -> None:
    escala = _escala_de_duas_faixas()
    assert escala.version == 1
    assert len(escala.bands) == 2  # noqa: PLR2004


def test_mesmo_par_de_faixa_nao_consecutivo_e_recusado_mesmo_com_intervalos_diferentes() -> None:
    # 1ª e 3ª com o mesmo (start, end) e intervalos 0 e 60; a 2ª diferente.
    with pytest.raises(DuplicateShiftBandError):
        _escala(
            _faixa("f1", _as(_SEXTA, 16), 8),
            _faixa("f2", _as(_SEXTA, 18), 5),
            _faixa("f3", _as(_SEXTA, 16), 8, break_minutes=_UMA_HORA),
        )


def test_faixas_sobrepostas_distintas_sao_aceitas() -> None:
    escala = _escala(_faixa("f1", _as(_SEXTA, 16), 8), _faixa("f2", _as(_SEXTA, 18), 5))
    assert escala.bands[0].time_range.overlaps(escala.bands[1].time_range)


@pytest.mark.parametrize("version", [0, -1])
def test_versao_menor_que_um_e_recusada(version: int) -> None:
    with pytest.raises(InvalidScheduleVersionError):
        _escala(version=version)


@pytest.mark.parametrize("version", [1, 7])
def test_versao_a_partir_de_um_e_aceita(version: int) -> None:
    assert _escala(version=version).version == version


def test_periodo_desalinhado_ao_calendario_fotografado_e_recusado() -> None:
    terca = _SEGUNDA + timedelta(days=1)
    with pytest.raises(InvalidSchedulePeriodError, match="desalinhado"):
        dataclasses.replace(_escala(), period=SchedulePeriod(first_day=terca))


def test_alinhamento_e_ao_calendario_da_escala_e_nao_ao_default() -> None:
    terca = _SEGUNDA + timedelta(days=1)
    calendario_de_terca = OperationalCalendar(
        week_start=Weekday.TUESDAY, day_cutoff=DayCutoff(at=time(5, 0))
    )
    escala = dataclasses.replace(
        _escala(), period=SchedulePeriod(first_day=terca), calendar=calendario_de_terca
    )
    assert escala.period.first_day == terca
    with pytest.raises(InvalidSchedulePeriodError):
        dataclasses.replace(escala, period=_PERIODO)


def test_faixa_que_comeca_na_madrugada_depois_do_ultimo_dia_e_aceita() -> None:
    # Caso discriminante (a): data civil fora do período (segunda 2026-10-05),
    # dia operacional dentro (domingo, o last_day). `start.date()` recusaria.
    madrugada = datetime(2026, 10, 5, 2, 0)
    escala = _escala(_faixa("f1", madrugada, 3))
    assert escala.operational_day_of(escala.bands[0]) == _DOMINGO


def test_faixa_que_comeca_na_madrugada_do_primeiro_dia_e_recusada() -> None:
    # Caso discriminante (b): data civil dentro (segunda 2026-09-28), dia
    # operacional fora (domingo 2026-09-27, anterior ao first_day).
    # `start.date()` aceitaria.
    with pytest.raises(TimeRangeOutsidePeriodError):
        _escala(_faixa("f1", _as(_SEGUNDA, 2), 3))


@pytest.mark.parametrize(
    "inicio",
    [
        pytest.param(datetime(2026, 10, 5, 10, 0), id="segunda_seguinte"),
        pytest.param(datetime(2026, 9, 27, 18, 0), id="domingo_anterior"),
    ],
)
def test_faixa_fora_do_periodo_e_recusada(inicio: datetime) -> None:
    with pytest.raises(TimeRangeOutsidePeriodError):
        _escala(_faixa("f1", inicio, 4))


def test_faixa_do_ultimo_dia_que_termina_depois_do_periodo_e_aceita() -> None:
    # ADR 4.1.0008 §3: domingo 22:00 a segunda 06:00.
    escala = _escala(_faixa("f1", _as(_DOMINGO, 22), 8))
    assert escala.bands[0].time_range.end > _as(_DOMINGO + timedelta(days=1), 0)


def test_shift_band_id_repetido_nao_consecutivo_e_recusado() -> None:
    with pytest.raises(DuplicateEntityIdError, match="ShiftBandId"):
        _escala(
            _faixa("f1", _as(_SEXTA, 8), 4),
            _faixa("f2", _as(_SEXTA, 12), 4),
            _faixa("f1", _as(_SEXTA, 16), 4),
        )


def test_faixa_repetida_por_inteiro_levanta_a_colisao_de_id_primeiro() -> None:
    # Mesmo id e mesmo intervalo: a precedência é colisão de id (§7, [decision] da
    # auditoria de mutação) — o terceiro nível da regra, ao lado de demanda e alocação.
    with pytest.raises(DuplicateEntityIdError, match="ShiftBandId"):
        _escala(_faixa("f1", _as(_SEXTA, 16), 4), _faixa("f1", _as(_SEXTA, 16), 4))


def test_shift_demand_id_repetido_em_faixas_distintas_e_recusado() -> None:
    with pytest.raises(DuplicateEntityIdError, match="ShiftDemandId"):
        _escala(
            _faixa("f1", _as(_SEXTA, 8), 4, _dem("d1", "cozinheiro")),
            _faixa("f2", _as(_SEXTA, 12), 4, _dem("d2", "cozinheiro")),
            _faixa("f3", _as(_SEXTA, 16), 4, _dem("d1", "cozinheiro")),
        )


def test_assignment_id_repetido_em_demandas_de_faixas_distintas_e_recusado() -> None:
    with pytest.raises(DuplicateEntityIdError, match="AssignmentId"):
        _escala(
            _faixa("f1", _as(_SEXTA, 8), 4, _dem("d1", "cozinheiro", _aloc("a1", "ana"))),
            _faixa("f2", _as(_SEXTA, 12), 4, _dem("d2", "cozinheiro", _aloc("a2", "bia"))),
            _faixa("f3", _as(_SEXTA, 16), 4, _dem("d3", "cozinheiro", _aloc("a1", "caio"))),
        )


def test_assignment_id_repetido_em_demandas_distintas_da_mesma_faixa_e_recusado() -> None:
    # A ShiftBand não vê ids de alocação entre as suas demandas (§5.15): é a raiz
    # que recusa (Checkpoint C do bloco 2, obs-A). Par nas posições 0 e 2.
    with pytest.raises(DuplicateEntityIdError, match="AssignmentId"):
        _escala(
            _faixa(
                "f1",
                _as(_SEXTA, 16),
                8,
                _dem("d1", "cozinheiro", _aloc("a1", "ana")),
                _dem("d2", "atendente", _aloc("a2", "bia")),
                _dem("d3", "barman", _aloc("a1", "caio")),
            )
        )


# --- CA22 (fecha): os 8 identificadores em cada entidade, por introspecção ------------

_TIPOS_DE_ID = (
    ScheduleId,
    ShiftBandId,
    ShiftDemandId,
    AssignmentId,
    TenantId,
    UnitId,
    EmployeeId,
    JobFunctionId,
)

# Uma instância válida de cada entidade; cada campo cujo tipo é um dos 8
# identificadores é trocado por vazio/whitespace (Checkpoint C do bloco 2, item 4).
_EXEMPLARES: dict[type, Callable[[], object]] = {
    Assignment: lambda: _aloc("a1", "ana"),
    ShiftDemand: lambda: _dem("d1", "cozinheiro"),
    ShiftBand: lambda: _faixa("f1", _as(_SEXTA, 16), 8),
    Schedule: _escala,
}


def _campos_de_id(entidade: type) -> tuple[str, ...]:
    dicas = typing.get_type_hints(entidade)
    return tuple(
        campo.name for campo in dataclasses.fields(entidade) if dicas[campo.name] in _TIPOS_DE_ID
    )


def test_toda_entidade_do_bc_esta_na_varredura_e_os_oito_tipos_sao_cobertos() -> None:
    # Anti-vácuo e totalidade: os 8 tipos aparecem em ao menos uma entidade.
    cobertos = {
        typing.get_type_hints(entidade)[campo]
        for entidade in _EXEMPLARES
        for campo in _campos_de_id(entidade)
    }
    assert cobertos == set(_TIPOS_DE_ID)


@pytest.mark.parametrize(
    ("entidade", "campo"),
    [(entidade, campo) for entidade in _EXEMPLARES for campo in _campos_de_id(entidade)],
    ids=lambda valor: getattr(valor, "__name__", str(valor)),
)
@pytest.mark.parametrize("vazio", ["", "   "])
def test_todo_campo_de_id_recusa_vazio_e_so_espaco(entidade: type, campo: str, vazio: str) -> None:
    exemplar: Any = _EXEMPLARES[entidade]()
    with pytest.raises(InvalidIdentifierError):
        dataclasses.replace(exemplar, **{campo: vazio})


# --- leituras: caminho positivo (CA24) ------------------------------------------------


def test_band_devolve_a_faixa_do_id() -> None:
    escala = _escala_de_duas_faixas()
    assert escala.band(ShiftBandId("f2")) is escala.bands[1]
    assert escala.band(ShiftBandId("f1")) is escala.bands[0]


def test_locate_demand_devolve_o_par_correto_em_cada_faixa() -> None:
    escala = _escala_de_duas_faixas()
    for faixa in escala.bands:
        for demanda in faixa.demands:
            encontrada = escala.locate_demand(demanda.id)
            assert encontrada[0] is faixa
            assert encontrada[1] is demanda


def test_locate_assignment_devolve_a_tripla_correta() -> None:
    escala = _escala_de_duas_faixas()
    vistos = 0
    for faixa in escala.bands:
        for demanda in faixa.demands:
            for alocacao in demanda.assignments:
                tripla = escala.locate_assignment(alocacao.id)
                assert tripla[0] is faixa
                assert tripla[1] is demanda
                assert tripla[2] is alocacao
                vistos += 1
    assert vistos == 4  # noqa: PLR2004


def test_bands_of_agrupa_pelo_dia_operacional() -> None:
    # A faixa de sábado 02:00-06:00, com corte 05:00, é de sexta.
    escala = _escala_de_duas_faixas()
    assert escala.bands_of(_SEXTA) == (escala.bands[0], escala.bands[1])
    assert escala.bands_of(_SABADO) == ()


def test_operational_day_of_devolve_o_dia_operacional_e_nao_o_civil() -> None:
    escala = _escala_de_duas_faixas()
    madrugada = escala.band(ShiftBandId("f2"))
    assert madrugada.time_range.start.date() == _SABADO
    assert escala.operational_day_of(madrugada) == _SEXTA


# --- leituras em minutos e a divergência por id (CA16, CA23 parcial) ------------------


def test_cenario_do_sponsor_pelas_leituras_da_raiz() -> None:
    escala = _escala_de_duas_faixas()
    cozinheiro, atendente = AssignmentId("a1"), AssignmentId("a2")
    assert escala.effective_break_minutes_of(cozinheiro) == _UMA_HORA
    assert escala.worked_minutes_of(cozinheiro) == 7 * 60
    assert escala.has_break_divergence(cozinheiro) is True
    assert escala.effective_break_minutes_of(atendente) == 0
    assert escala.worked_minutes_of(atendente) == 8 * 60
    assert escala.has_break_divergence(atendente) is False


def test_worked_minutes_of_delega_ao_sitio_unico() -> None:
    escala = _escala_de_duas_faixas()
    for faixa in escala.bands:
        for demanda in faixa.demands:
            for alocacao in demanda.assignments:
                esperado = faixa.time_range.worked_minutes(faixa.effective_break_of(alocacao))
                assert escala.worked_minutes_of(alocacao.id) == esperado


def test_has_break_divergence_da_raiz_delega_a_faixa_que_contem_a_alocacao() -> None:
    # Mesmo intervalo declarado (60) em duas faixas de intervalos distintos: só
    # diverge na faixa de intervalo 0. Uma raiz que consultasse a faixa errada,
    # ou que comparasse com um intervalo fixo, erraria um dos dois.
    escala = _escala(
        _faixa("f1", _as(_SEXTA, 8), 6, _dem("d1", "cozinheiro", _aloc("a1", "ana", 60))),
        _faixa(
            "f2",
            _as(_SEXTA, 16),
            8,
            _dem("d2", "cozinheiro", _aloc("a2", "bia", 60)),
            break_minutes=60,
        ),
    )
    assert escala.has_break_divergence(AssignmentId("a1")) is True
    assert escala.has_break_divergence(AssignmentId("a2")) is False
    assert escala.effective_break_minutes_of(AssignmentId("a2")) == _UMA_HORA
    assert escala.worked_minutes_of(AssignmentId("a2")) == 7 * 60


def test_alocacao_sem_declaracao_herda_o_intervalo_da_faixa_pela_raiz() -> None:
    escala = _escala(
        _faixa(
            "f1", _as(_SEXTA, 16), 8, _dem("d1", "cozinheiro", _aloc("a1", "ana")), break_minutes=30
        )
    )
    assert escala.effective_break_minutes_of(AssignmentId("a1")) == 30  # noqa: PLR2004
    assert escala.worked_minutes_of(AssignmentId("a1")) == 8 * 60 - 30
    assert escala.has_break_divergence(AssignmentId("a1")) is False


def test_intervalo_herdado_vem_da_faixa_que_contem_a_alocacao() -> None:
    # Checkpoint C do bloco 3, item 3: alocação SEM intervalo próprio na SEGUNDA
    # faixa, com intervalo diferente do da primeira. Uma raiz que lesse sempre a
    # primeira faixa devolveria 0.
    escala = _escala(
        _faixa("f1", _as(_SEXTA, 8), 6, _dem("d1", "cozinheiro", _aloc("a1", "ana"))),
        _faixa(
            "f2",
            _as(_SEXTA, 16),
            8,
            _dem("d2", "cozinheiro", _aloc("a2", "bia")),
            break_minutes=30,
        ),
    )
    assert escala.effective_break_minutes_of(AssignmentId("a2")) == 30  # noqa: PLR2004
    assert escala.worked_minutes_of(AssignmentId("a2")) == 8 * 60 - 30
    assert escala.effective_break_minutes_of(AssignmentId("a1")) == 0
    assert escala.worked_minutes_of(AssignmentId("a1")) == 6 * 60


def test_worked_minutes_of_passa_pelo_sitio_unico(monkeypatch: pytest.MonkeyPatch) -> None:
    # Teste-espião (Checkpoint C do bloco 3, item 5): a anotação `int` não impede
    # uma segunda aritmética dentro de `worked_minutes_of`; a sentinela sim.
    sentinela = 987_654
    chamadas: list[int | None] = []

    def espiao(self: TimeRange, break_minutes: int | None = None) -> int:
        chamadas.append(break_minutes)
        return sentinela

    escala = _escala_de_duas_faixas()
    monkeypatch.setattr(TimeRange, "worked_minutes", espiao)
    assert escala.worked_minutes_of(AssignmentId("a1")) == sentinela
    # Uma chamada, com o intervalo efetivo que a faixa calcula (60, declarado).
    assert chamadas == [_UMA_HORA]


# --- CA12 (parcial): as linhas das leituras na matriz §6 ------------------------------


@pytest.mark.parametrize(
    ("metodo", "excecao"), _MATRIZ_DAS_LEITURAS, ids=lambda v: getattr(v, "__name__", v)
)
def test_leitura_com_id_inexistente_levanta_a_excecao_da_matriz(
    metodo: str, excecao: type[SchedulingError]
) -> None:
    escala = _escala_de_duas_faixas()
    with pytest.raises(excecao):
        getattr(escala, metodo)("nao-existe")


def test_a_matriz_das_leituras_cobre_toda_leitura_que_recebe_id() -> None:
    # Derivada das assinaturas: toda leitura que recebe um id interno tem linha
    # na matriz (a §6 manda "…NotFoundError" para cada uma).
    ids_internos = (ShiftBandId, ShiftDemandId, AssignmentId)
    recebem_id = set()
    for nome in _LEITURAS:
        dicas = typing.get_type_hints(getattr(Schedule, nome))
        parametros = [
            p for p in inspect.signature(getattr(Schedule, nome)).parameters if p != "self"
        ]
        if any(dicas[p] in ids_internos for p in parametros):
            recebem_id.add(nome)
    assert recebem_id == {metodo for metodo, _ in _MATRIZ_DAS_LEITURAS}


# --- CA15 (fecha): superfície imutável e igualdade ------------------------------------


def _retorno(membro: object) -> object:
    alvo = membro.fget if isinstance(membro, property) else membro
    return typing.get_type_hints(alvo).get("return")


def test_as_leituras_publicas_sao_exatamente_as_oito() -> None:
    # As públicas de Schedule que NÃO devolvem Schedule são as leituras; as que
    # devolvem Schedule são as mutações (Tasks 09 e 10, varredura própria).
    leituras = {
        nome
        for nome, membro in vars(Schedule).items()
        if not nome.startswith("_") and callable(membro) and _retorno(membro) is not Schedule
    }
    assert leituras == set(_LEITURAS)


def _chamar_leitura(escala: Schedule, nome: str) -> object:
    argumentos: dict[str, object] = {
        "band": ShiftBandId("f1"),
        "locate_demand": ShiftDemandId("d1"),
        "locate_assignment": AssignmentId("a1"),
        "bands_of": _SEXTA,
        "operational_day_of": escala.bands[0],
        "worked_minutes_of": AssignmentId("a1"),
        "effective_break_minutes_of": AssignmentId("a1"),
        "has_break_divergence": AssignmentId("a1"),
    }
    return getattr(escala, nome)(argumentos[nome])


def _e_imutavel(valor: object) -> bool:
    if isinstance(valor, tuple):
        return all(_e_imutavel(item) for item in valor)
    if dataclasses.is_dataclass(valor):
        return type(valor).__dataclass_params__.frozen  # type: ignore[attr-defined,no-any-return]
    return isinstance(valor, (int, bool, date))


@pytest.mark.parametrize("leitura", _LEITURAS)
def test_cada_leitura_devolve_tupla_ou_valor_imutavel(leitura: str) -> None:
    valor = _chamar_leitura(_escala_de_duas_faixas(), leitura)
    assert not isinstance(valor, (list, dict, set))
    assert _e_imutavel(valor)


_ENTIDADES = (Assignment, ShiftDemand, ShiftBand, Schedule)
_VOS_DATACLASS = (TimeRange, DayCutoff, OperationalCalendar, SchedulePeriod, DemandQuantity)


@pytest.mark.parametrize("entidade", _ENTIDADES, ids=lambda c: c.__name__)
def test_entidades_sao_frozen_e_comparam_por_id(entidade: type) -> None:
    parametros = entidade.__dataclass_params__  # type: ignore[attr-defined]
    assert parametros.frozen is True
    assert parametros.eq is False
    assert "__eq__" in vars(entidade)
    assert "__hash__" in vars(entidade)


@pytest.mark.parametrize("vo", _VOS_DATACLASS, ids=lambda c: c.__name__)
def test_vos_sao_frozen_e_comparam_por_valor(vo: type) -> None:
    parametros = vo.__dataclass_params__  # type: ignore[attr-defined]
    assert parametros.frozen is True
    assert parametros.eq is True


def test_weekday_e_enum_de_valor() -> None:
    # O sexto VO não é dataclass: StrEnum compara por valor por construção.
    assert Weekday.from_string("monday") is Weekday.MONDAY


def test_escala_e_frozen() -> None:
    with pytest.raises(dataclasses.FrozenInstanceError):
        _escala().version = 2  # type: ignore[misc]


def test_escala_compara_por_id() -> None:
    a = _escala()
    b = dataclasses.replace(_escala_de_duas_faixas(), version=9)
    assert a == b
    assert hash(a) == hash(b)
    assert a != dataclasses.replace(a, id=ScheduleId("escala-2"))
    assert a.__eq__("escala-1") is NotImplemented


# --- CA16 (fecha): o sítio de horas é único na superfície pública ---------------------

# Todo membro público das 4 entidades que devolve `int`, com o que o número é.
# Cobrado contra as classes por introspecção: um `worked_minutes` novo em
# qualquer delas reprova aqui.
_MEMBROS_INTEIROS = {
    (Schedule, "worked_minutes_of"): "minutos trabalhados",
    (Schedule, "effective_break_minutes_of"): "minutos de intervalo",
    (ShiftBand, "effective_break_of"): "minutos de intervalo",
    (ShiftBand, "assignment_count"): "contagem",
    (ShiftDemand, "allocated"): "contagem",
}


def test_so_worked_minutes_of_devolve_minutos_trabalhados() -> None:
    inteiros = {
        (entidade, nome)
        for entidade in _ENTIDADES
        for nome, membro in vars(entidade).items()
        if not nome.startswith("_")
        and (callable(membro) or isinstance(membro, property))
        and _retorno(membro) is int
    }
    assert inteiros == set(_MEMBROS_INTEIROS)
    trabalhados = [
        chave for chave, rotulo in _MEMBROS_INTEIROS.items() if rotulo == "minutos trabalhados"
    ]
    assert trabalhados == [(Schedule, "worked_minutes_of")]
