"""Schemas Pydantic de request e response, e os conversores da borda — BC staff.

**Pydantic vive só aqui** (LAYOUT §7; skill `fastapi-thin-adapter`). Os use cases
recebem e devolvem dataclasses da camada `application`; um schema nunca atravessa
para dentro, e nenhum DTO de application é usado como schema.

**Nenhuma entidade de domínio aparece numa resposta.** `EmployeeResponse` é
montado a partir de `EmployeeResult`, não de `Employee` — e a propriedade é
verificável como **ausência de import**: nenhum módulo deste pacote importa
símbolo de `staff.domain.entities` (CA05).

Seis decisões deste módulo valem explicação, e nenhuma é cosmética.

**1. Nenhum request tem `tenant_id`, e a ausência é a defesa.** O tenant vem do
token e é resolvido no `composition_root` (ADR 0.0.0005); em staff ele não
aparece em lugar nenhum da requisição. A varredura de `model_fields` que trava
isso enumera também os aliases plausíveis (`restaurant_id`, `tenant`,
`restaurant`) e os campos de **vínculo de login** (`user_id`,
`employee_user_id`) — estes últimos por um motivo diferente: o vínculo entrou na
Stage 3.5, e `user_id` continua proibido **no request** porque nunca vem do
cliente — quem o gera é identity, atrás do gateway; o cliente manda o
**e-mail** (`CreateLoginRequest`) e recebe o `user_id` na resposta.

**2. O perfil de jornada é união discriminada por `type`, nos dois sentidos**
(ADR 3.6.0003 §Decision 1). É o que torna "sob demanda com carga" e "fixa sem
carga" irrepresentáveis no fio, do mesmo modo que a união de tipos os torna
irrepresentáveis no domínio. As duas variantes declaram `extra="forbid"`, e é o
que faz `{"type": "on_demand", "weekly_hours": "40"}` receber 422 em vez de ser
silenciosamente aparado — exigência literal de CA06. A escolha diverge de
propósito do `extra` permissivo dos schemas de identity: lá a permissividade
existe para que um `tenant_id` enviado seja **desarmado em silêncio** e o teste
possa observar a defesa; aqui o payload extra **é** o estado inválido que a união
existe para recusar.

**3. `weekly_hours` viaja como string, e a borda possui um conversor** — não uma
chamada nua a `Decimal(...)`. Medido: `Decimal("abc")` levanta
`decimal.InvalidOperation`, que é `ArithmeticError` e **não** `StaffError`; nada
registra handler para ela, e um `Decimal(payload)` no router responderia **500**.
O conversor traduz para `InvalidWeeklyHoursError` → 422, espelhando em forma o
`DayPeriod.from_string` que a mesma borda já usa pela mesma razão. A string
também preserva a **escala** que a Stage 3.3 provou sobreviver ao round-trip:
`"22.50"` volta `"22.50"`, não `22.5`.

**4. Valor com espaço em volta é recusado, não aparado** (D-3B1 do technical).
`Decimal("  40  ")` constrói `Decimal("40")` e o espaço some em silêncio —
normalização silenciosa, que o ADR 2.3.0005 recusa. A política tem de ser **uma
só dentro do pacote**: a cláusula 6 do ADR 3.6.0002 já diz, para o validador de
identificador, que *nada além dos três valores rejeitados é normalizado, aparado
ou reescrito*. Duas políticas opostas para espaço em branco dentro de um adapter
só seriam uma divergência invisível.

**5. Os dois campos derivados de `frozenset` saem ordenados, cada um com chave
nomeada** (ADR 3.6.0003 §Decision 4). `job_function_ids` pelo próprio id;
`shift_preference` pela **ordem de declaração do enum `DayPeriod`** — manhã,
tarde, noite, madrugada —, que é a sequência que a língua ubíqua já carrega e que
a ordem alfabética embaralharia. "Ordenado" sozinho deixaria duas leituras
defensáveis para o segundo campo.

**6. O segredo de R17 é declarado credencial no campo, e é isso que tira a
resposta do cache** (issue #61). `setup_link` é `SetupLink`: a marca
`x-credential` no JSON Schema do campo faz o middleware de
`shared/infrastructure/http/credential_no_store.py` gravar `Cache-Control:
no-store` e `Pragma: no-cache` em toda resposta de R17 — nos dois canais, porque
a política é da rota, não do valor. A chave vai por extenso porque adapter não
importa `shared.infrastructure` (LAYOUT §3); o teste deste schema a confere contra
o detector de `shared`. A marca fica no nível do campo, e não dentro da união,
para que a anotação continue `str | None`.

**A conversão de texto para value object acontece no router, não no schema.** É
o que faz a falha ser erro de **domínio** — e cair no mapa de status de
`error_handlers.py` — em vez de virar `RequestValidationError` do FastAPI, que
tem outro corpo e segue outro caminho. Os conversores deste módulo são funções
puras que o router chama; o schema em si só descreve a forma.
"""

from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Annotated, Final, Literal

from pydantic import BaseModel, ConfigDict, Field

from restaurant_hub.features.staff.application.dtos.results import (
    EmployeeLoginResult,
    EmployeeResult,
    JobFunctionResult,
)
from restaurant_hub.features.staff.domain.exceptions.errors import InvalidWeeklyHoursError
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

# A ordem de declaração do enum, materializada como chave de ordenação
# (ADR 3.6.0003 §Decision 4). Deriva de `DayPeriod` em vez de repetir a sequência
# à mão: um período novo entra na ordem certa sem ninguém lembrar deste módulo.
_ORDEM_DO_PERIODO: Final[dict[DayPeriod, int]] = {
    periodo: posicao for posicao, periodo in enumerate(DayPeriod.__members__.values())
}

# O link de definição de senha numa resposta (decisão 6 do módulo). A rota irmã de
# R17 que vai reemitir o link (concept 3.5 §10) devolve este mesmo valor: o schema
# dela usa este alias, e é a marca — não o nome do schema — que lhe dá `no-store`.
SetupLink = Annotated[str | None, Field(json_schema_extra={"x-credential": True})]


# ---------------------------------------------------------------------------
# Perfil de jornada — a união discriminada, compartilhada por request e response
# ---------------------------------------------------------------------------


class FixedSchedulePayload(BaseModel):
    """Jornada fixa no fio — `{"type": "fixed", "weekly_hours": "40.0"}`.

    `extra="forbid"` porque a variante **é** o contrato: um campo a mais aqui é o
    estado inválido que a união existe para recusar, não ruído a ignorar.
    """

    model_config = ConfigDict(extra="forbid")

    type: Literal["fixed"]
    weekly_hours: str


class OnDemandPayload(BaseModel):
    """Jornada sob demanda no fio — `{"type": "on_demand"}`, e nada mais.

    É esta variante que faz `{"type": "on_demand", "weekly_hours": "40"}` receber
    422 (CA06): sem `extra="forbid"`, o campo seria ignorado em silêncio e o
    cliente ficaria com uma jornada diferente da que pediu.
    """

    model_config = ConfigDict(extra="forbid")

    type: Literal["on_demand"]


WorkloadProfilePayload = Annotated[
    FixedSchedulePayload | OnDemandPayload,
    Field(discriminator="type"),
]


class UnavailabilityPayload(BaseModel):
    """Um período de indisponibilidade no fio.

    `start` e `end` viajam **ingênuos** (ADR 3.6.0003 §Decision 3): são
    wall-clock do fuso da unidade, e um offset aqui deslocaria o que o gerente
    declarou. Um valor de entrada com `Z` é parsado como tz-aware e recusado por
    `UnavailabilityPeriod` (422) — **não** convertido em silêncio.
    """

    start: datetime
    end: datetime


# ---------------------------------------------------------------------------
# Requests — §4.2 do concept
# ---------------------------------------------------------------------------


class CreateJobFunctionRequest(BaseModel):
    """Criação de função de trabalho no catálogo do tenant."""

    name: str


class RenameJobFunctionRequest(BaseModel):
    """Renomeação de função de trabalho."""

    name: str


class CreateEmployeeRequest(BaseModel):
    """Criação de funcionário na unidade do endereço.

    Sem `unit_id`: a unidade é o recurso pai e vem do **path** (ADR 3.4.0007).
    """

    name: str
    workload_profile: WorkloadProfilePayload
    job_function_ids: list[str]
    shift_preference: list[str] | None = None


class RenameEmployeeRequest(BaseModel):
    """Renomeação de funcionário."""

    name: str


class AssignJobFunctionsRequest(BaseModel):
    """Substituição do conjunto de funções do funcionário.

    É **substituição**, não acréscimo — daí o `PUT` da rota correspondente.
    """

    job_function_ids: list[str]


class ChangeWorkloadProfileRequest(BaseModel):
    """Troca do perfil de jornada."""

    workload_profile: WorkloadProfilePayload


class DeclareShiftPreferenceRequest(BaseModel):
    """Declaração (ou limpeza) da preferência de turno.

    **`shift_preference` não tem default**, espelhando o command: ali `None`
    significa "**limpe** a preferência", não "não mexa". Com default, um corpo
    `{}` limparia a preferência em silêncio — e o cliente que esqueceu o campo
    apagaria um dado sem pedir.
    """

    shift_preference: list[str] | None


class RegisterUnavailabilityRequest(BaseModel):
    """Acréscimo de um período de indisponibilidade."""

    start: datetime
    end: datetime


class CreateLoginRequest(BaseModel):
    """Criação do login de um funcionário (R17, Stage 3.5).

    Dois campos, os dois sem default. `email` viaja como **texto**: não é
    identificador de staff (não passa por `validate_identifier`) e não vira VO
    aqui — e-mail é vocabulário de identity, que o valida atrás do gateway
    (concept 3.5 §5.7). `delivery` é o canal do link de definição de senha:
    `"email"` (identity envia) ou `"link"` (volta na resposta, para entrega em
    mãos). Sem default porque o canal decide o **prazo** do link e a **exposição**
    do segredo — é o gestor que decide, explicitamente.
    """

    email: str
    delivery: Literal["email", "link"]


class CopyEmployeeRequest(BaseModel):
    """Cópia do funcionário para outra unidade.

    `target_unit_id` é o **único** identificador de unidade que chega pelo corpo,
    e a exceção é legítima: o destino é escolha do usuário, e por isso é o
    **segundo alvo de autorização** da rota (L-AG4), não um parâmetro de
    conveniência.
    """

    target_unit_id: str


# ---------------------------------------------------------------------------
# Responses
# ---------------------------------------------------------------------------


class JobFunctionResponse(BaseModel):
    """Função de trabalho no fio. Sem campo de estado — ela não tem ciclo de vida."""

    id: str
    tenant_id: str
    name: str

    @classmethod
    def from_result(cls, result: JobFunctionResult) -> "JobFunctionResponse":
        """Monta a resposta a partir do **result** do use case, nunca da entidade."""
        return cls(id=result.id, tenant_id=result.tenant_id, name=result.name)


class EmployeeResponse(BaseModel):
    """Funcionário no fio — a resposta de **toda** escrita sobre o registro."""

    id: str
    tenant_id: str
    unit_id: str
    name: str
    workload_profile: WorkloadProfilePayload
    shift_preference: list[str] | None
    job_function_ids: list[str]
    unavailabilities: list[UnavailabilityPayload]
    active: bool
    # Stage 3.5 — o login vinculado, ou `null`. Sai em **toda** resposta de
    # funcionário porque `from_result` lê o `EmployeeResult`, que já o carrega
    # pelo mapper único (CA13).
    user_id: str | None

    @classmethod
    def from_result(cls, result: EmployeeResult) -> "EmployeeResponse":
        """Monta a resposta a partir do **result** do use case, nunca da entidade.

        Os dois campos derivados de `frozenset` saem ordenados aqui, cada um com
        a sua chave: sem isso a ordem no fio dependeria do `PYTHONHASHSEED` do
        processo, e o cliente veria a mesma coleção em ordens diferentes entre
        dois deploys.
        """
        return cls(
            id=result.id,
            tenant_id=result.tenant_id,
            unit_id=result.unit_id,
            name=result.name,
            workload_profile=to_workload_profile_payload(result.workload_profile),
            shift_preference=to_shift_preference_payload(result.shift_preference),
            job_function_ids=sorted(result.job_function_ids),
            unavailabilities=[
                to_unavailability_payload(periodo) for periodo in result.unavailabilities
            ],
            active=result.active,
            user_id=result.user_id,
        )


class EmployeeLoginResponse(BaseModel):
    """A resposta de R17: o registro vinculado e, só no canal `link`, o segredo.

    `setup_link` é `null` no canal `email` — o link foi por e-mail e a API não o
    repete. No canal `link` é o único ponto em que o valor de um token de
    definição de senha sai por API (carve-out do ADR 3.5.0002), para quem acabou
    de provar `manage_staff` **e** `manage_users` sobre a unidade. É `SetupLink`, e
    a marca dele mantém a resposta fora de cache (decisão 6 do módulo).
    """

    employee: EmployeeResponse
    setup_link: SetupLink

    @classmethod
    def from_result(cls, result: EmployeeLoginResult) -> "EmployeeLoginResponse":
        return cls(
            employee=EmployeeResponse.from_result(result.employee),
            setup_link=result.setup_link,
        )


# ---------------------------------------------------------------------------
# Conversores da borda — funções puras que o router chama
# ---------------------------------------------------------------------------


def to_weekly_hours(raw: str) -> Decimal:
    """Texto → `Decimal`, com erro de **domínio** quando não é número.

    Duas recusas, e as duas são deliberadas:

    - **não-numérico** (`"abc"`, `""`, `"40,5"`): `decimal.InvalidOperation` é
      `ArithmeticError`, que nenhum handler alcança — sem esta tradução, seria
      500 (ADR 3.6.0003 §Decision 2);
    - **espaço em volta** (`"  40  "`): `Decimal` o apara em silêncio, e aparar é
      normalização silenciosa (ADR 2.3.0005; D-3B1 do technical). A forma crua
      tem de ser igual à forma sem espaços em volta.

    `"NaN"` e `"Infinity"` **não** são recusados aqui: eles constroem, e é
    `FixedSchedule.__post_init__` quem os recusa — também com
    `InvalidWeeklyHoursError`, também 422. Duplicar a checagem aqui criaria duas
    fontes para a mesma regra.
    """
    if raw != raw.strip():
        raise InvalidWeeklyHoursError(raw)
    try:
        return Decimal(raw)
    except InvalidOperation as exc:
        raise InvalidWeeklyHoursError(raw) from exc


def to_workload_profile(payload: FixedSchedulePayload | OnDemandPayload) -> WorkloadProfile:
    """Payload discriminado → value object do domínio.

    O `Literal` do discriminador é o que dá exaustividade estática ao `if`: uma
    variante nova sem tratamento aqui é erro de tipo, não ramo esquecido.
    """
    if isinstance(payload, FixedSchedulePayload):
        return FixedSchedule(weekly_hours=to_weekly_hours(payload.weekly_hours))
    return OnDemand()


def to_workload_profile_payload(
    profile: WorkloadProfile,
) -> FixedSchedulePayload | OnDemandPayload:
    """Value object → payload discriminado, preservando a escala do `Decimal`.

    `str(Decimal("22.50"))` é `"22.50"`: a escala é propriedade do valor, e
    reduzi-lo a `float` a perderia sem aviso.
    """
    if isinstance(profile, FixedSchedule):
        return FixedSchedulePayload(type="fixed", weekly_hours=str(profile.weekly_hours))
    return OnDemandPayload(type="on_demand")


def to_shift_preference_payload(preference: ShiftPreference | None) -> list[str] | None:
    """`ShiftPreference` → lista na **ordem de declaração** do enum, ou `None`.

    `None` significa "sem preferência declarada" e viaja como `null` — nunca como
    lista vazia, que o domínio recusa (`EmptyShiftPreferenceError`) e que faria o
    cliente confundir "não declarou" com "declarou nada".
    """
    if preference is None:
        return None
    return [
        periodo.value for periodo in sorted(preference.periods, key=_ORDEM_DO_PERIODO.__getitem__)
    ]


def to_unavailability_payload(periodo: UnavailabilityPeriod) -> UnavailabilityPayload:
    """Value object → payload, com os instantes ingênuos como estão."""
    return UnavailabilityPayload(start=periodo.start, end=periodo.end)
