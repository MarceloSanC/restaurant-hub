"""Testes do calendário operacional (value_objects/operational_calendar.py).

`Weekday` (CA6), `DayCutoff` (CA4, recusas de CA7, lado do VO de CA5) e
`OperationalCalendar` (lado positivo de CA7 e o gate de sítio único; o lado
"desalinhado" de CA8; `is_aligned` nos dois sentidos).
"""

import inspect
import re
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path

import pytest

from restaurant_hub.features import scheduling
from restaurant_hub.features.scheduling.domain.exceptions.errors import (
    InvalidDayCutoffError,
    InvalidSchedulePeriodError,
    InvalidWeekdayError,
)
from restaurant_hub.features.scheduling.domain.value_objects import operational_calendar
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

# Segunda-feira, 2026-09-28 — ancora os 7 dias da semana seguinte.
_SEGUNDA = date(2026, 9, 28)
_QUINTA = date(2026, 10, 1)
_SEXTA = date(2026, 10, 2)

# O conjunto fechado, nomes **e** valores (CA6).
_DIAS_ESPERADOS = {
    "MONDAY": "monday",
    "TUESDAY": "tuesday",
    "WEDNESDAY": "wednesday",
    "THURSDAY": "thursday",
    "FRIDAY": "friday",
    "SATURDAY": "saturday",
    "SUNDAY": "sunday",
}


# --- CA6: Weekday ---------------------------------------------------------------------


def test_weekday_e_exatamente_os_sete_nomes_e_valores() -> None:
    assert {dia.name: dia.value for dia in Weekday} == _DIAS_ESPERADOS
    assert len(Weekday) == len(_DIAS_ESPERADOS)


@pytest.mark.parametrize("deslocamento", range(7))
def test_from_date_bate_com_isoweekday_nos_sete_dias(deslocamento: int) -> None:
    dia = _SEGUNDA + timedelta(days=deslocamento)
    assert tuple(Weekday).index(Weekday.from_date(dia)) + 1 == dia.isoweekday()


def test_from_date_nomeia_o_dia_certo() -> None:
    # Ancoragem por nome, para que uma permutação dos membros não passe no teste
    # de isoweekday acima só por coincidência de índice.
    assert Weekday.from_date(_SEGUNDA) is Weekday.MONDAY
    assert Weekday.from_date(_SEXTA) is Weekday.FRIDAY
    assert Weekday.from_date(_SEGUNDA + timedelta(days=6)) is Weekday.SUNDAY


@pytest.mark.parametrize("valor", list(_DIAS_ESPERADOS.values()))
def test_from_string_aceita_os_sete_valores(valor: str) -> None:
    assert Weekday.from_string(valor).value == valor


@pytest.mark.parametrize("valor", ["", "segunda", "Monday", "MONDAY", " monday", "mon"])
def test_from_string_fora_do_conjunto_levanta_erro_de_dominio(valor: str) -> None:
    with pytest.raises(InvalidWeekdayError) as exc_info:
        Weekday.from_string(valor)
    # A causa original do StrEnum é preservada para depuração.
    assert isinstance(exc_info.value.__cause__, ValueError)


# --- CA7 (recusas): DayCutoff ---------------------------------------------------------


def test_corte_tz_aware_e_recusado() -> None:
    with pytest.raises(InvalidDayCutoffError, match="ingênuo"):
        DayCutoff(at=time(5, 0, tzinfo=UTC))


@pytest.mark.parametrize(
    "at",
    [
        pytest.param(time(5, 0, 1), id="segundo"),
        pytest.param(time(5, 0, 0, 1), id="microssegundo"),
    ],
)
def test_corte_sem_minuto_inteiro_e_recusado(at: time) -> None:
    with pytest.raises(InvalidDayCutoffError, match="minuto inteiro"):
        DayCutoff(at=at)


@pytest.mark.parametrize("at", [time(0, 0), time(5, 0), time(14, 30), time(23, 59)])
def test_corte_nao_tem_teto(at: time) -> None:
    # Q5 do sponsor (2026-09-27): corte tardio é configuração, não defeito.
    assert DayCutoff(at=at).at == at


def test_corte_compara_por_valor() -> None:
    assert DayCutoff(at=time(5, 0)) == DayCutoff(at=time(5, 0))
    assert hash(DayCutoff(at=time(5, 0))) == hash(DayCutoff(at=time(5, 0)))
    assert DayCutoff(at=time(5, 0)) != DayCutoff(at=time(6, 0))


# --- CA4: dia operacional -------------------------------------------------------------


@pytest.mark.parametrize(
    ("instante", "esperado"),
    [
        pytest.param(datetime(2026, 10, 2, 4, 59), _QUINTA, id="antes_do_corte_dia_anterior"),
        pytest.param(datetime(2026, 10, 2, 5, 0), _SEXTA, id="exatamente_no_corte_mesmo_dia"),
        pytest.param(datetime(2026, 10, 2, 5, 1), _SEXTA, id="depois_do_corte_mesmo_dia"),
        pytest.param(datetime(2026, 10, 2, 0, 0), _QUINTA, id="meia_noite_civil_dia_anterior"),
        pytest.param(datetime(2026, 10, 2, 23, 59), _SEXTA, id="fim_do_dia_civil"),
    ],
)
def test_corte_das_cinco(instante: datetime, esperado: date) -> None:
    assert DayCutoff(at=time(5, 0)).operational_day_of(instante) == esperado


@pytest.mark.parametrize(
    "instante",
    [datetime(2026, 10, 2, 0, 0), datetime(2026, 10, 2, 4, 59), datetime(2026, 10, 2, 23, 59)],
)
def test_corte_meia_noite_coincide_com_o_dia_civil(instante: datetime) -> None:
    assert DayCutoff(at=time(0, 0)).operational_day_of(instante) == instante.date()


def test_corte_tardio_poe_o_jantar_de_sexta_na_quinta() -> None:
    # O caso que reprova a implementação ingênua "sempre o dia civil" (CA4).
    jantar = datetime(2026, 10, 2, 22, 0)
    assert Weekday.from_date(jantar.date()) is Weekday.FRIDAY
    dia = DayCutoff(at=time(23, 0)).operational_day_of(jantar)
    assert dia == _QUINTA
    assert Weekday.from_date(dia) is Weekday.THURSDAY


def test_corte_tardio_exatamente_no_corte_e_do_mesmo_dia() -> None:
    assert DayCutoff(at=time(23, 0)).operational_day_of(datetime(2026, 10, 2, 23, 0)) == _SEXTA


# --- CA5 (lado do VO): faixa que ultrapassa o corte seguinte --------------------------


def test_faixa_que_ultrapassa_o_corte_seguinte_e_do_dia_do_start() -> None:
    # 22:00 de quinta a 06:00 de sexta, corte 05:00: o fim cai depois do corte de
    # sexta, e mesmo assim a faixa é da quinta (ADR 4.1.0008).
    faixa = TimeRange(start=datetime(2026, 10, 1, 22, 0), end=datetime(2026, 10, 2, 6, 0))
    corte = DayCutoff(at=time(5, 0))
    assert corte.operational_day_of(faixa.start) == _QUINTA
    assert corte.operational_day_of(faixa.end) == _SEXTA


# --- CA7 (lado positivo) e o gate de sítio único dos defaults -------------------------


def test_default_e_segunda_com_corte_as_cinco() -> None:
    calendario = OperationalCalendar.default()
    assert calendario.week_start is Weekday.MONDAY
    assert calendario.day_cutoff == DayCutoff(at=time(5, 0))


def test_calendario_compara_por_valor() -> None:
    assert OperationalCalendar.default() == OperationalCalendar(
        week_start=Weekday.MONDAY, day_cutoff=DayCutoff(at=time(5, 0))
    )
    assert OperationalCalendar.default() != OperationalCalendar(
        week_start=Weekday.SUNDAY, day_cutoff=DayCutoff(at=time(5, 0))
    )


def test_campos_do_calendario_nao_tem_default() -> None:
    # Default de campo viraria regra silenciosa (concept §7): construir sem os
    # dois campos tem de falhar.
    with pytest.raises(TypeError):
        OperationalCalendar()  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        DayCutoff()  # type: ignore[call-arg]


# O comando literal de CA7 (concept §11), traduzido para varredura permanente:
# `rg -n --glob 'src/restaurant_hub/features/scheduling/**/*.py'
#    -e 'time\(\s*5\s*,\s*0' -e '"05:00"' -e 'Weekday\.MONDAY'`
_PADROES_DOS_DEFAULTS = (r"time\(\s*5\s*,\s*0", r'"05:00"', r"Weekday\.MONDAY")


def _ocorrencias_dos_defaults_no_bc() -> set[tuple[Path, int]]:
    raiz = Path(next(iter(scheduling.__path__)))
    padrao = re.compile("|".join(_PADROES_DOS_DEFAULTS))
    return {
        (arquivo.resolve(), numero)
        for arquivo in raiz.rglob("*.py")
        for numero, linha in enumerate(arquivo.read_text(encoding="utf-8").splitlines(), 1)
        if padrao.search(linha)
    }


def test_defaults_aparecem_so_em_operational_calendar_default() -> None:
    linhas, inicio = inspect.getsourcelines(OperationalCalendar.default)
    arquivo = Path(inspect.getfile(operational_calendar)).resolve()
    linhas_do_default = {(arquivo, inicio + i) for i in range(len(linhas))}
    ocorrencias = _ocorrencias_dos_defaults_no_bc()
    # Anti-vácuo: a varredura acha o próprio default; sem isto um padrão quebrado
    # passaria com zero ocorrências.
    assert ocorrencias
    assert ocorrencias <= linhas_do_default


# --- operational_day_of delega ao corte ----------------------------------------------


@pytest.mark.parametrize(
    "instante",
    [datetime(2026, 10, 2, 4, 59), datetime(2026, 10, 2, 5, 0), datetime(2026, 10, 2, 22, 0)],
)
@pytest.mark.parametrize("corte", [time(0, 0), time(5, 0), time(23, 0)])
def test_operational_day_of_do_calendario_e_o_do_corte(instante: datetime, corte: time) -> None:
    calendario = OperationalCalendar(week_start=Weekday.MONDAY, day_cutoff=DayCutoff(at=corte))
    assert calendario.operational_day_of(instante) == DayCutoff(at=corte).operational_day_of(
        instante
    )


# --- period_starting_on e is_aligned (CA8, lado do calendário) -----------------------


def test_period_starting_on_no_week_start_produz_sete_dias() -> None:
    periodo = OperationalCalendar.default().period_starting_on(_SEGUNDA)
    assert periodo == SchedulePeriod(first_day=_SEGUNDA, days=7)


def test_period_starting_on_repassa_a_contagem() -> None:
    periodo = OperationalCalendar.default().period_starting_on(_SEGUNDA, days=14)
    assert periodo == SchedulePeriod(first_day=_SEGUNDA, days=14)


@pytest.mark.parametrize("deslocamento", range(1, 7))
def test_period_starting_on_fora_do_week_start_e_recusado(deslocamento: int) -> None:
    with pytest.raises(InvalidSchedulePeriodError, match="desalinhado"):
        OperationalCalendar.default().period_starting_on(_SEGUNDA + timedelta(days=deslocamento))


def test_period_starting_on_respeita_week_start_configurado() -> None:
    # Com week_start domingo, a segunda desalinha e o domingo alinha: o default
    # não está embutido na fábrica.
    domingo = _SEGUNDA - timedelta(days=1)
    calendario = OperationalCalendar(week_start=Weekday.SUNDAY, day_cutoff=DayCutoff(at=time(5, 0)))
    assert calendario.period_starting_on(domingo).first_day == domingo
    with pytest.raises(InvalidSchedulePeriodError, match="desalinhado"):
        calendario.period_starting_on(_SEGUNDA)


def test_period_starting_on_com_contagem_invalida_e_recusado_pelo_periodo() -> None:
    with pytest.raises(InvalidSchedulePeriodError, match="de 1 a 31 dias"):
        OperationalCalendar.default().period_starting_on(_SEGUNDA, days=0)


@pytest.mark.parametrize("dia_de_inicio", list(Weekday))
def test_is_aligned_nos_dois_sentidos_para_cada_week_start(dia_de_inicio: Weekday) -> None:
    calendario = OperationalCalendar(week_start=dia_de_inicio, day_cutoff=DayCutoff(at=time(5, 0)))
    semana = [_SEGUNDA + timedelta(days=i) for i in range(7)]
    alinhados = [dia for dia in semana if calendario.is_aligned(SchedulePeriod(first_day=dia))]
    assert len(alinhados) == 1
    assert Weekday.from_date(alinhados[0]) is dia_de_inicio
