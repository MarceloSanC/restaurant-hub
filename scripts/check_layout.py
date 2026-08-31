"""Script de validação de arquitetura — verifica violações das convenções do docs/LAYOUT.md.

Uso:
    python scripts/check_layout.py
    python scripts/check_layout.py --src src/restaurant_hub

Verifica:
1. Módulos de `domain/` não importam de `application/`, `adapters/`, `infrastructure/`
   ou de libs de framework (fastapi, sqlalchemy, pydantic).
2. Módulos de `application/` não importam de `adapters/` ou `infrastructure/`
   (libs de framework idem).
3. Adapters de uma feature não importam adapters de outras features nem de uma
   subcamada irmã da mesma feature (in não importa out, out não importa in).
4. `restaurant_hub/shared/` não importa de `restaurant_hub.features` (acoplamento inverso).
5. `main.py` não importa feature nenhuma — o entrypoint só conhece a factory.
6. Charter do composition root: só `@dataclass` e só as funções de wiring.
7. Classe de `application/dtos/` não tem comportamento.
9. `__init__.py` é marcador de pacote — docstring e nada mais.

Cada feature também precisa dos diretórios obrigatórios (`domain/`,
`application/`, `adapters/`).

E, acima de todas elas, a cobertura (M1 da issue #45): **todo `.py` de `src/`
casa com pelo menos uma regra**.

---

**Por que a cobertura é a regra mais importante deste arquivo.**

Uma auditoria de 2026-08-29 encontrou oito violações de Clean Architecture com
`lint-imports` em 9 kept / 0 broken e este script em exit 0. A causa-raiz não
foi uma regra errada: foi um arquivo que **nenhuma regra olhava**.
`composition_root.py` não casava com nenhuma âncora de `FORBIDDEN_IMPORTS`
(todas ancoradas em `/domain/`, `/application/`, `/adapters/in/`,
`/adapters/out/`, `/restaurant_hub/shared/`) e não era `source_module` de
contrato nenhum do `.importlinter` — e era o único arquivo do repositório a
carregar uma decisão de isolamento de tenant. Seis Stages construíram em cima
dele sem sintoma.

O padrão que isso instancia é geral: **quando uma regra de import ficou no
caminho, o código foi para onde o linter não olha.** Uma regra nova fecha uma
instância; a cobertura fecha a classe. Por isso `check_coverage` reprova um
arquivo sem regra em vez de ignorá-lo, e por isso as âncoras são **derivadas
das regras** (`coverage_anchors`) em vez de escritas numa segunda lista: uma
lista paralela envelhece, e envelhecer aqui significa voltar a ter arquivo
descoberto — com o gate verde.

**Limitação conhecida:** o script continua sem validar que apenas
`composition_root.py` faz wiring (instanciação direta de adapter concreto).
Essa regra é verificada por teste mecânico por bounded context
(`tests/unit/features/*/adapters/test_composition_root_*.py`) e documentada em
LAYOUT §6.

Retorna código de saída 0 se tudo OK, 1 se houver violações.
"""

import argparse
import ast
import sys
from pathlib import Path

# Um padrão com wildcard único tem exatamente 2 partes após split("*").
_EXPECTED_WILDCARD_PARTS = 2

# ---------------------------------------------------------------------------
# Regras 1-5 — dependência por camada
# ---------------------------------------------------------------------------

# Padrões de import proibidos por camada (chave = padrão no caminho do arquivo)
FORBIDDEN_IMPORTS: list[tuple[str, list[str]]] = [
    # domain não pode importar de application, adapters ou infrastructure
    (
        "/domain/",
        [
            "restaurant_hub.features.*.application",
            "restaurant_hub.features.*.adapters",
            "restaurant_hub.shared.infrastructure",
            "fastapi",
            "sqlalchemy",
            "pydantic",
        ],
    ),
    # application não pode importar de adapters ou infrastructure
    (
        "/application/",
        [
            "restaurant_hub.features.*.adapters",
            "restaurant_hub.shared.infrastructure",
            "fastapi",
            "sqlalchemy",
        ],
    ),
    # adapters/in não pode importar adapters/out (mesma feature) nem adapters de outras features
    (
        "/adapters/in/",
        [
            "restaurant_hub.features.*.adapters.out",
        ],
    ),
    # adapters/out não pode importar adapters/in (mesma feature) nem adapters de outras features
    (
        "/adapters/out/",
        [
            "restaurant_hub.features.*.adapters.in",
        ],
    ),
    # shared não pode importar de features (ancorado pelo prefixo do pacote)
    (
        "/restaurant_hub/shared/",
        [
            "restaurant_hub.features",
        ],
    ),
    # O entrypoint ASGI conhece `create_app` e mais nada. A regra existe porque
    # `main.py` era o segundo arquivo que nenhuma âncora de camada alcançava
    # (M1), e porque ele é o caminho mais curto para instanciar um adapter fora
    # do composition root: `app = create_app()` a uma linha de distância de um
    # `PostgresUserRepository(engine)` não pareceria estranho a ninguém.
    (
        "/restaurant_hub/main.py",
        [
            "restaurant_hub.features",
            "restaurant_hub.composition_root",
        ],
    ),
]

# Diretórios obrigatórios em cada feature
REQUIRED_FEATURE_DIRS = ["domain", "application", "adapters"]

# ---------------------------------------------------------------------------
# Regra 6 — charter do composition root (Gate 1 da issue #45)
# ---------------------------------------------------------------------------

COMPOSITION_ROOT_ANCHOR = "/restaurant_hub/composition_root.py"

# LAYOUT §6 lista o que o composition root faz: ler `Settings`, instanciar
# infraestrutura, instanciar repositórios, injetar e expor. Nada disso decide
# nada. As duas funções abaixo são a superfície inteira do módulo.
COMPOSITION_ROOT_FUNCTIONS = frozenset({"wire_dependencies", "build_http_wiring"})

# Classes que o charter tolera **sem** serem `@dataclass`, cada uma com a issue
# que a tira daqui. Entrada nova reprova o teste de não-crescimento
# (`tests/unit/test_check_layout.py`) até ser justificada do mesmo jeito.
#
# A allowlist é o ponto do desenho: ela não perdoa a dívida, ela a torna
# **contável**. Enquanto `_IdentityAccessGuard` estiver aqui, o número de
# classes que decidem acesso dentro do wiring é 1 — e é preciso uma linha de
# diff, visível em qualquer revisão, para transformá-lo em 2.
COMPOSITION_ROOT_CLASS_ALLOWLIST: dict[str, str] = {
    "_IdentityAccessGuard": (
        "issue #47 — o tradutor de acesso sai daqui para "
        "features/staff/adapters/out/identity/ (ADR 3.4.0001 §Consequences)"
    ),
}

# O `raise` é o sintoma mais direto de decisão dentro do wiring: quem monta
# grafo não recusa pedido. Hoje há exatamente um — o `PermissionDeniedError` da
# lei L-AG3 do tradutor — e ele é tolerado pela mesma issue, na mesma unidade
# sintática. Derivar esta allowlist da de classes é deliberado: são a mesma
# dívida, e duas listas independentes permitiriam tirar a classe da primeira
# deixando o `raise` perdoado pela segunda.
COMPOSITION_ROOT_RAISE_ALLOWLIST: dict[str, str] = dict(COMPOSITION_ROOT_CLASS_ALLOWLIST)

# ---------------------------------------------------------------------------
# Regra 7 — DTO não tem comportamento (Gate 6 da issue #45)
# ---------------------------------------------------------------------------

DTOS_ANCHOR = "/application/dtos/"

# Métodos tolerados em classe de `application/dtos/`, com o ADR que os põe lá.
# A chave é o par (classe, método), e não só o nome do método, para que um
# `is_active` numa classe nova não entre de carona no perdão deste.
DTO_METHOD_ALLOWLIST: dict[tuple[str, str], str] = {
    ("Session", "is_active"): (
        "ADR 2.2.0001 — a sessão de refresh é o registro que torna o logout real; "
        "a convenção half-open do intervalo mora com o dado que ela descreve"
    ),
    ("PasswordSetupToken", "is_usable"): (
        "ADR 2.5.0002 — token de setup é mecanismo separado do de sessão, e a "
        "mesma convenção half-open precisa ser explícita nos dois"
    ),
}

# ---------------------------------------------------------------------------
# Regra 9 — marcador de pacote não carrega código
# ---------------------------------------------------------------------------

PACKAGE_MARKER_ANCHOR = "/__init__.py"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def parse(file_path: Path) -> ast.Module | None:
    """Árvore do arquivo, ou None se ele não for Python analisável."""
    try:
        return ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
    except SyntaxError:
        return None


def get_imports(file_path: Path) -> list[str]:
    """Extrai todos os módulos importados de um arquivo Python."""
    tree = parse(file_path)
    if tree is None:
        return []

    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module)
    return imports


def matches_pattern(import_str: str, pattern: str) -> bool:
    """Verifica se um import corresponde a um padrão simples com wildcard (*)."""
    if "*" not in pattern:
        return import_str.startswith(pattern)
    parts = pattern.split("*")
    if len(parts) != _EXPECTED_WILDCARD_PARTS:
        return import_str.startswith(parts[0])
    prefix, suffix = parts
    if not import_str.startswith(prefix):
        return False
    remaining = import_str[len(prefix) :]
    # O sufixo deve aparecer em algum ponto após o prefixo
    return suffix == "" or suffix in remaining


def posix(file_path: Path) -> str:
    """Caminho normalizado — as âncoras são escritas com `/` mesmo no Windows."""
    return file_path.as_posix().replace("\\", "/")


def is_dataclass(node: ast.ClassDef) -> bool:
    """True se a classe carrega `@dataclass`, com ou sem argumentos."""
    for decorator in node.decorator_list:
        alvo = decorator.func if isinstance(decorator, ast.Call) else decorator
        nome = alvo.attr if isinstance(alvo, ast.Attribute) else getattr(alvo, "id", "")
        if nome == "dataclass":
            return True
    return False


def is_dunder(name: str) -> bool:
    """True para `__init__`, `__post_init__` e afins."""
    return name.startswith("__") and name.endswith("__")


def coverage_anchors() -> dict[str, str]:
    """Padrão de caminho → regra que inspeciona os arquivos que casam com ele.

    **Derivado das regras, nunca escrito à mão.** Uma segunda lista, mantida em
    paralelo, envelheceria em silêncio — e envelhecer aqui significa exatamente
    o defeito que M1 fecha: arquivo sem regra, com o gate verde.
    """
    anchors = {
        layer_pattern: f"dependência de camada ({layer_pattern.strip('/')})"
        for layer_pattern, _ in FORBIDDEN_IMPORTS
    }
    anchors[COMPOSITION_ROOT_ANCHOR] = "regra 6 — charter do composition root"
    anchors[DTOS_ANCHOR] = "regra 7 — DTO sem comportamento"
    anchors[PACKAGE_MARKER_ANCHOR] = "regra 9 — marcador de pacote"
    return anchors


# ---------------------------------------------------------------------------
# Verificadores
# ---------------------------------------------------------------------------


def check_layer_imports(src_root: Path) -> list[str]:
    """Regras 1-5 — cada camada só importa do que lhe é permitido."""
    violations: list[str] = []

    for py_file in src_root.rglob("*.py"):
        file_str = posix(py_file)
        imports = get_imports(py_file)

        for layer_pattern, forbidden in FORBIDDEN_IMPORTS:
            # Normaliza para verificar se o arquivo pertence à camada
            if layer_pattern not in file_str:
                continue

            for imp in imports:
                for forbidden_pattern in forbidden:
                    if matches_pattern(imp, forbidden_pattern):
                        rel = py_file.relative_to(src_root.parent)
                        violations.append(
                            f"VIOLAÇÃO: {rel} importa '{imp}' "
                            f"(proibido para camada '{layer_pattern.strip('/')}')"
                        )
                        break

    return violations


def check_feature_structure(features_root: Path) -> list[str]:
    """Verifica que cada feature tem os diretórios obrigatórios."""
    violations: list[str] = []

    if not features_root.exists():
        return [f"AVISO: diretório de features não encontrado: {features_root}"]

    for feature_dir in features_root.iterdir():
        if not feature_dir.is_dir() or feature_dir.name.startswith("_"):
            continue

        for required in REQUIRED_FEATURE_DIRS:
            if not (feature_dir / required).exists():
                violations.append(
                    f"ESTRUTURA: feature '{feature_dir.name}' não tem diretório '{required}/'"
                )

    return violations


def check_composition_root_charter(src_root: Path) -> list[str]:
    """Regra 6 — o composition root monta o grafo e não decide mais nada.

    Três asserções, porque são três as formas de a decisão entrar aqui: uma
    classe com comportamento, uma função que não é wiring, e um `raise`. As
    duas primeiras deixariam a lógica visível no diff; a terceira é a que
    passou despercebida por seis Stages.
    """
    violations: list[str] = []
    alvos = [f for f in src_root.rglob("*.py") if COMPOSITION_ROOT_ANCHOR in posix(f)]

    for py_file in alvos:
        tree = parse(py_file)
        if tree is None:
            continue
        rel = py_file.relative_to(src_root.parent)

        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                if not is_dataclass(node) and node.name not in COMPOSITION_ROOT_CLASS_ALLOWLIST:
                    violations.append(
                        f"CHARTER: {rel}:{node.lineno} — classe '{node.name}' não é "
                        f"@dataclass. O composition root expõe contêiner de "
                        f"dependência, não comportamento (LAYOUT §6)."
                    )
            elif (
                isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
                and node.name not in COMPOSITION_ROOT_FUNCTIONS
            ):
                violations.append(
                    f"CHARTER: {rel}:{node.lineno} — função '{node.name}' fora do "
                    f"charter. As únicas são: "
                    f"{', '.join(sorted(COMPOSITION_ROOT_FUNCTIONS))}."
                )

            if getattr(node, "name", "") in COMPOSITION_ROOT_RAISE_ALLOWLIST:
                continue
            for interno in ast.walk(node):
                if isinstance(interno, ast.Raise):
                    violations.append(
                        f"CHARTER: {rel}:{interno.lineno} — `raise` no composition "
                        f"root. Quem monta o grafo não recusa pedido; a recusa mora "
                        f"no use case ou no adapter que a decide."
                    )

    return violations


def check_dto_behaviour(src_root: Path) -> list[str]:
    """Regra 7 — classe de `application/dtos/` não tem método fora de dunders.

    DTO com comportamento é a porta pela qual a regra de negócio sai do domínio
    sem cruzar nenhuma fronteira de import: o método viaja **dentro** do dado,
    então nenhum contrato de import o vê. `Session.is_active` é o caso tolerado,
    e a allowlist é o que impede que o próximo passe pelo mesmo argumento.
    """
    violations: list[str] = []

    for py_file in sorted(src_root.rglob("*.py")):
        if DTOS_ANCHOR not in posix(py_file):
            continue
        tree = parse(py_file)
        if tree is None:
            continue
        rel = py_file.relative_to(src_root.parent)

        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            for membro in node.body:
                if not isinstance(membro, ast.FunctionDef | ast.AsyncFunctionDef):
                    continue
                if is_dunder(membro.name):
                    continue
                if (node.name, membro.name) in DTO_METHOD_ALLOWLIST:
                    continue
                violations.append(
                    f"DTO: {rel}:{membro.lineno} — '{node.name}.{membro.name}' é "
                    f"comportamento num DTO. O lugar da regra é a entidade de "
                    f"domínio ou o use case (LAYOUT §7)."
                )

    return violations


def check_package_markers(src_root: Path) -> list[str]:
    """Regra 9 — `__init__.py` carrega docstring e nada mais.

    Um `__init__.py` que re-exporta cria um caminho de import que **nenhuma
    âncora de camada alcança**: `from restaurant_hub.features.identity import X`
    não casa com `/domain/`, `/application/` nem `/adapters/`. É a mesma classe
    de ponto cego que M1 fecha, em miniatura — e a mais fácil de abrir, porque
    re-exportar parece cortesia com quem importa.
    """
    violations: list[str] = []

    for py_file in sorted(src_root.rglob("*.py")):
        if PACKAGE_MARKER_ANCHOR not in posix(py_file):
            continue
        tree = parse(py_file)
        if tree is None:
            continue
        rel = py_file.relative_to(src_root.parent)

        for node in tree.body:
            docstring = (
                isinstance(node, ast.Expr)
                and isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, str)
            )
            if not docstring:
                violations.append(
                    f"PACOTE: {rel}:{node.lineno} — marcador de pacote com código "
                    f"({type(node).__name__}). Re-exportar daqui abre um caminho de "
                    f"import que nenhuma regra de camada inspeciona."
                )

    return violations


def check_coverage(src_root: Path) -> list[str]:
    """M1 — nenhum `.py` de `src/` escapa de todas as regras.

    É o verificador que fecha a causa-raiz, e por isso não tem allowlist: um
    arquivo que não casa com regra nenhuma é, por definição, um arquivo que
    nenhum gate leu.
    """
    anchors = coverage_anchors()
    violations: list[str] = []

    for py_file in sorted(src_root.rglob("*.py")):
        file_str = posix(py_file)
        if any(anchor in file_str for anchor in anchors):
            continue
        rel = py_file.relative_to(src_root.parent)
        violations.append(
            f"COBERTURA: {rel} não casa com nenhuma regra deste script. "
            f"Um arquivo que nenhuma regra lê é onde a próxima violação vai "
            f"morar (issue #45, M1) — declare a regra que o governa."
        )

    return violations


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    """Executa todas as verificações e reporta os resultados."""
    parser = argparse.ArgumentParser(description="Valida a estrutura de arquitetura do projeto")
    parser.add_argument(
        "--src",
        default="src/restaurant_hub",
        help="Caminho para o pacote fonte (padrão: src/restaurant_hub)",
    )
    args = parser.parse_args()

    src_root = Path(args.src)
    if not src_root.exists():
        print(f"ERRO: diretório não encontrado: {src_root}")
        return 1

    features_root = src_root / "features"

    print(f"Verificando arquitetura em: {src_root.resolve()}")
    print()

    all_violations: list[str] = [
        *check_coverage(src_root),
        *check_layer_imports(src_root),
        *check_feature_structure(features_root),
        *check_composition_root_charter(src_root),
        *check_dto_behaviour(src_root),
        *check_package_markers(src_root),
    ]

    if all_violations:
        print(f"FALHOU — {len(all_violations)} violação(ões) encontrada(s):\n")
        for v in all_violations:
            print(f"  {v}")
        print()
        return 1

    print("PASSOU — nenhuma violação de arquitetura encontrada.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
