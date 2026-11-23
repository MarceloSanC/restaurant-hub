"""Emissão do token de definição de senha nos cinco use cases que a fazem (issue #205).

O passo — emitir o token, gravar o registro com o fingerprint e o prazo, montar o
link — vive em `InviteUserUseCase`, `InviteOwnerUseCase`, `ProvisionRestaurantUseCase`,
`ProvisionAccountUseCase` e `RequestPasswordResetUseCase`. Estes testes travam o
**efeito observável** do passo nos cinco, por igual, para que a extração da issue
#205 não mude nada:

- o registro gravado é **exatamente** o esperado (id, dono, propósito, fingerprint,
  emissão e expiração), com o prazo de cada fluxo;
- o valor gravado é o fingerprint do token que **o link** carrega — o link que a
  pessoa abre redime o registro que a emissão gravou, e o valor em claro não é
  gravado;
- uma emissão por execução, pela fonte do port (`SetupTokenIssuer.issue`).

No fim, os testes da definição única do passo, `_invitation.issue_setup_token`.
"""

from collections.abc import Callable
from dataclasses import dataclass, fields
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlsplit
from uuid import UUID

import pytest

from restaurant_hub.features.identity.application.dtos.commands import (
    InviteOwnerCommand,
    InviteUserCommand,
    ProvisionAccountCommand,
    ProvisionRestaurantCommand,
    RequestPasswordResetCommand,
)
from restaurant_hub.features.identity.application.dtos.identifiers import SetupTokenId
from restaurant_hub.features.identity.application.dtos.results import ProvisionedAccountResult
from restaurant_hub.features.identity.application.dtos.setup_tokens import (
    IssuedSetupToken,
    PasswordSetupToken,
    SetupTokenPurpose,
)
from restaurant_hub.features.identity.application.use_cases._invitation import (
    issue_setup_token,
    setup_link,
)
from restaurant_hub.features.identity.application.use_cases.invite_owner import (
    InviteOwnerUseCase,
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
from restaurant_hub.features.identity.application.use_cases.request_password_reset import (
    RequestPasswordResetUseCase,
)
from restaurant_hub.features.identity.domain.entities.restaurant import Restaurant
from restaurant_hub.features.identity.domain.entities.user import User
from restaurant_hub.features.identity.domain.value_objects.email import Email
from restaurant_hub.features.identity.domain.value_objects.identifiers import (
    RestaurantId,
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
from tests.fakes.features.identity.in_memory_unit_of_work import InMemoryUnitOfWork
from tests.fakes.features.identity.in_memory_unit_repository import InMemoryUnitRepository
from tests.fakes.features.identity.in_memory_user_repository import InMemoryUserRepository
from tests.fakes.features.identity.stub_action_authorizers import (
    TEST_ACTOR_ID,
    RecordingActionAuthorizer,
)
from tests.fakes.shared.fake_clock import FakeClock
from tests.fakes.shared.fake_id_generator import FakeIdGenerator
from tests.fakes.shared.recording_email_sender import RecordingEmailSender

pytestmark = pytest.mark.unit

_AGORA = datetime(2026, 11, 23, 9, 30, tzinfo=UTC)
_BASE_URL = "https://app.exemplo.com/"
_TENANT = RestaurantId("rest-a")
_CONVITE_TTL = timedelta(hours=72)
_ENTREGA_TTL = timedelta(days=10)
_RESET_TTL = timedelta(minutes=30)
_CADASTRADO = "cadastrado@x.com"
_USUARIO_CADASTRADO = UserId("user-cadastrado")


class _Contador(FakeSetupTokenIssuer):
    """O fake do port, contando as emissões — a fonte do valor é o port, uma vez."""

    def __init__(self) -> None:
        super().__init__()
        self.emissoes: list[str] = []

    def issue(self) -> IssuedSetupToken:
        emitido = super().issue()
        self.emissoes.append(emitido.value)
        return emitido


class _Grafo:
    """Fakes comuns aos cinco use cases, com um usuário já cadastrado (para o reset)."""

    def __init__(self) -> None:
        self.users = InMemoryUserRepository()
        self.restaurants = InMemoryRestaurantRepository()
        self.units = InMemoryUnitRepository()
        self.tokens = InMemoryPasswordSetupTokenRepository()
        self.issuer = _Contador()
        self.sender = RecordingEmailSender()
        self.ids = FakeIdGenerator()
        self.hasher = FakePasswordHasher()
        self.clock = FakeClock(_AGORA)
        self.unidade = InMemoryUnitOfWork(self.users, self.tokens, self.restaurants)
        self.restaurants.add(Restaurant(id=_TENANT, name="Cantina A"))
        self.users.add(
            User(
                id=_USUARIO_CADASTRADO,
                email=Email(_CADASTRADO),
                role=Role.MANAGER,
                tenant_id=_TENANT,
            ),
            self.hasher.hash("senha-atual"),
        )


def _link_do_email(grafo: _Grafo, _: object) -> str:
    (mensagem,) = grafo.sender.sent
    _, _, resto = mensagem.body_text.partition(_BASE_URL.rstrip("/") + "/definir-senha?token=")
    assert resto, mensagem.body_text
    return _BASE_URL.rstrip("/") + "/definir-senha?token=" + resto.split()[0]


def _link_do_result(_: _Grafo, resultado: object) -> str:
    assert isinstance(resultado, ProvisionedAccountResult)
    return resultado.setup_link


def _convidar(grafo: _Grafo) -> object:
    return InviteUserUseCase(
        users=grafo.users,
        restaurants=grafo.restaurants,
        units=grafo.units,
        hasher=grafo.hasher,
        tokens=grafo.tokens,
        token_issuer=grafo.issuer,
        email_sender=grafo.sender,
        id_generator=grafo.ids,
        clock=grafo.clock,
        invitation_ttl=_CONVITE_TTL,
        base_url=_BASE_URL,
        unit_of_work=grafo.unidade,
        authorizer=RecordingActionAuthorizer(),
    ).execute(
        InviteUserCommand(
            actor_id=TEST_ACTOR_ID, email=Email("nova@x.com"), role=Role.HR, tenant_id=_TENANT
        )
    )


def _convidar_dono(grafo: _Grafo) -> object:
    return InviteOwnerUseCase(
        users=grafo.users,
        restaurants=grafo.restaurants,
        hasher=grafo.hasher,
        tokens=grafo.tokens,
        token_issuer=grafo.issuer,
        email_sender=grafo.sender,
        id_generator=grafo.ids,
        clock=grafo.clock,
        invitation_ttl=_CONVITE_TTL,
        base_url=_BASE_URL,
        unit_of_work=grafo.unidade,
        authorizer=RecordingActionAuthorizer(),
    ).execute(
        InviteOwnerCommand(actor_id=TEST_ACTOR_ID, email=Email("dono@x.com"), tenant_id=_TENANT)
    )


def _provisionar_restaurante(grafo: _Grafo) -> object:
    return ProvisionRestaurantUseCase(
        restaurants=grafo.restaurants,
        users=grafo.users,
        hasher=grafo.hasher,
        tokens=grafo.tokens,
        token_issuer=grafo.issuer,
        email_sender=grafo.sender,
        id_generator=grafo.ids,
        clock=grafo.clock,
        invitation_ttl=_CONVITE_TTL,
        base_url=_BASE_URL,
        unit_of_work=grafo.unidade,
        authorizer=RecordingActionAuthorizer(),
    ).execute(
        ProvisionRestaurantCommand(
            actor_id=TEST_ACTOR_ID, name="Cantina B", owner_email=Email("dono@x.com")
        )
    )


def _provisionar_conta(handed_over: bool) -> Callable[[_Grafo], object]:
    def rodar(grafo: _Grafo) -> object:
        return ProvisionAccountUseCase(
            users=grafo.users,
            restaurants=grafo.restaurants,
            units=grafo.units,
            hasher=grafo.hasher,
            tokens=grafo.tokens,
            token_issuer=grafo.issuer,
            id_generator=grafo.ids,
            clock=grafo.clock,
            invitation_ttl=_CONVITE_TTL,
            handover_ttl=_ENTREGA_TTL,
            base_url=_BASE_URL,
            unit_of_work=grafo.unidade,
        ).execute(
            ProvisionAccountCommand(
                email=Email("func@x.com"),
                role=Role.EMPLOYEE,
                tenant_id=_TENANT,
                unit_ids=(),
                handed_over=handed_over,
            )
        )

    return rodar


def _pedir_redefinicao(grafo: _Grafo) -> object:
    return RequestPasswordResetUseCase(
        users=grafo.users,
        tokens=grafo.tokens,
        token_issuer=grafo.issuer,
        email_sender=grafo.sender,
        id_generator=grafo.ids,
        clock=grafo.clock,
        reset_ttl=_RESET_TTL,
        base_url=_BASE_URL,
        unit_of_work=grafo.unidade,
    ).execute(RequestPasswordResetCommand(email=Email(_CADASTRADO)))


@dataclass(frozen=True)
class _Caso:
    rodar: Callable[[_Grafo], object]
    link: Callable[[_Grafo, object], str]
    proposito: SetupTokenPurpose
    ttl: timedelta
    # O id do registro sai do mesmo `IdGenerator` que dá id ao usuário (e ao
    # restaurante): a posição dele na sequência fixa a ordem das chamadas.
    id_do_token: int
    # `None` = o dono é o usuário que o próprio use case acabou de criar.
    dono: UserId | None


_CASOS: dict[str, _Caso] = {
    "invite_user": _Caso(
        _convidar, _link_do_email, SetupTokenPurpose.INVITATION, _CONVITE_TTL, 2, None
    ),
    "invite_owner": _Caso(
        _convidar_dono, _link_do_email, SetupTokenPurpose.INVITATION, _CONVITE_TTL, 2, None
    ),
    "provision_restaurant": _Caso(
        _provisionar_restaurante,
        _link_do_email,
        SetupTokenPurpose.INVITATION,
        _CONVITE_TTL,
        3,
        None,
    ),
    "provision_account (e-mail)": _Caso(
        _provisionar_conta(False),
        _link_do_result,
        SetupTokenPurpose.INVITATION,
        _CONVITE_TTL,
        2,
        None,
    ),
    "provision_account (em mãos)": _Caso(
        _provisionar_conta(True),
        _link_do_result,
        SetupTokenPurpose.INVITATION,
        _ENTREGA_TTL,
        2,
        None,
    ),
    "request_password_reset": _Caso(
        _pedir_redefinicao,
        _link_do_email,
        SetupTokenPurpose.PASSWORD_RESET,
        _RESET_TTL,
        1,
        _USUARIO_CADASTRADO,
    ),
}


def _token_do_link(link: str) -> str:
    partes = urlsplit(link)
    assert f"{partes.scheme}://{partes.netloc}{partes.path}" == (
        "https://app.exemplo.com/definir-senha"
    )
    (valor,) = parse_qs(partes.query, strict_parsing=True)["token"]
    return valor


def _usuario_novo(grafo: _Grafo) -> UserId:
    (novo,) = (uid for uid in grafo.users.users if uid != _USUARIO_CADASTRADO)
    return novo


@pytest.mark.parametrize("nome", list(_CASOS))
def test_o_registro_gravado_e_exatamente_o_da_emissao(nome: str) -> None:
    caso = _CASOS[nome]
    grafo = _Grafo()

    resultado = caso.rodar(grafo)

    (registro,) = grafo.tokens.tokens.values()
    (valor,) = grafo.issuer.emissoes
    assert registro == PasswordSetupToken(
        id=SetupTokenId(str(UUID(int=caso.id_do_token))),
        user_id=caso.dono if caso.dono is not None else _usuario_novo(grafo),
        purpose=caso.proposito,
        token_fingerprint=grafo.issuer.fingerprint(valor),
        issued_at=_AGORA,
        expires_at=_AGORA + caso.ttl,
    )
    assert _token_do_link(caso.link(grafo, resultado)) == valor


@pytest.mark.parametrize("nome", list(_CASOS))
def test_o_valor_gravado_e_o_fingerprint_do_token_do_link(nome: str) -> None:
    """O link que a pessoa abre redime o registro gravado; o valor em claro não é gravado."""
    caso = _CASOS[nome]
    grafo = _Grafo()

    resultado = caso.rodar(grafo)

    valor = _token_do_link(caso.link(grafo, resultado))
    registro = grafo.tokens.find_by_fingerprint(grafo.issuer.fingerprint(valor))
    assert registro is not None
    # Nenhum campo gravado é o valor em claro (o fingerprint do fake o contém como
    # substring, por isso a comparação é campo a campo, e não por `in repr`).
    assert valor not in [getattr(registro, campo.name) for campo in fields(registro)]
    assert len(grafo.issuer.emissoes) == 1


# ---------------------------------------------------------------------------
# A definição única do passo — `issue_setup_token` (issue #205)
# ---------------------------------------------------------------------------


class _Ordem:
    """Port de emissão e gerador de ids que anotam a ordem em que são chamados."""

    def __init__(self) -> None:
        self.chamadas: list[str] = []
        self.issuer = FakeSetupTokenIssuer()
        self.ids = FakeIdGenerator()

    def issue(self) -> IssuedSetupToken:
        self.chamadas.append("issue")
        return self.issuer.issue()

    def fingerprint(self, token_value: str) -> str:
        return self.issuer.fingerprint(token_value)

    def next_id(self) -> UUID:
        self.chamadas.append("next_id")
        return self.ids.next_id()


@pytest.mark.parametrize(
    ("proposito", "ttl"),
    [
        (SetupTokenPurpose.INVITATION, _CONVITE_TTL),
        (SetupTokenPurpose.INVITATION, _ENTREGA_TTL),
        (SetupTokenPurpose.PASSWORD_RESET, _RESET_TTL),
    ],
)
def test_issue_setup_token_monta_registro_e_link_da_mesma_emissao(
    proposito: SetupTokenPurpose, ttl: timedelta
) -> None:
    ordem = _Ordem()

    emissao = issue_setup_token(
        ordem,
        ordem,
        user_id=UserId("user-9"),
        purpose=proposito,
        now=_AGORA,
        ttl=ttl,
        base_url=_BASE_URL,
    )

    assert emissao.record == PasswordSetupToken(
        id=SetupTokenId(str(UUID(int=1))),
        user_id=UserId("user-9"),
        purpose=proposito,
        token_fingerprint="sfp::setup-1",
        issued_at=_AGORA,
        expires_at=_AGORA + ttl,
    )
    # Byte a byte o link de `setup_link`, com o valor da mesma emissão.
    assert emissao.link == "https://app.exemplo.com/definir-senha?token=setup-1"
    assert emissao.link == setup_link(_BASE_URL, "setup-1")
    assert ordem.fingerprint(_token_do_link(emissao.link)) == emissao.record.token_fingerprint


def test_issue_setup_token_emite_uma_vez_e_antes_de_pedir_o_id() -> None:
    """A ordem das cópias substituídas: valor do port, depois id do registro."""
    ordem = _Ordem()

    issue_setup_token(
        ordem,
        ordem,
        user_id=UserId("user-9"),
        purpose=SetupTokenPurpose.INVITATION,
        now=_AGORA,
        ttl=_CONVITE_TTL,
        base_url=_BASE_URL,
    )

    assert ordem.chamadas == ["issue", "next_id"]


def test_issue_setup_token_nao_mostra_o_link_no_repr() -> None:
    emissao = issue_setup_token(
        FakeSetupTokenIssuer(),
        FakeIdGenerator(),
        user_id=UserId("user-9"),
        purpose=SetupTokenPurpose.INVITATION,
        now=_AGORA,
        ttl=_CONVITE_TTL,
        base_url=_BASE_URL,
    )

    assert "definir-senha" not in repr(emissao)
    assert "token=" not in repr(emissao)
