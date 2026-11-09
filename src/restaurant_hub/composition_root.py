"""Composition Root — único ponto de wiring de dependências da aplicação.

Este módulo é o ÚNICO lugar que conhece as implementações concretas. Ele instancia
cada dependência de infraestrutura e injeta nas camadas de aplicação. Se você
precisar trocar uma implementação (ex: Postgres → DynamoDB), mude APENAS aqui.
Nenhuma regra de negócio deve ser alterada.

Regra: nenhum outro módulo deve instanciar diretamente classes de `infrastructure/`
ou de `adapters/`. Há teste mecânico disso **por bounded context** —
`tests/unit/features/identity/adapters/test_composition_root_identity.py` e
`tests/unit/features/staff/adapters/test_composition_root_staff.py` — porque a
varredura de cada um é ancorada no seu próprio pacote de adapters: a de identity
não olha para `features/staff/adapters`, então um BC novo sem o seu teste entra
descoberto e o gate existente continua verde. A regra é fácil de violar sem
querer e invisível numa revisão de diff.

**Sobre o `ignore_imports` que este arquivo motiva** (Stage 2.3): a partir daqui o
composition root importa `features.identity.adapters`, e
`shared/infrastructure/http/app.py` importa o composition root. A cadeia
`shared → composition_root → features.adapters` viola literalmente o contrato
`shared-independence` do import-linter, e é a **exceção declarada em LAYOUT §6**.
A supressão lá é a mais estreita possível: só este par.

**Sobre os imports do adapter de entrada** (issue #45): até aqui eles passavam por
`importlib`, porque o pacote se chamava `in` — palavra reservada do Python, e
`from ...adapters.in.http...` é **SyntaxError**, não ImportError. O diretório
passou a se chamar `inbound/`, e com isso os imports voltaram a ser estáticos.
Não é cosmético: enquanto eram dinâmicos, **nenhuma** dessas arestas aparecia no
grafo do import-linter — o contorno da keyword era, ele próprio, um ponto cego.

**Por que o composition root entrega também o mapa de `dependency_overrides`:** as
chaves desse dicionário são os provedores `_get_*` definidos dentro de `router.py`.
Se `app.py` tivesse de alcançá-los, `shared` passaria a importar feature — e a
supressão estreita acima deixaria de bastar. Entregando o mapa pronto, `app.py`
continua sem conhecer feature nenhuma.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from fastapi import APIRouter, FastAPI

from restaurant_hub.features.identity.adapters.inbound.http import (
    dependencies as dependencies_module,
)
from restaurant_hub.features.identity.adapters.inbound.http import (
    error_handlers as error_handlers_module,
)
from restaurant_hub.features.identity.adapters.inbound.http import router as router_module
from restaurant_hub.features.identity.adapters.out.postgres.password_setup_token_repository import (
    PostgresPasswordSetupTokenRepository,
)
from restaurant_hub.features.identity.adapters.out.postgres.restaurant_repository import (
    PostgresRestaurantRepository,
)
from restaurant_hub.features.identity.adapters.out.postgres.session_repository import (
    PostgresSessionRepository,
)
from restaurant_hub.features.identity.adapters.out.postgres.unit_of_work import (
    PostgresUnitOfWork,
)
from restaurant_hub.features.identity.adapters.out.postgres.unit_repository import (
    PostgresUnitRepository,
)
from restaurant_hub.features.identity.adapters.out.postgres.user_repository import (
    PostgresUserRepository,
)
from restaurant_hub.features.identity.adapters.out.security.argon2_hasher import (
    Argon2PasswordHasher,
)
from restaurant_hub.features.identity.adapters.out.security.jwt_issuer import (
    JwtTokenIssuer,
)
from restaurant_hub.features.identity.adapters.out.security.setup_token_issuer import (
    Sha256SetupTokenIssuer,
)
from restaurant_hub.features.identity.application.facade import (
    IdentityAccessFacade,
    IdentityFacade,
)
from restaurant_hub.features.identity.application.use_cases.authenticate_user import (
    AuthenticateUserUseCase,
)
from restaurant_hub.features.identity.application.use_cases.authorize_action import (
    AuthorizeActionUseCase,
)
from restaurant_hub.features.identity.application.use_cases.create_unit import (
    CreateUnitUseCase,
)
from restaurant_hub.features.identity.application.use_cases.create_user import (
    CreateUserUseCase,
)
from restaurant_hub.features.identity.application.use_cases.get_account_role import (
    GetAccountRoleUseCase,
)
from restaurant_hub.features.identity.application.use_cases.invite_user import (
    InviteUserUseCase,
)
from restaurant_hub.features.identity.application.use_cases.provision_account import (
    ProvisionAccountUseCase,
)
from restaurant_hub.features.identity.application.use_cases.provision_restaurant import (
    ProvisionRestaurantUseCase,
)
from restaurant_hub.features.identity.application.use_cases.refresh_session import (
    RefreshSessionUseCase,
)
from restaurant_hub.features.identity.application.use_cases.request_password_reset import (
    RequestPasswordResetUseCase,
)
from restaurant_hub.features.identity.application.use_cases.revoke_all_sessions import (
    RevokeAllSessionsUseCase,
)
from restaurant_hub.features.identity.application.use_cases.revoke_session import (
    RevokeSessionUseCase,
)
from restaurant_hub.features.identity.application.use_cases.send_invitation import (
    SendInvitationUseCase,
)
from restaurant_hub.features.identity.application.use_cases.set_password_with_token import (
    SetPasswordWithTokenUseCase,
)
from restaurant_hub.features.staff.adapters.inbound.http import (
    dependencies as staff_dependencies_module,
)
from restaurant_hub.features.staff.adapters.inbound.http import (
    error_handlers as staff_error_handlers_module,
)
from restaurant_hub.features.staff.adapters.inbound.http import (
    router as staff_router_module,
)
from restaurant_hub.features.staff.adapters.out.identity.local_access_guard import (
    LocalAccessGuard,
)
from restaurant_hub.features.staff.adapters.out.identity.local_identity_gateway import (
    LocalIdentityGateway,
)
from restaurant_hub.features.staff.adapters.out.postgres.employee_repository import (
    PostgresEmployeeRepository,
)
from restaurant_hub.features.staff.adapters.out.postgres.job_function_repository import (
    PostgresJobFunctionRepository,
)
from restaurant_hub.features.staff.application.ports.out.access_guard import AccessGuard
from restaurant_hub.features.staff.application.ports.out.identity_gateway import (
    IdentityGateway,
)
from restaurant_hub.features.staff.application.use_cases.assign_job_functions import (
    AssignJobFunctionsUseCase,
)
from restaurant_hub.features.staff.application.use_cases.change_workload_profile import (
    ChangeWorkloadProfileUseCase,
)
from restaurant_hub.features.staff.application.use_cases.copy_employee_to_unit import (
    CopyEmployeeToUnitUseCase,
)
from restaurant_hub.features.staff.application.use_cases.create_employee import (
    CreateEmployeeUseCase,
)
from restaurant_hub.features.staff.application.use_cases.create_job_function import (
    CreateJobFunctionUseCase,
)
from restaurant_hub.features.staff.application.use_cases.create_login_for_employee import (
    CreateLoginForEmployeeUseCase,
)
from restaurant_hub.features.staff.application.use_cases.deactivate_employee import (
    DeactivateEmployeeUseCase,
)
from restaurant_hub.features.staff.application.use_cases.declare_shift_preference import (
    DeclareShiftPreferenceUseCase,
)
from restaurant_hub.features.staff.application.use_cases.delete_employee import (
    DeleteEmployeeUseCase,
)
from restaurant_hub.features.staff.application.use_cases.delete_job_function import (
    DeleteJobFunctionUseCase,
)
from restaurant_hub.features.staff.application.use_cases.list_employees import (
    ListEmployeesUseCase,
)
from restaurant_hub.features.staff.application.use_cases.list_job_functions import (
    ListJobFunctionsUseCase,
)
from restaurant_hub.features.staff.application.use_cases.reactivate_employee import (
    ReactivateEmployeeUseCase,
)
from restaurant_hub.features.staff.application.use_cases.register_unavailability import (
    RegisterUnavailabilityUseCase,
)
from restaurant_hub.features.staff.application.use_cases.remove_unavailability import (
    RemoveUnavailabilityUseCase,
)
from restaurant_hub.features.staff.application.use_cases.rename_employee import (
    RenameEmployeeUseCase,
)
from restaurant_hub.features.staff.application.use_cases.rename_job_function import (
    RenameJobFunctionUseCase,
)
from restaurant_hub.shared.application.ports.out.email_sender import EmailSender
from restaurant_hub.shared.infrastructure.clock.system_clock import SystemClock
from restaurant_hub.shared.infrastructure.config.settings import Settings, get_settings
from restaurant_hub.shared.infrastructure.database.connection import build_engine
from restaurant_hub.shared.infrastructure.email.console_sender import ConsoleSender
from restaurant_hub.shared.infrastructure.uuid_generator.uuid4_generator import (
    Uuid4Generator,
)


@dataclass
class ApplicationDependencies:
    """Contêiner com as dependências montadas e prontas para uso.

    Expõe **use cases**, não repositórios: a partir da Stage 2.4 os repositórios
    recuam para dentro deles, que é o que o docstring da versão anterior deste
    arquivo já antecipava. Os tipos são as classes de use case, e não ports,
    porque use case é código nosso — o que precisa ser abstrato é o que ele
    **consome**, e isso já está garantido pelas anotações de port nos construtores.
    """

    identity_authenticate_user: AuthenticateUserUseCase
    identity_refresh_session: RefreshSessionUseCase
    identity_revoke_session: RevokeSessionUseCase
    identity_provision_restaurant: ProvisionRestaurantUseCase
    identity_create_unit: CreateUnitUseCase
    identity_create_user: CreateUserUseCase
    identity_invite_user: InviteUserUseCase
    identity_request_password_reset: RequestPasswordResetUseCase
    identity_set_password_with_token: SetPasswordWithTokenUseCase
    identity_authorize_action: AuthorizeActionUseCase
    # Tipado desde a #47. Era `Any` desde a época em que o pacote de entrada se
    # chamava `in` (inalcançável por import estático); a #45 o tornou importável
    # e a #47, que moveu o consumidor, o anotou.
    identity_guard: dependencies_module.IdentityGuard

    # --- staff (Stage 3.3) ---------------------------------------------------
    #
    # Os 16 use cases do BC, e não os dois repositórios: o docstring acima é
    # explícito ("expõe **use cases**, não repositórios"), e o bloco 3.3 do
    # roadmap lista este arquivo em `arquivos_a_modificar` (D9). Não há adapter
    # de entrada de staff ainda — ele é da 3.4 —, então estes campos nascem
    # **sem consumidor**, e o custo está declarado: CA18 prova que estão montados
    # sobre os adapters Postgres, não que estão exercitados. A alternativa
    # (esperar a 3.4) deixaria a Stage entregando persistência que nada no boot
    # da aplicação alcança.
    staff_create_job_function: CreateJobFunctionUseCase
    staff_rename_job_function: RenameJobFunctionUseCase
    staff_delete_job_function: DeleteJobFunctionUseCase
    staff_list_job_functions: ListJobFunctionsUseCase
    staff_create_employee: CreateEmployeeUseCase
    staff_rename_employee: RenameEmployeeUseCase
    staff_list_employees: ListEmployeesUseCase
    staff_delete_employee: DeleteEmployeeUseCase
    staff_assign_job_functions: AssignJobFunctionsUseCase
    staff_change_workload_profile: ChangeWorkloadProfileUseCase
    staff_declare_shift_preference: DeclareShiftPreferenceUseCase
    staff_register_unavailability: RegisterUnavailabilityUseCase
    staff_remove_unavailability: RemoveUnavailabilityUseCase
    staff_deactivate_employee: DeactivateEmployeeUseCase
    staff_reactivate_employee: ReactivateEmployeeUseCase
    staff_copy_employee_to_unit: CopyEmployeeToUnitUseCase
    # Stage 3.5 — o 17º use case de staff (R17). Consome `staff_identity_gateway`,
    # como `staff_deactivate_employee` passou a consumir (R13).
    staff_create_login_for_employee: CreateLoginForEmployeeUseCase

    # --- staff (Stage 3.4) ---------------------------------------------------
    #
    # **O único campo anotado com um port**, e a assimetria em relação a tudo o
    # que está acima é deliberada — o docstring do contêiner explica a regra: os
    # campos de use case levam a classe concreta porque use case é código nosso,
    # e o que precisa ser abstrato é o que ele **consome**. Aqui o campo **é** o
    # consumido: quem o recebe (o router da Stage 3.6) não pode ter de mudar
    # quando a implementação mudar — e ela mudou: era `_IdentityAccessGuard`,
    # privada deste módulo, e é `LocalAccessGuard`, de
    # `staff/adapters/out/identity/`, desde a issue #47 (ADR 0.0.0016).
    #
    # Nasce **sem consumidor**, como os 16 acima e pela mesma razão declarada:
    # nenhuma rota de staff existe até a Stage 3.6 (CA21).
    staff_access_guard: AccessGuard

    # --- staff (Stage 3.5) ---------------------------------------------------
    #
    # O segundo campo anotado com um port, pela mesma regra do primeiro: é o
    # **consumido**. A implementação é `LocalIdentityGateway` sobre a
    # `IdentityFacade` — a única aresta entre os dois BCs (ADR 3.5.0001), montada
    # aqui sobre os **mesmos** repositórios, `sender` e `clock` das rotas de
    # identity, não um segundo grafo. Consumido por `staff_create_login_for_employee`
    # (R17) e `staff_deactivate_employee` (R13) — a **mesma** instância nos dois.
    staff_identity_gateway: IdentityGateway


@dataclass
class HttpWiring:
    """O que `create_app()` registra, montado sem que ele conheça features.

    São três peças, e as três são necessárias: os routers; os registradores de
    handlers de erro (que recebem o `app`, porque só o app registra exception
    handlers); e o mapa de overrides, cujas chaves vivem dentro dos módulos de
    router.

    **Duas viraram coleção na Stage 3.6, e uma continua mapa único — a assimetria
    é do domínio, não descuido.** Um bounded context traz o seu router e o seu
    registrador de handlers, então esses dois são por-BC e se acumulam. Já as
    chaves de `dependency_overrides` são as **funções** `_get_*` definidas dentro
    de cada módulo de router: elas já são distintas por construção entre BCs, e um
    mapa por BC só criaria a oportunidade de duas entradas para a mesma chave.

    A forma escolhida — campos plurais — é equivalente em consequência a uma lista
    de `HttpWiring`, e nenhuma das duas atravessa a fronteira do composition root
    (concept §7 D5). A terceira forma possível, pendurar staff no router de
    identity, é estruturalmente proibida: faria um BC importar o adapter do outro.
    """

    routers: tuple[APIRouter, ...]
    register_error_handlers: tuple[Callable[[FastAPI], None], ...]
    dependency_overrides: dict[Callable[..., Any], Callable[..., Any]]


def wire_dependencies(
    settings: Settings | None = None,
    *,
    email_sender: EmailSender | None = None,
) -> ApplicationDependencies:
    """Monta o grafo de dependências completo e devolve o contêiner.

    Chamado uma única vez na inicialização da aplicação (dentro de `create_app()`).
    Em testes, pode receber um `Settings` apontando para outro banco ou com outros
    TTLs — é o que torna o TTL observável como configuração (CA25).

    **Sem singleton global.** O `Engine` é criado aqui e vive dentro dos
    repositórios que o receberam; não há variável de módulo guardando conexão. Duas
    chamadas devolvem dois grafos independentes.

    `create_engine` **não abre conexão** (o pool é preguiçoso), então montar o grafo
    não exige banco no ar e o boot da aplicação não falha por causa de um Postgres
    que ainda está subindo.

    **`email_sender` é uma costura, não um atalho de teste.** Escolher a
    implementação de um port é literalmente o trabalho deste módulo; expor o
    parâmetro é o que permite ao teste e2e trocar **só** o envio de e-mail —
    exigência do ADR 0.0.0004 §Decision 7, "nada sai da máquina" — sem alcançar
    atributo privado de use case depois de montado, e sem construir um segundo
    grafo (com um segundo `Engine`) só para descartar o primeiro. O default
    continua sendo o adapter de produção desta Stage.
    """
    cfg = settings or get_settings()
    engine = build_engine(cfg.database_url)

    restaurants = PostgresRestaurantRepository(engine)
    units = PostgresUnitRepository(engine)
    users = PostgresUserRepository(engine)
    sessions = PostgresSessionRepository(engine)

    setup_tokens = PostgresPasswordSetupTokenRepository(engine)
    # Stage 2.6 — a unidade de trabalho de identity sobre o MESMO `Engine` dos
    # repositórios acima: é chaveada por ele, e um repositório de outro engine
    # escreveria fora dela em silêncio (ADR 2.6.0001, concept 2.6 R7).
    identity_unit_of_work = PostgresUnitOfWork(engine)

    # Staff (Stage 3.3), sobre o **mesmo** `Engine` — não um novo. Os dois ports
    # se cruzam (L-JF3 consulta funcionário, L-E4 consulta função), e dois
    # `Engine` fariam a guarda de remoção e a validade referencial olharem para
    # pools distintos do mesmo banco sem ganho nenhum.
    staff_job_functions = PostgresJobFunctionRepository(engine)
    staff_employees = PostgresEmployeeRepository(engine)

    hasher = Argon2PasswordHasher()
    setup_token_issuer = Sha256SetupTokenIssuer()
    # `ConsoleSender` é o adapter desta Stage: escreve local, nada sai da máquina
    # (ADR 0.0.0004 §Decision 7). O provedor real (Resend, kickoff #7) entra na
    # 6.2 e é a troca de **uma linha** aqui — nenhum use case muda, porque todos
    # dependem do port `EmailSender`, não desta classe.
    sender = email_sender if email_sender is not None else ConsoleSender()
    token_issuer = JwtTokenIssuer(secret_key=cfg.jwt_secret_key, algorithm=cfg.jwt_algorithm)
    clock = SystemClock()
    id_generator = Uuid4Generator()

    # TTLs vêm da configuração, nunca de literal no corpo de use case
    # (concept §5 regra 12 — este número é a janela de revogação do produto).
    access_ttl = timedelta(minutes=cfg.access_token_ttl_minutes)
    refresh_ttl = timedelta(days=cfg.refresh_token_ttl_days)
    # Unidades diferentes de propósito — ver `Settings`: convite tolera dias de
    # atraso humano, redefinição de senha é emergência de minutos.
    invitation_ttl = timedelta(hours=cfg.invitation_token_ttl_hours)
    reset_ttl = timedelta(minutes=cfg.password_reset_token_ttl_minutes)
    # Stage 3.5 — o prazo do link entregue em mãos (canal `link` de R17). Distinto
    # do prazo do convite de propósito: o teste de wiring passa valores diferentes
    # para que trocar um pelo outro aqui não fique verde.
    handover_ttl = timedelta(hours=cfg.handover_link_ttl_hours)

    authorize_action = AuthorizeActionUseCase(users=users, units=units)

    guard = dependencies_module.IdentityGuard(
        token_issuer=token_issuer,
        authorize_action=authorize_action,
    )

    # O `AccessGuard` de staff (issue #47, ADR 0.0.0016): autoriza pela fachada
    # de acesso sobre o **mesmo** `AuthorizeActionUseCase` do guard das rotas de
    # identity, e autentica pelo **mesmo** `IdentityGuard` — não um segundo
    # grafo, não um segundo `Engine` (ADR 3.4.0001 §Implementation notes). CA15
    # assere as duas identidades de objeto: um segundo guard passaria em
    # qualquer teste de tipo e faria as duas bordas decidirem acesso sobre
    # estados diferentes. Este módulo só liga as peças — a tradução e a lei
    # L-AG3 moram no adapter.
    staff_access_guard = LocalAccessGuard(
        access=IdentityAccessFacade(authorize_action=authorize_action),
        authenticate_request=guard.authenticate_principal,
    )

    # Stage 3.5 — a fachada de identity e o gateway de staff sobre ela (ADR
    # 3.5.0001). Os quatro use cases da fachada (o quarto, de leitura, é da 3.8 —
    # ADR 3.8.0001 §3) recebem **os mesmos** `users`,
    # `restaurants`, `units`, `hasher`, `setup_tokens`, `sessions`, `sender` e
    # `clock` que servem as rotas de identity: um grafo, um `Engine`. O gateway
    # é o único módulo de staff que importa identity, e importa só a fachada.
    identity_facade = IdentityFacade(
        provision_account=ProvisionAccountUseCase(
            users=users,
            restaurants=restaurants,
            units=units,
            hasher=hasher,
            tokens=setup_tokens,
            token_issuer=setup_token_issuer,
            id_generator=id_generator,
            clock=clock,
            invitation_ttl=invitation_ttl,
            handover_ttl=handover_ttl,
            base_url=cfg.app_base_url,
            unit_of_work=identity_unit_of_work,
        ),
        send_invitation=SendInvitationUseCase(email_sender=sender),
        revoke_all_sessions=RevokeAllSessionsUseCase(sessions=sessions, clock=clock),
        get_account_role=GetAccountRoleUseCase(users=users),
    )
    staff_identity_gateway = LocalIdentityGateway(identity_facade)

    return ApplicationDependencies(
        identity_authenticate_user=AuthenticateUserUseCase(
            users=users,
            sessions=sessions,
            hasher=hasher,
            token_issuer=token_issuer,
            id_generator=id_generator,
            clock=clock,
            access_token_ttl=access_ttl,
            refresh_token_ttl=refresh_ttl,
        ),
        identity_refresh_session=RefreshSessionUseCase(
            users=users,
            sessions=sessions,
            token_issuer=token_issuer,
            id_generator=id_generator,
            clock=clock,
            access_token_ttl=access_ttl,
            refresh_token_ttl=refresh_ttl,
            unit_of_work=identity_unit_of_work,
        ),
        identity_revoke_session=RevokeSessionUseCase(
            sessions=sessions, token_issuer=token_issuer, clock=clock
        ),
        identity_provision_restaurant=ProvisionRestaurantUseCase(
            restaurants=restaurants,
            users=users,
            hasher=hasher,
            tokens=setup_tokens,
            token_issuer=setup_token_issuer,
            email_sender=sender,
            id_generator=id_generator,
            clock=clock,
            invitation_ttl=invitation_ttl,
            base_url=cfg.app_base_url,
            unit_of_work=identity_unit_of_work,
        ),
        identity_create_unit=CreateUnitUseCase(
            units=units, restaurants=restaurants, id_generator=id_generator
        ),
        identity_create_user=CreateUserUseCase(
            users=users,
            restaurants=restaurants,
            units=units,
            hasher=hasher,
            id_generator=id_generator,
        ),
        identity_invite_user=InviteUserUseCase(
            users=users,
            restaurants=restaurants,
            units=units,
            hasher=hasher,
            tokens=setup_tokens,
            token_issuer=setup_token_issuer,
            email_sender=sender,
            id_generator=id_generator,
            clock=clock,
            invitation_ttl=invitation_ttl,
            base_url=cfg.app_base_url,
            unit_of_work=identity_unit_of_work,
        ),
        identity_request_password_reset=RequestPasswordResetUseCase(
            users=users,
            tokens=setup_tokens,
            token_issuer=setup_token_issuer,
            email_sender=sender,
            id_generator=id_generator,
            clock=clock,
            reset_ttl=reset_ttl,
            base_url=cfg.app_base_url,
            unit_of_work=identity_unit_of_work,
        ),
        identity_set_password_with_token=SetPasswordWithTokenUseCase(
            users=users,
            sessions=sessions,
            tokens=setup_tokens,
            token_issuer=setup_token_issuer,
            hasher=hasher,
            clock=clock,
            unit_of_work=identity_unit_of_work,
        ),
        identity_authorize_action=authorize_action,
        identity_guard=guard,
        staff_create_job_function=CreateJobFunctionUseCase(
            job_functions=staff_job_functions, id_generator=id_generator, guard=staff_access_guard
        ),
        staff_rename_job_function=RenameJobFunctionUseCase(
            job_functions=staff_job_functions, guard=staff_access_guard
        ),
        staff_delete_job_function=DeleteJobFunctionUseCase(
            job_functions=staff_job_functions, employees=staff_employees, guard=staff_access_guard
        ),
        staff_list_job_functions=ListJobFunctionsUseCase(
            job_functions=staff_job_functions, guard=staff_access_guard
        ),
        staff_create_employee=CreateEmployeeUseCase(
            employees=staff_employees,
            job_functions=staff_job_functions,
            id_generator=id_generator,
            guard=staff_access_guard,
        ),
        staff_rename_employee=RenameEmployeeUseCase(
            employees=staff_employees, guard=staff_access_guard
        ),
        staff_list_employees=ListEmployeesUseCase(
            employees=staff_employees, guard=staff_access_guard
        ),
        staff_delete_employee=DeleteEmployeeUseCase(
            employees=staff_employees, guard=staff_access_guard
        ),
        staff_assign_job_functions=AssignJobFunctionsUseCase(
            employees=staff_employees, job_functions=staff_job_functions, guard=staff_access_guard
        ),
        staff_change_workload_profile=ChangeWorkloadProfileUseCase(
            employees=staff_employees, guard=staff_access_guard
        ),
        staff_declare_shift_preference=DeclareShiftPreferenceUseCase(
            employees=staff_employees, guard=staff_access_guard
        ),
        staff_register_unavailability=RegisterUnavailabilityUseCase(
            employees=staff_employees, guard=staff_access_guard
        ),
        staff_remove_unavailability=RemoveUnavailabilityUseCase(
            employees=staff_employees, guard=staff_access_guard
        ),
        staff_deactivate_employee=DeactivateEmployeeUseCase(
            employees=staff_employees, gateway=staff_identity_gateway, guard=staff_access_guard
        ),
        staff_reactivate_employee=ReactivateEmployeeUseCase(
            employees=staff_employees, guard=staff_access_guard
        ),
        staff_copy_employee_to_unit=CopyEmployeeToUnitUseCase(
            employees=staff_employees, id_generator=id_generator, guard=staff_access_guard
        ),
        staff_create_login_for_employee=CreateLoginForEmployeeUseCase(
            employees=staff_employees, gateway=staff_identity_gateway, guard=staff_access_guard
        ),
        staff_access_guard=staff_access_guard,
        staff_identity_gateway=staff_identity_gateway,
    )


def build_http_wiring(deps: ApplicationDependencies) -> HttpWiring:
    """Carrega os adapters HTTP dos dois BCs e monta o que `create_app()` registra.

    **É aqui que as 17 rotas de staff passam a existir na aplicação.** Até esta
    Stage o BC era surdo-mudo: os use cases e o `staff_access_guard` estavam
    montados e nada no boot os alcançava. Os seis módulos de borda entram por
    import **estático** desde a #45; até então vinham por `importlib`, porque o
    pacote se chamava `in`.

    `create_engine` não abre conexão, então registrar um segundo router não muda
    o comportamento de boot: montar o grafo continua não exigindo banco no ar.
    """
    overrides: dict[Callable[..., Any], Callable[..., Any]] = {
        router_module._get_authenticate_user: lambda: deps.identity_authenticate_user,
        router_module._get_refresh_session: lambda: deps.identity_refresh_session,
        router_module._get_revoke_session: lambda: deps.identity_revoke_session,
        router_module._get_provision_restaurant: lambda: deps.identity_provision_restaurant,
        router_module._get_create_unit: lambda: deps.identity_create_unit,
        router_module._get_create_user: lambda: deps.identity_create_user,
        router_module._get_invite_user: lambda: deps.identity_invite_user,
        router_module._get_request_password_reset: (lambda: deps.identity_request_password_reset),
        router_module._get_set_password_with_token: (lambda: deps.identity_set_password_with_token),
        router_module._get_guard: lambda: deps.identity_guard,
    }

    # As 17 entradas de staff: os 16 use cases mais o guard. Escritas uma a uma,
    # como as de identity, e não derivadas por convenção de nome: o wiring é o
    # lugar onde a ligação entre duas peças é **declarada**, e uma convenção aqui
    # trocaria um erro em tempo de boot por um `getattr` que acerta por acidente.
    # A completude é cobrada por teste que enumera os `_get_*` do router.
    overrides.update(
        {
            staff_dependencies_module.get_access_guard: lambda: deps.staff_access_guard,
            staff_router_module._get_create_job_function: (lambda: deps.staff_create_job_function),
            staff_router_module._get_list_job_functions: lambda: deps.staff_list_job_functions,
            staff_router_module._get_rename_job_function: (lambda: deps.staff_rename_job_function),
            staff_router_module._get_delete_job_function: (lambda: deps.staff_delete_job_function),
            staff_router_module._get_create_employee: lambda: deps.staff_create_employee,
            staff_router_module._get_list_employees: lambda: deps.staff_list_employees,
            staff_router_module._get_rename_employee: lambda: deps.staff_rename_employee,
            staff_router_module._get_delete_employee: lambda: deps.staff_delete_employee,
            staff_router_module._get_assign_job_functions: (
                lambda: deps.staff_assign_job_functions
            ),
            staff_router_module._get_change_workload_profile: (
                lambda: deps.staff_change_workload_profile
            ),
            staff_router_module._get_declare_shift_preference: (
                lambda: deps.staff_declare_shift_preference
            ),
            staff_router_module._get_register_unavailability: (
                lambda: deps.staff_register_unavailability
            ),
            staff_router_module._get_remove_unavailability: (
                lambda: deps.staff_remove_unavailability
            ),
            staff_router_module._get_deactivate_employee: (lambda: deps.staff_deactivate_employee),
            staff_router_module._get_reactivate_employee: (lambda: deps.staff_reactivate_employee),
            staff_router_module._get_create_login_for_employee: (
                lambda: deps.staff_create_login_for_employee
            ),
            staff_router_module._get_copy_employee_to_unit: (
                lambda: deps.staff_copy_employee_to_unit
            ),
        }
    )

    return HttpWiring(
        routers=(router_module.router, staff_router_module.router),
        register_error_handlers=(
            error_handlers_module.register_identity_error_handlers,
            staff_error_handlers_module.register_staff_error_handlers,
        ),
        dependency_overrides=overrides,
    )
