"""Testes da fachada de identity — Stage 3.5, CA18 (ADR 3.5.0001).

Três coisas são contrato e cada uma tem o seu bloco:

1. **Conversão** — primitivo entra, VO chega ao use case (asserido sobre o
   command capturado por um espião **e** sobre o estado dos fakes com os use
   cases reais, para que o espião não seja a única testemunha).
2. **Transparência a exceções** — o que o use case levanta sobe **na mesma
   instância**; a fachada não captura, não traduz, não embrulha.
3. **Re-exportação** — `facade.EmailAlreadyRegisteredError` **é** a classe de
   `errors.py`, e `facade.InvalidEmailError` **é** a de `domain/exceptions`, para
   que o consumidor importe um módulo só e capture o mesmo tipo que o use case
   levanta.
"""

import dataclasses
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

import pytest

from restaurant_hub.features.identity.application import errors as erros_de_application
from restaurant_hub.features.identity.application import facade as modulo_facade
from restaurant_hub.features.identity.application.dtos.commands import (
    GetAccountRoleCommand,
    ProvisionAccountCommand,
    RevokeAllSessionsCommand,
    SendInvitationCommand,
)
from restaurant_hub.features.identity.application.dtos.identifiers import PasswordHash
from restaurant_hub.features.identity.application.dtos.results import (
    AccountRoleResult,
    ProvisionedAccountResult,
    UserResult,
)
from restaurant_hub.features.identity.application.errors import RoleNotProvisionableError
from restaurant_hub.features.identity.application.facade import (
    AccessGrant,
    AccessPrincipal,
    IdentityAccessFacade,
    IdentityFacade,
    ProvisionedAccount,
)
from restaurant_hub.features.identity.application.use_cases.authorize_action import (
    AuthorizeActionUseCase,
)
from restaurant_hub.features.identity.application.use_cases.get_account_role import (
    GetAccountRoleUseCase,
)
from restaurant_hub.features.identity.application.use_cases.provision_account import (
    ProvisionAccountUseCase,
)
from restaurant_hub.features.identity.application.use_cases.revoke_all_sessions import (
    RevokeAllSessionsUseCase,
)
from restaurant_hub.features.identity.application.use_cases.send_invitation import (
    SendInvitationUseCase,
)
from restaurant_hub.features.identity.domain.entities.restaurant import Restaurant
from restaurant_hub.features.identity.domain.entities.unit import Unit
from restaurant_hub.features.identity.domain.entities.user import User
from restaurant_hub.features.identity.domain.exceptions import errors as erros_de_dominio
from restaurant_hub.features.identity.domain.exceptions.errors import (
    InvalidEmailError,
    InvalidRoleError,
)
from restaurant_hub.features.identity.domain.value_objects.email import Email
from restaurant_hub.features.identity.domain.value_objects.identifiers import (
    RestaurantId,
    UnitId,
    UserId,
)
from restaurant_hub.features.identity.domain.value_objects.role import Role
from tests.fakes.features.identity.fake_password_hasher import FakePasswordHasher
from tests.fakes.features.identity.fake_setup_token_issuer import FakeSetupTokenIssuer
from tests.fakes.features.identity.in_memory_password_setup_token_repository import (
    InMemoryPasswordSetupTokenRepository,
)
from tests.fakes.features.identity.in_memory_restaurant_repository import (
    InMemoryRestaurantRepository,
)
from tests.fakes.features.identity.in_memory_session_repository import (
    InMemorySessionRepository,
)
from tests.fakes.features.identity.in_memory_unit_of_work import InMemoryUnitOfWork
from tests.fakes.features.identity.in_memory_unit_repository import InMemoryUnitRepository
from tests.fakes.features.identity.in_memory_user_repository import InMemoryUserRepository
from tests.fakes.shared.fake_clock import FakeClock
from tests.fakes.shared.fake_id_generator import FakeIdGenerator
from tests.fakes.shared.recording_email_sender import (
    EmailSenderFailure,
    RecordingEmailSender,
)

pytestmark = pytest.mark.unit

_AGORA = datetime(2026, 9, 14, 12, 0, tzinfo=UTC)
_BASE_URL = "https://app.exemplo.com"


# ---------------------------------------------------------------------------
# Espiões — capturam o command e devolvem/levantam o que o teste mandar
# ---------------------------------------------------------------------------


class _EspiaoDeProvisionamento(ProvisionAccountUseCase):
    """Não chama `super().__init__`: não tem grafo, só memória do que recebeu."""

    def __init__(self, *, levanta: Exception | None = None) -> None:
        self.commands: list[ProvisionAccountCommand] = []
        self._levanta = levanta

    def execute(self, command: ProvisionAccountCommand) -> ProvisionedAccountResult:
        self.commands.append(command)
        if self._levanta is not None:
            raise self._levanta
        return ProvisionedAccountResult(
            user=UserResult(
                id=UserId("user-99"),
                email=command.email,
                role=command.role,
                tenant_id=command.tenant_id,
                unit_ids=tuple(command.unit_ids),
            ),
            setup_link=f"{_BASE_URL}/definir-senha?token=setup-99",
        )


class _EspiaoDeEnvio(SendInvitationUseCase):
    def __init__(self, *, levanta: Exception | None = None) -> None:
        self.commands: list[SendInvitationCommand] = []
        self._levanta = levanta

    def execute(self, command: SendInvitationCommand) -> None:
        self.commands.append(command)
        if self._levanta is not None:
            raise self._levanta


class _EspiaoDeRevogacao(RevokeAllSessionsUseCase):
    def __init__(self, *, levanta: Exception | None = None) -> None:
        self.commands: list[RevokeAllSessionsCommand] = []
        self._levanta = levanta

    def execute(self, command: RevokeAllSessionsCommand) -> None:
        self.commands.append(command)
        if self._levanta is not None:
            raise self._levanta


class _EspiaoDePapel(GetAccountRoleUseCase):
    def __init__(
        self, *, devolve: AccountRoleResult | None = None, levanta: Exception | None = None
    ) -> None:
        self.commands: list[GetAccountRoleCommand] = []
        self._devolve = devolve
        self._levanta = levanta

    def execute(self, command: GetAccountRoleCommand) -> AccountRoleResult | None:
        self.commands.append(command)
        if self._levanta is not None:
            raise self._levanta
        return self._devolve


def _fachada_espia(
    *,
    provision: _EspiaoDeProvisionamento | None = None,
    send: _EspiaoDeEnvio | None = None,
    revoke: _EspiaoDeRevogacao | None = None,
    role: _EspiaoDePapel | None = None,
) -> tuple[IdentityFacade, _EspiaoDeProvisionamento, _EspiaoDeEnvio, _EspiaoDeRevogacao]:
    """O espião do papel não volta na tupla: quem o quer passa o seu e o guarda."""
    provision = provision or _EspiaoDeProvisionamento()
    send = send or _EspiaoDeEnvio()
    revoke = revoke or _EspiaoDeRevogacao()
    role = role or _EspiaoDePapel()
    return IdentityFacade(provision, send, revoke, role), provision, send, revoke


def _provisionar(  # noqa: PLR0913 — os cinco argumentos nomeados da fachada, com defaults
    fachada: IdentityFacade,
    *,
    email: str = "Maria@Cantina.com",
    role: str = "employee",
    tenant_id: str = "rest-a",
    unit_ids: Sequence[str] = ("unit-a1",),
    handed_over: bool = False,
) -> ProvisionedAccount:
    return fachada.provision_account(
        email=email,
        role=role,
        tenant_id=tenant_id,
        unit_ids=unit_ids,
        handed_over=handed_over,
    )


class TestConversaoDePrimitivos:
    def test_provision_converte_cada_primitivo_no_vo_correspondente(self) -> None:
        """CA18 — o consumidor manda `str`; o use case recebe VO."""
        fachada, espiao, _, _ = _fachada_espia()

        _provisionar(fachada, unit_ids=["unit-a1", "unit-a2"])

        (command,) = espiao.commands
        assert command.email == Email("maria@cantina.com")  # normalizado pelo VO
        assert command.role is Role.EMPLOYEE
        assert command.tenant_id == RestaurantId("rest-a")
        assert command.unit_ids == (UnitId("unit-a1"), UnitId("unit-a2"))
        assert isinstance(command.unit_ids, tuple)

    @pytest.mark.parametrize("handed_over", [True, False])
    def test_handed_over_e_repassado_sem_inversao(self, handed_over: bool) -> None:
        fachada, espiao, _, _ = _fachada_espia()

        _provisionar(fachada, handed_over=handed_over)

        assert espiao.commands[0].handed_over is handed_over

    def test_provision_devolve_primitivos_do_result(self) -> None:
        fachada, _, _, _ = _fachada_espia()

        conta = _provisionar(fachada)

        assert conta == ProvisionedAccount(
            user_id="user-99", setup_link=f"{_BASE_URL}/definir-senha?token=setup-99"
        )
        assert isinstance(conta.user_id, str)
        # `repr=False`: o link não sai em traceback do consumidor.
        assert "setup-99" not in repr(conta)

    def test_provisioned_account_e_frozen(self) -> None:
        """O DTO da fachada fica fora da varredura de `dtos/*` — o pino é aqui.

        Achado do Checkpoint C (bloco 3): `frozen=False` sobrevivia à suíte, porque
        `==` independe de `frozen` e a varredura de imutabilidade só olha os
        módulos internos de DTO.
        """
        assert ProvisionedAccount.__dataclass_params__.frozen  # type: ignore[attr-defined]
        campos = {campo.name: campo for campo in dataclasses.fields(ProvisionedAccount)}
        assert campos["setup_link"].repr is False

    def test_send_invitation_converte_o_email_e_repassa_o_link_intacto(self) -> None:
        fachada, _, espiao, _ = _fachada_espia()
        link = f"{_BASE_URL}/definir-senha?token=setup-7"

        fachada.send_invitation(user_id="user-7", email="  Joao@Cantina.com ", setup_link=link)

        (command,) = espiao.commands
        assert command.user_id == UserId("user-7")
        assert command.email == Email("joao@cantina.com")
        assert command.setup_link == link

    def test_revoke_all_sessions_converte_o_user_id(self) -> None:
        fachada, _, _, espiao = _fachada_espia()

        fachada.revoke_all_sessions("user-42")

        assert espiao.commands == [RevokeAllSessionsCommand(user_id=UserId("user-42"))]

    @pytest.mark.parametrize("papel", list(Role), ids=lambda papel: papel.value)
    def test_account_role_converte_o_user_id_e_devolve_o_valor_do_papel(self, papel: Role) -> None:
        espiao = _EspiaoDePapel(devolve=AccountRoleResult(role=papel))
        fachada, _, _, _ = _fachada_espia(role=espiao)

        papel_devolvido = fachada.account_role("user-42")

        assert papel_devolvido == papel.value
        # `Role` é `StrEnum`: o `==` acima passaria com o enum. O tipo é o que
        # trava a propriedade 1 — o consumidor não recebe tipos de identity.
        assert type(papel_devolvido) is str
        assert espiao.commands == [GetAccountRoleCommand(user_id=UserId("user-42"))]

    def test_account_role_de_conta_desconhecida_e_none(self) -> None:
        fachada, _, _, _ = _fachada_espia(role=_EspiaoDePapel(devolve=None))

        assert fachada.account_role("nunca-existiu") is None

    def test_cada_operacao_chama_so_o_seu_use_case(self) -> None:
        papel = _EspiaoDePapel()
        fachada, provision, send, revoke = _fachada_espia(role=papel)

        _provisionar(fachada)

        assert len(provision.commands) == 1
        assert send.commands == []
        assert revoke.commands == []
        assert papel.commands == []


class TestTransparenciaAExcecoes:
    """A fachada não captura, não traduz, não embrulha — a **mesma instância** sobe."""

    def test_excecao_do_provisionamento_sobe_na_mesma_instancia(self) -> None:
        falha = erros_de_application.EmailAlreadyRegisteredError("maria@cantina.com")
        fachada, _, _, _ = _fachada_espia(provision=_EspiaoDeProvisionamento(levanta=falha))

        with pytest.raises(erros_de_application.EmailAlreadyRegisteredError) as excinfo:
            _provisionar(fachada)

        assert excinfo.value is falha

    def test_excecao_do_envio_sobe_na_mesma_instancia(self) -> None:
        falha = EmailSenderFailure("smtp fora")
        fachada, _, _, _ = _fachada_espia(send=_EspiaoDeEnvio(levanta=falha))

        with pytest.raises(EmailSenderFailure) as excinfo:
            fachada.send_invitation(
                user_id="user-1", email="a@b.com", setup_link="https://x/definir-senha?token=t"
            )

        assert excinfo.value is falha

    def test_excecao_da_consulta_de_papel_sobe_na_mesma_instancia(self) -> None:
        falha = RuntimeError("banco fora")
        fachada, _, _, _ = _fachada_espia(role=_EspiaoDePapel(levanta=falha))

        with pytest.raises(RuntimeError) as excinfo:
            fachada.account_role("user-1")

        assert excinfo.value is falha

    def test_excecao_da_revogacao_sobe_na_mesma_instancia(self) -> None:
        falha = RuntimeError("banco fora")
        fachada, _, _, _ = _fachada_espia(revoke=_EspiaoDeRevogacao(levanta=falha))

        with pytest.raises(RuntimeError) as excinfo:
            fachada.revoke_all_sessions("user-1")

        assert excinfo.value is falha

    def test_email_invalido_levanta_antes_de_chegar_ao_use_case(self) -> None:
        """A conversão é da fachada — e o erro é o de domínio, sem tradução."""
        fachada, espiao, _, _ = _fachada_espia()

        with pytest.raises(InvalidEmailError):
            _provisionar(fachada, email="sem-arroba")

        assert espiao.commands == []

    def test_email_com_byte_nul_e_recusado_pela_fachada(self) -> None:
        """D8 da 3.5 — o VO barra o NUL, então o gateway de staff traduz para 422."""
        fachada, espiao, _, _ = _fachada_espia()

        with pytest.raises(InvalidEmailError):
            _provisionar(fachada, email="maria\x00@cantina.com")

        assert espiao.commands == []

    def test_papel_desconhecido_levanta_invalid_role_error(self) -> None:
        fachada, espiao, _, _ = _fachada_espia()

        with pytest.raises(InvalidRoleError):
            _provisionar(fachada, role="ceo")

        assert espiao.commands == []

    @pytest.mark.parametrize("papel", ["owner", "manager", "hr", "platform_admin"])
    def test_papel_que_nao_e_employee_e_recusado_sem_efeito(self, papel: str) -> None:
        """CA10 (Stage 2.7, ADR 2.7.0001 §Decision 5) — a fachada cria contas sem
        autorizar, então só serve o login de funcionário. Outro papel válido seria
        conta privilegiada criada sem "não se concede o que não se detém"."""
        fachada, espiao, _, _ = _fachada_espia()

        with pytest.raises(RoleNotProvisionableError) as erro:
            _provisionar(fachada, role=papel)

        assert erro.value.role == papel
        assert espiao.commands == []

    def test_o_papel_e_checado_antes_do_email(self) -> None:
        """CA10 — o domínio de entrada decide antes do formato: com e-mail inválido e
        papel recusado, sobe a recusa do papel."""
        fachada, espiao, _, _ = _fachada_espia()

        with pytest.raises(RoleNotProvisionableError):
            _provisionar(fachada, role="owner", email="sem-arroba")

        assert espiao.commands == []


class TestReexportacao:
    def test_reexporta_as_mesmas_classes_de_excecao(self) -> None:
        """Identidade de classe, não igualdade de nome: o `except` do consumidor
        tem de casar o objeto que o use case levanta."""
        assert (
            modulo_facade.EmailAlreadyRegisteredError
            is erros_de_application.EmailAlreadyRegisteredError
        )
        assert modulo_facade.InvalidEmailError is erros_de_dominio.InvalidEmailError

    def test_all_declara_exatamente_a_superficie_publica(self) -> None:
        # A fachada de acesso e os seus dois tipos, mais a exceção de L-AG3,
        # entraram com a issue #47 (ADR 0.0.0016).
        assert set(modulo_facade.__all__) == {
            "AccessGrant",
            "AccessPrincipal",
            "EmailAlreadyRegisteredError",
            "IdentityAccessFacade",
            "IdentityFacade",
            "InvalidEmailError",
            "PermissionDeniedError",
            "ProvisionedAccount",
        }


class TestSobreOsUseCasesReais:
    """O espião não é a única testemunha: o grafo real de fakes confirma a conversão."""

    def _fachada_real(
        self, users: InMemoryUserRepository | None = None
    ) -> tuple[IdentityFacade, InMemoryUserRepository, RecordingEmailSender]:
        users = users or InMemoryUserRepository()
        restaurants = InMemoryRestaurantRepository()
        units = InMemoryUnitRepository()
        restaurants.add(Restaurant(id=RestaurantId("rest-a"), name="Cantina A"))
        units.add(Unit(id=UnitId("unit-a1"), restaurant_id=RestaurantId("rest-a"), name="Centro"))
        sender = RecordingEmailSender()
        clock = FakeClock(_AGORA)
        tokens = InMemoryPasswordSetupTokenRepository()
        fachada = IdentityFacade(
            ProvisionAccountUseCase(
                users=users,
                restaurants=restaurants,
                units=units,
                hasher=FakePasswordHasher(),
                tokens=tokens,
                token_issuer=FakeSetupTokenIssuer(),
                id_generator=FakeIdGenerator(),
                clock=clock,
                invitation_ttl=timedelta(hours=72),
                handover_ttl=timedelta(hours=168),
                base_url=_BASE_URL,
                unit_of_work=InMemoryUnitOfWork(users, tokens),
            ),
            SendInvitationUseCase(sender),
            RevokeAllSessionsUseCase(InMemorySessionRepository(), clock),
            GetAccountRoleUseCase(users),
        )
        return fachada, users, sender

    def test_o_papel_da_conta_provisionada_e_employee_e_o_desconhecido_e_none(self) -> None:
        fachada, _, _ = self._fachada_real()
        conta = _provisionar(fachada)

        papel = fachada.account_role(conta.user_id)

        assert papel == "employee"
        assert type(papel) is str  # não o `Role` (StrEnum) — propriedade 1
        assert fachada.account_role("nunca-existiu") is None

    def test_falha_do_repositorio_atravessa_use_case_e_fachada(self) -> None:
        """A exceção **do repositório**, não a de um espião: prova o caminho inteiro."""
        falha = RuntimeError("banco fora")

        class _UsuariosQueFalham(InMemoryUserRepository):
            def find_by_id(self, user_id: UserId) -> User | None:
                raise falha

        fachada, _, _ = self._fachada_real(_UsuariosQueFalham())

        with pytest.raises(RuntimeError) as excinfo:
            fachada.account_role("user-1")

        assert excinfo.value is falha

    def test_provisiona_e_envia_pelo_grafo_real(self) -> None:
        fachada, users, sender = self._fachada_real()

        conta = _provisionar(fachada)
        fachada.send_invitation(
            user_id=conta.user_id, email="maria@cantina.com", setup_link=conta.setup_link
        )

        usuario = users.users[UserId(conta.user_id)]
        assert usuario.email == Email("maria@cantina.com")
        assert usuario.role is Role.EMPLOYEE
        assert usuario.tenant_id == RestaurantId("rest-a")
        assert [m.unit_id for m in users.memberships] == [UnitId("unit-a1")]
        assert conta.setup_link.startswith(f"{_BASE_URL}/definir-senha?token=")
        assert conta.setup_link in sender.sent[0].body_text

    def test_falha_do_envio_atravessa_trocada_com_o_id_da_conta(self) -> None:
        """Issue #175 — pelo grafo real, a falha do sender chega à fachada trocada.

        O consumidor recebe `InvitationNotSentError` com o id da conta, sem cadeia
        até a falha do provedor, cuja mensagem poderia ecoar destinatário e link.
        """
        fachada, _, sender = self._fachada_real()
        conta = _provisionar(fachada)
        sender.start_failing(EmailSenderFailure(f"recusado: {conta.setup_link}"))

        with pytest.raises(erros_de_application.InvitationNotSentError) as excinfo:
            fachada.send_invitation(
                user_id=conta.user_id, email="maria@cantina.com", setup_link=conta.setup_link
            )

        assert excinfo.value.user_id == conta.user_id
        assert excinfo.value.__cause__ is None
        assert excinfo.value.__context__ is None
        assert conta.setup_link not in str(excinfo.value)

    def test_email_repetido_sobe_como_a_excecao_reexportada(self) -> None:
        fachada, _, _ = self._fachada_real()
        _provisionar(fachada)

        with pytest.raises(modulo_facade.EmailAlreadyRegisteredError):
            _provisionar(fachada)


# ---------------------------------------------------------------------------
# A fachada de acesso (issue #47, ADR 0.0.0016)
#
# Sobre o use case **real** e os fakes de identity: a fachada de acesso não
# tem estado próprio, e um espião do use case testaria só a conversão — a
# metade que importa é que os dois oráculos fechados pela borda (a função
# `authorize_at_boundary`) também se fecham por aqui.
# ---------------------------------------------------------------------------


class TestFachadaDeAcesso:
    _TENANT = "rest-a"
    _UNIDADE = "unit-a1"

    def _montar(self) -> tuple[IdentityAccessFacade, InMemoryUserRepository]:
        users = InMemoryUserRepository()
        units = InMemoryUnitRepository()
        units.add(
            Unit(id=UnitId(self._UNIDADE), restaurant_id=RestaurantId(self._TENANT), name="C")
        )
        units.add(Unit(id=UnitId("unit-b1"), restaurant_id=RestaurantId("rest-b"), name="B"))
        for user_id, role, tenant in (
            ("gerente", Role.MANAGER, self._TENANT),
            ("dono", Role.OWNER, self._TENANT),
            ("admin", Role.PLATFORM_ADMIN, None),
        ):
            user = User(
                id=UserId(user_id),
                email=Email(f"{user_id}@x.com"),
                role=role,
                tenant_id=RestaurantId(tenant) if tenant is not None else None,
            )
            vinculos = (
                [user.link_to_unit(units.units[UnitId(self._UNIDADE)])]
                if role is Role.MANAGER
                else []
            )
            users.add(user, PasswordHash("hashed::x"), vinculos)
        return IdentityAccessFacade(AuthorizeActionUseCase(users=users, units=units)), users

    def _principal(
        self, user_id: str = "gerente", tenant: str | None = "rest-a"
    ) -> AccessPrincipal:
        return AccessPrincipal(user_id=user_id, tenant_id=tenant)

    def test_concede_e_devolve_o_escopo_em_texto(self) -> None:
        fachada, _ = self._montar()

        grant = fachada.authorize(
            self._principal(), "manage_staff", tenant_id=self._TENANT, unit_id=self._UNIDADE
        )

        assert grant == AccessGrant(
            role="manager", actor_tenant_id=self._TENANT, scope_unit_id=self._UNIDADE
        )
        assert type(grant.role) is str

    def test_permissao_tenant_wide_volta_sem_unidade(self) -> None:
        fachada, _ = self._montar()

        grant = fachada.authorize(
            self._principal(), "manage_job_functions", tenant_id=self._TENANT, unit_id=None
        )

        assert grant.scope_unit_id is None
        assert grant.actor_tenant_id == self._TENANT

    def test_ator_sem_tenant_volta_com_actor_tenant_id_ausente(self) -> None:
        """A fachada **não** impõe L-AG3 — é lei de staff, e o adapter de staff a impõe."""
        fachada, _ = self._montar()

        grant = fachada.authorize(
            self._principal("admin", None), "manage_platform", tenant_id=None, unit_id=None
        )

        assert grant.actor_tenant_id is None
        assert grant.role == "platform_admin"

    def test_o_tenant_omitido_chega_omitido_e_a_decisao_o_recusa(self) -> None:
        """A fachada não resolve a omissão: é do chamador (ADR 0.0.0005, cláusula 3)."""
        fachada, _ = self._montar()

        with pytest.raises(erros_de_application.TenantScopeRequiredError):
            fachada.authorize(
                self._principal(), "manage_staff", tenant_id=None, unit_id=self._UNIDADE
            )

    def test_tenant_vazio_nomeado_e_negado_e_nao_tratado_como_omitido(self) -> None:
        fachada, _ = self._montar()

        with pytest.raises(erros_de_application.TenantNotVisibleError):
            fachada.authorize(
                self._principal(), "manage_staff", tenant_id="", unit_id=self._UNIDADE
            )

    def test_ator_inexistente_e_o_401_da_borda(self) -> None:
        fachada, _ = self._montar()

        with pytest.raises(erros_de_application.InvalidAccessTokenError):
            fachada.authorize(
                self._principal("sumiu"),
                "manage_staff",
                tenant_id=self._TENANT,
                unit_id=self._UNIDADE,
            )

    def test_unidade_inexistente_e_indistinguivel_de_invisivel(self) -> None:
        fachada, _ = self._montar()

        with pytest.raises(erros_de_application.UnitNotVisibleError):
            fachada.authorize(
                self._principal(), "manage_staff", tenant_id=self._TENANT, unit_id="nao-existe"
            )

    def test_unidade_de_outro_tenant_e_negada(self) -> None:
        fachada, _ = self._montar()

        with pytest.raises(erros_de_application.TenantNotVisibleError):
            fachada.authorize(
                self._principal(), "manage_staff", tenant_id=self._TENANT, unit_id="unit-b1"
            )

    def test_negacao_de_rbac_sobe_crua(self) -> None:
        fachada, _ = self._montar()

        with pytest.raises(erros_de_application.PermissionDeniedError):
            fachada.authorize(
                self._principal(), "manage_tenant", tenant_id=self._TENANT, unit_id=None
            )

    def test_nome_de_permissao_desconhecido_e_defeito_e_nao_negacao(self) -> None:
        fachada, _ = self._montar()

        with pytest.raises(ValueError, match="manage_stafff"):
            fachada.authorize(
                self._principal(), "manage_stafff", tenant_id=self._TENANT, unit_id=None
            )

    def test_permission_denied_e_re_exportado_da_application(self) -> None:
        """O adapter de staff levanta L-AG3 com esta classe — e ela tem de ser a de identity."""
        assert modulo_facade.PermissionDeniedError is erros_de_application.PermissionDeniedError

    # --- Auditoria de testes da issue #47 — mutantes que sobreviviam -------

    def test_actor_tenant_id_e_o_do_ator_no_banco_e_nao_o_alvo_pedido(self) -> None:
        """Sobrevivia: devolver o tenant **pedido** como `actor_tenant_id`.

        É o campo sobre o qual o adapter de staff impõe L-AG3. `platform_admin`
        pula o passo 3, então nomear um tenant passa — e o grant tem de voltar
        **sem** tenant, para que staff o negue. Com o tenant pedido no lugar, o
        ator sem tenant sairia com escopo do restaurante que quisesse.
        """
        fachada, _ = self._montar()

        grant = fachada.authorize(
            self._principal("admin", None), "manage_platform", tenant_id=self._TENANT, unit_id=None
        )

        assert grant.actor_tenant_id is None

    @pytest.mark.parametrize(
        ("valor", "campo"),
        [
            (AccessPrincipal(user_id="u", tenant_id="t"), "tenant_id"),
            (
                AccessGrant(role="manager", actor_tenant_id="t", scope_unit_id=None),
                "actor_tenant_id",
            ),
        ],
        ids=["principal", "grant"],
    )
    def test_principal_e_grant_sao_imutaveis(self, valor: object, campo: str) -> None:
        """Sobrevivia: tirar `frozen` — o ator que decide acesso não pode ter o tenant reescrito."""
        with pytest.raises(dataclasses.FrozenInstanceError):
            setattr(valor, campo, "outro")
