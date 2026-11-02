"""Toda rota não-pública recusa sem credencial e sem permissão — Gate 2 da issue #45.

**Por que na raiz de `tests/e2e/`.** A regra é da aplicação inteira, não de um
bounded context: ela fala do conjunto de rotas que a app serve, qualquer que
seja a feature que as registrou. É o mesmo nível de `test_app_smoke.py`.

**Por que dirigido por varredura, e não por lista de casos.** Uma suíte que
enumera "login, refresh, criar restaurante…" cobre as rotas que existiam no dia
em que foi escrita. A rota seguinte nasce sem teste de negação, e a ausência não
tem sintoma: ninguém abre um teste de autorização ao adicionar um endpoint. Aqui
a enumeração sai da própria app — e é por isso que este arquivo entrou **antes**
da Stage 3.6: cada rota de staff passa a ser cobrada no instante em que for
registrada.

**A fonte da enumeração é `app.openapi()["paths"]`, e a escolha foi medida.**
`app.routes` **não** lista as rotas de um router incluído nesta versão do
FastAPI (0.139): ele guarda um `_IncludedRouter` opaco, sem `.routes`. Um gate
escrito sobre `app.routes` encontraria as quatro rotas embutidas (`/docs`,
`/openapi.json`, …), classificaria todas como públicas e passaria **vazio** —
verde por não ter olhado. `test_ha_rota_nao_publica_a_cobrar` é a guarda contra
essa família inteira de falhas, e foi ela que tornou o problema visível.

O preço do OpenAPI é que uma rota com `include_in_schema=False` não apareceria —
e escaparia do gate calada. `test_nenhuma_rota_esta_escondida_do_schema` fecha
isso pelo outro lado, lendo o router real que o composition root monta.

**As duas pernas usam mecanismos diferentes, e a diferença é do FastAPI.** A
dependência de autenticação roda **antes** da validação de corpo (medido: uma
dependência que levanta vence um corpo inválido), então a perna do 401 dispensa
payload e é 100% automática. Já o `guard.authorize` de cada rota roda **dentro**
do handler, depois da validação — logo o 403 só é observável com um corpo que a
rota aceite. O corpo é **sintetizado do schema OpenAPI** para que a perna do 403
também acompanhe rota nova sozinha; `_CORPOS_SOB_MEDIDA` existe para o caso em
que a síntese não dá conta, e uma resposta 422 nesta suíte é reportada como
"escreva o corpo aqui", nunca como aprovação.
"""

from collections.abc import AsyncIterator
from functools import cache
from http import HTTPStatus
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import Engine

from restaurant_hub.composition_root import build_http_wiring, wire_dependencies
from restaurant_hub.features.identity.adapters.out.postgres.user_repository import (
    PostgresUserRepository,
)
from restaurant_hub.features.identity.adapters.out.security.argon2_hasher import (
    Argon2PasswordHasher,
)
from restaurant_hub.features.identity.domain.entities.user import User
from restaurant_hub.features.identity.domain.value_objects.email import Email
from restaurant_hub.features.identity.domain.value_objects.identifiers import UserId
from restaurant_hub.features.identity.domain.value_objects.role import Role
from restaurant_hub.shared.infrastructure.config.settings import Settings
from restaurant_hub.shared.infrastructure.http.app import create_app
from tests.conftest import truncar_tudo
from tests.e2e.features.identity.conftest import ADMIN_EMAIL, API, SENHA_PADRAO, auth, fazer_login

pytestmark = pytest.mark.e2e

# As rotas que **não** exigem credencial, cada uma com o motivo. É allowlist:
# entrar aqui é decisão de segurança, e o teste de entrada morta abaixo cobra que
# cada uma continue existindo — allowlist que perdoa rota apagada é uma dispensa
# esperando por uma rota futura de mesmo caminho.
ROTAS_PUBLICAS: dict[tuple[str, str], str] = {
    ("POST", f"{API}/auth/login"): (
        "é a rota que **estabelece** a credencial; exigir uma seria circular"
    ),
    ("POST", f"{API}/auth/refresh"): (
        "a autoridade da operação é a posse do refresh, e ela existe justamente "
        "para quando o access já expirou (concept 2.4 §5 regra 5)"
    ),
    ("POST", f"{API}/auth/logout"): (
        "encerra a sessão do refresh apresentado e devolve 204 sempre; exigir "
        "access token impediria o logout de quem já o perdeu"
    ),
    ("POST", f"{API}/auth/password-reset-requests"): (
        "quem esqueceu a senha não tem credencial — é a premissa da rota"
    ),
    ("POST", f"{API}/auth/password"): (
        "a autoridade é o token de setup entregue fora de banda, por e-mail "
        "(ADR 2.5.0002); é assim que um convidado define a primeira senha"
    ),
}

# Corpos escritos à mão para rotas cujo schema a síntese não cobre. A síntese é
# por **tipo**, e o schema OpenAPI de `role` é `string` — o conjunto fechado de
# valores vive no domínio (`Role.from_string`), fora do alcance dela.
#
# As duas rotas abaixo parseiam o papel alvo **antes** de autorizar, e isso não é
# defeito: o conjunto de permissões exigidas é derivado do papel
# (`required_permissions_for_role`), então não há o que autorizar antes de saber
# qual é. Com `role` inválido a rota responde 422 sem chegar ao guard, e o teste
# do 403 não teria verificado autorização nenhuma.
_CORPOS_SOB_MEDIDA: dict[tuple[str, str], dict[str, Any]] = {
    ("POST", f"{API}/users"): {
        "email": "sintetizado@x.com",
        "password": "senha-de-sintese-do-gate-2",
        "role": Role.EMPLOYEE.value,
        "unit_ids": [],
    },
    ("POST", f"{API}/users/invitations"): {
        "email": "sintetizado@x.com",
        "role": Role.EMPLOYEE.value,
        "unit_ids": [],
    },
}

# Valor por tipo do JSON Schema. Deliberadamente burro: o objetivo é passar pela
# validação do Pydantic para alcançar o `guard.authorize`, e não construir um
# pedido plausível — a rota **não pode** chegar a executar.
_VALOR_POR_TIPO: dict[str, Any] = {
    "string": "x",
    "integer": 1,
    "number": 1,
    "boolean": False,
    "array": [],
    "object": {},
}

# Formatos do JSON Schema em que `"x"` não passa pela validação. Um `format`
# desconhecido cai no valor do tipo — e, se a rota o recusar, o teste diz para
# escrever o corpo à mão em vez de aceitar o 422.
_VALOR_POR_FORMATO: dict[str, Any] = {
    "date-time": "2026-01-01T08:00:00",
    "date": "2026-01-01",
    "time": "08:00:00",
    "uuid": "00000000-0000-4000-8000-000000000000",
    "email": "sintetizado@x.com",
}

# Substituto de parâmetro de caminho. Qualquer valor serve: a recusa acontece
# antes de o alvo ser procurado, e é essa ordem que o Gate 2 verifica.
_PARAMETRO = "x"

# Piso de tamanho do motivo de uma rota pública. Uma palavra não é argumento;
# o limiar existe para que "histórico" ou "legado" não passem como razão.
_TAMANHO_MINIMO_DO_MOTIVO = 20


def _settings(database_url: str) -> Settings:
    return Settings(
        _env_file=None,
        database_url=database_url,
        jwt_secret_key="segredo-de-teste-e2e-com-32-bytes-ou-mais",
    )


@pytest.fixture
def app_gate(engine: Engine, database_url: str) -> FastAPI:
    """App real, montada pelo composition root de produção, com banco limpo."""
    truncar_tudo(engine)
    return create_app(_settings(database_url))


@pytest.fixture
async def client_gate(app_gate: FastAPI) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(
        transport=ASGITransport(app=app_gate),
        base_url="http://testserver",
    ) as c:
        yield c


@pytest.fixture
def admin_gate(engine: Engine, app_gate: FastAPI) -> User:
    """O `platform_admin`, semeado pelo repositório — nenhuma rota o cria."""
    admin = User(
        id=UserId("platform-admin-gate"),
        email=Email(ADMIN_EMAIL),
        role=Role.PLATFORM_ADMIN,
        tenant_id=None,
    )
    PostgresUserRepository(engine).add(admin, Argon2PasswordHasher().hash(SENHA_PADRAO), ())
    return admin


@cache
def _spec() -> dict[str, Any]:
    """O schema OpenAPI da app real, sem banco no ar.

    Cacheado porque a perna do 403 o consulta uma vez por rota, e montar a app
    inteira a cada consulta seria um grafo de dependências novo por teste. A
    URL é deliberadamente inválida: `create_engine` não abre conexão, e uma URL
    que funcionasse convidaria alguém a usar esta função onde precisa de banco.
    """
    return create_app(_settings("postgresql+psycopg://x:x@localhost:1/x")).openapi()


def _rotas(spec: dict[str, Any]) -> list[tuple[str, str]]:
    """Todos os pares (método, caminho) que a app serve."""
    return sorted(
        (metodo.upper(), caminho)
        for caminho, operacoes in spec["paths"].items()
        for metodo in operacoes
    )


def _nao_publicas(rotas: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """As rotas que a allowlist não dispensa — o universo que o Gate 2 cobra."""
    return [rota for rota in rotas if rota not in ROTAS_PUBLICAS]


_TODAS = _rotas(_spec())
_NAO_PUBLICAS = _nao_publicas(_TODAS)


def _resolver(schema: dict[str, Any], spec: dict[str, Any]) -> dict[str, Any]:
    """Segue um `$ref` do OpenAPI até o objeto de schema."""
    referencia = schema.get("$ref")
    if referencia is None:
        return schema
    alvo: Any = spec
    for parte in referencia.removeprefix("#/").split("/"):
        alvo = alvo[parte]
    return dict(alvo)


def _valor(schema: dict[str, Any], spec: dict[str, Any]) -> Any:  # noqa: ANN401
    """Um valor que o schema aceita — recursivo, e só até onde precisa ir.

    A meta é **passar pela validação do Pydantic** para alcançar o
    `guard.authorize`, nunca produzir um pedido plausível: a rota não pode
    chegar a executar. Por isso `weekly_hours` sai como `"x"` — o schema o
    declara `string`, e a conversão para o value object do domínio acontece
    **depois** da autorização.

    Os ramos abaixo são exatamente os que uma rota exigiu ao responder 422 — os
    quatro primeiros na Stage 3.6, o do `enum` na 3.5:

    - `const` — o discriminador de união (`type: "fixed"`) não é uma string
      qualquer; um `"x"` ali reprova na validação;
    - `enum` — vocabulário fechado (`Literal["email", "link"]` do `delivery` de
      `POST /units/{unit_id}/employees/{employee_id}/login`). É o mesmo caso do
      `const` com mais de um valor permitido: qualquer string fora da lista
      reprova antes do guard;
    - `oneOf`/`anyOf` — a união discriminada de `workload_profile` e o
      `list | None` de `shift_preference`. Escolhe-se a primeira variante que
      não seja `null`, porque `null` satisfaz o schema sem exercitar nada;
    - objeto aninhado — a variante escolhida é ela própria um schema com
      campos obrigatórios;
    - `format` — `date-time` precisa parsear como `datetime`.
    """
    schema = _resolver(schema, spec)

    if "const" in schema:
        return schema["const"]

    if schema.get("enum"):
        return schema["enum"][0]

    for chave in ("oneOf", "anyOf", "allOf"):
        variantes = [
            variante
            for variante in schema.get(chave, [])
            if _resolver(variante, spec).get("type") != "null"
        ]
        if variantes:
            return _valor(variantes[0], spec)

    formato = schema.get("format")
    if formato in _VALOR_POR_FORMATO:
        return _VALOR_POR_FORMATO[formato]

    tipo = schema.get("type")
    if tipo == "object" or "properties" in schema:
        propriedades = schema.get("properties", {})
        return {
            nome: _valor(propriedades.get(nome, {}), spec) for nome in schema.get("required", [])
        }

    return _VALOR_POR_TIPO.get(tipo or "", "x")


def _corpo(metodo: str, caminho: str, spec: dict[str, Any]) -> dict[str, Any]:
    """Um corpo que a rota **aceita**, sintetizado do schema dela.

    Sintetizar — em vez de escrever um por rota — é o que faz a perna do 403
    acompanhar rota nova sem edição, e a Stage 3.6 é a prova: as suas dezesseis rotas
    de staff entraram nesta suíte sem uma linha de edição aqui. Só os campos
    obrigatórios entram: um campo opcional a mais só aumentaria a chance de a
    síntese errar o formato.
    """
    sob_medida = _CORPOS_SOB_MEDIDA.get((metodo, caminho))
    if sob_medida is not None:
        return sob_medida

    operacao = spec["paths"][caminho][metodo.lower()]
    corpo = operacao.get("requestBody", {})
    conteudo = corpo.get("content", {}).get("application/json", {})
    if not conteudo:
        return {}

    sintetizado = _valor(conteudo.get("schema", {}), spec)
    return sintetizado if isinstance(sintetizado, dict) else {}


def _query(metodo: str, caminho: str, spec: dict[str, Any]) -> dict[str, Any]:
    """Os parâmetros de **query** obrigatórios da rota, sintetizados.

    Sem isto, toda rota que exige filtro na query escaparia da perna do 403: o
    FastAPI valida os parâmetros junto com o corpo, antes do handler, então a
    ausência deles responde 422 e a execução nunca alcança o `guard.authorize`.

    `DELETE /units/{unit_id}/employees/{employee_id}/unavailabilities` é o caso
    que expôs isso — ela endereça o período a remover por `?start=&end=`, e não
    por corpo. Foi a Stage 3.6 que a trouxe, e o gate a acusou na primeira
    corrida contra o código dela.
    """
    operacao = spec["paths"][caminho][metodo.lower()]
    return {
        parametro["name"]: _valor(parametro.get("schema", {}), spec)
        for parametro in operacao.get("parameters", [])
        if parametro.get("in") == "query" and parametro.get("required", False)
    }


def _url(caminho: str) -> str:
    """Substitui os parâmetros de caminho por um valor qualquer."""
    partes = caminho.split("{")
    return partes[0] + "".join(_PARAMETRO + p.split("}", 1)[1] for p in partes[1:])


def _identificador(rota: tuple[str, str]) -> str:
    return f"{rota[0]} {rota[1]}"


# ---------------------------------------------------------------------------
# As guardas da varredura — sem elas, o gate passa vazio
# ---------------------------------------------------------------------------


def test_ha_rota_nao_publica_a_cobrar() -> None:
    """A guarda contra o gate vacuamente verde, e ela já pegou um caso real.

    `parametrize` sobre lista vazia produz zero testes e reporta sucesso. E a
    lista **fica** vazia com facilidade: a primeira versão deste arquivo lia
    `app.routes`, que nesta versão do FastAPI não expõe as rotas de um router
    incluído — encontrava só `/docs` e companhia, classificava tudo como público
    e passava sem cobrar nada.
    """
    assert _NAO_PUBLICAS, (
        f"nenhuma rota não-pública encontrada em {len(_TODAS)} rotas — a "
        f"enumeração quebrou, e sem esta asserção o gate inteiro sumiria com o "
        f"relatório do pytest idêntico ao de antes"
    )


def test_a_allowlist_de_rotas_publicas_nao_cresceu() -> None:
    """Rota pública nova reprova aqui até ser deliberada.

    É a metade que a asserção de entrada morta não cobra. Dispensar uma rota da
    perna do 401 é decisão de segurança, e o caminho de menor resistência para
    quem vê este gate vermelho é acrescentar a rota à allowlist — que é
    literalmente como se abre um endpoint sem revisão. Com o conjunto fixado
    aqui, a dispensa custa **duas** edições, e a segunda tem este docstring ao
    lado.

    As cinco de hoje são as de autenticação, e todas pela mesma razão de fundo:
    quem as chama, por definição, ainda não tem — ou já não tem — credencial.

    `_CORPOS_SOB_MEDIDA` **não** ganha asserção equivalente, de propósito: ela é
    dado de teste, não dispensa. Um corpo mal escrito ali não afrouxa nada — a
    asserção de 403 continua valendo, e um corpo que a validação recuse reprova
    como 422.
    """
    assert set(ROTAS_PUBLICAS) == {
        ("POST", f"{API}/auth/login"),
        ("POST", f"{API}/auth/refresh"),
        ("POST", f"{API}/auth/logout"),
        ("POST", f"{API}/auth/password-reset-requests"),
        ("POST", f"{API}/auth/password"),
    }


def test_a_allowlist_de_rotas_publicas_nao_tem_entrada_morta() -> None:
    """Rota pública que já não existe é uma dispensa esperando por um homônimo.

    O caminho é reaproveitado com naturalidade — `/auth/password` de hoje pode
    virar a rota autenticada de troca de senha amanhã. Se a entrada tivesse
    ficado, a rota nova nasceria dispensada da perna do 401, com a allowlist
    respondendo por uma decisão que ninguém tomou.
    """
    orfas = sorted(_identificador(rota) for rota in ROTAS_PUBLICAS if rota not in _TODAS)

    assert orfas == [], f"rotas públicas na allowlist que a app não serve: {orfas}"


def test_cada_rota_publica_declara_o_motivo_de_ser_publica() -> None:
    """Dispensa de credencial é decisão de segurança, e vem com argumento.

    Sem o motivo escrito, a allowlist vira uma lista de caminhos, e a pergunta
    "por que esta é pública?" passa a ser respondida por arqueologia de git.
    """
    sem_motivo = sorted(
        _identificador(rota)
        for rota, motivo in ROTAS_PUBLICAS.items()
        if len(motivo) < _TAMANHO_MINIMO_DO_MOTIVO
    )

    assert sem_motivo == []


def test_nenhum_corpo_sob_medida_esta_morto() -> None:
    """Corpo escrito à mão para rota que já não existe volta a esconder um 422.

    O catálogo é a válvula da síntese, e válvula que ninguém fecha deixa de
    significar alguma coisa: uma entrada órfã fica esperando um caminho
    homônimo, e no dia em que ele voltar a rota nasce com um corpo aceito por
    outra pessoa, para outra assinatura.
    """
    orfas = sorted(_identificador(rota) for rota in _CORPOS_SOB_MEDIDA if rota not in _TODAS)

    assert orfas == [], f"corpos sob medida para rotas que a app não serve: {orfas}"


def test_nenhuma_rota_esta_escondida_do_schema(database_url: str) -> None:
    """Fecha o furo do OpenAPI: `include_in_schema=False` sairia da varredura.

    A enumeração deste arquivo vem do schema, então uma rota escondida dele
    escaparia das duas pernas **em silêncio** — sem entrada morta na allowlist e
    sem falha em lugar nenhum. Aqui a fonte é outra: o router que o composition
    root monta, lido direto.
    """
    wiring = build_http_wiring(wire_dependencies(_settings(database_url)))
    escondidas = sorted(
        getattr(rota, "path", "?")
        for router in wiring.routers
        for rota in router.routes
        if not getattr(rota, "include_in_schema", True)
    )

    assert escondidas == [], (
        f"rotas fora do schema OpenAPI: {escondidas}. Elas não aparecem na "
        f"varredura deste arquivo e escapariam do Gate 2 sem sintoma."
    )


# ---------------------------------------------------------------------------
# Perna 1 — sem credencial, 401. Automática para toda rota, presente e futura.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("rota", _NAO_PUBLICAS, ids=_identificador)
async def test_rota_nao_publica_recusa_sem_credencial(
    client_gate: AsyncClient, rota: tuple[str, str]
) -> None:
    """401 sem `Authorization`, com corpo vazio de propósito.

    A dependência de autenticação roda antes da validação de corpo, então `{}`
    basta — e é melhor que um corpo válido: prova que a recusa não depende de o
    pedido estar bem formado. Uma rota que validasse o payload antes de
    autenticar responderia 422 aqui, e 422 a quem não se identificou já é
    informação sobre a forma do recurso.
    """
    metodo, caminho = rota

    resposta = await client_gate.request(metodo, _url(caminho), json={})

    assert resposta.status_code == HTTPStatus.UNAUTHORIZED, (
        f"{_identificador(rota)} respondeu {resposta.status_code} sem credencial. "
        f"Se a rota é pública, declare-a em ROTAS_PUBLICAS com o motivo; se não "
        f"é, ela está aberta."
    )


@pytest.mark.parametrize("rota", sorted(ROTAS_PUBLICAS), ids=_identificador)
async def test_rota_publica_nao_recusa_por_falta_de_credencial(
    client_gate: AsyncClient, rota: tuple[str, str]
) -> None:
    """A outra direção: a allowlist descreve rotas que de fato dispensam credencial.

    Sem isto, pôr uma rota autenticada na allowlist a tiraria do gate **e**
    ninguém notaria — a entrada não estaria morta e nada mais a examinaria. Aqui
    ela reprova por não se comportar como pública.
    """
    metodo, caminho = rota

    resposta = await client_gate.request(metodo, _url(caminho), json={})

    assert resposta.status_code != HTTPStatus.UNAUTHORIZED, (
        f"{_identificador(rota)} está na allowlist de rotas públicas e recusou "
        f"por falta de credencial — a entrada descreve algo que a rota não é"
    )


# ---------------------------------------------------------------------------
# Perna 2 — credencial válida de papel sem permissão, 403.
# ---------------------------------------------------------------------------


@pytest.fixture
async def token_sem_permissao(client_gate: AsyncClient, admin_gate: User) -> dict[str, str]:
    """Um `employee` autenticado — o papel cujo conjunto de permissões é vazio.

    `Role.EMPLOYEE` mapeia para `frozenset()` (`role.py`), então ele é negado em
    **qualquer** rota que exija permissão, seja qual for. É o que torna a perna
    do 403 independente da permissão que a rota nova venha a exigir: não há
    capacidade que este ator detenha.

    A cadeia é a real, pela API: admin cria restaurante, cria o owner, o owner
    cria a unidade e o usuário `employee`. Semear direto no repositório seria
    mais curto e provaria menos — o ator do teste passaria a ser um que nenhuma
    rota consegue produzir.
    """
    admin = await fazer_login(client_gate, ADMIN_EMAIL)
    email_owner = "dono-gate2@x.com"
    restaurante = (
        await client_gate.post(
            f"{API}/restaurants",
            json={"name": "Gate 2", "owner": {"email": email_owner, "password": SENHA_PADRAO}},
            headers=auth(admin),
        )
    ).json()["id"]
    owner = await fazer_login(client_gate, email_owner)

    unidade = (
        await client_gate.post(
            f"{API}/restaurants/{restaurante}/units",
            json={"name": "Unidade Gate 2"},
            headers=auth(owner),
        )
    ).json()["id"]

    email_employee = "sem-permissao-gate2@x.com"
    criacao = await client_gate.post(
        f"{API}/users",
        json={
            "email": email_employee,
            "password": SENHA_PADRAO,
            "role": Role.EMPLOYEE.value,
            "unit_ids": [unidade],
        },
        headers=auth(owner),
    )
    assert criacao.status_code == HTTPStatus.CREATED, criacao.text

    return auth(await fazer_login(client_gate, email_employee))


@pytest.mark.parametrize("rota", _NAO_PUBLICAS, ids=_identificador)
async def test_rota_nao_publica_recusa_papel_sem_permissao(
    client_gate: AsyncClient,
    token_sem_permissao: dict[str, str],
    rota: tuple[str, str],
) -> None:
    """403 com credencial válida de quem não detém capacidade nenhuma.

    A perna do 401 prova que a rota pede credencial; esta prova que ela pede
    **autorização**. As duas são necessárias: uma rota que autentica e não
    autoriza passa na primeira e serve o recurso a qualquer usuário do sistema.

    422 aqui **não é aprovação** — significa que o corpo sintetizado não passou
    na validação e a execução parou antes do guard. A mensagem manda escrever o
    corpo em `_CORPOS_SOB_MEDIDA`, e não relaxar a asserção.
    """
    metodo, caminho = rota
    corpo = _corpo(metodo, caminho, _spec())
    query = _query(metodo, caminho, _spec())

    resposta = await client_gate.request(
        metodo, _url(caminho), json=corpo, params=query, headers=token_sem_permissao
    )

    assert resposta.status_code != HTTPStatus.UNPROCESSABLE_ENTITY, (
        f"{_identificador(rota)} respondeu 422 ao corpo sintetizado {corpo}. A "
        f"execução parou na validação, antes do guard, então este teste não "
        f"chegou a verificar autorização nenhuma. Escreva um corpo aceito em "
        f"_CORPOS_SOB_MEDIDA[{(metodo, caminho)!r}]."
    )
    assert resposta.status_code == HTTPStatus.FORBIDDEN, (
        f"{_identificador(rota)} respondeu {resposta.status_code} a um "
        f"`employee`, que não detém permissão nenhuma. A rota autentica e não "
        f"autoriza: qualquer usuário do sistema alcança o recurso."
    )


# ---------------------------------------------------------------------------
# Os violadores plantados
#
# As asserções de status acima não são varreduras: `parametrize` transforma cada
# rota num teste próprio, e um 200 onde se esperava 401 falha alto. O que **é**
# varredura aqui é a camada de baixo — a enumeração, a classificação e a síntese
# de corpo —, e é ela que devolveria conjunto vazio sem sintoma. Os três testes
# abaixo a exercitam contra specs OpenAPI plantados, sem app e sem banco.
# ---------------------------------------------------------------------------


def test_uma_rota_nova_no_schema_entra_na_cobranca() -> None:
    """A rota que ninguém declarou cai em `_NAO_PUBLICAS`, não some.

    É a propriedade que faz este arquivo valer para a Stage 3.6 sem ser editado:
    `POST /api/v1/units/{id}/employees` não existe hoje, e no dia em que existir
    já nasce cobrada pelas duas pernas. Uma classificação invertida — "só cobro
    o que está numa lista" — passaria em tudo o que existe hoje e deixaria a
    rota nova de fora, que é exatamente o defeito que o gate existe para não ter.
    """
    plantado = {
        "paths": {
            f"{API}/auth/login": {"post": {}},
            f"{API}/units/{{unit_id}}/employees": {"post": {}, "get": {}},
        }
    }

    cobradas = _nao_publicas(_rotas(plantado))

    assert cobradas == [
        ("GET", f"{API}/units/{{unit_id}}/employees"),
        ("POST", f"{API}/units/{{unit_id}}/employees"),
    ]


def test_a_sintese_de_corpo_cobre_os_campos_obrigatorios_de_um_schema_plantado() -> None:
    """A síntese segue `$ref` e emite valor por tipo — só o que é obrigatório.

    Sem este teste, uma síntese quebrada devolveria `{}` para toda rota, a perna
    do 403 responderia 422 em todas, e a mensagem mandaria escrever um corpo sob
    medida para cada uma — trocando um gate automático por um catálogo escrito à
    mão, sem que nada apontasse a causa.
    """
    plantado = {
        "paths": {
            "/x": {
                "post": {
                    "requestBody": {
                        "content": {
                            "application/json": {"schema": {"$ref": "#/components/schemas/Novo"}}
                        }
                    }
                }
            }
        },
        "components": {
            "schemas": {
                "Novo": {
                    "properties": {
                        "nome": {"type": "string"},
                        "quantidade": {"type": "integer"},
                        "ids": {"type": "array"},
                        "opcional": {"type": "string"},
                    },
                    "required": ["nome", "quantidade", "ids"],
                }
            }
        },
    }

    assert _corpo("POST", "/x", plantado) == {"nome": "x", "quantidade": 1, "ids": []}


def test_o_corpo_sob_medida_vence_a_sintese() -> None:
    """A válvula precisa realmente desviar da síntese.

    Ela é o que impede que a única saída de um 422 seja afrouxar a asserção — e
    uma válvula que não desvia é pior que nenhuma: quem a usasse veria o mesmo
    422, e concluiria que o problema é a asserção.
    """
    rota = ("POST", f"{API}/users")

    assert _corpo(*rota, {"paths": {}}) == _CORPOS_SOB_MEDIDA[rota]


def test_os_parametros_de_caminho_sao_substituidos() -> None:
    """Dois parâmetros, para que a substituição não passe por casualidade.

    Com um só, um `str.replace` da primeira ocorrência ou um `split` truncado
    passariam. As chaves precisam sumir: um `{unit_id}` literal na URL vira 404
    de rota, e 404 não é nem 401 nem 403 — a rota sairia do gate parecendo
    coberta.
    """
    url = _url(f"{API}/restaurants/{{restaurant_id}}/units/{{unit_id}}/employees")

    assert url == f"{API}/restaurants/{_PARAMETRO}/units/{_PARAMETRO}/employees"
    assert "{" not in url
