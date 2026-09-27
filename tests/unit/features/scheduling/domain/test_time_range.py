"""Testes do VO TimeRange (value_objects/time_range.py) — CA1, CA2, CA3.

Um cenário inválido **por teste**: nenhum objeto recusado viola duas invariantes
ao mesmo tempo, para não fixar precedência entre validações coincidentes
(finding da 2.1, technical §5).
"""

from datetime import UTC, datetime, timedelta

import pytest

from restaurant_hub.features.scheduling.domain.exceptions.errors import (
    InvalidTimeRangeError,
)
from restaurant_hub.features.scheduling.domain.value_objects.time_range import TimeRange

pytestmark = pytest.mark.unit

# Quarta-feira, 2026-09-30 — um dia qualquer; as datas vivem dentro do valor.
_DIA = datetime(2026, 9, 30)


def _em(hora: int, minuto: int = 0, dias: int = 0) -> datetime:
    """Instante ingênuo de minuto inteiro, `dias` depois de `_DIA`."""
    return _DIA + timedelta(days=dias, hours=hora, minutes=minuto)


def _faixa(inicio: int, fim: int, break_minutes: int = 0) -> TimeRange:
    """Faixa de horas cheias no mesmo dia (ou no seguinte, se `fim` passar de 24)."""
    return TimeRange(start=_em(inicio), end=_em(fim), break_minutes=break_minutes)


# --- CA1: os 6 defeitos, um por teste -------------------------------------------------


def test_start_tz_aware_e_recusado() -> None:
    with pytest.raises(InvalidTimeRangeError, match="ingênuos"):
        TimeRange(start=_em(8).replace(tzinfo=UTC), end=_em(12))


def test_end_tz_aware_e_recusado() -> None:
    with pytest.raises(InvalidTimeRangeError, match="ingênuos"):
        TimeRange(start=_em(8), end=_em(12).replace(tzinfo=UTC))


@pytest.mark.parametrize(
    ("start", "end"),
    [
        pytest.param(_em(8).replace(second=1), _em(12), id="segundo_no_start"),
        pytest.param(_em(8).replace(microsecond=1), _em(12), id="microssegundo_no_start"),
        pytest.param(_em(8), _em(12).replace(second=59), id="segundo_no_end"),
        pytest.param(_em(8), _em(12).replace(microsecond=1), id="microssegundo_no_end"),
    ],
)
def test_instante_sem_minuto_inteiro_e_recusado(start: datetime, end: datetime) -> None:
    with pytest.raises(InvalidTimeRangeError, match="minuto inteiro"):
        TimeRange(start=start, end=end)


def test_start_igual_ao_end_e_recusado() -> None:
    with pytest.raises(InvalidTimeRangeError, match="início deve anteceder o fim"):
        _faixa(8, 8)


def test_start_depois_do_end_e_recusado() -> None:
    with pytest.raises(InvalidTimeRangeError, match="início deve anteceder o fim"):
        _faixa(12, 8)


def test_duracao_de_24h_e_um_minuto_e_recusada() -> None:
    # Borda exata do `<=`: um minuto além das 24h reprova.
    with pytest.raises(InvalidTimeRangeError, match="24h"):
        TimeRange(start=_em(8), end=_em(8, minuto=1, dias=1))


# --- CA1: a lista fechada de aceites-limite -------------------------------------------


def test_duracao_de_24h_exatas_e_aceita() -> None:
    faixa = TimeRange(start=_em(8), end=_em(8, dias=1))
    assert faixa.nominal_minutes == 24 * 60


def test_faixa_que_cruza_a_meia_noite_civil_e_aceita() -> None:
    faixa = _faixa(16, 24)  # 16:00 de quarta a 00:00 de quinta
    assert faixa.end == datetime(2026, 10, 1, 0, 0)
    assert faixa.nominal_minutes == 8 * 60


def test_faixa_que_cruza_o_corte_e_aceita() -> None:
    # 22:00 de quarta a 06:00 de quinta atravessa o corte default das 05:00; o
    # TimeRange não conhece o corte e não trata o caso (ADR 4.1.0008).
    faixa = _faixa(22, 30)
    assert faixa.nominal_minutes == 8 * 60


# --- CA2: o intervalo declarado da faixa ----------------------------------------------


def test_intervalo_negativo_e_recusado() -> None:
    with pytest.raises(InvalidTimeRangeError, match="negativo"):
        _faixa(8, 12, break_minutes=-1)


def test_intervalo_igual_a_duracao_nominal_e_recusado() -> None:
    # Alocação de zero horas não é trabalho (doc §3.2): borda exata do `<`.
    with pytest.raises(InvalidTimeRangeError, match="menor que a duração nominal"):
        _faixa(8, 12, break_minutes=240)


@pytest.mark.parametrize(
    ("break_minutes", "trabalhados"),
    [
        pytest.param(0, 240, id="zero"),
        pytest.param(60, 180, id="uma_hora"),
        pytest.param(239, 1, id="nominal_menos_um"),
    ],
)
def test_intervalos_aceitos_descontam_em_worked_minutes(
    break_minutes: int, trabalhados: int
) -> None:
    faixa = _faixa(8, 12, break_minutes=break_minutes)
    assert faixa.break_minutes == break_minutes
    assert faixa.worked_minutes() == faixa.nominal_minutes - break_minutes
    assert faixa.worked_minutes() == trabalhados


def test_intervalo_default_e_zero() -> None:
    faixa = TimeRange(start=_em(8), end=_em(12))
    assert faixa.break_minutes == 0
    assert faixa.worked_minutes() == 4 * 60


@pytest.mark.parametrize("intervalo_efetivo", [0, 30, 60, 479])
def test_worked_minutes_com_intervalo_explicito_desconta_o_argumento(
    intervalo_efetivo: int,
) -> None:
    # Faixa com 1h de intervalo; a alocação declara o seu (ADR 4.1.0011). O
    # argumento substitui o da faixa — inclusive o 0, que não é "ausente".
    faixa = _faixa(16, 24, break_minutes=60)
    assert faixa.worked_minutes(intervalo_efetivo) == 480 - intervalo_efetivo


def test_worked_minutes_com_none_usa_o_intervalo_da_faixa() -> None:
    faixa = _faixa(16, 24, break_minutes=60)
    assert faixa.worked_minutes(None) == 8 * 60 - 60


def test_contagem_e_em_minutos_inteiros() -> None:
    vinte = 20
    faixa = TimeRange(start=_em(8), end=_em(8, minuto=vinte), break_minutes=0)
    assert faixa.nominal_minutes == vinte
    assert type(faixa.nominal_minutes) is int
    assert type(faixa.worked_minutes()) is int


# --- CA3: tabela-verdade semi-aberta de overlaps --------------------------------------


@pytest.mark.parametrize(
    ("a", "b", "esperado"),
    [
        pytest.param(_faixa(8, 12), _faixa(10, 14), True, id="parcial"),
        pytest.param(_faixa(8, 16), _faixa(10, 12), True, id="contencao_total"),
        pytest.param(_faixa(8, 12), _faixa(8, 12), True, id="identidade"),
        pytest.param(_faixa(8, 12), _faixa(12, 14), False, id="adjacentes_nao_sobrepoem"),
        pytest.param(_faixa(8, 10), _faixa(12, 14), False, id="disjuntas"),
        pytest.param(_faixa(22, 30), _faixa(25, 27), True, id="cruza_meia_noite_sobrepoe"),
        pytest.param(_faixa(16, 24), _faixa(24, 30), False, id="cruza_meia_noite_adjacente"),
    ],
)
def test_tabela_verdade_do_overlaps_e_simetrica(a: TimeRange, b: TimeRange, esperado: bool) -> None:
    assert a.overlaps(b) is esperado
    assert b.overlaps(a) is esperado


def test_overlaps_ignora_o_intervalo_declarado() -> None:
    assert _faixa(8, 12, break_minutes=30).overlaps(_faixa(11, 14)) is True


# --- hours_key, construtores derivados e igualdade por valor --------------------------


def test_hours_key_e_o_par_sem_o_intervalo() -> None:
    faixa = _faixa(8, 12, break_minutes=30)
    assert faixa.hours_key == (_em(8), _em(12))


def test_mesmo_par_com_intervalos_diferentes_tem_hours_key_igual_e_valor_diferente() -> None:
    # É exatamente a chave de duplicidade que a raiz usará (ADR 4.1.0011).
    com_pausa = _faixa(8, 12, break_minutes=30)
    sem_pausa = _faixa(8, 12)
    assert com_pausa.hours_key == sem_pausa.hours_key
    assert com_pausa != sem_pausa


def test_igualdade_e_hash_por_valor() -> None:
    assert _faixa(8, 12, break_minutes=30) == _faixa(8, 12, break_minutes=30)
    assert hash(_faixa(8, 12, break_minutes=30)) == hash(_faixa(8, 12, break_minutes=30))
    assert _faixa(8, 12) != _faixa(8, 13)


def test_with_bounds_preserva_o_intervalo() -> None:
    original = _faixa(8, 12, break_minutes=30)
    reagendada = original.with_bounds(_em(9), _em(14))
    assert reagendada == TimeRange(start=_em(9), end=_em(14), break_minutes=30)
    assert original == _faixa(8, 12, break_minutes=30)


def test_with_bounds_revalida_e_recusa_encurtar_abaixo_do_intervalo() -> None:
    # Reagendar não muda o intervalo; se a nova faixa não comporta o intervalo,
    # a própria invariante recusa (concept §5.6).
    original = _faixa(8, 12, break_minutes=60)
    with pytest.raises(InvalidTimeRangeError, match="menor que a duração nominal"):
        original.with_bounds(_em(8), _em(9))


def test_with_break_troca_o_intervalo_e_mantem_o_par() -> None:
    original = _faixa(8, 12, break_minutes=30)
    redeclarada = original.with_break(45)
    assert redeclarada == _faixa(8, 12, break_minutes=45)
    assert redeclarada.hours_key == original.hours_key
    assert original == _faixa(8, 12, break_minutes=30)


def test_with_break_revalida() -> None:
    with pytest.raises(InvalidTimeRangeError, match="negativo"):
        _faixa(8, 12).with_break(-1)
