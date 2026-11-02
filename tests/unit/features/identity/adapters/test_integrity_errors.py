"""Tradução de `IntegrityError` → hierarquia `IdentityError` — CA20 / I11.

Metade destes testes cobre o que **é** traduzido; a outra metade cobre o que
**deliberadamente não é**. A segunda metade importa tanto quanto a primeira: a
não-tradução de FK é uma decisão explícita (concept §7 Decisão 7), e decisão sem
teste vira omissão silenciosa na primeira vez que alguém "consertar" o mapa
achando que faltava uma entrada.
"""

from types import SimpleNamespace

import pytest
from sqlalchemy.exc import IntegrityError

from restaurant_hub.features.identity.adapters.out.postgres import integrity_errors
from restaurant_hub.features.identity.application.errors import (
    EmailAlreadyRegisteredError,
    IdentityApplicationError,
    RestaurantAlreadyExistsError,
    SessionAlreadyExistsError,
    SessionFingerprintAlreadyExistsError,
    UnitAlreadyExistsError,
    UnitMembershipAlreadyExistsError,
    UserAlreadyExistsError,
)
from restaurant_hub.features.identity.domain.exceptions.errors import IdentityError

pytestmark = pytest.mark.unit


def _erro(constraint: str | None) -> IntegrityError:
    """`IntegrityError` com o `diag.constraint_name` que o psycopg 3 expõe."""
    original = SimpleNamespace(diag=SimpleNamespace(constraint_name=constraint))
    return IntegrityError("INSERT ...", {}, original)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("constraint", "esperado"),
    [
        ("pk_restaurants", RestaurantAlreadyExistsError),
        ("pk_units", UnitAlreadyExistsError),
        ("pk_users", UserAlreadyExistsError),
        ("uq_users_email", EmailAlreadyRegisteredError),
        ("pk_unit_memberships", UnitMembershipAlreadyExistsError),
        ("pk_sessions", SessionAlreadyExistsError),
        ("uq_sessions_fingerprint", SessionFingerprintAlreadyExistsError),
    ],
)
def test_constraint_de_negocio_vira_erro_de_dominio(
    constraint: str, esperado: type[Exception]
) -> None:
    traduzido = integrity_errors.traduzir(_erro(constraint), "chave-1")
    assert isinstance(traduzido, esperado)
    # Invariante #16 da 2.2: nada escapa da hierarquia e vira 500 por descuido.
    # Pertinência às **duas** raízes do BC (ADR 3.9.0001): o que importa é que
    # nada escape da hierarquia de identity, não qual das duas raízes.
    assert isinstance(traduzido, IdentityError | IdentityApplicationError)


@pytest.mark.parametrize(
    "constraint",
    [
        "fk_units_restaurant",
        "fk_users_tenant",
        "fk_memberships_unit",
        "fk_memberships_user",
        "fk_sessions_user",
    ],
)
def test_violacao_de_fk_nao_e_traduzida(constraint: str) -> None:
    """Decisão 7: FK sobe como `IntegrityError`, de propósito.

    O use case da 2.2 já valida existência de restaurante e mesmo-tenant **antes**
    de gravar, então uma FK que estoura aqui é concorrência exótica ou bug — e
    traduzi-la para erro de negócio a esconderia atrás de um 4xx plausível, que é
    a pior coisa que se pode fazer com um defeito.
    """
    erro = _erro(constraint)
    assert integrity_errors.traduzir(erro, "chave-1") is erro


def test_check_de_invariante_nao_e_traduzida() -> None:
    """As CHECKs guardam invariante de domínio que o construtor já impõe.

    Estourar uma delas significa que alguém escreveu no banco por fora do domínio
    — de novo, bug, não regra de negócio.
    """
    erro = _erro("ck_users_tenant_iff_platform_admin")
    assert integrity_errors.traduzir(erro, "user-1") is erro


def test_constraint_desconhecida_sobe_intacta() -> None:
    """Inventar erro de negócio para o que não se entende perde o bug de vista."""
    erro = _erro("uq_alguma_coisa_nova")
    assert integrity_errors.traduzir(erro, "x") is erro


def test_erro_sem_nome_de_constraint_sobe_intacto() -> None:
    """Sem `diag.constraint_name` não há como decidir — degradar para parsing de
    mensagem trocaria uma falha explícita por uma silenciosa."""
    erro = _erro(None)
    assert integrity_errors.traduzir(erro, "x") is erro


def test_erro_sem_diag_algum_sobe_intacto() -> None:
    """Outro driver, ou erro que não é de constraint."""
    erro = IntegrityError("INSERT ...", {}, Exception("boom"))  # type: ignore[arg-type]
    assert integrity_errors.traduzir(erro, "x") is erro
    assert integrity_errors.nome_da_constraint(erro) is None


def test_detalhe_chega_na_mensagem_do_erro_traduzido() -> None:
    """Sem a chave em conflito, a mensagem é inútil para diagnóstico."""
    traduzido = integrity_errors.traduzir(_erro("pk_users"), "user-42")
    assert "user-42" in str(traduzido)
