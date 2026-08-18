"""As quatro leis do port `AccessGuard`, contra a segunda implementação — CA14.

Um teste por lei, com o nome da lei no identificador (convenção das suítes de
lei do Step 3). O sujeito é o **fake**, e não o tradutor de produção: a lei que
só a implementação real cumpre não é lei, é descrição (ADR 3.4.0001
§Implementation notes). O tradutor entra na Task 06 e é obrigado pelas mesmas
quatro.

**Por que a identidade do objeto levantado é a asserção de L-AG1/L-AG2.**
`pytest.raises(TipoX)` prova que *algum* `TipoX` saiu — e passa para um
implementador que capture a exceção e relance um `TipoX` novo, que é exatamente
a tradução que as duas leis proíbem. `excinfo.value is guard.<sentinela>` só é
verdade se ninguém tocou no objeto no caminho. É a diferença entre "o tipo
combina" e "a exceção saiu crua".
"""

import pytest

from restaurant_hub.features.staff.application.ports.out.access_guard import AuthorizedScope
from restaurant_hub.features.staff.domain.value_objects.identifiers import TenantId, UnitId
from tests.fakes.features.staff.in_memory_access_guard import (
    FakeActor,
    FakeAuthorizationRejected,
    FakeCredentialRejected,
    InMemoryAccessGuard,
)

pytestmark = pytest.mark.unit

_MANAGE_STAFF = "manage_staff"
_MANAGE_JOB_FUNCTIONS = "manage_job_functions"
_TENANT = "t1"
_UNIT = "u1"
_OTHER_UNIT = "u2"


def _guard_with_actor(*, tenant_id: str | None = _TENANT) -> InMemoryAccessGuard:
    """Guard com credencial válida — o ponto de partida de tudo menos L-AG1."""
    return InMemoryAccessGuard(credential=FakeActor(id="a1", tenant_id=tenant_id))


# ---------------------------------------------------------------------------
# L-AG1 — a exceção de autenticação sai crua
# ---------------------------------------------------------------------------


def test_l_ag1_credencial_ausente_levanta_a_sentinela_crua() -> None:
    """Sem credencial, `authenticate` levanta — e levanta **o mesmo objeto**."""
    guard = InMemoryAccessGuard()

    with pytest.raises(FakeCredentialRejected) as excinfo:
        guard.authenticate(request=object())

    assert excinfo.value is guard.credential_error


def test_l_ag1_credencial_valida_devolve_o_ator_sem_levantar() -> None:
    """O ramo positivo, sem o qual a lei acima passaria vacuamente.

    Um guard que levantasse **sempre** satisfaria a asserção de L-AG1 e não
    seria implementação nenhuma.
    """
    guard = _guard_with_actor()

    assert guard.authenticate(request=object()) is guard.credential


# ---------------------------------------------------------------------------
# L-AG2 — a exceção de autorização sai crua
# ---------------------------------------------------------------------------


def test_l_ag2_alvo_nao_concedido_levanta_a_sentinela_crua() -> None:
    """Ator legítimo, alvo não concedido: levanta **o mesmo objeto**."""
    guard = _guard_with_actor()
    actor = guard.authenticate(request=object())

    with pytest.raises(FakeAuthorizationRejected) as excinfo:
        guard.authorize(actor, _MANAGE_STAFF, tenant_id=_TENANT, unit_id=_UNIT)

    assert excinfo.value is guard.authorization_error


def test_l_ag2_ator_que_este_guard_nao_emitiu_e_negado() -> None:
    """`Actor = object` deixa qualquer objeto passar pelo type-checker.

    Quem fecha essa porta é a implementação, em runtime — e sem esta asserção o
    fake poderia autorizar um ator forjado e a suíte não notaria.
    """
    guard = _guard_with_actor()
    guard.grant(_MANAGE_STAFF, tenant_id=_TENANT, unit_id=_UNIT)

    with pytest.raises(FakeAuthorizationRejected) as excinfo:
        guard.authorize(
            FakeActor(id="forjado", tenant_id=_TENANT),
            _MANAGE_STAFF,
            tenant_id=_TENANT,
            unit_id=_UNIT,
        )

    assert excinfo.value is guard.authorization_error


def test_l_ag2_alvo_concedido_devolve_o_escopo() -> None:
    """O ramo positivo de L-AG2 — o guard concede o que foi concedido."""
    guard = _guard_with_actor()
    guard.grant(_MANAGE_STAFF, tenant_id=_TENANT, unit_id=_UNIT)
    actor = guard.authenticate(request=object())

    escopo = guard.authorize(actor, _MANAGE_STAFF, tenant_id=_TENANT, unit_id=_UNIT)

    assert escopo == AuthorizedScope(tenant_id=TenantId(_TENANT), unit_id=UnitId(_UNIT))


def test_l_ag2_permissao_tenant_wide_devolve_escopo_sem_unidade() -> None:
    """`manage_job_functions` não nomeia unidade — e o escopo reflete isso.

    Sem esta asserção, `unit_id: UnitId | None` seria um `None` que nenhum teste
    exercita, e a Stage 3.6 descobriria na rota do catálogo de funções.
    """
    guard = _guard_with_actor()
    guard.grant(_MANAGE_JOB_FUNCTIONS, tenant_id=_TENANT)
    actor = guard.authenticate(request=object())

    escopo = guard.authorize(actor, _MANAGE_JOB_FUNCTIONS, tenant_id=_TENANT)

    assert escopo.unit_id is None
    assert escopo.tenant_id == _TENANT


# ---------------------------------------------------------------------------
# L-AG3 — `tenant_id` nunca sai vazio; ator sem tenant é negado
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("tenant_do_ator", [None, ""])
def test_l_ag3_ator_sem_tenant_e_negado_mesmo_com_o_alvo_concedido(
    tenant_do_ator: str | None,
) -> None:
    """A recusa **não** depende de o alvo estar fora do mapa de concessões.

    Os dois valores importam e são casos distintos: `None` é o
    `platform_admin` de hoje (`AuthorizedActor.actor_tenant_id` é
    `RestaurantId | None`), e `""` é o resultado que a coerção proibida
    (`TenantId(actor_tenant_id or "")`) produziria se alguém a escrevesse mais
    acima na cadeia. Os dois têm de terminar em recusa, não em escopo.
    """
    guard = InMemoryAccessGuard(credential=FakeActor(id="a1", tenant_id=tenant_do_ator))
    guard.grant(_MANAGE_STAFF, tenant_id=_TENANT, unit_id=_UNIT)
    actor = guard.authenticate(request=object())

    with pytest.raises(FakeAuthorizationRejected) as excinfo:
        guard.authorize(actor, _MANAGE_STAFF, tenant_id=_TENANT, unit_id=_UNIT)

    assert excinfo.value is guard.authorization_error


def test_l_ag3_nenhum_escopo_devolvido_carrega_tenant_falsy() -> None:
    """Varredura sobre **todos** os escopos que este guard consegue devolver.

    A lei é universal ("nunca devolve"), então a asserção pontual do teste
    acima não a esgota: ela cobre o caminho de recusa. Aqui o sujeito é o
    caminho de **sucesso** — e a asserção é sobre o conjunto inteiro de
    retornos, que é a forma de uma lei negativa virar teste.
    """
    guard = _guard_with_actor()
    guard.grant(_MANAGE_STAFF, tenant_id=_TENANT, unit_id=_UNIT)
    guard.grant(_MANAGE_STAFF, tenant_id=_TENANT, unit_id=_OTHER_UNIT)
    guard.grant(_MANAGE_JOB_FUNCTIONS, tenant_id=_TENANT)
    actor = guard.authenticate(request=object())

    escopos = [
        guard.authorize(actor, _MANAGE_STAFF, tenant_id=_TENANT, unit_id=_UNIT),
        guard.authorize(actor, _MANAGE_STAFF, tenant_id=_TENANT, unit_id=_OTHER_UNIT),
        guard.authorize(actor, _MANAGE_JOB_FUNCTIONS, tenant_id=_TENANT),
    ]

    assert escopos, "a varredura precisa de retornos para ter o que negar"
    assert all(escopo.tenant_id for escopo in escopos)


# ---------------------------------------------------------------------------
# L-AG4 — uma autorização por alvo
# ---------------------------------------------------------------------------


def test_l_ag4_autorizar_um_alvo_nao_autoriza_outro() -> None:
    """Unidade concedida não arrasta a vizinha — nem com a mesma permissão."""
    guard = _guard_with_actor()
    guard.grant(_MANAGE_STAFF, tenant_id=_TENANT, unit_id=_UNIT)
    actor = guard.authenticate(request=object())

    guard.authorize(actor, _MANAGE_STAFF, tenant_id=_TENANT, unit_id=_UNIT)

    with pytest.raises(FakeAuthorizationRejected) as excinfo:
        guard.authorize(actor, _MANAGE_STAFF, tenant_id=_TENANT, unit_id=_OTHER_UNIT)

    assert excinfo.value is guard.authorization_error


def test_l_ag4_cada_alvo_produz_a_sua_propria_chamada_no_registro() -> None:
    """A metade mecânica: **uma** chamada por alvo, nenhuma reaproveitada.

    O registro carrega o alvo justamente por isto — um `calls` que gravasse só
    `"authorize"` não distinguiria duas autorizações do mesmo alvo de duas de
    alvos diferentes, e a lei ficaria sem asserção possível.
    """
    guard = _guard_with_actor()
    guard.grant(_MANAGE_STAFF, tenant_id=_TENANT, unit_id=_UNIT)
    guard.grant(_MANAGE_STAFF, tenant_id=_TENANT, unit_id=_OTHER_UNIT)
    actor = guard.authenticate(request=object())
    guard.calls.clear()

    guard.authorize(actor, _MANAGE_STAFF, tenant_id=_TENANT, unit_id=_UNIT)
    guard.authorize(actor, _MANAGE_STAFF, tenant_id=_TENANT, unit_id=_OTHER_UNIT)

    assert guard.calls == [
        f"authorize({_MANAGE_STAFF},{_TENANT},{_UNIT})",
        f"authorize({_MANAGE_STAFF},{_TENANT},{_OTHER_UNIT})",
    ]


def test_l_ag4_a_autorizacao_negada_tambem_aparece_no_registro() -> None:
    """Contar só as bem-sucedidas esconderia a tentativa — e L-AG4 é sobre chamadas."""
    guard = _guard_with_actor()
    actor = guard.authenticate(request=object())
    guard.calls.clear()

    with pytest.raises(FakeAuthorizationRejected):
        guard.authorize(actor, _MANAGE_STAFF, tenant_id=_TENANT, unit_id=_UNIT)

    assert guard.calls == [f"authorize({_MANAGE_STAFF},{_TENANT},{_UNIT})"]
