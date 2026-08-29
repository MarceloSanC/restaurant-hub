"""Schemas de boundary e conversores da borda de staff — CA02(a), CA04, CA05, CA06.

**As varreduras derivam o domínio do código, e é isso que as faz crescer
sozinhas.** Nenhum `parametrize` deste arquivo lista schema, campo ou módulo à
mão: os requests saem de uma varredura do módulo por `__name__`, os campos saem
de `model_fields` — recursivamente, para alcançar também os aninhados —, e os
módulos da varredura de import saem do **pacote**. Consequência operacional: um
schema acrescentado na Task 05, ou um módulo novo em `adapters/in/http/`, entra
nestas travas sem que ninguém precise lembrar deste arquivo.
"""

import ast
import datetime
import decimal
import importlib
import pathlib
import pkgutil

import pytest
from pydantic import BaseModel, ValidationError
from pydantic import TypeAdapter as PydanticTypeAdapter

from restaurant_hub.features.staff.application.dtos.results import (
    EmployeeResult,
    JobFunctionResult,
)
from restaurant_hub.features.staff.domain.exceptions.errors import InvalidWeeklyHoursError
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

# O pacote é alcançado por `importlib` porque `in` é keyword Python (LAYOUT §8) —
# o mesmo caminho que o `composition_root` usa.
_PACOTE_HTTP_STAFF = "restaurant_hub.features.staff.adapters.in.http"

schemas = importlib.import_module(f"{_PACOTE_HTTP_STAFF}.schemas")

_PERFIL_FIXO = {"type": "fixed", "weekly_hours": "40.0"}
_PERFIL_SOB_DEMANDA = {"type": "on_demand"}


def _requests() -> list[type[BaseModel]]:
    """Todos os `*Request` do módulo, **derivados** e não listados.

    Listar seria o representante estreito de sempre: um request novo nasceria
    fora de CA02(a) e a varredura continuaria verde.
    """
    encontrados = [
        objeto
        for nome, objeto in vars(schemas).items()
        if nome.endswith("Request") and isinstance(objeto, type) and issubclass(objeto, BaseModel)
    ]
    assert encontrados, "a varredura precisa encontrar requests para ter o que negar"
    return encontrados


def _campos_recursivos(modelo: type[BaseModel], vistos: set[type[BaseModel]]) -> set[str]:
    """Nomes de campo de um modelo **e dos modelos aninhados nele**.

    A recursão não é zelo decorativo: `CreateEmployeeRequest.workload_profile` é
    uma união de dois modelos, e um `tenant_id` declarado dentro de uma das
    variantes escaparia inteiramente de uma varredura de primeiro nível — que é
    a forma mais provável de CA02(a) envelhecer.
    """
    if modelo in vistos:
        return set()
    vistos.add(modelo)

    nomes: set[str] = set()
    for nome, info in modelo.model_fields.items():
        nomes.add(nome)
        for aninhado in _modelos_em(info.annotation):
            nomes |= _campos_recursivos(aninhado, vistos)
    return nomes


def _modelos_em(anotacao: object) -> list[type[BaseModel]]:
    """Os `BaseModel` alcançáveis de uma anotação, incluindo os de união e lista."""
    if isinstance(anotacao, type) and issubclass(anotacao, BaseModel):
        return [anotacao]
    encontrados: list[type[BaseModel]] = []
    for argumento in getattr(anotacao, "__args__", ()):
        encontrados.extend(_modelos_em(argumento))
    for metadado in getattr(anotacao, "__metadata__", ()):
        encontrados.extend(_modelos_em(metadado))
    return encontrados


# ---------------------------------------------------------------------------
# CA02(a) — nenhum campo de request influencia o tenant, e nenhum vincula login
# ---------------------------------------------------------------------------

# A lista negra tem **duas** origens, e confundi-las esconderia metade da regra.
#
# Os quatro primeiros são sobre **tenant**: ele vem do token e é resolvido no
# composition root (ADR 0.0.0005), então nenhum nome pelo qual um cliente possa
# declará-lo tem lugar num corpo de staff. Os aliases entram porque a defesa é
# contra a *ideia*, não contra a grafia: um `restaurant_id` no corpo consumido
# pelo router faria o mesmo estrago que um `tenant_id`.
#
# Os dois últimos são sobre **vínculo de login**, que é `non_goal` do roadmap e
# entra no registro só na Stage 3.5. O concept §4.3 é honesto ao chamar a
# ausência de "hoje vacuamente verdadeiro": é o nome estar nesta lista que a
# converte de declaração em trava, e sem isso a célula da tabela de `non_goals`
# ficaria vazia.
_CAMPOS_PROIBIDOS_EM_REQUEST = (
    "tenant_id",
    "restaurant_id",
    "tenant",
    "restaurant",
    "user_id",
    "employee_user_id",
)


@pytest.mark.parametrize("proibido", _CAMPOS_PROIBIDOS_EM_REQUEST)
def test_ca02a_nenhum_request_declara_campo_da_lista_negra(proibido: str) -> None:
    """Varredura de `model_fields` sobre **todos** os requests, e os aninhados."""
    culpados = [
        modelo.__name__
        for modelo in _requests()
        if proibido in _campos_recursivos(modelo, vistos=set())
    ]

    assert culpados == [], f"campo proibido {proibido!r} declarado em: {culpados}"


def test_ca02a_a_varredura_alcanca_os_modelos_aninhados() -> None:
    """A varredura precisa **enxergar** o aninhado, senão a asserção acima é vácua.

    Sem esta prova, `_campos_recursivos` poderia devolver só o primeiro nível e
    CA02(a) passaria com um `tenant_id` escondido numa variante da união de
    perfil de jornada. O sujeito é o campo `type`, que só existe lá dentro.
    """
    campos = _campos_recursivos(schemas.CreateEmployeeRequest, vistos=set())

    assert "type" in campos
    assert "weekly_hours" in campos


# ---------------------------------------------------------------------------
# CA06 — o perfil de jornada é união discriminada
# ---------------------------------------------------------------------------

_PAYLOADS_DE_PERFIL_RECUSADOS = [
    pytest.param({"type": "on_demand", "weekly_hours": "40"}, id="sob-demanda-com-carga"),
    pytest.param({"type": "fixed"}, id="fixa-sem-carga"),
    pytest.param({"type": "xpto"}, id="discriminador-desconhecido"),
    pytest.param({"weekly_hours": "40"}, id="sem-discriminador"),
]


@pytest.mark.parametrize("payload", _PAYLOADS_DE_PERFIL_RECUSADOS)
def test_ca06_o_perfil_de_jornada_recusa_as_combinacoes_irrepresentaveis(
    payload: dict[str, str],
) -> None:
    """As duas metades de CA06 que são recusa, mais os dois defeitos vizinhos.

    "Sob demanda com carga" só é recusado porque a variante declara
    `extra="forbid"`: sem isso o campo seria **ignorado em silêncio** e o cliente
    ficaria com uma jornada diferente da que pediu — 200 em vez de 422.
    """
    with pytest.raises(ValidationError):
        schemas.ChangeWorkloadProfileRequest(workload_profile=payload)


def test_ca06_o_payload_de_jornada_fixa_produz_o_value_object_com_a_carga() -> None:
    """O ramo positivo: payload válido → `FixedSchedule` com o `Decimal` certo."""
    pedido = schemas.ChangeWorkloadProfileRequest(workload_profile=_PERFIL_FIXO)

    perfil = schemas.to_workload_profile(pedido.workload_profile)

    assert perfil == FixedSchedule(weekly_hours=decimal.Decimal("40.0"))


def test_ca06_o_payload_de_jornada_sob_demanda_produz_o_value_object_sem_carga() -> None:
    """O outro ramo positivo — e sem ele `OnDemand` nunca seria construído."""
    pedido = schemas.ChangeWorkloadProfileRequest(workload_profile=_PERFIL_SOB_DEMANDA)

    assert schemas.to_workload_profile(pedido.workload_profile) == OnDemand()


# ---------------------------------------------------------------------------
# Conversor de `weekly_hours` — D-3B1 e ADR 3.6.0003 §Decision 2
# ---------------------------------------------------------------------------

_CARGAS_RECUSADAS_PELO_CONVERSOR = [
    pytest.param("abc", id="nao-numerico"),
    pytest.param("", id="vazio"),
    pytest.param("40,5", id="virgula-decimal"),
    pytest.param("  40  ", id="espaco-em-volta"),
    pytest.param(" 40", id="espaco-a-esquerda"),
    pytest.param("40 ", id="espaco-a-direita"),
    pytest.param("40\n", id="quebra-de-linha"),
]


@pytest.mark.parametrize("raw", _CARGAS_RECUSADAS_PELO_CONVERSOR)
def test_o_conversor_de_carga_recusa_o_que_viraria_500_e_o_que_seria_aparado(raw: str) -> None:
    """Duas famílias numa asserção só, e as duas terminam em erro de **domínio**.

    Os três primeiros levantariam `decimal.InvalidOperation` — `ArithmeticError`,
    que nenhum handler alcança — e virariam 500. Os quatro últimos construiriam
    um `Decimal` **diferente do que o cliente escreveu**, em silêncio: é o
    ADR 2.3.0005 aplicado a este campo (D-3B1).
    """
    with pytest.raises(InvalidWeeklyHoursError):
        schemas.to_weekly_hours(raw)


@pytest.mark.parametrize("raw", ["40", "40.0", "22.50", "0.5"])
def test_o_conversor_de_carga_aceita_o_numero_bem_formado_preservando_a_escala(raw: str) -> None:
    """A escala faz parte do valor: `"22.50"` não é `"22.5"` no fio."""
    convertido = schemas.to_weekly_hours(raw)

    assert convertido == decimal.Decimal(raw)
    assert str(convertido) == raw


@pytest.mark.parametrize("raw", ["NaN", "Infinity", "-Infinity"])
def test_a_carga_nao_finita_passa_pelo_conversor_e_morre_no_dominio(raw: str) -> None:
    """O limite declarado do conversor, e por que ele **não** duplica a checagem.

    `Decimal("NaN")` constrói, então o conversor não tem o que traduzir; quem
    recusa é `FixedSchedule.__post_init__`, com a **mesma** exceção e o mesmo
    422. Duplicar a regra aqui criaria duas fontes para ela, e uma delas
    envelheceria primeiro.
    """
    assert schemas.to_weekly_hours(raw).is_finite() is False

    with pytest.raises(InvalidWeeklyHoursError):
        FixedSchedule(weekly_hours=schemas.to_weekly_hours(raw))


# ---------------------------------------------------------------------------
# CA04 — round-trip de escala, datetimes ingênuos e os dois campos ordenados
# ---------------------------------------------------------------------------


def _employee_result(
    *,
    workload_profile: object = None,
    shift_preference: ShiftPreference | None = None,
    job_function_ids: frozenset[JobFunctionId] = frozenset(),
    unavailabilities: tuple[UnavailabilityPeriod, ...] = (),
) -> EmployeeResult:
    """Result real do use case — a resposta é montada a partir dele, nunca da entidade."""
    return EmployeeResult(
        id=EmployeeId("e1"),
        tenant_id=TenantId("t1"),
        unit_id=UnitId("u1"),
        name="Ana",
        workload_profile=workload_profile or OnDemand(),  # type: ignore[arg-type]
        shift_preference=shift_preference,
        job_function_ids=job_function_ids,
        unavailabilities=unavailabilities,
        active=True,
    )


def test_ca04_a_carga_semanal_sobrevive_ao_round_trip_em_valor_e_escala() -> None:
    """`"22.50"` entra e `"22.50"` volta — `float` perderia o zero final."""
    pedido = schemas.ChangeWorkloadProfileRequest(
        workload_profile={"type": "fixed", "weekly_hours": "22.50"}
    )
    perfil = schemas.to_workload_profile(pedido.workload_profile)

    corpo = schemas.EmployeeResponse.from_result(
        _employee_result(workload_profile=perfil)
    ).model_dump()

    assert corpo["workload_profile"] == {"type": "fixed", "weekly_hours": "22.50"}


def test_ca04_as_funcoes_saem_ordenadas_pelo_proprio_id() -> None:
    """A asserção é contra a **lista esperada**, não entre duas execuções.

    A iteração de `frozenset` é determinística **dentro de um processo** (o
    `PYTHONHASHSEED` é sorteado por processo), então "duas chamadas devolvem o
    mesmo corpo" é verdade com ou sem `sorted()` e não mata mutação nenhuma. O
    que mata é comparar com a ordem que se espera.
    """
    ids = [JobFunctionId(valor) for valor in ("jf-c", "jf-a", "jf-b")]

    corpo = schemas.EmployeeResponse.from_result(
        _employee_result(job_function_ids=frozenset(ids))
    ).model_dump()

    assert corpo["job_function_ids"] == sorted(ids)
    assert corpo["job_function_ids"] == ["jf-a", "jf-b", "jf-c"]


def test_ca04_a_preferencia_sai_na_ordem_de_declaracao_do_enum_nao_na_alfabetica() -> None:
    """A chave é **nomeada**, e as duas ordens discordam — que é o que dá refutação.

    Alfabética seria `afternoon, morning, night, overnight`; a de declaração é
    `morning, afternoon, night, overnight`. Um teste com um conjunto em que as
    duas coincidissem não distinguiria as implementações.
    """
    preferencia = ShiftPreference(
        periods=frozenset({DayPeriod.OVERNIGHT, DayPeriod.MORNING, DayPeriod.AFTERNOON})
    )

    corpo = schemas.EmployeeResponse.from_result(
        _employee_result(shift_preference=preferencia)
    ).model_dump()

    assert corpo["shift_preference"] == ["morning", "afternoon", "overnight"]
    assert corpo["shift_preference"] != sorted(corpo["shift_preference"])


def test_ca04_a_preferencia_ausente_viaja_como_null_e_nao_como_lista_vazia() -> None:
    """Nao-declarada e declarada-vazia sao coisas diferentes; o dominio recusa a segunda."""
    corpo = schemas.EmployeeResponse.from_result(_employee_result()).model_dump()

    assert corpo["shift_preference"] is None


def test_ca04_os_instantes_de_indisponibilidade_voltam_ingenuos() -> None:
    """Sem offset na saída: são wall-clock do fuso da unidade (ADR 3.1.0005)."""
    periodo = UnavailabilityPeriod(
        start=datetime.datetime(2026, 3, 1, 8, 0),
        end=datetime.datetime(2026, 3, 1, 12, 0),
    )

    corpo = schemas.EmployeeResponse.from_result(
        _employee_result(unavailabilities=(periodo,))
    ).model_dump()

    assert corpo["unavailabilities"][0]["start"].tzinfo is None
    assert corpo["unavailabilities"][0]["end"].tzinfo is None


def test_o_instante_com_z_e_parsado_como_tz_aware_e_nao_convertido_em_silencio() -> None:
    """A metade de entrada de ADR 3.6.0003 §Decision 3.

    O schema **aceita** o valor (é `datetime` válido) e o mantém tz-aware; quem
    o recusa é `UnavailabilityPeriod`, com `InvalidUnavailabilityPeriodError` →
    422. O que não pode acontecer é o offset ser descartado no caminho.
    """
    pedido = schemas.RegisterUnavailabilityRequest(
        start="2026-03-01T08:00:00Z", end="2026-03-01T12:00:00Z"
    )

    assert pedido.start.tzinfo is not None


def test_a_resposta_de_funcao_sai_do_result_com_os_tres_campos() -> None:
    """`JobFunctionResponse` não tem campo de estado — a função não tem ciclo de vida."""
    corpo = schemas.JobFunctionResponse.from_result(
        JobFunctionResult(id=JobFunctionId("jf1"), tenant_id=TenantId("t1"), name="Garçom")
    ).model_dump()

    assert corpo == {"id": "jf1", "tenant_id": "t1", "name": "Garçom"}


# ---------------------------------------------------------------------------
# `DeclareShiftPreferenceRequest` — o campo sem default (metade de CA03)
# ---------------------------------------------------------------------------


def test_a_preferencia_de_turno_e_obrigatoria_no_corpo_que_a_declara() -> None:
    """Corpo `{}` é recusado: com default, ele **limparia** a preferência em silêncio."""
    with pytest.raises(ValidationError):
        schemas.DeclareShiftPreferenceRequest()


def test_a_preferencia_de_turno_aceita_null_explicito_para_limpar() -> None:
    """`null` é o pedido de limpeza, e tem de ser distinguível da omissão."""
    assert schemas.DeclareShiftPreferenceRequest(shift_preference=None).shift_preference is None


# ---------------------------------------------------------------------------
# CA05 — nenhum módulo do pacote importa símbolo de `staff.domain.entities`
# ---------------------------------------------------------------------------


def _modulos_do_pacote_http() -> list[pathlib.Path]:
    """Os `.py` que o pacote **contém** — derivado, portanto cresce com as Tasks."""
    pacote = importlib.import_module(_PACOTE_HTTP_STAFF)
    raiz = pathlib.Path(next(iter(pacote.__path__)))
    encontrados = sorted(raiz.glob("*.py"))
    assert encontrados, "a varredura precisa de módulos para ter o que negar"
    return encontrados


def test_ca05_nenhum_modulo_do_adapter_importa_entidade_de_dominio() -> None:
    """Varredura de **imports**, que é decidível — não de anotações, que não é.

    O domínio sai do pacote, não de uma lista: `error_handlers.py`,
    `dependencies.py` e `router.py` entram nesta trava assim que existirem, sem
    que ninguém precise estender este teste.
    """
    culpados: list[str] = []
    for arquivo in _modulos_do_pacote_http():
        arvore = ast.parse(arquivo.read_text(encoding="utf-8"))
        for no in ast.walk(arvore):
            if isinstance(no, ast.ImportFrom) and "staff.domain.entities" in (no.module or ""):
                culpados.append(f"{arquivo.name}:{no.lineno}")
            if isinstance(no, ast.Import):
                culpados += [
                    f"{arquivo.name}:{no.lineno}"
                    for alias in no.names
                    if "staff.domain.entities" in alias.name
                ]

    assert culpados == [], f"import de entidade de domínio no adapter: {culpados}"


def test_ca05_a_varredura_de_import_cobre_o_pacote_inteiro_e_nao_uma_amostra() -> None:
    """Fecha a ponta que faria a asserção acima envelhecer em silêncio.

    Se `_modulos_do_pacote_http` deixasse de enxergar um módulo — por glob
    errado, por subpacote —, CA05 continuaria verde sobre o que restou. A
    comparação é contra o que o `pkgutil` enumera, que é uma segunda fonte.
    """
    pacote = importlib.import_module(_PACOTE_HTTP_STAFF)
    pelo_pkgutil = {info.name for info in pkgutil.iter_modules(list(pacote.__path__))}
    pelo_glob = {arquivo.stem for arquivo in _modulos_do_pacote_http()} - {"__init__"}

    assert pelo_glob == pelo_pkgutil


def test_a_uniao_de_perfil_e_realmente_discriminada_pelo_campo_type() -> None:
    """A união é discriminada, e não "tenta uma, tenta outra".

    Sem o discriminador, o Pydantic tentaria as variantes em ordem e a mensagem
    de erro apontaria a variante errada — mas, pior, um payload ambíguo poderia
    casar a primeira que servisse. O `TypeAdapter` é o que permite exercitar a
    união isolada do request que a contém.
    """
    adaptador = PydanticTypeAdapter(schemas.WorkloadProfilePayload)

    assert isinstance(adaptador.validate_python(_PERFIL_FIXO), schemas.FixedSchedulePayload)
    assert isinstance(adaptador.validate_python(_PERFIL_SOB_DEMANDA), schemas.OnDemandPayload)
