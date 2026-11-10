"""Testes do use case `invite_owner` — Stage 2.7, CA15 (paridade) e regras próprias.

Até a Stage 2.7 a rota `POST /restaurants/{id}/owners` rodava `InviteUserUseCase` com
`role=OWNER` e sem unidades. O use case novo existe para declarar o **seu**
requisito (`manage_platform`); o resto do comportamento tem de ser o mesmo, e a
paridade é provada rodando os dois sobre grafos idênticos e comparando o efeito
observável: result, contas, tokens, e-mails e exceções.
"""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest

from restaurant_hub.features.identity.application.dtos.commands import (
    InviteOwnerCommand,
    InviteUserCommand,
)
from restaurant_hub.features.identity.application.errors import (
    EmailAlreadyRegisteredError,
    InvitationNotSentError,
    RestaurantNotFoundError,
)
from restaurant_hub.features.identity.application.use_cases.invite_owner import (
    InviteOwnerUseCase,
)
from restaurant_hub.features.identity.application.use_cases.invite_user import (
    InviteUserUseCase,
)
from restaurant_hub.features.identity.domain.entities.restaurant import Restaurant
from restaurant_hub.features.identity.domain.value_objects.email import Email
from restaurant_hub.features.identity.domain.value_objects.identifiers import RestaurantId
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
from tests.fakes.shared.recording_email_sender import (
    EmailSenderFailure,
    RecordingEmailSender,
)

pytestmark = pytest.mark.unit

_AGORA = datetime(2026, 11, 9, 12, 0, tzinfo=UTC)
_TENANT = RestaurantId("rest-a")
_EMAIL_JA_USADO = "ja-usado@x.com"


class _Grafo:
    """Um grafo de fakes semeado igual para os dois use cases."""

    def __init__(self, *, sender_falha: bool = False) -> None:
        self.users = InMemoryUserRepository()
        self.restaurants = InMemoryRestaurantRepository()
        self.tokens = InMemoryPasswordSetupTokenRepository()
        self.sender = RecordingEmailSender(
            fail_with=EmailSenderFailure("provedor fora do ar") if sender_falha else None
        )
        self.restaurants.add(Restaurant(id=_TENANT, name="Cantina A"))
        self.comum: dict[str, object] = {
            "users": self.users,
            "restaurants": self.restaurants,
            "hasher": FakePasswordHasher(),
            "tokens": self.tokens,
            "token_issuer": FakeSetupTokenIssuer(),
            "email_sender": self.sender,
            "id_generator": FakeIdGenerator(),
            "clock": FakeClock(_AGORA),
            "invitation_ttl": timedelta(hours=72),
            "base_url": "https://app.exemplo.com",
            "unit_of_work": InMemoryUnitOfWork(self.users, self.tokens),
        }

    def convidar_dono(self, email: str, tenant: RestaurantId = _TENANT) -> object:
        use_case = InviteOwnerUseCase(**self.comum, authorizer=RecordingActionAuthorizer())
        return use_case.execute(
            InviteOwnerCommand(actor_id=TEST_ACTOR_ID, email=Email(email), tenant_id=tenant)
        )

    def convidar_como_antes(self, email: str, tenant: RestaurantId = _TENANT) -> object:
        """O caminho de antes da Stage 2.7: `InviteUserUseCase`, `role=OWNER`, sem unidades."""
        use_case = InviteUserUseCase(
            **self.comum,
            units=InMemoryUnitRepository(),
            authorizer=RecordingActionAuthorizer(),
        )
        return use_case.execute(
            InviteUserCommand(
                actor_id=TEST_ACTOR_ID, email=Email(email), role=Role.OWNER, tenant_id=tenant
            )
        )

    def estado(self) -> tuple[object, ...]:
        return (
            {uid: (u.email, u.role, u.tenant_id) for uid, u in self.users.users.items()},
            dict(self.users.password_hashes),
            {tid: (t.user_id, t.purpose, t.expires_at) for tid, t in self.tokens.tokens.items()},
            self.sender.sent,
        )


def _rodar(
    caminho: Callable[[_Grafo], object], grafo: _Grafo
) -> tuple[object, type[BaseException] | None]:
    try:
        return caminho(grafo), None
    except Exception as exc:
        return None, type(exc)


_CENARIOS_DE_PARIDADE: dict[str, tuple[str, RestaurantId, bool]] = {
    # nome: (e-mail, tenant, sender falha)
    "caminho feliz": ("dono@x.com", _TENANT, False),
    "restaurante inexistente": ("dono@x.com", RestaurantId("rest-inexistente"), False),
    "e-mail repetido com restaurante inexistente": (
        _EMAIL_JA_USADO,
        RestaurantId("rest-inexistente"),
        False,
    ),
    "e-mail repetido": (_EMAIL_JA_USADO, _TENANT, False),
    "falha de envio": ("dono@x.com", _TENANT, True),
}


@pytest.mark.parametrize("nome", sorted(_CENARIOS_DE_PARIDADE))
def test_paridade_com_o_convite_de_antes(nome: str) -> None:
    """CA15 — mesmo result, mesmo efeito, mesma exceção que o caminho de antes."""
    email, tenant, sender_falha = _CENARIOS_DE_PARIDADE[nome]
    novo, antigo = _Grafo(sender_falha=sender_falha), _Grafo(sender_falha=sender_falha)
    for grafo in (novo, antigo):
        if email == _EMAIL_JA_USADO:
            semente = _Grafo()
            semente.convidar_dono(email)
            for uid, user in semente.users.users.items():
                grafo.users.add(user, semente.users.password_hashes[uid], ())

    resultado_novo = _rodar(lambda g: g.convidar_dono(email, tenant), novo)
    resultado_antigo = _rodar(lambda g: g.convidar_como_antes(email, tenant), antigo)

    assert resultado_novo == resultado_antigo
    assert novo.estado() == antigo.estado()


def test_os_cenarios_de_paridade_exercitam_cada_desfecho() -> None:
    """Sem isto a paridade poderia comparar só caminhos felizes."""
    desfechos = set()
    for email, tenant, sender_falha in _CENARIOS_DE_PARIDADE.values():
        grafo = _Grafo(sender_falha=sender_falha)
        if email == _EMAIL_JA_USADO:
            grafo.convidar_dono(email)
        desfechos.add(_rodar(lambda g, e=email, t=tenant: g.convidar_dono(e, t), grafo)[1])

    assert desfechos == {
        None,
        RestaurantNotFoundError,
        EmailAlreadyRegisteredError,
        InvitationNotSentError,
    }


def test_o_papel_e_sempre_owner_e_o_tenant_o_do_command() -> None:
    resultado = _Grafo().convidar_dono("dono@x.com")

    assert resultado.role is Role.OWNER
    assert resultado.tenant_id == _TENANT
    assert resultado.unit_ids == ()


def test_falha_de_envio_deixa_conta_e_token_comitados() -> None:
    grafo = _Grafo(sender_falha=True)

    with pytest.raises(InvitationNotSentError):
        grafo.convidar_dono("dono@x.com")

    assert len(grafo.users.users) == 1
    assert len(grafo.tokens.tokens) == 1
