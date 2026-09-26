"""R17 — o login do funcionário (Stage 3.5, CA10 e a metade unitária de CA12/CA13).

A rota que fecha o inventário em **17**, e a única de staff que exige **duas**
permissões sobre o mesmo alvo: `manage_staff` porque altera o registro do
funcionário, `manage_users` porque cria uma conta em identity (concept 3.5 §5.3).
O que este módulo trava, acima do status: a **ordem** das duas autorizações, a
**ausência** da segunda quando a primeira nega, e que o `setup_link` só sai no
canal `link`.
"""

from collections.abc import Iterator
from functools import partial
from http import HTTPStatus

import pytest
from httpx import ASGITransport, AsyncClient

from restaurant_hub.features.staff.adapters.inbound.http import router as router_module
from restaurant_hub.features.staff.application.use_cases.create_login_for_employee import (
    CreateLoginForEmployeeUseCase,
)
from restaurant_hub.features.staff.domain.entities.employee import Employee
from restaurant_hub.features.staff.domain.value_objects.identifiers import (
    EmployeeId,
    JobFunctionId,
    TenantId,
    UnitId,
    UserId,
)
from restaurant_hub.features.staff.domain.value_objects.workload_profile import OnDemand
from tests.fakes.features.staff.in_memory_access_guard import FakeAuthorizationRejected
from tests.fakes.features.staff.in_memory_identity_gateway import InMemoryIdentityGateway
from tests.unit.features.staff.adapters.test_http_router_job_functions import (
    _TENANT,
    _UNIDADE,
    Ambiente,
)

pytestmark = pytest.mark.unit

_EMAIL = "novo@x.com"
_SUFIXO = "/units/{unit_id}/employees/{employee_id}"

# A declaração de R17 — é o que faz as varreduras de `test_http_boundary_sweeps.py`
# alcançarem a rota. **201**: a conta em identity passa a existir.
INVOCACOES: dict[tuple[str, str], dict[str, object]] = {
    ("POST", f"{_SUFIXO}/login"): {
        "path": {"unit_id": _UNIDADE, "employee_id": "emp-1"},
        "query": {},
        "body": {"email": _EMAIL, "delivery": "link"},
        "sucesso": HTTPStatus.CREATED,
    },
}

_URL = f"/api/v1/units/{_UNIDADE}/employees/emp-1/login"


def _devolve(instancia: object) -> object:
    return instancia


class AmbienteComGateway(Ambiente):
    """O ambiente da 3.6 mais um gateway **observável** para R17.

    `overrides_de_use_case` conecta um `InMemoryIdentityGateway` anônimo por
    reflexão — suficiente para as rotas que não o exercitam. Aqui o gateway
    precisa ser lido (`logins`, `sent`), então o provedor de R17 é reconectado a
    um use case montado sobre **este** gateway. O ambiente base já concede
    `manage_users`; os testes que medem a **recusa** o retiram, para que a
    recusa seja a variável do cenário e não um efeito da montagem.
    """

    def __init__(self) -> None:
        super().__init__()
        self.gateway = InMemoryIdentityGateway()
        self.app.dependency_overrides[router_module._get_create_login_for_employee] = partial(
            _devolve, CreateLoginForEmployeeUseCase(self.fakes.employees, self.gateway)
        )

    def autorizacoes(self) -> list[str]:
        return [c for c in self.guard.calls if c.startswith("authorize(")]

    def sem(self, permissao: str) -> None:
        self.guard.grants = {alvo for alvo in self.guard.grants if alvo[0] != permissao}


@pytest.fixture
def ambiente() -> AmbienteComGateway:
    return AmbienteComGateway()


@pytest.fixture
async def client(ambiente: AmbienteComGateway) -> Iterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=ambiente.app), base_url="http://t") as c:
        yield c


def _com_funcionario(
    ambiente: Ambiente, *, active: bool = True, user_id: UserId | None = None
) -> Employee:
    ambiente.com_funcao("jf-1")
    funcionario = Employee(
        id=EmployeeId("emp-1"),
        tenant_id=TenantId(_TENANT),
        unit_id=UnitId(_UNIDADE),
        name="Ana",
        workload_profile=OnDemand(),
        shift_preference=None,
        job_function_ids=frozenset({JobFunctionId("jf-1")}),
        active=active,
        user_id=user_id,
    )
    ambiente.fakes.employees.add(funcionario)
    return funcionario


def _relido(ambiente: Ambiente) -> Employee:
    registro = ambiente.fakes.employees.find_by_id(
        TenantId(_TENANT), UnitId(_UNIDADE), EmployeeId("emp-1")
    )
    assert registro is not None
    return registro


# ---------------------------------------------------------------------------
# Os dois canais — 201, `user_id` no registro, `setup_link` conforme o canal
# ---------------------------------------------------------------------------


async def test_r17_canal_link_devolve_o_link_e_o_registro_vinculado(
    client: AsyncClient, ambiente: AmbienteComGateway
) -> None:
    _com_funcionario(ambiente)

    resposta = await client.post(_URL, json={"email": _EMAIL, "delivery": "link"})

    assert resposta.status_code == HTTPStatus.CREATED, resposta.text
    corpo = resposta.json()
    (user_id,) = ambiente.gateway.logins
    assert corpo["employee"]["user_id"] == user_id
    assert corpo["employee"]["id"] == "emp-1"
    assert corpo["employee"]["unit_id"] == _UNIDADE
    assert corpo["setup_link"] == ambiente.gateway.logins[user_id].setup_link
    assert ambiente.gateway.sent == []
    assert _relido(ambiente).user_id == user_id


async def test_r17_canal_email_envia_e_nao_devolve_o_link(
    client: AsyncClient, ambiente: AmbienteComGateway
) -> None:
    _com_funcionario(ambiente)

    resposta = await client.post(_URL, json={"email": _EMAIL, "delivery": "email"})

    assert resposta.status_code == HTTPStatus.CREATED, resposta.text
    corpo = resposta.json()
    (user_id,) = ambiente.gateway.logins
    assert corpo["setup_link"] is None
    assert corpo["employee"]["user_id"] == user_id
    assert ambiente.gateway.sent == [(_EMAIL, ambiente.gateway.logins[user_id].setup_link)]
    # O segredo não aparece em lugar nenhum do corpo no canal e-mail.
    assert ambiente.gateway.logins[user_id].setup_link not in resposta.text


async def test_r17_o_email_e_repassado_verbatim_e_o_canal_como_enum(
    client: AsyncClient, ambiente: AmbienteComGateway
) -> None:
    """O e-mail chega ao gateway **como veio**, e o canal como enum."""
    _com_funcionario(ambiente)

    await client.post(_URL, json={"email": "  Maria@Cantina.com ", "delivery": "email"})

    (user_id,) = ambiente.gateway.logins
    assert ambiente.gateway.logins[user_id].email == "  Maria@Cantina.com "
    assert ambiente.gateway.logins[user_id].delivery.value == "email"
    assert ambiente.gateway.logins[user_id].tenant_id == _TENANT
    assert ambiente.gateway.logins[user_id].unit_id == _UNIDADE


async def test_r17_o_email_nao_passa_pelo_validador_de_identificador(
    client: AsyncClient, ambiente: AmbienteComGateway
) -> None:
    """Concept §5.7 — e o valor escolhido é o que **discrimina** a propriedade.

    Achado do Checkpoint C do bloco 5: com `"  Maria@Cantina.com "` o teste não
    distinguia "não passa pelo validador" de "passa e o validador aceita" — o
    validador devolve verbatim tudo o que não é vazio, whitespace-only ou NUL
    (ADR 3.6.0002 §2). A mutação `email=validate_identifier(payload.email, ...)`
    sobrevivia a 1525 testes.

    O byte NUL é exatamente o valor em que as duas leituras divergem: o validador
    o **recusa** (422 de staff, sem tocar em identity), e quem valida o e-mail é
    identity, atrás do gateway. Aqui o fake aceita — então 201 prova que o
    validador não foi chamado sobre o e-mail.

    **Divisão de trabalho com o e2e, para que os dois não pareçam contraditórios:**
    este teste mede que *a borda de staff não julga* o e-mail (fake aceitando ⇒
    201); `test_employee_login_flow.py::test_ca31_email_com_byte_nul_e_422_de_staff`
    mede que *o VO `Email` de identity julga* e que a recusa chega traduzida como
    422. Mesmo valor, peças diferentes — "consertar" um deles para casar com o
    outro apagaria uma das duas propriedades.
    """
    _com_funcionario(ambiente)
    com_nul = "nul\x00@dentro.com"

    resposta = await client.post(_URL, json={"email": com_nul, "delivery": "link"})

    assert resposta.status_code == HTTPStatus.CREATED, resposta.text
    (user_id,) = ambiente.gateway.logins
    assert ambiente.gateway.logins[user_id].email == com_nul
    assert ambiente.autorizacoes(), "as autorizações rodaram — o 201 não veio por atalho"


# ---------------------------------------------------------------------------
# R15 pelo adapter — remover registro vinculado é 409 (ADR 3.5.0003 §1b)
# ---------------------------------------------------------------------------


async def test_r15_remover_registro_vinculado_e_409_com_corpo_de_staff(
    client: AsyncClient, ambiente: AmbienteComGateway
) -> None:
    """A recusa de R15 chegava ao fio só no e2e; aqui ela tem o caminho do adapter.

    O que se mede além do status: o corpo é o de staff (o mapa classificou
    `EmployeeHasLoginError`), a mensagem manda desligar, e o registro **continua
    lá** com o vínculo — remover não é desvincular.
    """
    _com_funcionario(ambiente, user_id=UserId("login-9"))

    resposta = await client.delete(f"/api/v1/units/{_UNIDADE}/employees/emp-1")

    assert resposta.status_code == HTTPStatus.CONFLICT, resposta.text
    assert resposta.json()["type"] == "staff_error"
    assert "desligue-o" in resposta.json()["detail"]
    assert _relido(ambiente).user_id == UserId("login-9")


async def test_r15_remover_registro_sem_login_continua_204(
    client: AsyncClient, ambiente: AmbienteComGateway
) -> None:
    """O contraste que impede a guarda de virar "R15 recusa sempre"."""
    _com_funcionario(ambiente)

    resposta = await client.delete(f"/api/v1/units/{_UNIDADE}/employees/emp-1")

    assert resposta.status_code == HTTPStatus.NO_CONTENT, resposta.text
    assert (
        ambiente.fakes.employees.find_by_id(
            TenantId(_TENANT), UnitId(_UNIDADE), EmployeeId("emp-1")
        )
        is None
    )


# ---------------------------------------------------------------------------
# CA10 — duas autorizações, na ordem, sobre a unidade do path
# ---------------------------------------------------------------------------


async def test_ca10_autoriza_manage_staff_e_depois_manage_users_sobre_a_unidade_do_path(
    client: AsyncClient, ambiente: AmbienteComGateway
) -> None:
    """A ordem e o alvo são o contrato — asseridos como strings exatas."""
    _com_funcionario(ambiente)
    ambiente.guard.calls.clear()

    resposta = await client.post(_URL, json={"email": _EMAIL, "delivery": "link"})

    assert resposta.status_code == HTTPStatus.CREATED
    assert ambiente.autorizacoes() == [
        f"authorize(manage_staff,None,{_UNIDADE})",
        f"authorize(manage_users,None,{_UNIDADE})",
    ]


async def test_ca10_sem_manage_staff_nao_ha_segunda_autorizacao_nem_conta(
    client: AsyncClient, ambiente: AmbienteComGateway
) -> None:
    """Quando a primeira nega, a segunda **não acontece** — e identity não é tocada."""
    _com_funcionario(ambiente)
    ambiente.sem("manage_staff")
    ambiente.guard.calls.clear()

    with pytest.raises(FakeAuthorizationRejected) as excinfo:
        await client.post(_URL, json={"email": _EMAIL, "delivery": "link"})

    assert excinfo.value is ambiente.guard.authorization_error
    assert ambiente.autorizacoes() == [f"authorize(manage_staff,None,{_UNIDADE})"]
    assert ambiente.gateway.calls == []
    assert _relido(ambiente).user_id is None


async def test_ca10_sem_manage_users_a_conta_nao_nasce(
    client: AsyncClient, ambiente: AmbienteComGateway
) -> None:
    """`manage_staff` sozinho não basta: quem só gere a equipe não cria contas."""
    _com_funcionario(ambiente)
    ambiente.sem("manage_users")
    ambiente.guard.calls.clear()

    with pytest.raises(FakeAuthorizationRejected) as excinfo:
        await client.post(_URL, json={"email": _EMAIL, "delivery": "link"})

    assert excinfo.value is ambiente.guard.authorization_error
    assert ambiente.autorizacoes() == [
        f"authorize(manage_staff,None,{_UNIDADE})",
        f"authorize(manage_users,None,{_UNIDADE})",
    ]
    assert ambiente.gateway.calls == []
    assert _relido(ambiente).user_id is None


async def test_ca21_identificador_invalido_e_recusado_antes_de_qualquer_autorizacao(
    client: AsyncClient, ambiente: AmbienteComGateway
) -> None:
    _com_funcionario(ambiente)
    ambiente.guard.calls.clear()

    resposta = await client.post(
        f"/api/v1/units/{_UNIDADE}/employees/%20%20%20/login",
        json={"email": _EMAIL, "delivery": "link"},
    )

    assert resposta.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert resposta.json()["type"] == "staff_error"
    assert ambiente.autorizacoes() == []
    assert ambiente.gateway.calls == []


# ---------------------------------------------------------------------------
# As faixas pelo adapter — 404, 409, 422 (o e2e prova o mesmo pelo HTTP real)
# ---------------------------------------------------------------------------


async def test_r17_registro_inexistente_e_404_sem_tocar_identity(
    client: AsyncClient, ambiente: AmbienteComGateway
) -> None:
    resposta = await client.post(_URL, json={"email": _EMAIL, "delivery": "link"})

    assert resposta.status_code == HTTPStatus.NOT_FOUND
    assert resposta.json()["type"] == "staff_error"
    assert ambiente.gateway.calls == []


@pytest.mark.parametrize(
    ("arranjo", "trecho"),
    [
        pytest.param({"user_id": UserId("login-antigo")}, "já tem login", id="ja-vinculado"),
        pytest.param({"active": False}, "desligado", id="desligado"),
    ],
)
async def test_r17_as_guardas_do_dominio_respondem_409_com_corpo_de_staff(
    client: AsyncClient, ambiente: AmbienteComGateway, arranjo: dict[str, object], trecho: str
) -> None:
    _com_funcionario(ambiente, **arranjo)  # type: ignore[arg-type]

    resposta = await client.post(_URL, json={"email": _EMAIL, "delivery": "link"})

    assert resposta.status_code == HTTPStatus.CONFLICT, resposta.text
    assert resposta.json()["type"] == "staff_error"
    assert trecho in resposta.json()["detail"]
    assert ambiente.gateway.calls == []


async def test_r17_email_ja_usado_e_409_e_nada_e_gravado(
    client: AsyncClient, ambiente: AmbienteComGateway
) -> None:
    _com_funcionario(ambiente)
    ambiente.gateway.used_emails.add(_EMAIL)

    resposta = await client.post(_URL, json={"email": _EMAIL, "delivery": "link"})

    assert resposta.status_code == HTTPStatus.CONFLICT, resposta.text
    assert resposta.json()["type"] == "staff_error"
    assert _EMAIL in resposta.json()["detail"]
    assert _relido(ambiente).user_id is None


async def test_r17_email_invalido_para_identity_e_422_de_staff(
    client: AsyncClient, ambiente: AmbienteComGateway
) -> None:
    _com_funcionario(ambiente)
    ambiente.gateway.invalid_emails.add("sem-arroba")

    resposta = await client.post(_URL, json={"email": "sem-arroba", "delivery": "link"})

    assert resposta.status_code == HTTPStatus.UNPROCESSABLE_ENTITY, resposta.text
    assert resposta.json()["type"] == "staff_error"
    assert _relido(ambiente).user_id is None


@pytest.mark.parametrize(
    "corpo",
    [
        pytest.param({}, id="vazio"),
        pytest.param({"email": _EMAIL}, id="sem-canal"),
        pytest.param({"delivery": "link"}, id="sem-email"),
        pytest.param({"email": _EMAIL, "delivery": "xpto"}, id="canal-desconhecido"),
    ],
)
async def test_r17_corpo_fora_do_schema_e_422_do_framework(
    client: AsyncClient, ambiente: AmbienteComGateway, corpo: dict[str, object]
) -> None:
    """Os dois campos são obrigatórios e o canal é `Literal` — a forma é do framework."""
    _com_funcionario(ambiente)

    resposta = await client.post(_URL, json=corpo)

    assert resposta.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert resposta.json()["type"] == "validation_error"
    assert ambiente.gateway.calls == []


async def test_r17_a_falha_do_envio_sobe_crua_e_o_vinculo_fica(
    client: AsyncClient, ambiente: AmbienteComGateway
) -> None:
    """CA30 pelo adapter: sem handler para a falha do sender, ela sobe — e o registro aponta."""
    _com_funcionario(ambiente)
    falha = RuntimeError("smtp indisponível")
    ambiente.gateway.fail_send_with = falha

    with pytest.raises(RuntimeError) as excinfo:
        await client.post(_URL, json={"email": _EMAIL, "delivery": "email"})

    assert excinfo.value is falha
    (user_id,) = ambiente.gateway.logins
    assert _relido(ambiente).user_id == user_id


# ---------------------------------------------------------------------------
# CA13 (metade unitária) — o `user_id` sai em toda resposta de funcionário
# ---------------------------------------------------------------------------


async def test_ca13_o_registro_vinculado_traz_o_user_id_nas_outras_rotas(
    client: AsyncClient, ambiente: AmbienteComGateway
) -> None:
    _com_funcionario(ambiente, user_id=UserId("login-9"))

    listagem = await client.get(f"/api/v1/units/{_UNIDADE}/employees")
    renomeado = await client.patch(
        f"/api/v1/units/{_UNIDADE}/employees/emp-1", json={"name": "Ana Maria"}
    )

    assert listagem.status_code == HTTPStatus.OK
    assert listagem.json()[0]["user_id"] == "login-9"
    assert renomeado.status_code == HTTPStatus.OK
    assert renomeado.json()["user_id"] == "login-9"


async def test_ca13_o_registro_sem_login_traz_user_id_nulo(
    client: AsyncClient, ambiente: AmbienteComGateway
) -> None:
    _com_funcionario(ambiente)

    listagem = await client.get(f"/api/v1/units/{_UNIDADE}/employees")

    assert listagem.json()[0]["user_id"] is None
