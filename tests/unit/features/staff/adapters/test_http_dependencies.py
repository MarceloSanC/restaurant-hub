"""Validador de identificador, requisito de acesso e provedor de ator — ADR 3.6.0002.

**A restrição é do tamanho da divergência medida, e as duas metades são teste.**
Provar que os três valores são rejeitados sem provar que o resto passa **verbatim**
deixaria a porta aberta para alguém endurecer a validação "por segurança" — e uma
validação que apara acento ou recusa quebra de linha quebraria dados legítimos
que a Stage 3.3 mediu como sobreviventes do round-trip. Por isso o conjunto
adversarial da 3.3 é congelado aqui, do lado do **aceite**.
"""

import dataclasses
import inspect
import typing

import pytest
from pydantic import BaseModel

from restaurant_hub.features.staff.adapters.inbound.http import dependencies, schemas
from restaurant_hub.features.staff.domain.exceptions.errors import InvalidIdentifierError

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# O validador — os três valores rejeitados, e nada além deles
# ---------------------------------------------------------------------------

# Os três, e a razão de cada um é diferente (concept §5.14):
#
# - `"\x00"` é o único que produz **500 hoje**: `psycopg` o recusa client-side
#   com `DataError`, que não é `IntegrityError` (o tradutor da 3.3 nunca é
#   chamado), não é `StaffError` e não é `IdentityError`;
# - `""` e `"   "` **não** produzem 500 — serializam normalmente e terminam em
#   404 ou 403. São recusados por higiene declarada: identificador em branco é o
#   balde de falso isolamento que `InvalidIdentifierError` nomeia.
#
# Registrar a razão certa importa: com a razão errada ("senão vira 500"), a
# primeira pessoa que medir os dois últimos os removeria da lista.
_IDENTIFICADORES_RECUSADOS = [
    pytest.param("", id="vazio"),
    pytest.param("   ", id="so-whitespace"),
    pytest.param("\t\n", id="whitespace-nao-espaco"),
    pytest.param("\x00", id="nul-sozinho"),
    pytest.param("a\x00b", id="nul-no-meio"),
    pytest.param("jf-1\x00", id="nul-no-fim"),
]

# Congelado da Stage 3.3 (`tests/unit/features/staff/domain/test_employee.py`),
# **verbatim**: destes cinco, nenhum divergia entre fake e Postgres — só o byte
# NUL divergia. Eles entram aqui do lado do **aceite** para provar que a
# restrição não cresceu.
_IDENTIFICADORES_ACEITOS = (
    "José Antônio",
    "\U0001f469\u200d\U0001f373",
    "linha1\nlinha2",
    'Ana "Nana" O\'Brien',
    "a" * 1000,
)
_IDS_ADVERSARIAIS = ["acento", "emoji_zwj", "quebra_de_linha", "aspas", "mil_caracteres"]


@pytest.mark.parametrize("raw", _IDENTIFICADORES_RECUSADOS)
def test_o_validador_recusa_os_tres_valores_do_adr(raw: str) -> None:
    """Vazio, só-whitespace e byte NUL — e a exceção é de **domínio**, não HTTP.

    `InvalidIdentifierError` é `StaffError`, então o mapa de status a classifica
    como 422 pelo mesmo caminho de qualquer outra invariante violada. Levantar
    uma `HTTPException` aqui faria a borda ter duas formas de dizer 422, e só uma
    delas carregaria o discriminador de corpo de staff.
    """
    with pytest.raises(InvalidIdentifierError):
        dependencies.validate_identifier(raw, entity="funcionário")


@pytest.mark.parametrize("raw", _IDENTIFICADORES_ACEITOS, ids=_IDS_ADVERSARIAIS)
def test_o_validador_aceita_o_conjunto_adversarial_da_33_verbatim(raw: str) -> None:
    """Aceita **e devolve o mesmo valor**: nada é aparado nem reescrito.

    A segunda asserção é a que importa. Um validador que fizesse
    `return raw.strip()` passaria em "aceita" e apagaria em silêncio a diferença
    entre dois identificadores distintos — normalização silenciosa, que o
    ADR 2.3.0005 recusa e que a cláusula 6 do ADR 3.6.0002 proíbe nominalmente.
    """
    assert dependencies.validate_identifier(raw, entity="função") == raw


@pytest.mark.parametrize("raw", ["  jf-1", "jf-1  ", " jf-1 "])
def test_o_validador_aceita_com_espaco_em_volta_sem_apara_lo(raw: str) -> None:
    """O caso que separa "só-whitespace" de "tem whitespace".

    `"  jf-1  "` **não** é identificador em branco: tem conteúdo. Recusá-lo seria
    uma restrição a mais que ninguém decidiu, e apará-lo seria a normalização que
    o pacote inteiro proíbe. A política de espaço em branco é **uma só** dentro
    do adapter — a mesma que o conversor de `weekly_hours` aplica (D-3B1).
    """
    assert dependencies.validate_identifier(raw, entity="função") == raw


def test_a_mensagem_do_erro_nomeia_a_entidade_que_o_chamador_declarou() -> None:
    """A entidade existe para o diagnóstico, e não muda a classificação."""
    with pytest.raises(InvalidIdentifierError) as excinfo:
        dependencies.validate_identifier("", entity="unidade destino")

    assert "unidade destino" in str(excinfo.value)


def test_o_validador_nao_aceita_tenant() -> None:
    """O tenant nunca chega pela requisição — não há o que validar (concept §5.3).

    A asserção é sobre a **assinatura**: uma função que aceitasse `tenant_id`
    convidaria alguém a passá-lo, e o convite é o começo do campo de corpo que o
    ADR 0.0.0005 existe para tornar inexprimível.
    """
    parametros = set(inspect.signature(dependencies.validate_identifier).parameters)

    assert parametros == {"raw", "entity"}


# ---------------------------------------------------------------------------
# O helper de introspecção — o domínio de CA20 no eixo do corpo
# ---------------------------------------------------------------------------


def _todos_os_requests() -> list[type]:
    """Os `*Request` do módulo de schemas, derivados e não listados."""
    encontrados = [
        objeto
        for nome, objeto in vars(schemas).items()
        if nome.endswith("Request") and isinstance(objeto, type) and issubclass(objeto, BaseModel)
    ]
    assert encontrados, "a varredura precisa encontrar requests para ter o que derivar"
    return encontrados


def test_o_helper_encontra_exatamente_os_identificadores_de_corpo_de_hoje() -> None:
    """CA20, eixo do corpo: o domínio é **derivado**, e este teste prova o que ele dá.

    São dois, e os dois vão direto ao banco: `target_unit_id` para
    `units.find_by_id` **dentro de identity** (é o segundo alvo de autorização de
    R16) e cada elemento de `job_function_ids` para `find_all_by_ids` do
    repositório de funções, **antes** da construção da entidade. Nenhum dos dois
    passa por `Employee.__post_init__`.
    """
    encontrados = {
        campo.name
        for modelo in _todos_os_requests()
        for campo in dependencies.identifier_fields(modelo)
    }

    assert encontrados == {"target_unit_id", "job_function_ids"}


def test_o_helper_distingue_o_campo_escalar_da_colecao() -> None:
    """A distinção não é decoração: ela decide **o que** a varredura corrompe.

    Corromper `job_function_ids` inteiro — trocando a lista por `"\\x00"` —
    produziria um erro de **forma**, isto é, o 422 do `RequestValidationError` do
    framework, e a varredura ficaria verde contra o erro errado. O que se
    corrompe é um **elemento**.
    """
    por_nome = {
        campo.name: campo
        for modelo in _todos_os_requests()
        for campo in dependencies.identifier_fields(modelo)
    }

    assert por_nome["target_unit_id"].is_collection is False
    assert por_nome["job_function_ids"].is_collection is True


def test_o_helper_ignora_campo_que_nao_e_identificador() -> None:
    """`name`, `workload_profile` e `shift_preference` não entram na varredura.

    Sem esta asserção, um helper que devolvesse **todos** os campos passaria nos
    dois testes acima quando o conjunto por acaso coincidisse, e a varredura de
    CA20 passaria a corromper campos que não são identificadores — medindo outra
    coisa.
    """
    nomes = {campo.name for campo in dependencies.identifier_fields(schemas.CreateEmployeeRequest)}

    assert nomes == {"job_function_ids"}


def test_o_helper_reconhece_um_campo_de_identificador_plantado() -> None:
    """Guarda que nunca viu um positivo não é guarda.

    Um helper que devolvesse sempre `()` passaria em "ignora o que não é
    identificador" e faria o eixo de corpo de CA20 varrer o conjunto vazio — 422
    nenhum a asserir, e verde.
    """

    class RequestPlantado(BaseModel):
        name: str
        unit_id: str
        outros_ids: list[str]

    campos = {
        campo.name: campo.is_collection for campo in dependencies.identifier_fields(RequestPlantado)
    }

    assert campos == {"unit_id": False, "outros_ids": True}


def test_o_helper_enxerga_a_colecao_sob_optional() -> None:
    """`list[str] | None` continua sendo coleção — o `None` não a esconde."""

    class RequestOpcional(BaseModel):
        extra_ids: list[str] | None = None

    (campo,) = dependencies.identifier_fields(RequestOpcional)

    assert campo.is_collection is True


# ---------------------------------------------------------------------------
# Requisito de acesso por rota
# ---------------------------------------------------------------------------


def test_as_permissoes_atravessam_a_fronteira_como_valores() -> None:
    """Citadas, jamais importadas: o enum mora do outro lado (ADR 3.4.0001).

    O preço está declarado — um erro de digitação não é pego pelo type-checker —,
    e é por isso que os dois literais ficam num só lugar, conferidos aqui contra
    os valores que `AuthorizeActionUseCase` conhece.
    """
    assert dependencies.PERMISSION_MANAGE_STAFF == "manage_staff"
    assert dependencies.PERMISSION_MANAGE_JOB_FUNCTIONS == "manage_job_functions"


def test_o_catalogo_de_funcoes_declara_alvo_sem_unidade() -> None:
    """`manage_job_functions` é tenant-wide (ADR 3.4.0008): o alvo é o restaurante.

    O passo 4 de `AuthorizeActionUseCase` dispensa a unidade **por permissão** —
    não por papel. Declarar `names_unit=True` aqui faria a rota do catálogo pedir
    uma unidade que ela não endereça.
    """
    assert dependencies.MANAGE_JOB_FUNCTIONS_ACCESS.permission == "manage_job_functions"
    assert dependencies.MANAGE_JOB_FUNCTIONS_ACCESS.names_unit is False


def test_a_equipe_declara_alvo_com_unidade() -> None:
    """`manage_staff` endereça a unidade do path (ADR 3.4.0007)."""
    assert dependencies.MANAGE_STAFF_IN_UNIT_ACCESS.permission == "manage_staff"
    assert dependencies.MANAGE_STAFF_IN_UNIT_ACCESS.names_unit is True


def test_o_login_do_funcionario_declara_manage_users_com_unidade() -> None:
    """Stage 3.5 — a terceira permissão citada por staff, e a primeira de identity.

    `manage_users` atravessa a fronteira como **valor**, como as duas de staff; o
    requisito nomeia a unidade porque o alvo de R17 é a unidade do path
    (concept 3.5 §5.3), e é sobre ela que `manager`/`hr` detêm a permissão.
    """
    assert dependencies.PERMISSION_MANAGE_USERS == "manage_users"
    assert dependencies.MANAGE_USERS_IN_UNIT_ACCESS.permission == "manage_users"
    assert dependencies.MANAGE_USERS_IN_UNIT_ACCESS.names_unit is True


def test_o_requisito_de_acesso_nao_carrega_papel_nem_bypass() -> None:
    """A decisão de acesso **não acontece em staff** (concept §5.2).

    O requisito é declaração: permissão e forma do alvo, e nada mais. Um campo
    de papel, de allowlist ou de bypass aqui seria o começo da segunda tabela de
    política — que é o defeito que o port `AccessGuard` existe para impedir.
    """
    campos = {campo.name for campo in dataclasses.fields(dependencies.AccessRequirement)}

    assert campos == {"permission", "names_unit"}


# ---------------------------------------------------------------------------
# O provedor de ator
# ---------------------------------------------------------------------------


class _GuardEspiao:
    """Dublê mínimo: registra a requisição recebida e devolve um ator sentinela."""

    def __init__(self, erro: Exception | None = None) -> None:
        self.recebeu: object = None
        self.ator = object()
        self.erro = erro

    def authenticate(self, request: object) -> object:
        self.recebeu = request
        if self.erro is not None:
            raise self.erro
        return self.ator


def test_o_provedor_de_ator_delega_ao_guard_e_devolve_o_ator() -> None:
    """A dependência não interpreta a credencial — repassa a requisição e o ator."""
    guard = _GuardEspiao()
    requisicao = object()

    devolvido = dependencies.authenticated_actor(requisicao, guard)

    assert guard.recebeu is requisicao
    assert devolvido is guard.ator


def test_o_provedor_de_ator_nao_traduz_a_excecao_de_autenticacao() -> None:
    """L-AG1 na borda: **o mesmo objeto** sobe.

    É o que fará a faixa 401 de staff ser byte-idêntica à de identity. Um
    `try/except` que relançasse uma exceção nova passaria em
    `pytest.raises(TipoX)` e falha aqui — a asserção é de **identidade**.
    """

    class _Sentinela(Exception):
        pass

    sentinela = _Sentinela()
    guard = _GuardEspiao(erro=sentinela)

    with pytest.raises(_Sentinela) as excinfo:
        dependencies.authenticated_actor(object(), guard)

    assert excinfo.value is sentinela


def test_o_provedor_do_guard_levanta_quando_o_wiring_nao_aconteceu() -> None:
    """Falhar alto é melhor que servir um `None` que quebra três camadas adiante.

    A função é apenas a **chave** do `dependency_overrides`; se ela for chamada
    de verdade, o composition root não a substituiu — e um guard ausente numa
    rota de escrita é falha de acesso, não de conveniência.
    """
    with pytest.raises(RuntimeError, match="staff_access_guard"):
        dependencies.get_access_guard()


def test_o_provedor_de_ator_e_uma_dependencia_e_nao_um_middleware() -> None:
    """A forma é contrato (ADR 2.4.0003), e é observável na assinatura.

    Com `Depends`, uma rota **sem** guard é visível na assinatura da função; com
    middleware global seria preciso manter uma allowlist de rotas públicas, que
    erra por omissão e **abre** rota sem querer. A asserção é que o alias que o
    router consome carrega um `Depends` apontando para este provedor.
    """
    metadados = typing.get_args(dependencies.CurrentActor)[1:]

    assert [getattr(m, "dependency", None) for m in metadados] == [dependencies.authenticated_actor]
