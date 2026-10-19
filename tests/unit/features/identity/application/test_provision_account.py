"""Testes do use case `provision_account` — Stage 3.5, CA15; Stage 2.6, CA4.

O que estes testes protegem: a conta nasce **sem senha utilizável**, o token
ganha o **prazo do canal**, nenhum e-mail sai daqui, e o link devolvido é o
**único** lugar onde o valor do token aparece — com a forma exata que o front-end
consome. A ordem das checagens é a de `InviteUserUseCase`, e o teste de
precedência da 2.5 está replicado porque a ordem é contrato, não detalhe.
"""

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

import pytest

from restaurant_hub.features.identity.application.dtos.commands import (
    ProvisionAccountCommand,
)
from restaurant_hub.features.identity.application.dtos.identifiers import PasswordHash
from restaurant_hub.features.identity.application.dtos.setup_tokens import (
    PasswordSetupToken,
    SetupTokenPurpose,
)
from restaurant_hub.features.identity.application.errors import (
    EmailAlreadyRegisteredError,
    RestaurantNotFoundError,
    UnitNotFoundError,
)
from restaurant_hub.features.identity.application.use_cases.provision_account import (
    ProvisionAccountUseCase,
)
from restaurant_hub.features.identity.domain.entities.restaurant import Restaurant
from restaurant_hub.features.identity.domain.entities.unit import Unit
from restaurant_hub.features.identity.domain.entities.user import User
from restaurant_hub.features.identity.domain.exceptions.errors import (
    CrossTenantError,
    PlatformAdminMembershipError,
)
from restaurant_hub.features.identity.domain.value_objects.email import Email
from restaurant_hub.features.identity.domain.value_objects.identifiers import (
    RestaurantId,
    UnitId,
)
from restaurant_hub.features.identity.domain.value_objects.role import Role
from restaurant_hub.features.identity.domain.value_objects.unit_membership import (
    UnitMembership,
)
from tests.fakes.features.identity.fake_password_hasher import FakePasswordHasher
from tests.fakes.features.identity.fake_setup_token_issuer import FakeSetupTokenIssuer
from tests.fakes.features.identity.in_memory_password_setup_token_repository import (
    InMemoryPasswordSetupTokenRepository,
)
from tests.fakes.features.identity.in_memory_restaurant_repository import (
    InMemoryRestaurantRepository,
)
from tests.fakes.features.identity.in_memory_unit_of_work import InMemoryUnitOfWork
from tests.fakes.features.identity.in_memory_unit_repository import InMemoryUnitRepository
from tests.fakes.features.identity.in_memory_user_repository import InMemoryUserRepository
from tests.fakes.shared.fake_clock import FakeClock
from tests.fakes.shared.fake_id_generator import FakeIdGenerator

pytestmark = pytest.mark.unit

_AGORA = datetime(2026, 9, 14, 12, 0, tzinfo=UTC)
# Distintos de propósito: com prazos iguais o teste do canal seria vácuo.
_TTL_CONVITE = timedelta(hours=72)
_TTL_EM_MAOS = timedelta(hours=168)
_BASE_URL = "https://app.exemplo.com"


class _FalhaInjetada(Exception):
    pass


class _Registro:
    """Ordem das escritas tentadas, compartilhada pelos injetores, e onde falhar."""

    def __init__(self, falhar_em: int | None = None) -> None:
        self.falhar_em = falhar_em
        self.escritas: list[str] = []

    def escreveu(self, nome: str) -> None:
        self.escritas.append(nome)
        if self.falhar_em is not None and len(self.escritas) == self.falhar_em:
            raise _FalhaInjetada(nome)


class _UsuariosRegistrados(InMemoryUserRepository):
    def __init__(self, registro: _Registro) -> None:
        super().__init__()
        self._registro = registro

    def add(
        self,
        user: User,
        password_hash: PasswordHash,
        memberships: Sequence[UnitMembership] = (),
    ) -> None:
        super().add(user, password_hash, memberships)
        self._registro.escreveu("users.add")


class _TokensRegistrados(InMemoryPasswordSetupTokenRepository):
    def __init__(self, registro: _Registro) -> None:
        super().__init__()
        self._registro = registro

    def add(self, token: PasswordSetupToken) -> None:
        super().add(token)
        self._registro.escreveu("tokens.add")


class Cenario:
    """Grafo de fakes montado uma vez — **sem `EmailSender`**: o use case não envia."""

    def __init__(self, *, base_url: str = _BASE_URL, registro: _Registro | None = None) -> None:
        self.users = (
            _UsuariosRegistrados(registro) if registro is not None else InMemoryUserRepository()
        )
        self.restaurants = InMemoryRestaurantRepository()
        self.units = InMemoryUnitRepository()
        self.hasher = FakePasswordHasher()
        self.tokens = (
            _TokensRegistrados(registro)
            if registro is not None
            else InMemoryPasswordSetupTokenRepository()
        )
        self.issuer = FakeSetupTokenIssuer()
        self.clock = FakeClock(_AGORA)

        self.restaurants.add(Restaurant(id=RestaurantId("rest-a"), name="Cantina A"))
        self.restaurants.add(Restaurant(id=RestaurantId("rest-b"), name="Cantina B"))
        self.units.add(
            Unit(id=UnitId("unit-a1"), restaurant_id=RestaurantId("rest-a"), name="Centro")
        )
        self.units.add(
            Unit(id=UnitId("unit-b1"), restaurant_id=RestaurantId("rest-b"), name="Outra")
        )

        self.unidade = InMemoryUnitOfWork(self.users, self.tokens)
        self.use_case = ProvisionAccountUseCase(
            users=self.users,
            restaurants=self.restaurants,
            units=self.units,
            hasher=self.hasher,
            tokens=self.tokens,
            token_issuer=self.issuer,
            id_generator=FakeIdGenerator(),
            clock=self.clock,
            invitation_ttl=_TTL_CONVITE,
            handover_ttl=_TTL_EM_MAOS,
            base_url=base_url,
            unit_of_work=self.unidade,
        )


def _comando(
    email: str = "funcionario@x.com",
    role: Role = Role.EMPLOYEE,
    tenant: str | None = "rest-a",
    unit_ids: tuple[str, ...] = ("unit-a1",),
    *,
    handed_over: bool = False,
) -> ProvisionAccountCommand:
    return ProvisionAccountCommand(
        email=Email(email),
        role=role,
        tenant_id=RestaurantId(tenant) if tenant is not None else None,
        unit_ids=tuple(UnitId(u) for u in unit_ids),
        handed_over=handed_over,
    )


def _valor_do_link(link: str) -> str:
    """Extrai o valor do token do link, como a pessoa faria ao abri-lo."""
    _, _, resto = link.partition("token=")
    return resto


class TestCaminhoFeliz:
    def test_cria_a_conta_com_hash_inutilizavel(self) -> None:
        """CA15 — a conta nasce sem senha que alguém consiga usar (ADR 2.5.0004)."""
        cenario = Cenario()

        resultado = cenario.use_case.execute(_comando())

        hash_gravado = cenario.users.password_hashes[resultado.user.id]
        assert hash_gravado != cenario.hasher.dummy_hash()
        assert cenario.hasher.verify("qualquer-senha", hash_gravado) is False

    def test_dois_provisionamentos_gravam_hashes_distintos(self) -> None:
        """Segunda lei de `unusable_hash`: nenhum par de contas compartilha a string."""
        cenario = Cenario()

        primeiro = cenario.use_case.execute(_comando("a@x.com"))
        segundo = cenario.use_case.execute(_comando("b@x.com"))

        assert (
            cenario.users.password_hashes[primeiro.user.id]
            != cenario.users.password_hashes[segundo.user.id]
        )

    def test_emite_exatamente_um_token_de_convite(self) -> None:
        cenario = Cenario()

        resultado = cenario.use_case.execute(_comando())

        assert len(cenario.tokens.tokens) == 1
        token = next(iter(cenario.tokens.tokens.values()))
        assert token.user_id == resultado.user.id
        assert token.purpose is SetupTokenPurpose.INVITATION
        assert token.consumed_at is None

    def test_o_link_tem_a_forma_exata_e_o_valor_casa_o_fingerprint_gravado(self) -> None:
        """CA15 — a forma é a que o front-end consome; o valor é o do token persistido.

        A forma é transcrita como literal, não derivada do helper: se
        `setup_link` mudar, este teste é quem avisa que o contrato com o
        front-end mudou junto.
        """
        cenario = Cenario()

        resultado = cenario.use_case.execute(_comando())

        valor = _valor_do_link(resultado.setup_link)
        assert resultado.setup_link == f"{_BASE_URL}/definir-senha?token={valor}"
        assert valor.startswith("setup-")
        token = next(iter(cenario.tokens.tokens.values()))
        assert token.token_fingerprint not in resultado.setup_link
        assert cenario.issuer.fingerprint(valor) == token.token_fingerprint

    def test_barra_final_da_base_url_nao_duplica(self) -> None:
        cenario = Cenario(base_url=f"{_BASE_URL}/")

        resultado = cenario.use_case.execute(_comando())

        assert resultado.setup_link.startswith(f"{_BASE_URL}/definir-senha?token=")

    def test_sem_entrega_em_maos_o_prazo_e_o_do_convite(self) -> None:
        cenario = Cenario()

        cenario.use_case.execute(_comando(handed_over=False))

        token = next(iter(cenario.tokens.tokens.values()))
        assert token.issued_at == _AGORA
        assert token.expires_at == _AGORA + _TTL_CONVITE

    def test_com_entrega_em_maos_o_prazo_e_o_de_handover(self) -> None:
        """CA15 — o canal muda **só** o prazo; propósito e tudo o mais são iguais."""
        cenario = Cenario()

        cenario.use_case.execute(_comando(handed_over=True))

        token = next(iter(cenario.tokens.tokens.values()))
        assert token.expires_at == _AGORA + _TTL_EM_MAOS
        assert token.purpose is SetupTokenPurpose.INVITATION

    def test_o_repr_do_result_nao_carrega_o_link(self) -> None:
        """`repr=False` — o result fica nos locals de quem falhar depois dele."""
        cenario = Cenario()

        resultado = cenario.use_case.execute(_comando())

        assert _valor_do_link(resultado.setup_link) not in repr(resultado)
        assert "definir-senha" not in repr(resultado)

    def test_devolve_o_usuario_com_os_vinculos_gravados(self) -> None:
        cenario = Cenario()

        resultado = cenario.use_case.execute(_comando("maria@x.com"))

        assert resultado.user.email == Email("maria@x.com")
        assert resultado.user.role is Role.EMPLOYEE
        assert resultado.user.tenant_id == RestaurantId("rest-a")
        assert resultado.user.unit_ids == (UnitId("unit-a1"),)

    def test_deduplica_unidades_repetidas(self) -> None:
        cenario = Cenario()

        resultado = cenario.use_case.execute(_comando(unit_ids=("unit-a1", "unit-a1")))

        assert resultado.user.unit_ids == (UnitId("unit-a1"),)

    def test_sem_unidades_tambem_provisiona(self) -> None:
        cenario = Cenario()

        resultado = cenario.use_case.execute(_comando(role=Role.MANAGER, unit_ids=()))

        assert resultado.user.unit_ids == ()


class TestCasosDeErro:
    def test_email_ja_registrado_levanta(self) -> None:
        cenario = Cenario()
        cenario.use_case.execute(_comando("ocupado@x.com"))

        with pytest.raises(EmailAlreadyRegisteredError):
            cenario.use_case.execute(_comando("ocupado@x.com"))

    def test_email_ja_registrado_nao_emite_token(self) -> None:
        """Sondar endereços não pode produzir tokens órfãos."""
        cenario = Cenario()
        cenario.use_case.execute(_comando("ocupado@x.com"))

        with pytest.raises(EmailAlreadyRegisteredError):
            cenario.use_case.execute(_comando("ocupado@x.com"))

        assert len(cenario.tokens.tokens) == 1

    def test_email_ocupado_levanta_antes_de_consultar_o_restaurante(self) -> None:
        """O primeiro par da ordem verbatim: unicidade global **antes** do tenant.

        Com tenant fantasma **e** e-mail ocupado, o que sobe é
        `EmailAlreadyRegisteredError` — se a consulta ao restaurante viesse
        primeiro, subiria `RestaurantNotFoundError`, e sondar um e-mail qualquer
        ensinaria que aquele tenant não existe. A auditoria de testes mediu que só
        o par `platform_admin`↔unidades tinha teste de ordem.
        """
        cenario = Cenario()
        cenario.use_case.execute(_comando("ocupado@x.com"))

        with pytest.raises(EmailAlreadyRegisteredError):
            cenario.use_case.execute(_comando("ocupado@x.com", tenant="rest-fantasma"))

    def test_platform_admin_com_unidade_levanta_antes_de_consultar_unidades(self) -> None:
        """A ordem é contrato (2.5, replicado): `UnitNotFoundError` aqui revelaria quais existem."""
        cenario = Cenario()

        with pytest.raises(PlatformAdminMembershipError):
            cenario.use_case.execute(
                _comando(role=Role.PLATFORM_ADMIN, tenant=None, unit_ids=("nao-existe",))
            )

    def test_tenant_inexistente_levanta(self) -> None:
        cenario = Cenario()

        with pytest.raises(RestaurantNotFoundError):
            cenario.use_case.execute(_comando(tenant="rest-fantasma"))

    def test_unidade_inexistente_levanta(self) -> None:
        cenario = Cenario()

        with pytest.raises(UnitNotFoundError):
            cenario.use_case.execute(_comando(unit_ids=("unit-fantasma",)))

    def test_unidade_de_outro_tenant_levanta(self) -> None:
        cenario = Cenario()

        with pytest.raises(CrossTenantError):
            cenario.use_case.execute(_comando(unit_ids=("unit-b1",)))

    def test_erro_de_validacao_nao_cria_conta_nem_token(self) -> None:
        cenario = Cenario()

        with pytest.raises(UnitNotFoundError):
            cenario.use_case.execute(_comando("nao@x.com", unit_ids=("unit-fantasma",)))

        assert cenario.users.exists_by_email(Email("nao@x.com")) is False
        assert cenario.tokens.tokens == {}


_ESCRITAS = ("users.add", "tokens.add")


class TestUnidadeDeTrabalho:
    """Stage 2.6 CA4 — conta e token são tudo ou nada (o órfão da 3.5 §6.4 fecha aqui)."""

    def test_as_duas_escritas_acontecem_dentro_de_uma_unidade(self) -> None:
        registro = _Registro()
        cenario = Cenario(registro=registro)

        cenario.use_case.execute(_comando())

        assert tuple(registro.escritas) == _ESCRITAS
        assert (cenario.unidade.aberturas, cenario.unidade.commits) == (1, 1)

    @pytest.mark.parametrize("n", range(1, len(_ESCRITAS) + 1))
    def test_falha_na_escrita_n_nao_deixa_nada_gravado(self, n: int) -> None:
        registro = _Registro(falhar_em=n)
        cenario = Cenario(registro=registro)

        with pytest.raises(_FalhaInjetada):
            cenario.use_case.execute(_comando())

        assert tuple(registro.escritas) == _ESCRITAS[:n]
        assert cenario.users.exists_by_email(Email("funcionario@x.com")) is False
        assert cenario.users.memberships == []
        assert cenario.tokens.tokens == {}
        assert cenario.unidade.rollbacks == 1
