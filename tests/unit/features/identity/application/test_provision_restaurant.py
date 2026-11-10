"""Testes do use case `provision_restaurant` — issue #67 (ADR 0.0.0014) e #114 (ADR 0.0.0018).

O que estes testes protegem: o restaurante e o seu `owner` nascem **juntos** —
nenhuma falha deixa um restaurante sem dono —, o papel emitido é sempre `owner`
(nunca vem do command), o tenant do dono é o restaurante novo, as recusas
acontecem antes de qualquer escrita, e — desde a #114 — o dono nasce **sem senha
utilizável**, com um token de convite cujo valor só existe no corpo do e-mail,
enviado depois do commit.
"""

import re
from collections.abc import Sequence
from dataclasses import fields
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from restaurant_hub.features.identity.application.dtos.commands import (
    ProvisionRestaurantCommand,
)
from restaurant_hub.features.identity.application.dtos.identifiers import (
    PasswordHash,
    SetupTokenId,
)
from restaurant_hub.features.identity.application.dtos.setup_tokens import (
    PasswordSetupToken,
    SetupTokenPurpose,
)
from restaurant_hub.features.identity.application.errors import (
    EmailAlreadyRegisteredError,
    InvitationNotSentError,
    RestaurantAlreadyExistsError,
)
from restaurant_hub.features.identity.application.use_cases.provision_restaurant import (
    ProvisionRestaurantUseCase,
)
from restaurant_hub.features.identity.domain.entities.restaurant import Restaurant
from restaurant_hub.features.identity.domain.entities.user import User
from restaurant_hub.features.identity.domain.exceptions.errors import InvalidNameError
from restaurant_hub.features.identity.domain.value_objects.email import Email
from restaurant_hub.features.identity.domain.value_objects.identifiers import (
    RestaurantId,
    UserId,
)
from restaurant_hub.features.identity.domain.value_objects.role import Role
from restaurant_hub.features.identity.domain.value_objects.unit_membership import (
    UnitMembership,
)
from restaurant_hub.shared.application.ports.out.email_sender import EmailMessage
from tests.fakes.features.identity.fake_password_hasher import FakePasswordHasher
from tests.fakes.features.identity.fake_setup_token_issuer import FakeSetupTokenIssuer
from tests.fakes.features.identity.in_memory_password_setup_token_repository import (
    InMemoryPasswordSetupTokenRepository,
)
from tests.fakes.features.identity.in_memory_restaurant_repository import (
    InMemoryRestaurantRepository,
)
from tests.fakes.features.identity.in_memory_unit_of_work import InMemoryUnitOfWork
from tests.fakes.features.identity.in_memory_user_repository import InMemoryUserRepository
from tests.fakes.shared.fake_clock import FakeClock
from tests.fakes.shared.fake_id_generator import FakeIdGenerator
from tests.fakes.shared.recording_email_sender import (
    EmailSenderFailure,
    RecordingEmailSender,
)

pytestmark = pytest.mark.unit

# Distintos de propósito: com o mesmo id para os três, trocar qual vai para o
# restaurante, qual para o dono e qual para o token passaria despercebido.
_ID_DO_RESTAURANTE = UUID("11111111-1111-1111-1111-111111111111")
_ID_DO_DONO = UUID("22222222-2222-2222-2222-222222222222")
_ID_DO_TOKEN = UUID("33333333-3333-3333-3333-333333333333")
_EMAIL = Email("dono@cantina.com")
_ESCRITAS = ("restaurants.add", "users.add", "tokens.add")
_AGORA = datetime(2026, 11, 9, 12, 0, tzinfo=UTC)
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


class _RestaurantesRegistrados(InMemoryRestaurantRepository):
    def __init__(self, registro: _Registro) -> None:
        super().__init__()
        self._registro = registro

    def add(self, restaurant: Restaurant) -> None:
        super().add(restaurant)
        self._registro.escreveu("restaurants.add")


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


class _UsuariosQueNaoVeemOEmail(InMemoryUserRepository):
    """`exists_by_email` mente `False`: a corrida em que outro cadastro comita entre a
    checagem e o `users.add`. Quem recusa é o próprio `add` — o índice único."""

    def exists_by_email(self, email: Email) -> bool:
        return False


class _SenderQueObservaAUnidade(RecordingEmailSender):
    """Anota, a cada envio, quantos commits a unidade já tinha feito."""

    def __init__(self, *, fail_with: Exception | None = None) -> None:
        super().__init__(fail_with=fail_with)
        self.unidade: InMemoryUnitOfWork | None = None
        self.commits_no_envio: list[int] = []

    def send(self, message: EmailMessage) -> None:
        assert self.unidade is not None
        self.commits_no_envio.append(self.unidade.commits)
        super().send(message)


class Cenario:
    def __init__(
        self,
        *,
        registro: _Registro | None = None,
        users: InMemoryUserRepository | None = None,
        falha_no_envio: Exception | None = None,
    ) -> None:
        self.registro = registro if registro is not None else _Registro()
        self.restaurants = _RestaurantesRegistrados(self.registro)
        self.users = users if users is not None else _UsuariosRegistrados(self.registro)
        self.tokens = _TokensRegistrados(self.registro)
        self.hasher = FakePasswordHasher()
        self.issuer = FakeSetupTokenIssuer()
        self.sender = _SenderQueObservaAUnidade(fail_with=falha_no_envio)
        self.ids = FakeIdGenerator([_ID_DO_RESTAURANTE, _ID_DO_DONO, _ID_DO_TOKEN])
        self.unidade = InMemoryUnitOfWork(self.restaurants, self.users, self.tokens)
        self.sender.unidade = self.unidade
        self.use_case = ProvisionRestaurantUseCase(
            restaurants=self.restaurants,
            users=self.users,
            hasher=self.hasher,
            tokens=self.tokens,
            token_issuer=self.issuer,
            email_sender=self.sender,
            id_generator=self.ids,
            clock=FakeClock(_AGORA),
            invitation_ttl=_TTL,
            base_url=_BASE_URL,
            unit_of_work=self.unidade,
        )


def _comando(name: str = "Cantina do Zé") -> ProvisionRestaurantCommand:
    return ProvisionRestaurantCommand(name=name, owner_email=_EMAIL)


def _valor_do_link(corpo: str) -> str:
    """Extrai o valor do token do link, como o dono faria."""
    _, _, resto = corpo.partition("token=")
    return resto.split()[0]


class TestCaminhoFeliz:
    def test_cria_o_restaurante_com_o_id_do_gerador(self) -> None:
        cenario = Cenario()

        resultado = cenario.use_case.execute(_comando())

        assert resultado.id == str(_ID_DO_RESTAURANTE)
        assert resultado.name == "Cantina do Zé"
        gravado = cenario.restaurants.restaurants[RestaurantId(str(_ID_DO_RESTAURANTE))]
        assert gravado.name == "Cantina do Zé"

    def test_cria_o_dono_como_owner_do_restaurante_novo(self) -> None:
        cenario = Cenario()

        resultado = cenario.use_case.execute(_comando())

        dono = cenario.users.users[UserId(str(_ID_DO_DONO))]
        assert dono.role is Role.OWNER
        assert dono.tenant_id == resultado.id
        assert dono.email == _EMAIL
        assert resultado.owner.id == dono.id
        assert resultado.owner.role is Role.OWNER
        assert resultado.owner.tenant_id == resultado.id
        assert resultado.owner.email == _EMAIL
        assert resultado.owner.unit_ids == ()

    def test_dono_nasce_com_hash_inutilizavel(self) -> None:
        """ADR 0.0.0018 — a conta do dono não tem senha que alguém consiga usar.

        Nem o `dummy_hash()`, cuja pré-imagem é um literal do repositório (ADR
        2.5.0004): as duas coisas são asseridas.
        """
        cenario = Cenario()

        cenario.use_case.execute(_comando())

        gravado = cenario.users.password_hashes[UserId(str(_ID_DO_DONO))]
        assert gravado != cenario.hasher.dummy_hash()
        assert gravado.startswith("unusable::")
        assert cenario.hasher.verify("qualquer-senha", gravado) is False

    def test_command_nao_tem_campo_de_senha(self) -> None:
        """A senha em claro do dono deixou de atravessar a API de plataforma: o
        command que o adapter monta não tem onde carregá-la (ADR 0.0.0018)."""
        nomes = {campo.name for campo in fields(ProvisionRestaurantCommand)}

        assert nomes == {"name", "owner_email"}

    def test_emite_um_token_de_convite_para_o_dono(self) -> None:
        cenario = Cenario()

        resultado = cenario.use_case.execute(_comando())

        assert list(cenario.tokens.tokens) == [SetupTokenId(str(_ID_DO_TOKEN))]
        token = cenario.tokens.tokens[SetupTokenId(str(_ID_DO_TOKEN))]
        assert token.user_id == resultado.owner.id
        assert token.purpose is SetupTokenPurpose.INVITATION
        assert token.consumed_at is None
        assert token.issued_at == _AGORA
        assert token.expires_at == _AGORA + _TTL

    def test_envia_o_convite_ao_dono_com_o_link_do_token(self) -> None:
        cenario = Cenario()

        cenario.use_case.execute(_comando())

        assert len(cenario.sender.sent) == 1
        mensagem = cenario.sender.sent[0]
        assert mensagem.to == _EMAIL.value
        assert mensagem.subject == "Convite para o Restaurant Hub"
        assert f"{_BASE_URL}/definir-senha?token=" in mensagem.body_text
        token = next(iter(cenario.tokens.tokens.values()))
        assert cenario.issuer.fingerprint(_valor_do_link(mensagem.body_text)) == (
            token.token_fingerprint
        )
        assert token.token_fingerprint not in mensagem.body_text

    def test_result_nao_carrega_o_token(self) -> None:
        """Um token no result acabaria na resposta da API (regra 1 da 2.5)."""
        cenario = Cenario()

        resultado = cenario.use_case.execute(_comando())

        assert _valor_do_link(cenario.sender.sent[0].body_text) not in repr(resultado)

    def test_dono_nasce_sem_vinculo_de_unidade(self) -> None:
        """O restaurante acabou de nascer: não há unidade a que o dono pertença."""
        cenario = Cenario()

        cenario.use_case.execute(_comando())

        assert cenario.users.memberships == []


class TestCasosDeErro:
    def test_nome_vazio_levanta_sem_gravar_nada(self) -> None:
        cenario = Cenario()

        with pytest.raises(InvalidNameError):
            cenario.use_case.execute(_comando(name="   "))

        assert cenario.registro.escritas == []
        assert cenario.unidade.aberturas == 0
        assert cenario.sender.sent == ()

    def test_email_ja_registrado_levanta_sem_gravar_nada(self) -> None:
        cenario = Cenario()
        InMemoryUserRepository.add(
            cenario.users,
            User(
                id=UserId("outro"),
                email=_EMAIL,
                role=Role.OWNER,
                tenant_id=RestaurantId("rest-antigo"),
            ),
            PasswordHash("h"),
        )

        with pytest.raises(EmailAlreadyRegisteredError, match=re.escape(repr(_EMAIL.value))):
            cenario.use_case.execute(_comando())

        assert cenario.restaurants.restaurants == {}
        assert cenario.registro.escritas == []
        assert cenario.unidade.aberturas == 0
        assert cenario.sender.sent == ()

    def test_nome_vazio_tem_precedencia_sobre_email_ocupado(self) -> None:
        """A checagem local e grátis vem antes da que consulta o repositório."""
        cenario = Cenario()
        InMemoryUserRepository.add(
            cenario.users,
            User(id=UserId("outro"), email=_EMAIL, role=Role.OWNER, tenant_id=RestaurantId("r")),
            PasswordHash("h"),
        )

        with pytest.raises(InvalidNameError):
            cenario.use_case.execute(_comando(name=""))


class TestUnidadeDeTrabalho:
    """Issue #67 — restaurante e dono são tudo ou nada; #114 — e o token do convite."""

    def test_as_tres_escritas_acontecem_dentro_de_uma_unidade(self) -> None:
        cenario = Cenario()

        cenario.use_case.execute(_comando())

        assert tuple(cenario.registro.escritas) == _ESCRITAS
        assert (cenario.unidade.aberturas, cenario.unidade.commits) == (1, 1)

    def test_o_envio_acontece_depois_de_a_unidade_comitar(self) -> None:
        """ADR 2.6.0002 §3 — um e-mail enviado de dentro de uma unidade que depois
        desfizesse levaria um link para token inexistente."""
        cenario = Cenario()

        cenario.use_case.execute(_comando())

        assert cenario.sender.commits_no_envio == [1]

    @pytest.mark.parametrize("n", range(1, len(_ESCRITAS) + 1))
    def test_falha_na_escrita_n_nao_deixa_nada_nem_envia(self, n: int) -> None:
        cenario = Cenario(registro=_Registro(falhar_em=n))

        with pytest.raises(_FalhaInjetada):
            cenario.use_case.execute(_comando())

        assert tuple(cenario.registro.escritas) == _ESCRITAS[:n]
        assert cenario.restaurants.restaurants == {}
        assert cenario.users.users == {}
        assert cenario.users.exists_by_email(_EMAIL) is False
        assert cenario.tokens.tokens == {}
        assert cenario.sender.sent == ()
        assert cenario.unidade.rollbacks == 1

    def test_falha_do_envio_propaga_e_deixa_o_tenant_comitado(self) -> None:
        """Regra 13 da 2.5: reportar sucesso sem o e-mail ter saído é pior que
        falhar. O tenant existe; a recuperação é o pedido público de redefinição."""
        cenario = Cenario(falha_no_envio=EmailSenderFailure("fora"))

        # Issue #170 — a falha sobe trocada, com o id do DONO (não o do restaurante
        # nem o do token: os três ids do cenário são distintos de propósito).
        with pytest.raises(InvitationNotSentError) as excinfo:
            cenario.use_case.execute(_comando())

        assert excinfo.value.user_id == str(_ID_DO_DONO)

        assert RestaurantId(str(_ID_DO_RESTAURANTE)) in cenario.restaurants.restaurants
        assert cenario.users.exists_by_email(_EMAIL) is True
        assert len(cenario.tokens.tokens) == 1
        assert (cenario.unidade.commits, cenario.unidade.rollbacks) == (1, 0)

    def test_email_tomado_numa_corrida_desfaz_o_restaurante(self) -> None:
        """O `users.add` recusa pelo índice único depois do `restaurants.add`."""
        usuarios = _UsuariosQueNaoVeemOEmail()
        InMemoryUserRepository.add(
            usuarios,
            User(id=UserId("outro"), email=_EMAIL, role=Role.OWNER, tenant_id=RestaurantId("r")),
            PasswordHash("h"),
        )
        cenario = Cenario(users=usuarios)

        with pytest.raises(EmailAlreadyRegisteredError):
            cenario.use_case.execute(_comando())

        assert cenario.registro.escritas == ["restaurants.add"]
        assert cenario.restaurants.restaurants == {}
        assert set(usuarios.users) == {UserId("outro")}
        assert cenario.tokens.tokens == {}
        assert cenario.sender.sent == ()
        assert cenario.unidade.rollbacks == 1

    def test_id_de_restaurante_repetido_nao_cria_o_dono(self) -> None:
        cenario = Cenario()
        cenario.restaurants.restaurants[RestaurantId(str(_ID_DO_RESTAURANTE))] = Restaurant(
            id=RestaurantId(str(_ID_DO_RESTAURANTE)), name="Antigo"
        )

        with pytest.raises(RestaurantAlreadyExistsError):
            cenario.use_case.execute(_comando())

        assert cenario.users.users == {}
        assert cenario.tokens.tokens == {}
        assert cenario.sender.sent == ()
        assert cenario.restaurants.restaurants[RestaurantId(str(_ID_DO_RESTAURANTE))].name == (
            "Antigo"
        )
