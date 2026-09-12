"""`importlib.import_module` em `tests/` só com caminho **calculado** — nunca literal.

**Por que existe.** Até a issue #45 o pacote de entrada se chamava `in/`,
keyword Python, e a única forma de alcançá-lo era `importlib`. O diretório virou
`inbound/` e o import estático passou a funcionar — mas dezessete arquivos de
teste continuaram usando a forma dinâmica por inércia, e o padrão se copia por
analogia: o próximo teste de rota abriria com `importlib.import_module(...)`
porque o vizinho abre assim.

**O custo não é estético, e são três coisas que a forma dinâmica esconde:**

1. **Ponto cego no import-linter.** Import dinâmico não é aresta do grafo. Um
   teste da Stage 2.4 importando adapter da 3.6 por `importlib` não acusa
   contrato nenhum — a mesma família de defeito que a #45 existe para fechar.
2. **`Any` em cascata.** O módulo vem sem tipo, e cada nome extraído dele
   (`router_module._get_guard`) é `Any`; nada é checado.
3. **Sem refactoring seguro.** Renomear `_get_guard` não quebra
   `router_module._get_guard` em tempo de análise — só em execução.

**O que continua legítimo, e o teste distingue.** `importlib` com caminho
**calculado** é a ferramenta certa e fica: `test_status_map.py` parametriza
por bounded context, `test_http_boundary_sweeps.py` e `test_application_guards.py`
varrem pacotes. A regra é sobre o argumento: string literal, ou f-string cujas
partes formatadas sejam constantes de módulo com valor literal, é caminho fixo —
e caminho fixo se escreve como `import`.
"""

import ast
import pathlib

import pytest

pytestmark = pytest.mark.unit

_TESTS = pathlib.Path(__file__).resolve().parents[1]
_PREFIXO_DE_SRC = "restaurant_hub."

_LITERAL = (
    "import importlib\n"
    'm = importlib.import_module("restaurant_hub.features.x.adapters.inbound.http.router")\n'
)
_FSTRING_SOBRE_CONSTANTE = (
    "import importlib\n"
    '_PACOTE = "restaurant_hub.features.x.adapters.inbound.http"\n'
    'm = importlib.import_module(f"{_PACOTE}.router")\n'
)
_NOME_DE_CONSTANTE = (
    "import importlib\n"
    '_PACOTE = "restaurant_hub.features.x.adapters.inbound.http"\n'
    "m = importlib.import_module(_PACOTE)\n"
)
_PARAMETRIZADO_POR_BC = (
    "import importlib\n"
    "def f(bc: str) -> None:\n"
    '    importlib.import_module(f"restaurant_hub.features.{bc}.errors")\n'
)
_VARREDURA_DE_PACOTE = (
    "import importlib\n"
    "for info in infos:\n"
    "    importlib.import_module(f'{pacote.__name__}.{info.name}')\n"
)
_FORA_DE_SRC = 'import importlib\nimportlib.import_module("yaml")\n'


def _constantes_literais(arvore: ast.Module) -> dict[str, str]:
    """`_PACOTE_X = "…"` no nível do módulo — o que torna uma f-string fixa."""
    return {
        no.targets[0].id: no.value.value
        for no in arvore.body
        if isinstance(no, ast.Assign)
        and len(no.targets) == 1
        and isinstance(no.targets[0], ast.Name)
        and isinstance(no.value, ast.Constant)
        and isinstance(no.value.value, str)
    }


def _caminho_fixo(arg: ast.expr, consts: dict[str, str]) -> str | None:
    """O caminho resolvido estaticamente, ou None se depende de runtime."""
    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
        return arg.value
    if isinstance(arg, ast.Name):
        return consts.get(arg.id)
    if isinstance(arg, ast.JoinedStr):
        partes: list[str] = []
        for parte in arg.values:
            if isinstance(parte, ast.Constant):
                partes.append(str(parte.value))
            elif (
                isinstance(parte, ast.FormattedValue)
                and isinstance(parte.value, ast.Name)
                and parte.value.id in consts
            ):
                partes.append(consts[parte.value.id])
            else:
                return None
        return "".join(partes)
    return None


def _imports_dinamicos_fixos(arvore: ast.Module) -> list[tuple[int, str]]:
    """As chamadas `importlib.import_module(<caminho fixo de src/>)` do módulo."""
    consts = _constantes_literais(arvore)
    achados: list[tuple[int, str]] = []
    for no in ast.walk(arvore):
        if not (
            isinstance(no, ast.Call)
            and isinstance(no.func, ast.Attribute)
            and no.func.attr == "import_module"
            and isinstance(no.func.value, ast.Name)
            and no.func.value.id == "importlib"
            and len(no.args) == 1
        ):
            continue
        caminho = _caminho_fixo(no.args[0], consts)
        if caminho is not None and caminho.startswith(_PREFIXO_DE_SRC):
            achados.append((no.lineno, caminho))
    return achados


def test_nenhum_teste_importa_modulo_de_src_por_importlib_com_caminho_fixo() -> None:
    """A varredura real, sobre `tests/` inteiro."""
    culpados: dict[str, list[tuple[int, str]]] = {}
    for arquivo in sorted(_TESTS.rglob("*.py")):
        if "__pycache__" in arquivo.parts:
            continue
        arvore = ast.parse(arquivo.read_text(encoding="utf-8"), filename=str(arquivo))
        achados = _imports_dinamicos_fixos(arvore)
        if achados:
            culpados[str(arquivo.relative_to(_TESTS))] = achados

    assert culpados == {}, (
        f"`importlib.import_module` com caminho fixo de src/ em tests/: {culpados}. "
        f"Caminho fixo se escreve como `from … import …` — a forma dinâmica não "
        f"aparece no grafo do import-linter e chega sem tipo."
    )


@pytest.mark.parametrize(
    "codigo",
    [
        pytest.param(_LITERAL, id="literal"),
        pytest.param(_FSTRING_SOBRE_CONSTANTE, id="f-string-sobre-constante"),
        pytest.param(_NOME_DE_CONSTANTE, id="nome-de-constante"),
    ],
)
def test_um_import_dinamico_de_caminho_fixo_plantado_reprova(codigo: str) -> None:
    """Guarda que nunca viu um positivo não é guarda — as três formas fixas."""
    achados = _imports_dinamicos_fixos(ast.parse(codigo))

    assert len(achados) == 1
    assert achados[0][1].startswith(_PREFIXO_DE_SRC)


@pytest.mark.parametrize(
    "codigo",
    [
        pytest.param(_PARAMETRIZADO_POR_BC, id="parametrizado-por-bc"),
        pytest.param(_VARREDURA_DE_PACOTE, id="varredura-de-pacote"),
        pytest.param(_FORA_DE_SRC, id="fora-de-src"),
    ],
)
def test_um_import_dinamico_de_caminho_calculado_nao_reprova(codigo: str) -> None:
    """A outra direção: o que continua legítimo continua passando.

    Sem este caso, uma varredura que acusasse **todo** `import_module` passaria
    no teste acima — e a saída de quem a visse reprovar `test_status_map.py`
    seria desligá-la.
    """
    assert _imports_dinamicos_fixos(ast.parse(codigo)) == []
