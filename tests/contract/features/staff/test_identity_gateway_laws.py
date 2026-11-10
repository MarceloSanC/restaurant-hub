"""As cinco leis do `IdentityGateway` — L-IG1…L-IG5 — como contrato (Stages 3.5 e 3.8).

Nasce **já** em `tests/contract/`, na forma que o ADR 3.3.0007 fixou para os
repositórios: um corpo de teste só, parametrizado pela fixture `gateway` sobre
as implementações do port (`IMPLEMENTACOES_DO_GATEWAY` no `conftest.py`). Na
Task 04 da Stage só o fake roda; a Task 09 acrescenta o `LocalIdentityGateway`
sobre a fachada de identity — e é aí que cada lei passa a ser **lei**, e não
descrição de um implementador.

O corpo **não sabe** com qual implementação fala. Os cenários que cada lado
produz do seu jeito (e-mail já usado; unidade que não existe; envio que falha)
chegam por **funções de arranjo** do holder, e os efeitos que só o outro lado
da fronteira enxerga (papel do login criado; token que o redime) por **funções
de observação** — ver `GatewaySobContrato`. Qualquer `if` sobre a implementação
aqui é acusado por `test_no_implementation_branching.py`.

A lei mais importante do módulo é a segunda metade de **L-IG2**: um gateway que
traduzisse `CrossTenantError` para `LoginEmailAlreadyInUseError`, ou que
engolisse a falha do envio, passaria em todos os outros testes — e o segundo
caso é o modo de falha exato que a regra 13 da 2.5 existe para impedir (201
sem e-mail, gerente convencido de que convidou).
"""

import dataclasses

import pytest

from restaurant_hub.features.staff.application.errors import (
    InvalidLoginEmailError,
    LoginEmailAlreadyInUseError,
    StaffApplicationError,
)
from restaurant_hub.features.staff.application.ports.out import identity_gateway
from restaurant_hub.features.staff.application.ports.out.identity_gateway import (
    LoginDelivery,
    ProvisionedLogin,
)
from restaurant_hub.features.staff.domain.exceptions.errors import StaffError
from restaurant_hub.features.staff.domain.value_objects.identifiers import (
    TenantId,
    UnitId,
    UserId,
)
from tests.contract.features.staff.conftest import GatewaySobContrato

pytestmark = pytest.mark.contract

_EMAIL = "ana@cantina.com"
_OUTRO_EMAIL = "bruno@cantina.com"
# O tipo do erro do envio é irrelevante para a lei: o que se assere é que **a
# mesma instância** sobe. `RuntimeError` porque é o que o `RecordingEmailSender`
# da 2.5 já usa como falha sob demanda.
_FALHA_DO_ENVIO = RuntimeError("smtp indisponível")


def _provisionar(
    gateway: GatewaySobContrato,
    email: str = _EMAIL,
    *,
    delivery: LoginDelivery = LoginDelivery.LINK,
    tenant_id: TenantId | None = None,
    unit_id: UnitId | None = None,
) -> ProvisionedLogin:
    return gateway.gateway.provision_employee_login(
        email=email,
        tenant_id=tenant_id if tenant_id is not None else gateway.tenant_id,
        unit_id=unit_id if unit_id is not None else gateway.unit_id,
        delivery=delivery,
    )


# ---------------------------------------------------------------------------
# L-IG1 — papel e escopo são do port; o resultado é o login recém-criado
# ---------------------------------------------------------------------------


def test_l_ig1_o_login_criado_e_de_funcionario(gateway: GatewaySobContrato) -> None:
    """O port não tem parâmetro de papel — e o que nasce é `employee`, sempre."""
    login = _provisionar(gateway)

    assert gateway.login_role_of(login.user_id) == "employee"


def test_l_ig1_o_login_e_escopado_ao_tenant_e_a_unidade_do_registro(
    gateway: GatewaySobContrato,
) -> None:
    """A metade de escopo de L-IG1: dentro do tenant e membro de **exatamente** a unidade.

    Do lado real, o `User` criado tem `tenant_id` e uma única membership — a da
    unidade passada. Um gateway que passasse `unit_ids=()` ou a unidade errada
    passaria em todos os outros testes de L-IG1 e morreria aqui.
    """
    login = _provisionar(gateway)

    assert gateway.login_scope_of(login.user_id) == (
        str(gateway.tenant_id),
        (str(gateway.unit_id),),
    )


def test_l_ig1_cada_provisionamento_e_um_login_novo(gateway: GatewaySobContrato) -> None:
    """Dois pedidos, dois `user_id` — nunca um pré-existente (L-IG1)."""
    primeiro = _provisionar(gateway, _EMAIL)
    segundo = _provisionar(gateway, _OUTRO_EMAIL)

    assert primeiro.user_id != segundo.user_id


def test_l_ig1_o_link_redime_o_proprio_login_e_nenhum_outro(
    gateway: GatewaySobContrato,
) -> None:
    """A metade de L-IG1 que um fake preguiçoso quebraria: `user_id` fixo, link fixo."""
    primeiro = _provisionar(gateway, _EMAIL)
    segundo = _provisionar(gateway, _OUTRO_EMAIL)

    assert gateway.token_redeems(primeiro.user_id, primeiro.setup_link)
    assert gateway.token_redeems(segundo.user_id, segundo.setup_link)
    assert not gateway.token_redeems(primeiro.user_id, segundo.setup_link)
    assert not gateway.token_redeems(segundo.user_id, primeiro.setup_link)


def test_d9_o_canal_atravessa_o_port_e_decide_o_prazo(gateway: GatewaySobContrato) -> None:
    """`delivery` atravessa o port porque identity precisa dele para o TTL (D9)."""
    em_maos = _provisionar(gateway, _EMAIL, delivery=LoginDelivery.LINK)
    por_email = _provisionar(gateway, _OUTRO_EMAIL, delivery=LoginDelivery.EMAIL)

    assert gateway.entregue_em_maos(em_maos.user_id)
    assert not gateway.entregue_em_maos(por_email.user_id)


# ---------------------------------------------------------------------------
# L-IG2 — duas exceções são traduzidas; o resto sobe cru
# ---------------------------------------------------------------------------


def _assert_traduzida_sem_apagar_a_causa(excecao: Exception) -> None:
    """A tradução **encadeia** (`raise ... from exc`) — a lei que o `from None` viola.

    Achado da auditoria de testes: trocar `from exc` por `from None` nas duas
    traduções do gateway passava em 1773 testes. O status e a mensagem são os
    mesmos; o que se perde é o traceback que mostra **quem** recusou do outro lado
    da fronteira — e é ele que separa "identity disse não" de "staff inventou um
    erro". A causa não pode ser de staff: se fosse, a tradução teria embrulhado a
    si mesma em vez de preservar a origem.
    """
    causa = excecao.__cause__
    assert causa is not None, (
        "a tradução perdeu a causa: use `raise ... from exc` (L-IG2), senão o "
        "traceback deixa de mostrar quem recusou do outro lado da fronteira"
    )
    assert not isinstance(causa, StaffError | StaffApplicationError), (
        f"a causa é um erro de staff: {causa!r}"
    )


def test_l_ig2_email_ja_usado_vira_o_erro_de_staff(gateway: GatewaySobContrato) -> None:
    gateway.email_ja_usado(_EMAIL)

    with pytest.raises(LoginEmailAlreadyInUseError) as excecao:
        _provisionar(gateway, _EMAIL)
    assert type(excecao.value) is LoginEmailAlreadyInUseError
    assert _EMAIL in str(excecao.value)
    _assert_traduzida_sem_apagar_a_causa(excecao.value)


def test_l_ig2_o_email_do_login_recem_criado_passa_a_estar_em_uso(
    gateway: GatewaySobContrato,
) -> None:
    """Unicidade global é do outro lado, mas a tradução vale para o que ele grava."""
    _provisionar(gateway, _EMAIL)

    with pytest.raises(LoginEmailAlreadyInUseError):
        _provisionar(gateway, _EMAIL)


def test_l_ig2_email_malformado_vira_o_erro_de_staff(gateway: GatewaySobContrato) -> None:
    """Todos os e-mails que **este lado** recusa, e não um representante.

    O conjunto inclui o byte NUL desde a Stage 3.5: o VO de identity o recusa
    antes da regex (D8), e é a única forma de provar, **sem banco**, que o NUL
    atravessa VO → fachada → gateway e volta como erro de staff. Com um valor só
    (`"nao-e-email"`), remover a checagem de NUL do VO não derrubava teste nenhum
    de staff — medido pela auditoria de testes.
    """
    invalidos = gateway.emails_invalidos()
    assert invalidos, "nenhum e-mail inválido arranjado — a lei ficaria vácua"

    for invalido in invalidos:
        with pytest.raises(InvalidLoginEmailError) as excecao:
            _provisionar(gateway, invalido)
        assert type(excecao.value) is InvalidLoginEmailError, invalido
        _assert_traduzida_sem_apagar_a_causa(excecao.value)


@pytest.mark.parametrize(
    "arranjo",
    ["unidade_inexistente", "unidade_de_outro_tenant", "tenant_inexistente"],
)
def test_l_ig2_qualquer_outra_falha_sobe_crua(gateway: GatewaySobContrato, arranjo: str) -> None:
    """As três falhas que a fachada pode produzir e que **não** são de staff.

    Parametrizado sobre o **domínio** das falhas cruas alcançáveis pelo
    provisionamento — não sobre um representante. Um gateway que traduzisse
    `CrossTenantError` para `LoginEmailAlreadyInUseError` passaria nos dois
    testes acima e morreria aqui.
    """
    cenario = getattr(gateway, arranjo)()

    with pytest.raises(cenario.tipo_esperado) as excecao:
        gateway.gateway.provision_employee_login(
            email=_EMAIL,
            tenant_id=TenantId(cenario.valor)
            if cenario.argumento == "tenant_id"
            else gateway.tenant_id,
            unit_id=UnitId(cenario.valor) if cenario.argumento == "unit_id" else gateway.unit_id,
            delivery=LoginDelivery.LINK,
        )
    assert type(excecao.value) is cenario.tipo_esperado
    # "Crua" é mais que "do mesmo tipo": um gateway que fizesse
    # `except X as e: raise X(*e.args)` preservaria o tipo e perderia a instância
    # e o traceback — e, como o re-raise acontece dentro de um `except`, deixaria
    # `__context__` preenchido. Propagação sem toque não tem causa nem contexto.
    assert excecao.value.__cause__ is None
    assert excecao.value.__context__ is None


def test_l_ig2_a_falha_do_envio_sobe_crua_e_e_a_mesma_instancia(
    gateway: GatewaySobContrato,
) -> None:
    """A metade de L-IG2 que fecha o "201 sem e-mail" (2.5 §5 regra 13)."""
    login = _provisionar(gateway, _EMAIL, delivery=LoginDelivery.EMAIL)
    gateway.envio_falha(_FALHA_DO_ENVIO)

    with pytest.raises(RuntimeError) as excecao:
        gateway.gateway.send_login_invitation(
            user_id=login.user_id, email=_EMAIL, setup_link=login.setup_link
        )
    assert excecao.value is _FALHA_DO_ENVIO
    assert gateway.enviados_para(_EMAIL) == []


def test_o_envio_bem_sucedido_entrega_o_link_ao_email(
    gateway: GatewaySobContrato,
) -> None:
    login = _provisionar(gateway, _EMAIL, delivery=LoginDelivery.EMAIL)

    gateway.gateway.send_login_invitation(
        user_id=login.user_id, email=_EMAIL, setup_link=login.setup_link
    )

    assert gateway.enviados_para(_EMAIL) == [login.setup_link]


# ---------------------------------------------------------------------------
# L-IG3 — `setup_link` é segredo de uso único
# ---------------------------------------------------------------------------


def test_l_ig3_o_link_nao_aparece_no_repr_do_resultado(gateway: GatewaySobContrato) -> None:
    """`repr=False` no DTO — o que impede um `--showlocals` de imprimir o segredo."""
    campos = {campo.name: campo for campo in dataclasses.fields(ProvisionedLogin)}
    assert campos["setup_link"].repr is False

    login = _provisionar(gateway)
    assert login.setup_link not in repr(login)
    assert "token" not in repr(login)


# ---------------------------------------------------------------------------
# L-IG4 — `revoke_login_sessions` é idempotente e total
# ---------------------------------------------------------------------------


def test_l_ig4_revogar_alcanca_o_login(gateway: GatewaySobContrato) -> None:
    login = _provisionar(gateway)

    gateway.gateway.revoke_login_sessions(login.user_id)

    assert gateway.foi_revogado(login.user_id)


def test_l_ig4_revogar_duas_vezes_nao_e_erro(gateway: GatewaySobContrato) -> None:
    login = _provisionar(gateway)

    gateway.gateway.revoke_login_sessions(login.user_id)
    gateway.gateway.revoke_login_sessions(login.user_id)

    assert gateway.foi_revogado(login.user_id)


def test_l_ig4_revogar_id_desconhecido_nao_e_erro(gateway: GatewaySobContrato) -> None:
    """Total: o desligamento de um registro cujo login sumiu não pode falhar por isso."""
    gateway.gateway.revoke_login_sessions(UserId("login-que-nunca-existiu"))


# ---------------------------------------------------------------------------
# L-IG5 — `is_employee_login` responde se o login é de funcionário (Stage 3.8)
# ---------------------------------------------------------------------------

# Todo papel que **não** é o de funcionário, por valor: o corpo do contrato é de
# staff e não nomeia `Role`. Um representante só deixaria passar `!= "manager"`
# ou `in ("employee", "hr")` — o quantificador "se e somente se" pede todos.
_PAPEIS_QUE_NAO_SAO_DE_FUNCIONARIO = ("owner", "manager", "hr", "platform_admin")


def test_l_ig5_login_provisionado_e_de_funcionario(gateway: GatewaySobContrato) -> None:
    login = _provisionar(gateway)

    assert gateway.gateway.is_employee_login(login.user_id) is True


@pytest.mark.parametrize("papel", _PAPEIS_QUE_NAO_SAO_DE_FUNCIONARIO)
def test_l_ig5_login_de_outro_papel_nao_e_de_funcionario(
    gateway: GatewaySobContrato, papel: str
) -> None:
    """O caso (b) da issue #60: gerente ou dono vinculado a um registro de escala."""
    login = gateway.login_de_outro_papel(papel)
    assert gateway.login_role_of(login) == papel  # o arranjo produziu o que diz

    assert gateway.gateway.is_employee_login(login) is False


def test_l_ig5_login_desconhecido_e_false_e_nao_erro(gateway: GatewaySobContrato) -> None:
    """Sem conta não há sessão a revogar — e o desligamento não pode falhar por isso."""
    assert gateway.gateway.is_employee_login(UserId("login-que-nunca-existiu")) is False


def test_l_ig5_falha_da_consulta_sobe_crua_na_mesma_instancia(
    gateway: GatewaySobContrato,
) -> None:
    """*Fail-open* proibido: um `False` aqui faria o desligamento gravar com sessão viva."""
    login = _provisionar(gateway)
    falha = RuntimeError("identity fora")
    gateway.consulta_de_papel_falha(falha)

    with pytest.raises(RuntimeError) as excinfo:
        gateway.gateway.is_employee_login(login.user_id)

    assert excinfo.value is falha


# ---------------------------------------------------------------------------
# As leis estão escritas no port
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("lei", ["L-IG1", "L-IG2", "L-IG3", "L-IG4", "L-IG5"])
def test_a_lei_esta_documentada_no_port(gateway: GatewaySobContrato, lei: str) -> None:
    """Lei sem texto normativo é convenção — e convenção não sobrevive à segunda
    implementação. Recebe a fixture sem usá-la para rodar sob cada implementação,
    como os seus irmãos de repositório (`test_no_implementation_branching.py`)."""
    assert lei in (identity_gateway.__doc__ or "")
