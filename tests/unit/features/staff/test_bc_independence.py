"""A independência do BC staff em relação a identity — CA12 e CA13.

**Por que na raiz de `tests/unit/features/staff/`, e não dentro de uma camada.**
As duas varreduras deste arquivo falam do bounded context **inteiro** (todos os
módulos de `features/staff/`) e de um arquivo de configuração do repositório
(`.importlinter`); nenhuma delas é regra de `domain/`, `application/` ou
`adapters/`. Pô-lo dentro de uma dessas pastas afirmaria que a regra é da
camada, o que é falso. O raciocínio é o de `tests/unit/test_bootstrap.py`
(teste transversal sobe ao nível cuja fronteira a regra descreve) — **por
analogia, não por precedente literal**: aquele ocupa um nível já usado, este
abre um slot novo. Nada valida caminhos sob `tests/` (`check_layout.py` só olha
`src/`), então a escolha é de convenção e fica declarada aqui em vez de
implícita (technical §7).

**Por que um teste, se `lint-imports` já roda em `make check`.** Os dois
cobrem coisas diferentes, e a diferença é o conteúdo do CA13:

- `lint-imports` prova que o contrato **como está escrito** passa. Um
  `ignore_imports` acrescentado ao contrato o mantém verde enquanto abre a
  fronteira — a supressão é invisível para ele, porque é ele quem a obedece.
- Este arquivo prova que o contrato **não foi afrouxado além do decidido** (lê o
  `.importlinter` e falha se a lista de supressões for outra que a única aresta
  nomeada) e que o BC não **nomeia** o vocabulário do outro lado, que é mais
  estreito que não importar: um `Literal["manage_staff"]` é aceitável, um
  `Permission` importado não é — e a distinção não é expressável como contrato
  de import.

**Desde a Stage 3.5 a fronteira tem exatamente uma aresta** (ADR 3.5.0001): o
gateway em `adapters/out/identity/` importa **um** módulo de identity — a
fachada — por um par nomeado no contrato. O que este arquivo assere mudou de
"zero" para "exatamente este": qual pacote pode importar, qual módulo pode ser
importado, e que o papel do login atravessa como **valor**. Um segundo par entra
por decisão — editando a lista aqui e no `.importlinter` no mesmo commit —,
nunca por deriva.
"""

import ast
import configparser
import pathlib

import pytest

pytestmark = pytest.mark.unit

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[4]
_FEATURES = _REPO_ROOT / "src" / "restaurant_hub" / "features"
_STAFF = _FEATURES / "staff"
_IMPORTLINTER = _REPO_ROOT / ".importlinter"

_PREFIXO_DE_FEATURE = "restaurant_hub.features."
_SECAO_BC_INDEPENDENCE = "importlinter:contract:bc-independence"
_MODULO_IDENTITY = "restaurant_hub.features.identity"
# Entrou na Stage 4.1 (3º BC). A lista explícita abaixo e a varredura de pasta de
# `test_ca13_...` são um par: sem a primeira, um contrato vazio passaria; sem a
# segunda, o **quarto** BC entraria em silêncio.
_MODULO_SCHEDULING = "restaurant_hub.features.scheduling"
_MODULO_STAFF = "restaurant_hub.features.staff"

# A única aresta (ADR 3.5.0001 §3): **qual** pacote de staff pode importar
# identity, **qual** módulo de identity ele pode importar, e o par tal como o
# `.importlinter` o escreve. Três constantes, uma decisão.
_PACOTE_DO_GATEWAY = pathlib.PurePosixPath("adapters/out/identity")
_MODULO_DA_FACHADA = "restaurant_hub.features.identity.application.facade"
_PAR_UNICO = (
    "restaurant_hub.features.staff.adapters.out.identity.* -> "
    "restaurant_hub.features.identity.application.facade"
)
_GATEWAY = _STAFF / "adapters" / "out" / "identity" / "local_identity_gateway.py"
# Issue #47 (ADR 0.0.0016): o segundo consumidor da mesma aresta — o `AccessGuard`
# que até ali era `_IdentityAccessGuard`, no composition root.
_ACCESS_GUARD = _STAFF / "adapters" / "out" / "identity" / "local_access_guard.py"
# L-IG1: o papel do login de funcionário é do port, e atravessa como valor.
_PAPEL_DE_FUNCIONARIO = "employee"

# O vocabulário de acesso de identity. Não basta não importar: **nomear** o tipo
# já é conhecer como o outro BC decide, e é o começo de reimplementar a decisão
# aqui (ADR 3.4.0001, alternativa D).
_VOCABULARIO_DE_IDENTITY = frozenset({"Role", "Permission"})


def _modulos_de_staff() -> list[pathlib.Path]:
    """Todos os `.py` do BC — sem filtro por camada, que é o ponto do CA12."""
    return sorted(_STAFF.rglob("*.py"))


def _identificadores(arvore: ast.AST) -> set[str]:
    """Nomes que o módulo **usa**, em qualquer posição sintática.

    Colhe de onde um identificador pode aparecer sem ser conteúdo de string:
    referência (`Name`), acesso a atributo (`Attribute`), alias de import,
    definição de classe/função, parâmetro e argumento nomeado. Texto dentro de
    docstring **não** conta, e é por isso que a menção a `Role.from_string` na
    docstring de `shift_preference.py` não reprova este teste: citar o outro BC
    em prosa é referência, usá-lo é acoplamento.
    """
    nomes: set[str] = set()
    for no in ast.walk(arvore):
        if isinstance(no, ast.Name):
            nomes.add(no.id)
        elif isinstance(no, ast.Attribute):
            nomes.add(no.attr)
        elif isinstance(no, ast.alias):
            nomes.add(no.name.split(".")[-1])
            if no.asname:
                nomes.add(no.asname)
        elif isinstance(no, ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            nomes.add(no.name)
        elif isinstance(no, ast.arg) or (isinstance(no, ast.keyword) and no.arg is not None):
            nomes.add(no.arg)
    return nomes


def _alvos_de_import(arvore: ast.AST) -> set[str]:
    """Módulos alcançados por `import X` e `from X import ...`."""
    alvos: set[str] = set()
    for no in ast.walk(arvore):
        if isinstance(no, ast.ImportFrom) and no.module:
            alvos.add(no.module)
        elif isinstance(no, ast.Import):
            alvos.update(alias.name for alias in no.names)
    return alvos


def _contrato_bc_independence() -> configparser.SectionProxy:
    """A seção do `.importlinter`, lida como configuração e não como texto."""
    parser = configparser.ConfigParser()
    parser.read(_IMPORTLINTER, encoding="utf-8")
    assert parser.has_section(_SECAO_BC_INDEPENDENCE), (
        f"o contrato {_SECAO_BC_INDEPENDENCE!r} sumiu do .importlinter — "
        f"apagá-lo deixaria `lint-imports` verde com a fronteira aberta"
    )
    return parser[_SECAO_BC_INDEPENDENCE]


def _violacoes_da_aresta(caminho_relativo: pathlib.PurePosixPath, alvos: set[str]) -> list[str]:
    """Por que um módulo de staff que importa identity **não** é a aresta permitida.

    Devolve vazio quando o módulo está sob `adapters/out/identity/` **e** todo
    import de identity é a fachada. Fatorado para que o teste negativo abaixo
    possa exercitar o detector com casos plantados, sem gravar violador em `src/`.
    """
    de_identity = sorted(alvo for alvo in alvos if alvo.startswith(_MODULO_IDENTITY))
    if not de_identity:
        return []
    razoes: list[str] = []
    if not caminho_relativo.is_relative_to(_PACOTE_DO_GATEWAY):
        razoes.append(f"fora de {_PACOTE_DO_GATEWAY}/ — só o gateway pode importar identity")
    alem_da_fachada = [alvo for alvo in de_identity if alvo != _MODULO_DA_FACHADA]
    if alem_da_fachada:
        razoes.append(f"importa identity além da fachada: {alem_da_fachada}")
    return razoes


def test_ca12_so_o_gateway_importa_identity_e_importa_so_a_fachada() -> None:
    """A varredura é sobre o BC inteiro, um arquivo de cada vez.

    `lint-imports` já cobriria isto, mas o faz sobre o grafo que o contrato
    descreve — e o contrato é editável. Aqui a asserção não passa por ele: a
    forma da aresta (ADR 3.5.0001 §3) é reaplicada sobre a árvore de import de
    cada módulo. O gateway **tem** de aparecer como importador — senão a
    asserção estaria verde por vácuo.
    """
    importadores: dict[str, set[str]] = {}
    for arquivo in _modulos_de_staff():
        alvos = _alvos_de_import(
            ast.parse(arquivo.read_text(encoding="utf-8"), filename=str(arquivo))
        )
        if any(alvo.startswith(_MODULO_IDENTITY) for alvo in alvos):
            importadores[arquivo.relative_to(_STAFF).as_posix()] = alvos

    violacoes = {
        caminho: razoes
        for caminho, alvos in importadores.items()
        if (razoes := _violacoes_da_aresta(pathlib.PurePosixPath(caminho), alvos))
    }
    assert violacoes == {}, (
        f"módulos de staff fora da única aresta permitida: {violacoes}. "
        f"Só `{_PACOTE_DO_GATEWAY}/` importa identity, e só `{_MODULO_DA_FACHADA}` "
        f"(ADR 3.5.0001 §3)."
    )
    # Os dois adapters da aresta, e só eles — desde a issue #47. Um terceiro
    # importador sob `adapters/out/identity/` passaria pela forma acima (o
    # curinga o autoriza); aqui ele entra por decisão.
    assert set(importadores) == {
        _GATEWAY.relative_to(_STAFF).as_posix(),
        _ACCESS_GUARD.relative_to(_STAFF).as_posix(),
    }, f"importadores de identity em staff: {sorted(importadores)}"


def test_ca12_nenhum_modulo_de_staff_nomeia_role_nem_permission() -> None:
    """Mais estreito que não importar — e é a metade que o import-linter não vê.

    Um `Permission` que chegasse por `TYPE_CHECKING`, por `importlib` ou por
    `globals()` não apareceria como import no grafo, e o contrato seguiria
    verde. O que o desenho proíbe é staff **conhecer** o vocabulário fechado do
    outro BC — por isso a asserção é sobre o nome usado, não sobre a aresta.
    """
    culpados: dict[str, list[str]] = {}
    for arquivo in _modulos_de_staff():
        arvore = ast.parse(arquivo.read_text(encoding="utf-8"), filename=str(arquivo))
        encontrados = _identificadores(arvore) & _VOCABULARIO_DE_IDENTITY
        if encontrados:
            culpados[str(arquivo.relative_to(_STAFF))] = sorted(encontrados)

    assert culpados == {}, (
        f"staff nomeia o vocabulário de identity: {culpados}. A permissão "
        f'atravessa a fronteira como **valor** (`"manage_staff"`), nunca como enum.'
    )


def test_ca13_o_contrato_bc_independence_tem_exatamente_o_par_da_fachada() -> None:
    """CA13 — a lista de supressões é **exata**, e a única entrada é a fachada.

    Até a Stage 3.4 este teste asseria que a lista não existia ("zero" só é
    propriedade se algo o medir). A 3.5 abriu a fronteira por **uma** aresta,
    nomeada (ADR 3.5.0001 §3), e a asserção passou de "nenhuma" para "esta, e só
    esta": um segundo `ignore_imports` — mesmo apontando para a fachada, mesmo
    vindo de outro pacote de staff — reprova aqui até que alguém o decida e o
    escreva nos dois lugares. E `unmatched_ignore_imports_alerting = error` faz
    o par apontar para um import que existe: se o gateway deixar de importar a
    fachada, a supressão vira erro em vez de lixo silencioso.
    """
    contrato = _contrato_bc_independence()

    pares = [linha.strip() for linha in contrato["ignore_imports"].splitlines() if linha.strip()]
    assert pares == [_PAR_UNICO], (
        f"o contrato `bc-independence` tem outra lista de supressões: {pares}. "
        "A única aresta entre os BCs é `staff.adapters.out.identity.* -> "
        "identity.application.facade` (ADR 3.5.0001 §3); uma segunda entra por "
        "decisão, editando esta constante e o `.importlinter` no mesmo commit."
    )
    assert contrato["unmatched_ignore_imports_alerting"] == "error"


def test_ca13_o_contrato_continua_sendo_independencia_entre_os_bcs() -> None:
    """Sem isto, afrouxar o contrato passaria pela porta de trás.

    Trocar `type = independence` por `forbidden` com um `forbidden_modules`
    vazio, ou remover um dos módulos da lista, deixaria `lint-imports`
    verde e a asserção de `ignore_imports` também — porque não haveria
    supressão nenhuma a encontrar. O contrato precisa continuar sendo o que o
    CA13 diz que é.

    **Fala dos BCs, não "dos dois".** Eram dois até a Stage 4.1, que trouxe
    `scheduling`; `type = independence` é par a par entre todos os módulos
    listados, e a asserção é sobre o conjunto inteiro.
    """
    contrato = _contrato_bc_independence()
    modulos = contrato["modules"].split()

    assert contrato["type"] == "independence"
    assert sorted(modulos) == sorted([_MODULO_IDENTITY, _MODULO_SCHEDULING, _MODULO_STAFF])


def test_ca13_o_contrato_cobre_todos_os_bcs_que_existem_na_pasta_features() -> None:
    """A lista explícita acima, cobrada contra a realidade — Stage 4.1.

    A asserção anterior é uma lista escrita à mão: ela envelhece em silêncio. Um
    BC **ausente** do contrato não viola nada — `type = independence` só cobra os
    pares entre os módulos que estão lá —, então `lint-imports` seguiria **KEPT**
    com a fronteira do BC novo inteiramente aberta, e a lista explícita seguiria
    verde porque ninguém a cobraria contra a pasta.

    É o defeito que esta asserção paga: a Stage 4.1 descobriu que o terceiro BC
    entrava sem gate, e o quarto entraria do mesmo jeito. É a forma de
    `test_a_lista_de_bounded_contexts_cobre_a_pasta_features`
    (`tests/unit/test_status_map.py`), aplicada ao contrato em vez de à
    parametrização.
    """
    na_pasta = {
        _PREFIXO_DE_FEATURE + pasta.name
        for pasta in _FEATURES.iterdir()
        if pasta.is_dir() and not pasta.name.startswith(("_", "."))
    }
    assert na_pasta, f"nenhum BC encontrado em {_FEATURES} — a varredura quebrou"

    no_contrato = set(_contrato_bc_independence()["modules"].split())

    assert no_contrato == na_pasta, (
        f"o contrato `bc-independence` divergiu da pasta features/: "
        f"faltam {sorted(na_pasta - no_contrato)}, sobram "
        f"{sorted(no_contrato - na_pasta)}. Um BC fora do contrato não viola "
        f"nada — `lint-imports` fica verde com a fronteira dele aberta."
    )


def test_o_gateway_fixa_o_papel_de_funcionario_como_valor() -> None:
    """L-IG1 pelo lado da fronteira: o papel atravessa como **literal**, não como enum.

    O gateway é o único módulo de staff que fala com identity, e é justamente
    onde `Role.EMPLOYEE` seria tentador. A varredura de vocabulário acima já
    reprova o nome; esta assere o positivo: existe uma constante com o valor
    `"employee"`, e é ela que o gateway passa em `role=`.
    """
    arvore = ast.parse(_GATEWAY.read_text(encoding="utf-8"), filename=str(_GATEWAY))

    constantes = {
        alvo.id: no.value.value
        for no in ast.walk(arvore)
        if isinstance(no, ast.Assign) and isinstance(no.value, ast.Constant)
        for alvo in no.targets
        if isinstance(alvo, ast.Name)
    }
    nomes_com_o_papel = {
        nome for nome, valor in constantes.items() if valor == _PAPEL_DE_FUNCIONARIO
    }
    assert nomes_com_o_papel, f"o gateway não declara o literal {_PAPEL_DE_FUNCIONARIO!r}"

    argumentos_role = [
        palavra.value
        for no in ast.walk(arvore)
        if isinstance(no, ast.Call)
        for palavra in no.keywords
        if palavra.arg == "role"
    ]
    assert argumentos_role, "o gateway não passa `role=` para a fachada"
    assert all(
        isinstance(valor, ast.Name) and valor.id in nomes_com_o_papel for valor in argumentos_role
    ), "o `role=` passado à fachada não é a constante com o papel de funcionário"


def test_os_dois_detectores_reprovam_um_caso_plantado() -> None:
    """Teste negativo: guarda que nunca viu um positivo não é guarda.

    Os dois detectores são varreduras que devolvem conjunto vazio quando o
    código está limpo — e devolveriam conjunto vazio também se estivessem
    quebrados. O código violador é analisado aqui, não gravado em `src/`.
    """
    violador = ast.parse(
        "from restaurant_hub.features.identity.domain.value_objects.permission "
        "import Permission\n"
        "def decide(role: Role) -> Permission: ...\n"
    )

    assert any(alvo.startswith(_MODULO_IDENTITY) for alvo in _alvos_de_import(violador))
    assert _identificadores(violador) & _VOCABULARIO_DE_IDENTITY == _VOCABULARIO_DE_IDENTITY


@pytest.mark.parametrize(
    ("caminho", "alvo", "razao_esperada"),
    [
        pytest.param(
            "application/use_cases/create_login.py",
            _MODULO_DA_FACHADA,
            "fora de",
            id="fachada-importada-fora-do-gateway",
        ),
        pytest.param(
            "adapters/out/identity/local_identity_gateway.py",
            "restaurant_hub.features.identity.application.use_cases.provision_account",
            "além da fachada",
            id="gateway-importando-alem-da-fachada",
        ),
        pytest.param(
            "adapters/out/identity/local_identity_gateway.py",
            "restaurant_hub.features.identity.domain.value_objects.role",
            "além da fachada",
            id="gateway-importando-o-dominio-de-identity",
        ),
    ],
)
def test_o_detector_da_aresta_reprova_os_dois_lados_da_forma(
    caminho: str, alvo: str, razao_esperada: str
) -> None:
    """A forma da aresta tem dois lados (quem importa; o que importa) — cada um reprova só."""
    razoes = _violacoes_da_aresta(pathlib.PurePosixPath(caminho), {alvo})

    assert len(razoes) == 1
    assert razao_esperada in razoes[0]


def test_o_detector_da_aresta_aceita_exatamente_o_gateway_sobre_a_fachada() -> None:
    razoes = _violacoes_da_aresta(
        pathlib.PurePosixPath("adapters/out/identity/local_identity_gateway.py"),
        {_MODULO_DA_FACHADA, "restaurant_hub.features.staff.application.errors"},
    )

    assert razoes == []
