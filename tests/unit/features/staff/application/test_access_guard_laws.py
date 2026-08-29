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
_OTHER_TENANT = "t2"
_UNIT = "u1"
_OTHER_UNIT = "u2"

# **Os dois alvos do Step 3, e o par é a unidade de parametrização das leis.**
#
# Não é simetria decorativa. Com as leis escritas só sobre `manage_staff`, a
# recusa passa a estar travada **por permissão**, e não como propriedade: uma
# guarda condicionada — `if not actor_tenant_id and permission !=
# "manage_job_functions"` — satisfaz a suíte inteira e deixa
# `AuthorizedScope(tenant_id=None)` sair do guard. Medido: essa mutação
# sobrevivia antes desta parametrização, nas **duas** implementações do port.
#
# O agravante é que o desenho já argumenta contra ela: o tradutor impõe L-AG3
# em vez de confiar no *"platform_admin é negado antes, no passo 2"* justamente
# porque o mapa RBAC é editável. Uma profundidade de defesa que cobre metade do
# vocabulário é meia defesa — e a metade descoberta era a permissão **cujo alvo
# é o restaurante inteiro**.
#
# A unidade viaja junto da permissão porque as duas são um alvo só: ação
# tenant-wide não nomeia unidade, e um par `(manage_job_functions, "u1")` não é
# um alvo que exista.
_ALVOS = [
    pytest.param(_MANAGE_STAFF, _UNIT, id="unit-scoped"),
    pytest.param(_MANAGE_JOB_FUNCTIONS, None, id="tenant-wide"),
]

# **O eixo do tenant na chamada — nomeado x omitido** (ADR 0.0.0005).
#
# `tenant_id=None` significa *"o tenant do próprio ator"*, e o significado é do
# **contrato**: as duas implementações do port são obrigadas por ele. Este
# `parametrize` é deliberadamente **idêntico em forma** ao de
# `test_composition_root_staff.py`, que cobra a mesma lei do tradutor de
# produção — cobrar as duas com conjuntos de valores diferentes é o sinal de
# alerta mais forte da família "lei universal, representante estreito", e foi
# assim que a Stage 3.4 vazou duas mutações.
#
# O eixo entra em **produto** com `_ALVOS` porque a resolução do tenant não pode
# ser propriedade de uma permissão: uma resolução condicionada a `permission ==
# "manage_staff"` deixaria o catálogo de funções — cujo alvo é o restaurante
# inteiro — inalcançável, e nenhuma suíte parametrizada só sobre `manage_staff`
# observaria isso.
_TENANT_NA_CHAMADA = [
    pytest.param(_TENANT, id="tenant-nomeado"),
    pytest.param(None, id="tenant-omitido"),
]


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


@pytest.mark.parametrize(("permission", "unit"), _ALVOS)
def test_l_ag2_alvo_nao_concedido_levanta_a_sentinela_crua(
    permission: str,
    unit: str | None,
) -> None:
    """Ator legítimo, alvo não concedido: levanta **o mesmo objeto**.

    Parametrizado sobre as duas permissões porque é um ramo de **recusa**: sem
    isso, a permissão tenant-wide só apareceria em caminho de sucesso, e uma
    negação que a dispensasse não teria teste que a observasse.
    """
    guard = _guard_with_actor()
    actor = guard.authenticate(request=object())

    with pytest.raises(FakeAuthorizationRejected) as excinfo:
        guard.authorize(actor, permission, tenant_id=_TENANT, unit_id=unit)

    assert excinfo.value is guard.authorization_error


@pytest.mark.parametrize(("permission", "unit"), _ALVOS)
def test_l_ag2_ator_que_este_guard_nao_emitiu_e_negado(
    permission: str,
    unit: str | None,
) -> None:
    """`Actor = object` deixa qualquer objeto passar pelo type-checker.

    Quem fecha essa porta é a implementação, em runtime — e sem esta asserção o
    fake poderia autorizar um ator forjado e a suíte não notaria. O alvo está
    **concedido** de propósito: o que se prova é que a recusa vem do ator, não
    da falta de concessão — e vale para as duas permissões.
    """
    guard = _guard_with_actor()
    guard.grant(permission, tenant_id=_TENANT, unit_id=unit)

    with pytest.raises(FakeAuthorizationRejected) as excinfo:
        guard.authorize(
            FakeActor(id="forjado", tenant_id=_TENANT),
            permission,
            tenant_id=_TENANT,
            unit_id=unit,
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
# ADR 0.0.0005 — `tenant_id` ausente significa "o tenant do próprio ator"
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("tenant_na_chamada", _TENANT_NA_CHAMADA)
@pytest.mark.parametrize(("permission", "unit"), _ALVOS)
def test_o_tenant_omitido_resolve_para_o_do_ator_e_alcanca_a_concessao(
    permission: str,
    unit: str | None,
    tenant_na_chamada: str | None,
) -> None:
    """A concessão é feita com o tenant **nomeado**, e a chamada que o omite a alcança.

    É a lei do ADR 0.0.0005 do lado do fake, e ela tem duas metades que este
    único teste cobra porque são a mesma travessia: o **pedido** (a ausência
    resolve para o tenant do ator antes de consultar `grants` — sem isso a
    chamada omissa não acharia a concessão e cairia na recusa) e a **resposta**
    (o escopo devolvido carrega o tenant do ator).

    **A asserção é contra o escopo esperado, escrito por extenso, e não entre as
    duas execuções.** Comparar o resultado nomeado com o omitido passaria se os
    **dois** estivessem errados do mesmo jeito — é a lição que CA04 registra
    sobre `sorted`, aplicada aqui.
    """
    guard = _guard_with_actor()
    guard.grant(permission, tenant_id=_TENANT, unit_id=unit)
    actor = guard.authenticate(request=object())

    escopo = guard.authorize(actor, permission, tenant_id=tenant_na_chamada, unit_id=unit)

    assert escopo == AuthorizedScope(
        tenant_id=TenantId(_TENANT),
        unit_id=UnitId(unit) if unit is not None else None,
    )


@pytest.mark.parametrize(("permission", "unit"), _ALVOS)
def test_omitir_o_tenant_produz_o_mesmo_resultado_que_nomear_o_do_ator(
    permission: str,
    unit: str | None,
) -> None:
    """A equivalência literal do critério — as duas formas do pedido, um resultado."""
    guard = _guard_with_actor()
    guard.grant(permission, tenant_id=_TENANT, unit_id=unit)
    actor = guard.authenticate(request=object())

    nomeado = guard.authorize(actor, permission, tenant_id=_TENANT, unit_id=unit)
    omitido = guard.authorize(actor, permission, tenant_id=None, unit_id=unit)

    assert nomeado == omitido


@pytest.mark.parametrize(("permission", "unit"), _ALVOS)
def test_o_tenant_omitido_nao_alcanca_a_concessao_de_outro_tenant(
    permission: str,
    unit: str | None,
) -> None:
    """A resolução é do tenant **do ator**, não de um tenant qualquer.

    Sem esta recusa, uma implementação que tratasse a ausência como curinga —
    "qualquer concessão serve" — passaria no teste acima, e a ausência deixaria
    de ser a forma **mais restritiva** do pedido que o ADR 0.0.0005 promete.
    """
    guard = _guard_with_actor()
    guard.grant(permission, tenant_id=_OTHER_TENANT, unit_id=unit)
    actor = guard.authenticate(request=object())

    with pytest.raises(FakeAuthorizationRejected) as excinfo:
        guard.authorize(actor, permission, tenant_id=None, unit_id=unit)

    assert excinfo.value is guard.authorization_error


# ---------------------------------------------------------------------------
# L-AG3 — `tenant_id` nunca sai vazio; ator sem tenant é negado
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("tenant_na_chamada", _TENANT_NA_CHAMADA)
@pytest.mark.parametrize("tenant_do_ator", [None, ""])
@pytest.mark.parametrize(("permission", "unit"), _ALVOS)
def test_l_ag3_ator_sem_tenant_e_negado_mesmo_com_o_alvo_concedido(
    permission: str,
    unit: str | None,
    tenant_do_ator: str | None,
    tenant_na_chamada: str | None,
) -> None:
    """A recusa **não** depende de o alvo estar fora do mapa de concessões.

    Três dimensões, e as três foram medidas como necessárias.

    **O tenant na chamada:** L-AG3 tem de valer nos **dois** eixos do
    ADR 0.0.0005. O eixo omitido é o que a resolução nova cria, e é o perigoso:
    uma resolução escrita como `TenantId(tenant_id or actor.tenant_id or "")`
    passaria no eixo nomeado e reabriria o tenant vazio no omitido.

    **O valor do tenant:** `None` é o `platform_admin` de hoje
    (`AuthorizedActor.actor_tenant_id` é `RestaurantId | None`), e `""` é o
    resultado que a coerção proibida (`TenantId(actor_tenant_id or "")`)
    produziria se alguém a escrevesse mais acima na cadeia.

    **A permissão:** L-AG3 é propriedade do *guard*, não de uma capacidade. Com
    só `manage_staff`, condicionar a recusa a `permission !=
    "manage_job_functions"` mantinha a suíte verde — e a permissão dispensada
    seria justamente a de alcance tenant-wide.

    As oito combinações têm de terminar em recusa, não em escopo.
    """
    guard = InMemoryAccessGuard(credential=FakeActor(id="a1", tenant_id=tenant_do_ator))
    guard.grant(permission, tenant_id=_TENANT, unit_id=unit)
    actor = guard.authenticate(request=object())

    with pytest.raises(FakeAuthorizationRejected) as excinfo:
        guard.authorize(actor, permission, tenant_id=tenant_na_chamada, unit_id=unit)

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
        guard.authorize(actor, _MANAGE_STAFF, tenant_id=tenant_na_chamada, unit_id=_UNIT)
        for tenant_na_chamada in (_TENANT, None)
    ] + [
        guard.authorize(actor, _MANAGE_STAFF, tenant_id=_TENANT, unit_id=_OTHER_UNIT),
        guard.authorize(actor, _MANAGE_JOB_FUNCTIONS, tenant_id=None),
        guard.authorize(actor, _MANAGE_JOB_FUNCTIONS, tenant_id=_TENANT),
    ]

    assert escopos, "a varredura precisa de retornos para ter o que negar"
    assert all(escopo.tenant_id for escopo in escopos)


# ---------------------------------------------------------------------------
# L-AG4 — uma autorização por alvo
# ---------------------------------------------------------------------------


def test_l_ag4_autorizar_uma_unidade_nao_autoriza_a_vizinha() -> None:
    """Unidade concedida não arrasta a vizinha — nem com a mesma permissão."""
    guard = _guard_with_actor()
    guard.grant(_MANAGE_STAFF, tenant_id=_TENANT, unit_id=_UNIT)
    actor = guard.authenticate(request=object())

    guard.authorize(actor, _MANAGE_STAFF, tenant_id=_TENANT, unit_id=_UNIT)

    with pytest.raises(FakeAuthorizationRejected) as excinfo:
        guard.authorize(actor, _MANAGE_STAFF, tenant_id=_TENANT, unit_id=_OTHER_UNIT)

    assert excinfo.value is guard.authorization_error


def test_l_ag4_autorizar_um_tenant_nao_autoriza_o_outro_em_permissao_tenant_wide() -> None:
    """A forma que L-AG4 assume quando o alvo **não é** uma unidade.

    Sem este caso, o ramo de **recusa** de L-AG4 nunca rodaria com
    `manage_job_functions`: a permissão tenant-wide só aparecia em caminho de
    sucesso, e "autorizar um alvo não autoriza outro" ficava provado apenas para
    o eixo que ela não usa. Aqui o alvo que muda é o **restaurante**, que é o que
    o catálogo de funções endereça (`workforce.md` §3.2).
    """
    guard = _guard_with_actor()
    guard.grant(_MANAGE_JOB_FUNCTIONS, tenant_id=_TENANT)
    actor = guard.authenticate(request=object())

    guard.authorize(actor, _MANAGE_JOB_FUNCTIONS, tenant_id=_TENANT)

    with pytest.raises(FakeAuthorizationRejected) as excinfo:
        guard.authorize(actor, _MANAGE_JOB_FUNCTIONS, tenant_id=_OTHER_TENANT)

    assert excinfo.value is guard.authorization_error


def test_l_ag4_autorizar_uma_permissao_nao_autoriza_a_outra() -> None:
    """O terceiro eixo do alvo: a **permissão**.

    `manage_staff` concedido numa unidade não concede `manage_job_functions` no
    mesmo tenant, e vice-versa. Sem esta asserção, um guard que resolvesse por
    `(tenant, unidade)` ignorando a permissão passaria em tudo o que está acima.
    """
    guard = _guard_with_actor()
    guard.grant(_MANAGE_STAFF, tenant_id=_TENANT, unit_id=_UNIT)
    actor = guard.authenticate(request=object())

    with pytest.raises(FakeAuthorizationRejected) as excinfo:
        guard.authorize(actor, _MANAGE_JOB_FUNCTIONS, tenant_id=_TENANT)

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


@pytest.mark.parametrize(("permission", "unit"), _ALVOS)
def test_l_ag4_a_autorizacao_negada_tambem_aparece_no_registro(
    permission: str,
    unit: str | None,
) -> None:
    """Contar só as bem-sucedidas esconderia a tentativa — e L-AG4 é sobre chamadas."""
    guard = _guard_with_actor()
    actor = guard.authenticate(request=object())
    guard.calls.clear()

    with pytest.raises(FakeAuthorizationRejected):
        guard.authorize(actor, permission, tenant_id=_TENANT, unit_id=unit)

    assert guard.calls == [f"authorize({permission},{_TENANT},{unit})"]
