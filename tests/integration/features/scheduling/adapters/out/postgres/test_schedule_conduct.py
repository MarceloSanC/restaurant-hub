"""Conduta do repositório de escala sob concorrência — CA07 e CA11.

**CA07 — intercalação determinística, não sorte de agendamento.** O escritor A roda numa
thread e é **parado** por um gancho de evento do SQLAlchemy logo depois de escrever a raiz,
antes do commit. Só então o escritor B parte, e o teste consulta `pg_locks` até ver B
**esperando** (lock não concedido) — o `advisory` da unidade, ou, em unidades diferentes, o
`transactionid` da checagem de unicidade. Aí A é liberado. Tudo com tempo-limite: se B não
aparecer esperando, o teste **falha** em vez de travar.

**CA11 — snapshot único nas três leituras.** Um gancho dispara, exatamente uma vez, um `save`
comitado por outra conexão **entre** o `SELECT` da raiz e o das filhas. A leitura em curso
tem de devolver o estado anterior inteiro (a versão e as faixas do mesmo estado); a
seguinte, o novo.
"""

import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, date, datetime, time, timedelta

import pytest
from sqlalchemy import Engine, event, text
from sqlalchemy.exc import IntegrityError

from restaurant_hub.features.scheduling.adapters.out.postgres.schedule_repository import (
    PostgresScheduleRepository,
)
from restaurant_hub.features.scheduling.adapters.out.postgres.tables import schedules
from restaurant_hub.features.scheduling.application.errors import (
    IdentifierInUseError,
    SchedulePeriodTakenError,
    ScheduleVersionConflictError,
)
from restaurant_hub.features.scheduling.application.ports.out.schedule_repository import (
    ScheduleChange,
)
from restaurant_hub.features.scheduling.domain.entities.schedule import Schedule
from restaurant_hub.features.scheduling.domain.value_objects.identifiers import (
    ScheduleId,
    ShiftBandId,
    TenantId,
    UnitId,
)
from restaurant_hub.features.scheduling.domain.value_objects.operational_calendar import (
    OperationalCalendar,
)
from restaurant_hub.features.scheduling.domain.value_objects.schedule_period import (
    SchedulePeriod,
)
from restaurant_hub.features.scheduling.domain.value_objects.time_range import TimeRange
from tests.contract.features.scheduling.support import NO_NEIGHBOURS, project, read_trail

pytestmark = [pytest.mark.integration]

_T = TenantId("t1")
_U1, _U2 = UnitId("u1"), UnitId("u2")
_SEG = date(2026, 11, 2)
_QUANDO = datetime(2026, 11, 1, 12, 0, tzinfo=UTC)
_PRAZO = 15.0  # segundos — generoso para o runner, e a falha é explícita


def _escala(sid: str, first_day: date = _SEG, unit: UnitId = _U1) -> Schedule:
    return Schedule(
        id=ScheduleId(sid),
        tenant_id=_T,
        unit_id=unit,
        period=SchedulePeriod(first_day=first_day),
        calendar=OperationalCalendar.default(),
    )


def _faixa(dia: date, hora: int) -> TimeRange:
    inicio = datetime.combine(dia, time(hora))
    return TimeRange(start=inicio, end=inicio + timedelta(hours=4))


def _mudanca(previous: int | None) -> ScheduleChange:
    return ScheduleChange(
        author_user_id="user-ger",
        occurred_at=_QUANDO,
        previous_version=previous,
        operations=(),
        acknowledged=(),
    )


@pytest.fixture
def repo(banco_limpo: Engine) -> PostgresScheduleRepository:
    return PostgresScheduleRepository(banco_limpo)


# ---------------------------------------------------------------------------
# CA07 — dois escritores, intercalados de forma determinística
# ---------------------------------------------------------------------------


class _Escritor(threading.Thread):
    """Roda uma escrita e guarda o resultado (a exceção, ou `None`)."""

    def __init__(self, nome: str, escrita: Callable[[], None]) -> None:
        super().__init__(name=nome, daemon=True)
        self._escrita = escrita
        self.erro: BaseException | None = None
        self.terminou = False

    def run(self) -> None:
        try:
            self._escrita()
        except BaseException as erro:  # devolvido ao teste, que o assere
            self.erro = erro
        finally:
            self.terminou = True


_NOME_DE_A = "escritor-A"


@contextmanager
def _pausa_depois_de(
    engine: Engine, prefixo: str
) -> Iterator[tuple[threading.Event, threading.Event]]:
    """Para a thread de A logo depois do primeiro statement dela que começa com `prefixo`.

    A thread é reconhecida pelo nome, fixado antes de ela partir: nenhum statement de A
    escapa do gancho por corrida entre o `start` e a marcação.
    """
    parado, liberar = threading.Event(), threading.Event()

    def depois(*args: object) -> None:
        if threading.current_thread().name != _NOME_DE_A or parado.is_set():
            return
        if " ".join(str(args[2]).split()).startswith(prefixo):
            parado.set()
            liberar.wait(_PRAZO)

    event.listen(engine, "after_cursor_execute", depois)
    try:
        yield parado, liberar
    finally:
        liberar.set()
        event.remove(engine, "after_cursor_execute", depois)


def _espera_lock_nao_concedido(engine: Engine, tipo: str, b: _Escritor) -> None:
    """Consulta `pg_locks` até aparecer um lock `tipo` não concedido — B esperando."""
    limite = datetime.now(UTC) + timedelta(seconds=_PRAZO)
    while datetime.now(UTC) < limite:
        assert not b.terminou, f"B terminou sem esperar o lock {tipo}: {b.erro!r}"
        with engine.connect() as conexao:
            esperando = conexao.execute(
                text("SELECT count(*) FROM pg_locks WHERE NOT granted AND locktype = :tipo"),
                {"tipo": tipo},
            ).scalar_one()
        if esperando:
            return
        threading.Event().wait(0.05)
    pytest.fail(f"B não apareceu esperando um lock {tipo} em {_PRAZO}s")


def _intercalar(
    engine: Engine,
    prefixo_de_a: str,
    escrita_a: Callable[[], None],
    escrita_b: Callable[[], None],
    lock_de_b: str,
) -> tuple[_Escritor, _Escritor]:
    """A escreve a raiz e para; B parte e é visto esperando; A é liberado; os dois terminam."""
    with _pausa_depois_de(engine, prefixo_de_a) as (parado, liberar):
        a = _Escritor(_NOME_DE_A, escrita_a)
        a.start()
        assert parado.wait(_PRAZO), f"A não chegou a {prefixo_de_a!r}: {a.erro!r}"
        b = _Escritor("escritor-B", escrita_b)
        b.start()
        try:
            _espera_lock_nao_concedido(engine, lock_de_b, b)
        finally:
            liberar.set()
        a.join(_PRAZO)
        b.join(_PRAZO)
    assert not a.is_alive() and not b.is_alive(), "escritor travado"
    return a, b


def test_dois_saves_sobre_a_mesma_versao_b_recebe_conflito(
    repo: PostgresScheduleRepository, banco_limpo: Engine
) -> None:
    v1 = _escala("s1")
    repo.add(v1, _mudanca(None))
    a, b = _intercalar(
        banco_limpo,
        "UPDATE schedules",
        lambda: repo.save(
            v1.enable_band(ShiftBandId("fa"), _faixa(_SEG, 10)), 1, NO_NEIGHBOURS, _mudanca(1)
        ),
        lambda: repo.save(
            v1.enable_band(ShiftBandId("fb"), _faixa(_SEG, 15)), 1, NO_NEIGHBOURS, _mudanca(1)
        ),
        "advisory",
    )
    assert a.erro is None
    assert isinstance(b.erro, ScheduleVersionConflictError)
    assert b.erro.current_version == 2  # noqa: PLR2004
    assert len(read_trail(banco_limpo, "s1")) == 2  # noqa: PLR2004
    lida = repo.find_by_id(_T, _U1, ScheduleId("s1"))
    assert lida is not None
    assert [faixa.id for faixa in lida.bands] == ["fa"]


def test_dois_adds_de_periodos_que_se_cruzam_b_recebe_periodo_tomado(
    repo: PostgresScheduleRepository, banco_limpo: Engine
) -> None:
    a, b = _intercalar(
        banco_limpo,
        "INSERT INTO schedules",
        lambda: repo.add(_escala("s1"), _mudanca(None)),
        lambda: repo.add(_escala("s2"), _mudanca(None)),
        "advisory",
    )
    assert a.erro is None
    assert isinstance(b.erro, SchedulePeriodTakenError)
    assert repo.find_by_id(_T, _U1, ScheduleId("s2")) is None


def test_dois_saves_com_o_mesmo_id_interno_novo_b_recebe_id_em_uso(
    repo: PostgresScheduleRepository, banco_limpo: Engine
) -> None:
    # Duas semanas de distância: não são vizinhas, e a recusa é a do id, não a de L-SC9.
    s1, s2 = _escala("s1"), _escala("s2", _SEG + timedelta(days=14))
    repo.add(s1, _mudanca(None))
    repo.add(s2, _mudanca(None))
    a, b = _intercalar(
        banco_limpo,
        "UPDATE schedules",
        lambda: repo.save(
            s1.enable_band(ShiftBandId("fx"), _faixa(_SEG, 10)), 1, NO_NEIGHBOURS, _mudanca(1)
        ),
        lambda: repo.save(
            s2.enable_band(ShiftBandId("fx"), _faixa(s2.period.first_day, 10)),
            1,
            NO_NEIGHBOURS,
            _mudanca(1),
        ),
        "advisory",
    )
    assert a.erro is None
    assert isinstance(b.erro, IdentifierInUseError)
    assert (b.erro.id_type, b.erro.value) == ("ShiftBandId", "fx")


def test_em_unidades_diferentes_o_mesmo_id_de_escala_cai_na_pk_traduzida(
    repo: PostgresScheduleRepository, banco_limpo: Engine
) -> None:
    """Locks de unidade distintos: B passa pela checagem e espera a unicidade de A."""
    a, b = _intercalar(
        banco_limpo,
        "INSERT INTO schedules",
        lambda: repo.add(_escala("s1", unit=_U1), _mudanca(None)),
        lambda: repo.add(_escala("s1", unit=_U2), _mudanca(None)),
        "transactionid",
    )
    assert a.erro is None
    assert isinstance(b.erro, IdentifierInUseError)
    assert (b.erro.id_type, b.erro.value) == ("ScheduleId", "s1")
    assert repo.find_by_id(_T, _U2, ScheduleId("s1")) is None


# ---------------------------------------------------------------------------
# CA11 — snapshot único nas três leituras
# ---------------------------------------------------------------------------


@contextmanager
def _save_entre_raiz_e_filhas(engine: Engine, escrita: Callable[[], None]) -> Iterator[list[str]]:
    """Antes do primeiro `SELECT … FROM schedule_bands` da leitura, comita `escrita` uma vez.

    Devolve os statements da leitura vistos pelo gancho, para asserir a posição do disparo.
    """
    disparos: list[str] = []
    vistos: list[str] = []

    def antes(*args: object) -> None:
        statement = " ".join(str(args[2]).split())
        if disparos:
            return
        vistos.append(statement)
        if statement.startswith("SELECT") and "FROM schedule_bands" in statement:
            disparos.append(statement)
            escrita()

    event.listen(engine, "before_cursor_execute", antes)
    try:
        yield vistos
    finally:
        event.remove(engine, "before_cursor_execute", antes)
    assert len(disparos) == 1, "o save concorrente não disparou"


_LEITURAS: dict[str, Callable[[PostgresScheduleRepository], Schedule]] = {
    "find_by_id": lambda repo: _unica(repo.find_by_id(_T, _U1, ScheduleId("s1"))),
    "list_in_range": lambda repo: _unica(*repo.list_in_range(_T, _U1, _SEG, _SEG)),
    "list_ending_before": lambda repo: _unica(
        *repo.list_ending_before(_T, _U1, _SEG + timedelta(days=7), 5)
    ),
}


def _unica(*escalas: Schedule | None) -> Schedule:
    assert len(escalas) == 1 and escalas[0] is not None, escalas
    return escalas[0]


@pytest.mark.parametrize("leitura", _LEITURAS)
def test_save_concorrente_entre_raiz_e_filhas_nao_rasga_o_agregado(
    repo: PostgresScheduleRepository, banco_limpo: Engine, leitura: str
) -> None:
    v1 = _escala("s1").enable_band(ShiftBandId("f1"), _faixa(_SEG, 10))
    repo.add(v1, _mudanca(None))
    v2 = v1.disable_band(ShiftBandId("f1")).enable_band(ShiftBandId("f2"), _faixa(_SEG, 15))
    ler = _LEITURAS[leitura]

    with _save_entre_raiz_e_filhas(
        banco_limpo, lambda: repo.save(v2, v1.version, NO_NEIGHBOURS, _mudanca(v1.version))
    ) as vistos:
        durante = ler(repo)

    # O disparo veio depois da raiz: a leitura já tinha lido `schedules` naquela transação.
    assert any("FROM schedules" in statement for statement in vistos[:-1]), vistos
    assert project(durante) == project(v1)
    assert project(ler(repo)) == project(v2)


def test_escritor_que_contorna_o_lock_faz_o_add_cair_na_exclusion_traduzida(
    repo: PostgresScheduleRepository, banco_limpo: Engine
) -> None:
    """A garantia do banco contra quem não toma o lock, e a sua tradução no `add` (§6).

    Uma conexão grava, por fora do adapter e sem o lock da unidade, uma escala que cobre os
    mesmos dias, e não comita. O `add` passa pelas checagens (não enxerga a linha não
    comitada), espera a exclusion constraint resolver (`transactionid`) e, quando a outra
    comita, cai em `ex_schedules_unit_days_disjoint` — traduzida para
    `SchedulePeriodTakenError`, com o `IntegrityError` preservado como causa.
    """
    with banco_limpo.connect() as intrusa:
        intrusa.execute(
            schedules.insert().values(
                id="s9",
                tenant_id=_T,
                unit_id=_U1,
                first_day=_SEG,
                days=7,
                week_start="monday",
                day_cutoff=time(5),
                version=1,
            )
        )
        b = _Escritor("escritor-B", lambda: repo.add(_escala("s1"), _mudanca(None)))
        b.start()
        try:
            _espera_lock_nao_concedido(banco_limpo, "transactionid", b)
        finally:
            intrusa.commit()
        b.join(_PRAZO)
    assert not b.is_alive(), "escritor travado"
    assert isinstance(b.erro, SchedulePeriodTakenError)
    assert isinstance(b.erro.__cause__, IntegrityError)
    assert repo.find_by_id(_T, _U1, ScheduleId("s1")) is None
