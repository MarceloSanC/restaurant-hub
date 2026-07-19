"""Testes do use case `create_user` — concept CA3, CA4, CA5.

Boa parte destes testes existe para fixar a **ordem** das checagens (§5.7). A
ordem não é preferência de estilo: ela decide qual informação o caller recebe, e
duas das checagens vazariam existência de recursos se rodassem fora de lugar.
"""

from uuid import UUID

import pytest

from restaurant_hub.features.identity.application.dtos.commands import CreateUserCommand
from restaurant_hub.features.identity.application.errors import (
    EmailAlreadyRegisteredError,
    RestaurantNotFoundError,
    UnitNotFoundError,
)
from restaurant_hub.features.identity.application.use_cases.create_user import (
    CreateUserUseCase,
)
from restaurant_hub.features.identity.domain.entities.restaurant import Restaurant
from restaurant_hub.features.identity.domain.entities.unit import Unit
from restaurant_hub.features.identity.domain.exceptions.errors import (
    CrossTenantError,
    MissingTenantError,
    PlatformAdminMembershipError,
    PlatformAdminTenantError,
)
from restaurant_hub.features.identity.domain.value_objects.email import Email
from restaurant_hub.features.identity.domain.value_objects.identifiers import (
    RestaurantId,
    UnitId,
    UserId,
)
from restaurant_hub.features.identity.domain.value_objects.role import Role
from tests.fakes.features.identity.fake_password_hasher import FakePasswordHasher
from tests.fakes.features.identity.in_memory_restaurant_repository import (
    InMemoryRestaurantRepository,
)
from tests.fakes.features.identity.in_memory_unit_repository import InMemoryUnitRepository
from tests.fakes.features.identity.in_memory_user_repository import InMemoryUserRepository
from tests.fakes.shared.fake_id_generator import FakeIdGenerator

pytestmark = pytest.mark.unit

_FIXED_ID = UUID("33333333-3333-3333-3333-333333333333")
_TENANT_A = RestaurantId("rest-a")
_TENANT_B = RestaurantId("rest-b")
_UNIT_A1 = UnitId("unit-a1")
_UNIT_A2 = UnitId("unit-a2")
_UNIT_B1 = UnitId("unit-b1")


class _Fixture:
    """Bateria de fakes compartilhada, como o composition root fará na 2.4."""

    def __init__(self) -> None:
        self.users = InMemoryUserRepository()
        self.restaurants = InMemoryRestaurantRepository()
        self.units = InMemoryUnitRepository()
        self.hasher = FakePasswordHasher()
        self.restaurants.add(Restaurant(id=_TENANT_A, name="Cantina A"))
        self.restaurants.add(Restaurant(id=_TENANT_B, name="Cantina B"))
        self.units.add(Unit(id=_UNIT_A1, restaurant_id=_TENANT_A, name="Centro"))
        self.units.add(Unit(id=_UNIT_A2, restaurant_id=_TENANT_A, name="Praia"))
        self.units.add(Unit(id=_UNIT_B1, restaurant_id=_TENANT_B, name="Outra"))
        self.use_case = CreateUserUseCase(
            self.users,
            self.restaurants,
            self.units,
            self.hasher,
            FakeIdGenerator([_FIXED_ID]),
        )


def _command(**overrides: object) -> CreateUserCommand:
    base: dict[str, object] = {
        "email": Email("gerente@x.com"),
        "plain_password": "s3nha",
        "role": Role.MANAGER,
        "tenant_id": _TENANT_A,
        "unit_ids": (_UNIT_A1,),
    }
    base.update(overrides)
    return CreateUserCommand(**base)  # type: ignore[arg-type]


def test_cria_usuario_com_hash_e_nunca_com_a_senha_em_claro() -> None:
    """CA3 — o repositório recebe o hash produzido pelo port, não a senha.

    O fake usa um esquema transparente (`hashed::<senha>`) para ser legível na
    asserção, então o que se prova aqui é que o valor persistido **passou pelo
    hasher** e não é o texto cru — a força criptográfica é responsabilidade do
    adapter argon2 da 2.4, não deste teste.
    """
    fixture = _Fixture()

    result = fixture.use_case.execute(_command())

    assert result.id == str(_FIXED_ID)
    guardado = fixture.users.password_hashes[UserId(result.id)]
    assert guardado == fixture.hasher.hash("s3nha")
    assert guardado != "s3nha"


def test_email_duplicado_em_outro_tenant_e_rejeitado() -> None:
    """CA3 — unicidade é global (kickoff #2), não por restaurante."""
    fixture = _Fixture()
    fixture.use_case.execute(_command(tenant_id=_TENANT_A))

    with pytest.raises(EmailAlreadyRegisteredError):
        fixture.use_case.execute(_command(tenant_id=_TENANT_B, unit_ids=(_UNIT_B1,)))


def test_unicidade_de_email_e_cobrada_antes_da_regra_de_platform_admin() -> None:
    """A precedência (1) → (2) do §5.7, que nenhum outro teste distingue.

    Cada um dos outros testes aciona uma só das duas checagens, então ambos
    passam mesmo com a ordem trocada. Só um command que viola as **duas** —
    e-mail já registrado E `platform_admin` com unidade — revela qual vem antes.
    Verificado por mutação: trocar as checagens derruba apenas este teste.
    """
    fixture = _Fixture()
    fixture.use_case.execute(_command(email=Email("colisao@x.com")))

    with pytest.raises(EmailAlreadyRegisteredError):
        fixture.use_case.execute(
            _command(
                email=Email("colisao@x.com"),
                role=Role.PLATFORM_ADMIN,
                tenant_id=None,
                unit_ids=(_UNIT_A1,),
            )
        )


def test_email_duplicado_ignora_diferenca_de_caixa() -> None:
    """CA3 — `Email` normaliza no domínio, então a unicidade herda isso."""
    fixture = _Fixture()
    fixture.use_case.execute(_command(email=Email("dono@x.com")))

    with pytest.raises(EmailAlreadyRegisteredError):
        fixture.use_case.execute(_command(email=Email("Dono@X.com")))


def test_restaurante_inexistente_e_rejeitado() -> None:
    fixture = _Fixture()

    with pytest.raises(RestaurantNotFoundError):
        fixture.use_case.execute(_command(tenant_id=RestaurantId("nao-existe"), unit_ids=()))


def test_papel_de_restaurante_sem_tenant_viola_invariante_do_dominio() -> None:
    """A invariante é da 2.1 e sobe sem reembrulho."""
    fixture = _Fixture()

    with pytest.raises(MissingTenantError):
        fixture.use_case.execute(_command(tenant_id=None, unit_ids=()))


def test_cria_platform_admin_sem_tenant() -> None:
    """CA4 — acesso de plataforma vive fora de qualquer tenant (ADR 2.1.0002)."""
    fixture = _Fixture()

    result = fixture.use_case.execute(
        _command(role=Role.PLATFORM_ADMIN, tenant_id=None, unit_ids=())
    )

    assert result.tenant_id is None
    assert result.unit_ids == ()


def test_platform_admin_com_tenant_viola_invariante() -> None:
    fixture = _Fixture()

    with pytest.raises(PlatformAdminTenantError):
        fixture.use_case.execute(
            _command(role=Role.PLATFORM_ADMIN, tenant_id=_TENANT_A, unit_ids=())
        )


def test_platform_admin_com_unidade_e_rejeitado_sem_consultar_o_repositorio() -> None:
    """CA4 — a ordem impede um vazamento sutil de existência de unidade.

    Se a unidade fosse resolvida primeiro, o `platform_admin` receberia
    `UnitNotFoundError` para unidade inexistente e `PlatformAdminMembershipError`
    para unidade existente: a diferença entre as respostas enumeraria unidades.
    """
    fixture = _Fixture()

    with pytest.raises(PlatformAdminMembershipError):
        fixture.use_case.execute(
            _command(role=Role.PLATFORM_ADMIN, tenant_id=None, unit_ids=(_UNIT_A1,))
        )

    assert fixture.units.find_calls == 0
    assert fixture.users.users == {}


def test_cria_vinculo_por_unidade_informada() -> None:
    """CA5 — caminho feliz da visibilidade por unidade."""
    fixture = _Fixture()

    result = fixture.use_case.execute(_command(unit_ids=(_UNIT_A1, _UNIT_A2)))

    assert result.unit_ids == (_UNIT_A1, _UNIT_A2)
    vinculos = fixture.users.list_memberships(UserId(result.id))
    assert [v.unit_id for v in vinculos] == [_UNIT_A1, _UNIT_A2]


def test_unidades_repetidas_sao_deduplicadas_preservando_a_ordem() -> None:
    """CA5 — vínculo é relação; repetido daria conflito de PK na 2.3."""
    fixture = _Fixture()

    result = fixture.use_case.execute(_command(unit_ids=(_UNIT_A2, _UNIT_A1, _UNIT_A2)))

    assert result.unit_ids == (_UNIT_A2, _UNIT_A1)


def test_unidade_de_outro_tenant_e_rejeitada() -> None:
    """CA5 — isolamento imposto pelo domínio, não reimplementado aqui."""
    fixture = _Fixture()

    with pytest.raises(CrossTenantError):
        fixture.use_case.execute(_command(tenant_id=_TENANT_A, unit_ids=(_UNIT_B1,)))

    assert fixture.users.users == {}


def test_unidade_inexistente_e_rejeitada() -> None:
    fixture = _Fixture()

    with pytest.raises(UnitNotFoundError):
        fixture.use_case.execute(_command(unit_ids=(UnitId("nao-existe"),)))

    assert fixture.users.users == {}


def test_nada_e_persistido_quando_uma_validacao_falha() -> None:
    """Falha parcial deixaria usuário sem credencial ou sem vínculo."""
    fixture = _Fixture()

    with pytest.raises(CrossTenantError):
        fixture.use_case.execute(_command(unit_ids=(_UNIT_A1, _UNIT_B1)))

    assert fixture.users.users == {}
    assert fixture.users.password_hashes == {}
    assert fixture.users.list_all_memberships() == ()


def test_usuario_sem_unidade_e_valido() -> None:
    """Um `owner` enxerga o tenant inteiro por bypass, sem precisar de vínculo."""
    fixture = _Fixture()

    result = fixture.use_case.execute(_command(role=Role.OWNER, unit_ids=()))

    assert result.unit_ids == ()
    assert fixture.users.list_memberships(UserId(result.id)) == ()
