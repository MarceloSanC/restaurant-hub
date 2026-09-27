"""Testes do calendário operacional (value_objects/operational_calendar.py).

`Weekday` (CA6), `DayCutoff` (CA4, lado das recusas de CA7, lado do VO de CA5).
"""

from datetime import UTC, date, datetime, time, timedelta

import pytest

from restaurant_hub.features.scheduling.domain.exceptions.errors import (
    InvalidDayCutoffError,
    InvalidWeekdayError,
)
from restaurant_hub.features.scheduling.domain.value_objects.operational_calendar import (
    DayCutoff,
    Weekday,
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
