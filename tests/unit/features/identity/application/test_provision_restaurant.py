"""Testes do use case `provision_restaurant` — issue #67, ADR 0.0.0012.

O que estes testes protegem: o restaurante e o seu `owner` nascem **juntos** —
nenhuma falha deixa um restaurante sem dono —, o papel emitido é sempre `owner`
(nunca vem do command), o tenant do dono é o restaurante novo, e as recusas
acontecem antes de qualquer escrita.
"""

from collections.abc import Sequence
from uuid import UUID

import pytest

from restaurant_hub.features.identity.application.dtos.commands import (
    ProvisionRestaurantCommand,
)
from restaurant_hub.features.identity.application.dtos.identifiers import PasswordHash
from restaurant_hub.features.identity.application.errors import (
    EmailAlreadyRegisteredError,
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
from tests.fakes.features.identity.fake_password_hasher import FakePasswordHasher
from tests.fakes.features.identity.in_memory_restaurant_repository import (
    InMemoryRestaurantRepository,
)
from tests.fakes.features.identity.in_memory_unit_of_work import InMemoryUnitOfWork
from tests.fakes.features.identity.in_memory_user_repository import InMemoryUserRepository
from tests.fakes.shared.fake_id_generator import FakeIdGenerator

pytestmark = pytest.mark.unit

# Distintos de propósito: com o mesmo id para os dois, trocar qual vai para o
# restaurante e qual vai para o dono passaria despercebido.
_ID_DO_RESTAURANTE = UUID("11111111-1111-1111-1111-111111111111")
_ID_DO_DONO = UUID("22222222-2222-2222-2222-222222222222")
_EMAIL = Email("dono@cantina.com")
_SENHA = "s3nha-do-dono"
_ESCRITAS = ("restaurants.add", "users.add")


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


class _UsuariosQueNaoVeemOEmail(InMemoryUserRepository):
    """`exists_by_email` mente `False`: a corrida em que outro cadastro comita entre a
    checagem e o `users.add`. Quem recusa é o próprio `add` — o índice único."""

    def exists_by_email(self, email: Email) -> bool:
        return False


class Cenario:
    def __init__(
        self,
        *,
        registro: _Registro | None = None,
        users: InMemoryUserRepository | None = None,
    ) -> None:
        self.registro = registro if registro is not None else _Registro()
        self.restaurants = _RestaurantesRegistrados(self.registro)
        self.users = users if users is not None else _UsuariosRegistrados(self.registro)
        self.hasher = FakePasswordHasher()
        self.ids = FakeIdGenerator([_ID_DO_RESTAURANTE, _ID_DO_DONO])
        self.unidade = InMemoryUnitOfWork(self.restaurants, self.users)
        self.use_case = ProvisionRestaurantUseCase(
            restaurants=self.restaurants,
            users=self.users,
            hasher=self.hasher,
            id_generator=self.ids,
            unit_of_work=self.unidade,
        )


def _comando(name: str = "Cantina do Zé") -> ProvisionRestaurantCommand:
    return ProvisionRestaurantCommand(name=name, owner_email=_EMAIL, owner_plain_password=_SENHA)


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

    def test_grava_o_hash_da_senha_e_nao_a_senha(self) -> None:
        cenario = Cenario()

        cenario.use_case.execute(_comando())

        gravado = cenario.users.password_hashes[UserId(str(_ID_DO_DONO))]
        assert gravado == cenario.hasher.hash(_SENHA)
        assert gravado != _SENHA

    def test_dono_nasce_sem_vinculo_de_unidade(self) -> None:
        """O restaurante acabou de nascer: não há unidade a que o dono pertença."""
        cenario = Cenario()

        cenario.use_case.execute(_comando())

        assert cenario.users.memberships == []

    def test_o_repr_do_command_nao_carrega_a_senha(self) -> None:
        assert _SENHA not in repr(_comando())


class TestCasosDeErro:
    def test_nome_vazio_levanta_sem_gravar_nada(self) -> None:
        cenario = Cenario()

        with pytest.raises(InvalidNameError):
            cenario.use_case.execute(_comando(name="   "))

        assert cenario.registro.escritas == []
        assert cenario.unidade.aberturas == 0

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

        with pytest.raises(EmailAlreadyRegisteredError):
            cenario.use_case.execute(_comando())

        assert cenario.restaurants.restaurants == {}
        assert cenario.registro.escritas == []
        assert cenario.unidade.aberturas == 0

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
    """Issue #67 — restaurante e dono são tudo ou nada."""

    def test_as_duas_escritas_acontecem_dentro_de_uma_unidade(self) -> None:
        cenario = Cenario()

        cenario.use_case.execute(_comando())

        assert tuple(cenario.registro.escritas) == _ESCRITAS
        assert (cenario.unidade.aberturas, cenario.unidade.commits) == (1, 1)

    @pytest.mark.parametrize("n", range(1, len(_ESCRITAS) + 1))
    def test_falha_na_escrita_n_nao_deixa_restaurante_nem_dono(self, n: int) -> None:
        cenario = Cenario(registro=_Registro(falhar_em=n))

        with pytest.raises(_FalhaInjetada):
            cenario.use_case.execute(_comando())

        assert tuple(cenario.registro.escritas) == _ESCRITAS[:n]
        assert cenario.restaurants.restaurants == {}
        assert cenario.users.users == {}
        assert cenario.users.exists_by_email(_EMAIL) is False
        assert cenario.unidade.rollbacks == 1

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
        assert cenario.unidade.rollbacks == 1

    def test_id_de_restaurante_repetido_nao_cria_o_dono(self) -> None:
        cenario = Cenario()
        cenario.restaurants.restaurants[RestaurantId(str(_ID_DO_RESTAURANTE))] = Restaurant(
            id=RestaurantId(str(_ID_DO_RESTAURANTE)), name="Antigo"
        )

        with pytest.raises(RestaurantAlreadyExistsError):
            cenario.use_case.execute(_comando())

        assert cenario.users.users == {}
        assert cenario.restaurants.restaurants[RestaurantId(str(_ID_DO_RESTAURANTE))].name == (
            "Antigo"
        )
