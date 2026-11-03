"""Mapa exceção → status HTTP do BC staff (ADR 3.4.0002, decidido na 3.4).

**Mora na feature, não em `shared`.** O handler genérico de
`shared/infrastructure/http/error_handlers.py` converte `DomainError` em 422 e
continua valendo como rede de segurança para o domínio; mas as classes de staff não
podem ser referenciadas de `shared`, que não importa de features (LAYOUT §7).

**Um handler só, registrado sobre as duas raízes do BC** — `StaffError` (domínio) e
`StaffApplicationError` (aplicação), ADR 3.9.0001. Starlette escolhe o handler pelo
primeiro tipo do `__mro__` da exceção que estiver registrado; toda classe deste BC
tem uma raiz só, que vem antes de `DomainError`/`ApplicationError`, então este
handler ganha do genérico. É **só aqui** que a ordem da MRO importa — a hierarquia
não é desenhada para o framework —, e o status sai do mapa abaixo.

**A totalidade do mapa é um teste, não uma promessa.** Um erro novo sem entrada
cairia no default 422 em silêncio, que é exatamente como um 409 vira 422 sem
ninguém notar. O teste enumera recursivamente as subclasses e falha se alguma não
tiver entrada própria.

**Staff não registra entrada 401 nem 403, e a ausência é a decisão.** As duas
faixas são de identity, cujo handler está registrado sobre a **app** e é
alcançado por MRO: `InvalidAccessTokenError` e `PermissionDeniedError` sobem
cruas do port `AccessGuard` (L-AG1/L-AG2) e chegam lá exatamente como identity as
levantou. Uma entrada 401/403 aqui criaria uma **segunda** faixa distinguível
para a mesma condição — e um 403 de staff distinguível de um 403 de identity é
justamente o oráculo que L-AG1/L-AG2 compram ao proibir a tradução.

**O corpo carrega um discriminador próprio (`"type": "staff_error"`), e ele é
infraestrutura de teste, não enfeite.** Na faixa 422 esta app tem **duas**
origens: um erro de staff e o `RequestValidationError` do framework, que o
handler compartilhado renderiza com corpo constante
(`{"detail": "requisição inválida", "type": "validation_error"}`). O
ADR 3.6.0002, ao rejeitar a sua Alternativa A, já nomeava a diferença — *"a
different body shape"*, *"dois formatos distinguíveis para a mesma classe de
defeito"*. É este discriminador que as varreduras de borda asserem: sem ele, um
422 do framework satisfaz um critério de segurança de staff, e a rota que
esqueceu o validador de identificador passa no próprio teste.

**As cinco classificações com leitura alternativa plausível são consumidas do
ADR 3.4.0002 §4, não re-decididas aqui** — cada uma tem o seu porquê no
comentário da entrada correspondente.
"""

from typing import Final

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from restaurant_hub.features.staff.application.errors import (
    EmployeeAlreadyExistsError,
    EmployeeHasLoginError,
    EmployeeInUseError,
    EmployeeNotFoundError,
    EmployeeRelocationError,
    InvalidLoginEmailError,
    JobFunctionAlreadyExistsError,
    JobFunctionInUseError,
    JobFunctionNameAlreadyExistsError,
    JobFunctionNotFoundError,
    LoginEmailAlreadyInUseError,
    SameUnitCopyError,
    StaffApplicationError,
)
from restaurant_hub.features.staff.domain.exceptions.errors import (
    EmployeeAlreadyHasLoginError,
    EmptyJobFunctionsError,
    EmptyShiftPreferenceError,
    InvalidDayPeriodError,
    InvalidIdentifierError,
    InvalidNameError,
    InvalidUnavailabilityPeriodError,
    InvalidWeeklyHoursError,
    OverlappingUnavailabilityError,
    StaffError,
    TerminatedEmployeeLoginError,
    UnavailabilityNotFoundError,
)

# O que este BC pode levantar: as suas duas raízes (ADR 3.9.0001 §2).
type StaffFailure = StaffError | StaffApplicationError

HTTP_NOT_FOUND: Final = 404
HTTP_CONFLICT: Final = 409
HTTP_UNPROCESSABLE: Final = 422

# O discriminador do corpo de erro de staff. Ver o docstring do módulo: ele é o
# que separa um 422 **desta** borda de um 422 do `RequestValidationError` do
# framework, e as varreduras de identificador inválido dependem dessa separação
# para não ficarem verdes contra o erro errado.
STAFF_ERROR_TYPE: Final = "staff_error"

STAFF_ERROR_STATUS: Final[dict[type[StaffFailure], int]] = {
    # 404 — recurso endereçável ausente **no tenant do ator** e, para
    # funcionário, **na unidade do endereço** (ADR 3.4.0007). Os dois são falhas
    # de lookup, sob `StaffApplicationError` (ADR 3.9.0001); o 404 vem daqui, não
    # da hierarquia.
    JobFunctionNotFoundError: HTTP_NOT_FOUND,
    EmployeeNotFoundError: HTTP_NOT_FOUND,
    # 409 — conflito com estado **já gravado**: ou a chave existe, ou uma
    # referência existente impede a remoção. É a definição de faixa do
    # ADR 3.4.0002 §4, e é dela que sai o par `InUse`: o payload está correto,
    # e o que impede a operação é **outro registro**.
    JobFunctionNameAlreadyExistsError: HTTP_CONFLICT,
    # Entradas por **totalidade**: as duas colisões de **id** são inalcançáveis
    # por HTTP, e a razão é a mesma para as duas — o id é um UUID gerado dentro
    # do use case, nunca enviado pelo cliente, e a colisão exigiria que dois
    # UUID4 batessem. Nenhuma rota expõe uma entrada por onde produzi-las.
    # Registrado aqui pela mesma razão que `EmployeeInUseError` e
    # `EmployeeRelocationError` abaixo: para que ninguém gaste uma Task tentando
    # produzi-las por e2e. Quem cobra a ausência é
    # `test_toda_excecao_alcancavel_do_mapa_tem_cenario_e2e`.
    JobFunctionAlreadyExistsError: HTTP_CONFLICT,
    EmployeeAlreadyExistsError: HTTP_CONFLICT,
    JobFunctionInUseError: HTTP_CONFLICT,
    # `EmployeeInUseError` continua **sem produtor em v1** (nasce com o Step 4) e
    # mesmo assim tem entrada própria: totalidade é sobre a hierarquia, não sobre
    # o que é alcançável hoje. Não escrever e2e esperando produzi-la.
    EmployeeInUseError: HTTP_CONFLICT,
    # 409 — as quatro recusas de **login** da Stage 3.5 (concept §6.1), todas
    # conflito com estado já gravado: o registro **já** tem login; o registro
    # está **desligado** (criar login é conceder acesso, e desligar cortou o que
    # o registro concedia — ADR 3.8.0001);
    # o e-mail já é login de alguém (tradução de `EmailAlreadyRegisteredError`
    # pelo gateway, L-IG2); o registro tem login e a **remoção** é recusada —
    # irmã de `EmployeeInUseError` (ADR 3.5.0003 §1b). Nascem na Task 01 da
    # Stage, antes de qualquer produtor: até a Task 11 são inalcançáveis por
    # HTTP, e `test_staff_status_bands.py` as declara assim.
    EmployeeAlreadyHasLoginError: HTTP_CONFLICT,
    TerminatedEmployeeLoginError: HTTP_CONFLICT,
    LoginEmailAlreadyInUseError: HTTP_CONFLICT,
    EmployeeHasLoginError: HTTP_CONFLICT,
    # 422 — invariante violada **pelo conteúdo enviado**.
    InvalidNameError: HTTP_UNPROCESSABLE,
    InvalidIdentifierError: HTTP_UNPROCESSABLE,
    InvalidWeeklyHoursError: HTTP_UNPROCESSABLE,
    InvalidDayPeriodError: HTTP_UNPROCESSABLE,
    EmptyShiftPreferenceError: HTTP_UNPROCESSABLE,
    EmptyJobFunctionsError: HTTP_UNPROCESSABLE,
    InvalidUnavailabilityPeriodError: HTTP_UNPROCESSABLE,
    # 422 e **não** 409: invariante do agregado violada pelo período que o
    # cliente enviou, não colisão de chave gravada.
    OverlappingUnavailabilityError: HTTP_UNPROCESSABLE,
    # 422 e **não** 404: o período é um valor **dentro** do agregado, não um
    # recurso endereçável — o funcionário existe e foi encontrado. Por isso a
    # classe fica sob `StaffError`, e não com os dois lookups acima.
    UnavailabilityNotFoundError: HTTP_UNPROCESSABLE,
    # Entrada por **totalidade**: `EmployeeRelocationError` é **inalcançável por
    # HTTP nesta Stage**, porque nenhuma rota permite enviar `unit_id` num
    # update. Registrado aqui para que ninguém escreva e2e esperando produzi-la.
    EmployeeRelocationError: HTTP_UNPROCESSABLE,
    # 422 e **não** 409: nada está em conflito — o cliente nomeou a origem como
    # destino.
    SameUnitCopyError: HTTP_UNPROCESSABLE,
    # 422 — o que chegou como e-mail de login não é e-mail (tradução de
    # `InvalidEmailError` de identity pelo gateway, L-IG2; inclui o byte NUL,
    # que o VO `Email` passa a recusar na Stage 3.5, D8).
    InvalidLoginEmailError: HTTP_UNPROCESSABLE,
}


def resolve_status(exc: StaffFailure) -> int:
    """Status da exceção, resolvido pelo `__mro__`.

    Percorrer o MRO — em vez de olhar só `type(exc)` — faz uma subclasse futura
    herdar a classificação do pai em runtime. **Isso não relaxa a totalidade**: o
    teste continua exigindo entrada própria para cada classe concreta, e a
    herança existe só para que um erro não classificado degrade para algo
    sensato em produção em vez de virar 500.
    """
    for exc_type in type(exc).__mro__:
        status = STAFF_ERROR_STATUS.get(exc_type)
        if status is not None:
            return status
    return HTTP_UNPROCESSABLE


def build_error_response(exc: StaffFailure) -> JSONResponse:
    """Monta a resposta do erro de staff, com o discriminador de corpo próprio.

    Não há regra de corpo constante aqui, e a assimetria com identity é
    deliberada: as faixas que exigem corpo constante são 401 e 403, que staff
    **não** produz. As faixas de staff — 404, 409 e 422 — falam de um recurso que
    o próprio cliente endereçou ou de uma invariante que o payload dele violou, e
    a autorização já correu antes, de modo que a mensagem só fala do tenant do
    ator.
    """
    return JSONResponse(
        status_code=resolve_status(exc),
        content={"detail": str(exc), "type": STAFF_ERROR_TYPE},
    )


def register_staff_error_handlers(app: FastAPI) -> None:
    """Registra o handler único do BC sobre as **duas** raízes (ADR 3.9.0001 §4).

    Uma raiz sem registro deixaria os erros dela sem handler algum — não há rede
    genérica para `ApplicationError` —, e `test_status_map.py` cobra o registro de
    cada raiz.
    """

    @app.exception_handler(StaffApplicationError)
    @app.exception_handler(StaffError)
    async def staff_error_handler(request: Request, exc: StaffFailure) -> JSONResponse:
        return build_error_response(exc)
