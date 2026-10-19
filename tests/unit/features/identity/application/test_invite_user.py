"""Testes do use case `invite_user` — Stage 2.5, CA6; Stage 2.6, CA4 e CA8.

O que estes testes protegem, acima de tudo: a conta convidada **não tem senha
utilizável** e o token **não vaza** para lugar nenhum além do corpo do e-mail.
"""

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

import pytest

from restaurant_hub.features.identity.application.dtos.commands import InviteUserCommand
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
from restaurant_hub.features.identity.application.use_cases.invite_user import (
    InviteUserUseCase,
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
from tests.fakes.shared.recording_email_sender import (
    EmailSenderFailure,
    RecordingEmailSender,
)

_AGORA = datetime(2026, 7, 20, 12, 0, tzinfo=UTC)
_TTL = timedelta(hours=72)
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
    """Grafo de fakes montado uma vez, com acesso a cada peça na asserção."""

    def __init__(
        self,
        *,
        sender: RecordingEmailSender | None = None,
        registro: _Registro | None = None,
    ) -> None:
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
        self.sender = sender if sender is not None else RecordingEmailSender()
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
        self.use_case = InviteUserUseCase(
            users=self.users,
            restaurants=self.restaurants,
            units=self.units,
            hasher=self.hasher,
            tokens=self.tokens,
            token_issuer=self.issuer,
            email_sender=self.sender,
            id_generator=FakeIdGenerator(),
            clock=self.clock,
            invitation_ttl=_TTL,
            base_url=_BASE_URL,
            unit_of_work=self.unidade,
        )


def _comando(
    email: str = "convidado@x.com",
    role: Role = Role.MANAGER,
    tenant: str | None = "rest-a",
    unit_ids: tuple[str, ...] = (),
) -> InviteUserCommand:
    return InviteUserCommand(
        email=Email(email),
        role=role,
        tenant_id=RestaurantId(tenant) if tenant is not None else None,
        unit_ids=tuple(UnitId(u) for u in unit_ids),
    )


class TestCaminhoFeliz:
    def test_cria_o_usuario_com_hash_inutilizavel(self) -> None:
        """CA6 — a conta nasce sem senha que alguém consiga usar.

        Não basta "não é a senha certa": o hash não pode ser o `dummy_hash()`,
        cuja pré-imagem é um literal do repositório (ADR 2.5.0004). Este teste
        assere as duas coisas.
        """
        cenario = Cenario()

        resultado = cenario.use_case.execute(_comando())

        hash_gravado = cenario.users.password_hashes[resultado.id]
        assert hash_gravado != cenario.hasher.dummy_hash()
        assert cenario.hasher.verify("qualquer-senha", hash_gravado) is False

    def test_emite_exatamente_um_token_de_convite(self) -> None:
        cenario = Cenario()

        resultado = cenario.use_case.execute(_comando())

        assert len(cenario.tokens.tokens) == 1
        token = next(iter(cenario.tokens.tokens.values()))
        assert token.user_id == resultado.id
        assert token.purpose is SetupTokenPurpose.INVITATION
        assert token.consumed_at is None

    def test_persiste_apenas_o_fingerprint_do_token(self) -> None:
        """CA6 — o valor não pode estar em lugar nenhum do que foi gravado."""
        cenario = Cenario()

        cenario.use_case.execute(_comando())

        token = next(iter(cenario.tokens.tokens.values()))
        valor_enviado = cenario.sender.sent[0].body_text
        assert token.token_fingerprint not in valor_enviado
        assert cenario.issuer.fingerprint(_valor_do_link(valor_enviado)) == (
            token.token_fingerprint
        )

    def test_envia_exatamente_uma_mensagem_para_o_convidado(self) -> None:
        cenario = Cenario()

        cenario.use_case.execute(_comando("alguem@x.com"))

        assert len(cenario.sender.sent) == 1
        assert cenario.sender.sent[0].to == "alguem@x.com"

    def test_corpo_contem_o_valor_do_token_num_link(self) -> None:
        """CA6 — é o único lugar do sistema onde o valor aparece."""
        cenario = Cenario()

        cenario.use_case.execute(_comando())

        corpo = cenario.sender.sent[0].body_text
        assert _BASE_URL in corpo
        assert "token=" in corpo
        assert _valor_do_link(corpo).startswith("setup-")

    def test_expiracao_usa_o_ttl_injetado(self) -> None:
        """O prazo é configuração, não literal no corpo do use case."""
        cenario = Cenario()

        cenario.use_case.execute(_comando())

        token = next(iter(cenario.tokens.tokens.values()))
        assert token.issued_at == _AGORA
        assert token.expires_at == _AGORA + _TTL

    def test_result_nao_carrega_o_token(self) -> None:
        """Um token no result acabaria numa resposta de API (regra 1)."""
        cenario = Cenario()

        resultado = cenario.use_case.execute(_comando())

        valor = _valor_do_link(cenario.sender.sent[0].body_text)
        assert valor not in repr(resultado)

    def test_vincula_as_unidades_pedidas(self) -> None:
        cenario = Cenario()

        resultado = cenario.use_case.execute(_comando(unit_ids=("unit-a1",)))

        assert resultado.unit_ids == (UnitId("unit-a1"),)

    def test_deduplica_unidades_repetidas(self) -> None:
        cenario = Cenario()

        resultado = cenario.use_case.execute(_comando(unit_ids=("unit-a1", "unit-a1")))

        assert resultado.unit_ids == (UnitId("unit-a1"),)


class TestCasosDeErro:
    def test_email_ja_registrado_levanta(self) -> None:
        cenario = Cenario()
        cenario.use_case.execute(_comando("ocupado@x.com"))

        with pytest.raises(EmailAlreadyRegisteredError):
            cenario.use_case.execute(_comando("ocupado@x.com"))

    def test_email_ja_registrado_nao_emite_token_nem_envia(self) -> None:
        """Reconvidar não é caminho de recuperação — e não pode custar um e-mail.

        Se a checagem viesse depois da emissão, sondar endereços produziria
        tokens órfãos e mensagens para caixas de terceiros.
        """
        cenario = Cenario()
        cenario.use_case.execute(_comando("ocupado@x.com"))

        with pytest.raises(EmailAlreadyRegisteredError):
            cenario.use_case.execute(_comando("ocupado@x.com"))

        assert len(cenario.tokens.tokens) == 1
        assert len(cenario.sender.sent) == 1

    def test_platform_admin_com_unidade_levanta_antes_de_consultar_unidades(self) -> None:
        """A ordem é contrato: `UnitNotFoundError` aqui revelaria quais existem."""
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

    def test_erro_de_validacao_nao_envia_e_mail(self) -> None:
        cenario = Cenario()

        with pytest.raises(UnitNotFoundError):
            cenario.use_case.execute(_comando(unit_ids=("unit-fantasma",)))

        assert cenario.sender.sent == ()

    def test_falha_do_sender_propaga(self) -> None:
        """Regra 13 — reportar sucesso sem o e-mail ter saído é pior que falhar.

        No caminho de **convite** a exceção sobe; no de redefinição de senha ela
        é absorvida, porque lá deixá-la subir enumeraria contas.
        """
        cenario = Cenario(sender=RecordingEmailSender(fail_with=EmailSenderFailure("fora")))

        with pytest.raises(EmailSenderFailure):
            cenario.use_case.execute(_comando())

    def test_falha_do_sender_deixa_o_usuario_criado(self) -> None:
        """O usuário existe, então o caminho de recuperação é a redefinição.

        Stage 2.6 (CA8): conta **e** token já comitados quando o envio falha — o
        envio vem depois da unidade, e a falha dele não a desfaz.
        """
        cenario = Cenario(sender=RecordingEmailSender(fail_with=EmailSenderFailure("fora")))

        with pytest.raises(EmailSenderFailure):
            cenario.use_case.execute(_comando("preso@x.com"))

        assert cenario.users.exists_by_email(Email("preso@x.com")) is True
        assert len(cenario.tokens.tokens) == 1
        assert (cenario.unidade.commits, cenario.unidade.rollbacks) == (1, 0)


_ESCRITAS = ("users.add", "tokens.add")


class TestUnidadeDeTrabalho:
    """Stage 2.6 CA4 — conta e token são tudo ou nada."""

    def test_as_duas_escritas_acontecem_dentro_de_uma_unidade(self) -> None:
        registro = _Registro()
        cenario = Cenario(registro=registro)

        cenario.use_case.execute(_comando())

        assert tuple(registro.escritas) == _ESCRITAS
        assert (cenario.unidade.aberturas, cenario.unidade.commits) == (1, 1)

    @pytest.mark.parametrize("n", range(1, len(_ESCRITAS) + 1))
    def test_falha_na_escrita_n_nao_deixa_nada_gravado_nem_envia(self, n: int) -> None:
        registro = _Registro(falhar_em=n)
        cenario = Cenario(registro=registro)

        with pytest.raises(_FalhaInjetada):
            cenario.use_case.execute(_comando())

        assert tuple(registro.escritas) == _ESCRITAS[:n]
        assert cenario.users.exists_by_email(Email("convidado@x.com")) is False
        assert cenario.users.memberships == []
        assert cenario.tokens.tokens == {}
        assert cenario.sender.sent == ()
        assert cenario.unidade.rollbacks == 1

    def test_o_envio_acontece_depois_de_a_unidade_comitar(self) -> None:
        cenario = Cenario()
        commits_no_envio: list[int] = []
        enviar_original = cenario.sender.send

        def enviar_observado(mensagem: object) -> None:
            commits_no_envio.append(cenario.unidade.commits)
            enviar_original(mensagem)  # type: ignore[arg-type]

        cenario.sender.send = enviar_observado  # type: ignore[method-assign]
        cenario.use_case.execute(_comando())

        assert commits_no_envio == [1]


def _valor_do_link(corpo: str) -> str:
    """Extrai o valor do token do link, como o convidado faria."""
    _, _, resto = corpo.partition("token=")
    return resto.split()[0]
