"""R18, R19 e R20 — a gestão do vínculo de login pela borda (Stage 3.10, CA13 e CA6).

O que este módulo trava, acima do status: as **duas** autorizações na ordem de R17
(e a ausência da segunda quando a primeira nega), o `email` repassado sem passar
pelo validador de identificador, o 422 de e-mail malformado na borda (CA6), o
mesmo corpo de 404 para as recusas da conta (CA2) e as respostas 409 das guardas.
A declaração `INVOCACOES` leva as três rotas às varreduras de
`test_http_boundary_sweeps.py`.
"""

from collections.abc import Iterator
from functools import partial
from http import HTTPStatus

import pytest
from httpx import ASGITransport, AsyncClient

from restaurant_hub.features.staff.adapters.inbound.http import router as router_module
from restaurant_hub.features.staff.application.use_cases.link_existing_login import (
    LinkExistingLoginUseCase,
)
from restaurant_hub.features.staff.application.use_cases.relink_login import RelinkLoginUseCase
from restaurant_hub.features.staff.application.use_cases.unlink_login import UnlinkLoginUseCase
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

_EMAIL = "gerente@x.com"
_SUFIXO = "/units/{unit_id}/employees/{employee_id}"
_CAMINHO = {"unit_id": _UNIDADE, "employee_id": "emp-1"}
_CONTA = UserId("conta-existente")

# A declaração das três rotas — o que faz as varreduras alcançá-las. **200** com o
# registro, como as transições R13 e R14 (concept 3.10 D9).
INVOCACOES: dict[tuple[str, str], dict[str, object]] = {
    ("POST", f"{_SUFIXO}/login-link"): {
        "path": _CAMINHO,
        "query": {},
        "body": {"email": _EMAIL},
        "sucesso": HTTPStatus.OK,
    },
    ("PUT", f"{_SUFIXO}/login-link"): {
        "path": _CAMINHO,
        "query": {},
        "body": {"email": _EMAIL},
        "sucesso": HTTPStatus.OK,
    },
    ("DELETE", f"{_SUFIXO}/login-link"): {
        "path": _CAMINHO,
        "query": {},
        "body": None,
        "sucesso": HTTPStatus.OK,
    },
}

_URL = f"/api/v1/units/{_UNIDADE}/employees/emp-1/login-link"


def _devolve(instancia: object) -> object:
    return instancia


class AmbienteComGateway(Ambiente):
    """O ambiente da 3.6 com as três rotas sobre um gateway **observável**."""

    def __init__(self) -> None:
        super().__init__()
        self.gateway = InMemoryIdentityGateway()
        self.gateway.seed_account(
            _CONTA,
            email=_EMAIL,
            tenant_id=TenantId(_TENANT),
            unit_ids=frozenset({UnitId(_UNIDADE)}),
        )
        for provedor, classe in (
            (router_module._get_link_existing_login, LinkExistingLoginUseCase),
            (router_module._get_relink_login, RelinkLoginUseCase),
            (router_module._get_unlink_login, UnlinkLoginUseCase),
        ):
            self.app.dependency_overrides[provedor] = partial(
                _devolve, classe(self.fakes.employees, self.gateway, guard=self.guard)
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


async def _chamar(client: AsyncClient, metodo: str, email: str | None = _EMAIL) -> object:
    corpo = None if metodo == "DELETE" else {"email": email}
    return await client.request(metodo, _URL, json=corpo)


# --- caminho feliz -----------------------------------------------------------


async def test_r18_vincula_e_devolve_o_registro_com_o_login(
    client: AsyncClient, ambiente: AmbienteComGateway
) -> None:
    _com_funcionario(ambiente)

    resposta = await client.post(_URL, json={"email": _EMAIL})

    assert resposta.status_code == HTTPStatus.OK, resposta.text
    corpo = resposta.json()
    assert (corpo["id"], corpo["unit_id"], corpo["user_id"]) == ("emp-1", _UNIDADE, _CONTA)
    assert _relido(ambiente).user_id == _CONTA


async def test_r19_troca_e_devolve_o_registro_com_o_login_novo(
    client: AsyncClient, ambiente: AmbienteComGateway
) -> None:
    _com_funcionario(ambiente, user_id=UserId("login-antigo"))

    resposta = await client.put(_URL, json={"email": _EMAIL})

    assert resposta.status_code == HTTPStatus.OK, resposta.text
    assert resposta.json()["user_id"] == _CONTA
    assert _relido(ambiente).user_id == _CONTA


async def test_r20_desvincula_e_devolve_o_registro_sem_login(
    client: AsyncClient, ambiente: AmbienteComGateway
) -> None:
    _com_funcionario(ambiente, user_id=_CONTA)

    resposta = await client.delete(_URL)

    assert resposta.status_code == HTTPStatus.OK, resposta.text
    assert resposta.json()["user_id"] is None
    assert _relido(ambiente).user_id is None


async def test_o_email_chega_ao_gateway_como_veio(
    client: AsyncClient, ambiente: AmbienteComGateway
) -> None:
    """Sem `validate_identifier` no e-mail: o NUL, que ele recusaria, chega ao gateway."""
    _com_funcionario(ambiente)
    com_nul = "nul\x00@dentro.com"

    resposta = await client.post(_URL, json={"email": com_nul})

    assert resposta.status_code == HTTPStatus.NOT_FOUND, resposta.text
    assert f"find_login_by_email({com_nul!r})" in ambiente.gateway.calls


# --- autorização: duas, na ordem, sobre a unidade do path --------------------


@pytest.mark.parametrize("metodo", ["POST", "PUT", "DELETE"])
async def test_autoriza_manage_staff_e_depois_manage_users_sobre_a_unidade_do_path(
    client: AsyncClient, ambiente: AmbienteComGateway, metodo: str
) -> None:
    _com_funcionario(ambiente, user_id=None if metodo == "POST" else UserId("login-antigo"))
    ambiente.guard.calls.clear()

    resposta = await _chamar(client, metodo)

    assert resposta.status_code == HTTPStatus.OK, resposta.text  # type: ignore[attr-defined]
    assert ambiente.autorizacoes() == [
        f"authorize(manage_staff,None,{_UNIDADE})",
        f"authorize(manage_users,None,{_UNIDADE})",
        f"authorize(manage_staff,{_TENANT},{_UNIDADE})",
        f"authorize(manage_users,{_TENANT},{_UNIDADE})",
    ]


@pytest.mark.parametrize("metodo", ["POST", "PUT", "DELETE"])
@pytest.mark.parametrize("permissao", ["manage_staff", "manage_users"])
async def test_negacao_de_qualquer_das_duas_nao_deixa_efeito(
    client: AsyncClient, ambiente: AmbienteComGateway, metodo: str, permissao: str
) -> None:
    antes = None if metodo == "POST" else UserId("login-antigo")
    _com_funcionario(ambiente, user_id=antes)
    ambiente.sem(permissao)
    ambiente.guard.calls.clear()

    with pytest.raises(FakeAuthorizationRejected):
        await _chamar(client, metodo)

    esperadas = [f"authorize(manage_staff,None,{_UNIDADE})"]
    if permissao == "manage_users":
        esperadas.append(f"authorize(manage_users,None,{_UNIDADE})")
    assert ambiente.autorizacoes() == esperadas
    assert ambiente.gateway.calls == []
    assert _relido(ambiente).user_id == antes


@pytest.mark.parametrize("metodo", ["POST", "PUT", "DELETE"])
async def test_identificador_invalido_e_recusado_antes_de_autorizar(
    client: AsyncClient, ambiente: AmbienteComGateway, metodo: str
) -> None:
    ambiente.guard.calls.clear()
    corpo = None if metodo == "DELETE" else {"email": _EMAIL}

    resposta = await client.request(
        metodo, f"/api/v1/units/{_UNIDADE}/employees/%20%20%20/login-link", json=corpo
    )

    assert resposta.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert resposta.json()["type"] == "staff_error"
    assert ambiente.autorizacoes() == []


# --- recusas pelo mapa -------------------------------------------------------


@pytest.mark.parametrize("metodo", ["POST", "PUT"])
async def test_ca6_email_malformado_e_422_de_staff(
    client: AsyncClient, ambiente: AmbienteComGateway, metodo: str
) -> None:
    _com_funcionario(ambiente, user_id=None if metodo == "POST" else UserId("login-antigo"))
    ambiente.gateway.invalid_emails.add("nao-e-email")

    resposta = await _chamar(client, metodo, email="nao-e-email")

    assert resposta.status_code == HTTPStatus.UNPROCESSABLE_ENTITY  # type: ignore[attr-defined]
    assert resposta.json()["type"] == "staff_error"  # type: ignore[attr-defined]


@pytest.mark.parametrize("metodo", ["POST", "PUT"])
async def test_ca2_as_recusas_da_conta_tem_o_mesmo_404_e_o_mesmo_corpo(
    client: AsyncClient, ambiente: AmbienteComGateway, metodo: str
) -> None:
    """E-mail sem conta, outro tenant, `platform_admin` e sem alcance: indistinguíveis."""
    antes = None if metodo == "POST" else UserId("login-antigo")
    _com_funcionario(ambiente, user_id=antes)
    contas = {
        "outro@x.com": {
            "tenant_id": TenantId("tenant-b"),
            "unit_ids": frozenset({UnitId(_UNIDADE)}),
        },
        "adm@x.com": {"tenant_id": None},
        "longe@x.com": {"tenant_id": TenantId(_TENANT), "unit_ids": frozenset({UnitId("u-z")})},
    }
    for email, conta in contas.items():
        ambiente.gateway.seed_account(UserId(f"conta-{email}"), email=email, **conta)  # type: ignore[arg-type]

    respostas = [await _chamar(client, metodo, email=email) for email in ("ninguem@x.com", *contas)]

    assert {r.status_code for r in respostas} == {HTTPStatus.NOT_FOUND}  # type: ignore[attr-defined]
    detalhes = {
        r.json()["detail"].replace(email, "<e-mail>")  # type: ignore[attr-defined]
        for r, email in zip(respostas, ("ninguem@x.com", *contas), strict=True)
    }
    assert len(detalhes) == 1, detalhes
    assert _relido(ambiente).user_id == antes


@pytest.mark.parametrize(
    ("metodo", "registro"),
    [
        pytest.param("POST", {"user_id": UserId("outro")}, id="r18-vinculado"),
        pytest.param("POST", {"active": False}, id="r18-desligado"),
        pytest.param("PUT", {}, id="r19-sem-login"),
        pytest.param("PUT", {"user_id": UserId("outro"), "active": False}, id="r19-desligado"),
        pytest.param("DELETE", {}, id="r20-sem-login"),
    ],
)
async def test_as_guardas_respondem_409_de_staff(
    client: AsyncClient, ambiente: AmbienteComGateway, metodo: str, registro: dict[str, object]
) -> None:
    _com_funcionario(ambiente, **registro)  # type: ignore[arg-type]

    resposta = await _chamar(client, metodo)

    assert resposta.status_code == HTTPStatus.CONFLICT, resposta.text  # type: ignore[attr-defined]
    assert resposta.json()["type"] == "staff_error"  # type: ignore[attr-defined]


async def test_r18_conta_ja_em_outro_registro_da_unidade_e_409(
    client: AsyncClient, ambiente: AmbienteComGateway
) -> None:
    _com_funcionario(ambiente)
    ambiente.fakes.employees.add(
        Employee(
            id=EmployeeId("emp-2"),
            tenant_id=TenantId(_TENANT),
            unit_id=UnitId(_UNIDADE),
            name="Bia",
            workload_profile=OnDemand(),
            shift_preference=None,
            job_function_ids=frozenset({JobFunctionId("jf-1")}),
            user_id=_CONTA,
        )
    )

    resposta = await client.post(_URL, json={"email": _EMAIL})

    assert resposta.status_code == HTTPStatus.CONFLICT, resposta.text
    assert "outro registro da unidade" in resposta.json()["detail"]
