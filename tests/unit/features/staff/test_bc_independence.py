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
- Este arquivo prova que o contrato **não foi afrouxado** (lê o `.importlinter`
  e falha se a lista de supressões existir) e que o BC não **nomeia** o
  vocabulário do outro lado, que é mais estreito que não importar: um
  `Literal["manage_staff"]` é aceitável, um `Permission` importado não é — e a
  distinção não é expressável como contrato de import.
"""

import ast
import configparser
import pathlib

import pytest

pytestmark = pytest.mark.unit

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[4]
_STAFF = _REPO_ROOT / "src" / "restaurant_hub" / "features" / "staff"
_IMPORTLINTER = _REPO_ROOT / ".importlinter"

_SECAO_BC_INDEPENDENCE = "importlinter:contract:bc-independence"
_MODULO_IDENTITY = "restaurant_hub.features.identity"
_MODULO_STAFF = "restaurant_hub.features.staff"

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


def test_ca12_nenhum_modulo_de_staff_importa_identity() -> None:
    """A varredura é sobre o BC inteiro, um arquivo de cada vez.

    `lint-imports` já cobriria isto, mas o faz sobre o grafo que o contrato
    descreve — e o contrato é editável. Aqui a asserção não passa por ele.
    """
    culpados = {
        str(arquivo.relative_to(_STAFF))
        for arquivo in _modulos_de_staff()
        if any(
            alvo.startswith(_MODULO_IDENTITY)
            for alvo in _alvos_de_import(
                ast.parse(arquivo.read_text(encoding="utf-8"), filename=str(arquivo))
            )
        )
    }

    assert culpados == set(), (
        f"módulos de staff importando {_MODULO_IDENTITY}: {sorted(culpados)}. "
        f"O vocabulário de acesso entra pelo port `AccessGuard`, e a tradução "
        f"mora no composition root (ADR 3.4.0001 §3)."
    )


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


def test_ca13_o_contrato_bc_independence_nao_tem_nenhum_ignore_imports() -> None:
    """CA13 — a supressão que ninguém escreveu é a que este teste guarda.

    O `ignore_imports` é o caminho de menor resistência no dia em que um import
    cross-BC aparecer: uma linha no `.importlinter` deixa `make check` verde e a
    fronteira aberta. O ADR 3.4.0001 escolheu o tradutor no composition root
    justamente para que o número seja **zero**, e "zero" só é uma propriedade se
    algo o medir.
    """
    contrato = _contrato_bc_independence()

    assert "ignore_imports" not in contrato, (
        "o contrato `bc-independence` ganhou `ignore_imports`: "
        f"{contrato.get('ignore_imports')!r}. É DoD da Stage 3.4 que a lista não "
        "exista — a alternativa medida (adapter em staff) custaria TRÊS pares, "
        "não um (ADR 3.4.0001, alternativa A)."
    )


def test_ca13_o_contrato_continua_sendo_independencia_entre_os_dois_bcs() -> None:
    """Sem isto, afrouxar o contrato passaria pela porta de trás.

    Trocar `type = independence` por `forbidden` com um `forbidden_modules`
    vazio, ou remover um dos dois módulos da lista, deixaria `lint-imports`
    verde e a asserção de `ignore_imports` também — porque não haveria
    supressão nenhuma a encontrar. O contrato precisa continuar sendo o que o
    CA13 diz que é.
    """
    contrato = _contrato_bc_independence()
    modulos = contrato["modules"].split()

    assert contrato["type"] == "independence"
    assert sorted(modulos) == sorted([_MODULO_IDENTITY, _MODULO_STAFF])


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
