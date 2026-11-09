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
   subcamada irmã da mesma feature (inbound não importa out, out não importa inbound).
4. `restaurant_hub/shared/` não importa de `restaurant_hub.features` (acoplamento inverso).
5. `main.py` não importa feature nenhuma — o entrypoint só conhece a factory.
6. Charter do composition root: só `@dataclass` e só as funções de wiring.
7. Classe de `application/dtos/` não tem comportamento.
8. Cada classe de `application/dtos/results.py` é construída em **um** sítio.
9. `__init__.py` é marcador de pacote — docstring e nada mais.
10. Use case com duas ou mais escritas escreve todas dentro de **uma** unidade de
    trabalho (ADR 2.6.0002 §5), salvo allowlist contável.

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
(todas ancoradas em `/domain/`, `/application/`, `/adapters/inbound/`,
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
import re
import sys
from dataclasses import dataclass
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
    # adapters/inbound não pode importar adapters/out (mesma feature) nem adapters de outra
    (
        "/adapters/inbound/",
        [
            "restaurant_hub.features.*.adapters.out",
        ],
    ),
    # adapters/out não pode importar adapters/inbound (mesma feature) nem adapters de outra
    (
        "/adapters/out/",
        [
            "restaurant_hub.features.*.adapters.inbound",
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
# **contável**. **Está vazia desde a issue #47**, que moveu `_IdentityAccessGuard`
# para `features/staff/adapters/out/identity/local_access_guard.py` (ADR
# 0.0.0016) — o número de classes que decidem acesso dentro do wiring é 0, e é
# preciso uma linha de diff, visível em qualquer revisão, para transformá-lo em 1.
# A estrutura fica: é ela que o teste de não-crescimento cobra.
COMPOSITION_ROOT_CLASS_ALLOWLIST: dict[str, str] = {}

# Funções de módulo toleradas fora do charter — mesma exigência de justificativa.
#
# Vazia desde a issue #47. A única entrada que já teve, `_tenant_id_do_ator`,
# era **a mesma unidade de dívida** que `_IdentityAccessGuard` (helper exclusivo
# dele, chegado pela Stage 3.6 depois de o gate ser escrito) e saiu junto: a
# resolução do tenant omitido (ADR 0.0.0005, cláusula 3) é hoje uma linha
# tipada de `LocalAccessGuard.authorize`.
COMPOSITION_ROOT_FUNCTION_ALLOWLIST: dict[str, str] = {}

# O `raise` é o sintoma mais direto de decisão dentro do wiring: quem monta
# grafo não recusa pedido. Desde a #47 não há nenhum — o `PermissionDeniedError`
# da lei L-AG3 saiu com o tradutor —, e um futuro só seria tolerado pelas mesmas
# entradas, nas mesmas unidades sintáticas. Derivar esta allowlist das outras
# duas é deliberado: são a mesma dívida, e listas independentes permitiriam tirar
# a classe de uma delas deixando o `raise` perdoado pela outra.
COMPOSITION_ROOT_RAISE_ALLOWLIST: dict[str, str] = {
    **COMPOSITION_ROOT_CLASS_ALLOWLIST,
    **COMPOSITION_ROOT_FUNCTION_ALLOWLIST,
}

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
# Regra 8 — um sítio de construção por result (Gate 8 da issue #45)
# ---------------------------------------------------------------------------

RESULTS_ANCHOR = "/application/dtos/results.py"

# A regra vale para **toda** classe declarada num `results.py`, e não só para as
# que terminam em `Result`: `AuthorizedActor` é result de use case e não carrega
# o sufixo, e uma regra por sufixo daria uma saída de uma palavra a quem
# quisesse escapar dela.
EXPECTED_CONSTRUCTION_SITES = 1

# ---------------------------------------------------------------------------
# Regra 9 — marcador de pacote não carrega código
# ---------------------------------------------------------------------------

PACKAGE_MARKER_ANCHOR = "/__init__.py"

# ---------------------------------------------------------------------------
# Regra 11 — a hierarquia de exceções não fala de protocolo (ADR 3.9.0001 §6)
# ---------------------------------------------------------------------------

# Os módulos que **definem** a hierarquia de erro: as duas raízes de `shared` e os
# módulos de erro de domínio e de aplicação de cada bounded context.
ERROR_HIERARCHY_ANCHORS = ("/domain/exceptions/", "/application/errors.py")

# O vocabulário do transporte, sem distinção de caixa. "status" e "borda" ficam de fora
# de propósito: têm uso legítimo no domínio (status de escala; bordas inclusivas de um
# período). As fronteiras não usam `\b`, porque `_` é caractere de palavra e as grafias
# idiomáticas do framework vêm compostas — `exception_handler`, `HTTPException`,
# `Http404`, `HTTP_404_NOT_FOUND`, `__mro__`. Número de status é só `4xx`/`5xx`, sem
# letra, dígito ou ponto colado: `2.3.0003`, `R13` e `600` não casam. Limite conhecido:
# um número de 400 a 599 que não é status (uma quantidade de minutos) também reprova —
# o fallback é estreitar o padrão, nunca uma allowlist.
PROTOCOL_VOCABULARY = re.compile(
    r"(?<![a-z0-9])http"
    r"|fastapi|starlette|handler"
    r"|(?<![a-z0-9])mro(?![a-z0-9])"
    r"|method[- ]resolution order|resolução de métodos"
    r"|(?<![a-z0-9.])[45](?:\d\d|xx)(?![a-z0-9])",
    re.IGNORECASE,
)


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
    anchors[RESULTS_ANCHOR] = "regra 8 — um sítio de construção por result"
    anchors[PACKAGE_MARKER_ANCHOR] = "regra 9 — marcador de pacote"
    anchors[USE_CASES_ANCHOR] = "regra 10 — escrita múltipla só dentro de uma unidade"
    for anchor in ERROR_HIERARCHY_ANCHORS:
        anchors[anchor] = "regra 11 — a hierarquia de exceções não fala de protocolo"
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
                and node.name not in COMPOSITION_ROOT_FUNCTION_ALLOWLIST
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


def check_result_construction_sites(src_root: Path) -> list[str]:
    """Regra 8 — cada classe de `results.py` é construída em exatamente um sítio.

    O modo de falha é o campo novo. Com o result montado campo a campo em N
    lugares, acrescentar um atributo exige N edições idênticas; esquecer uma
    não é erro de tipo quando o campo tem default — é uma resposta a menos, num
    dos N caminhos, servida com status 200.

    Zero sítios também reprova: result que ninguém constrói é DTO morto, e a
    forma de ele ficar assim é justamente a extração feita pela metade.
    """
    declaradas: dict[str, Path] = {}
    for py_file in sorted(src_root.rglob("*.py")):
        if RESULTS_ANCHOR not in posix(py_file):
            continue
        tree = parse(py_file)
        if tree is None:
            continue
        for stmt in tree.body:
            if isinstance(stmt, ast.ClassDef):
                declaradas[stmt.name] = py_file

    sitios: dict[str, list[str]] = {nome: [] for nome in declaradas}
    for py_file in sorted(src_root.rglob("*.py")):
        tree = parse(py_file)
        if tree is None:
            continue
        rel = py_file.relative_to(src_root.parent)
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id in sitios
            ):
                sitios[node.func.id].append(f"{rel}:{node.lineno}")

    violations: list[str] = []
    for nome, encontrados in sorted(sitios.items()):
        if len(encontrados) == EXPECTED_CONSTRUCTION_SITES:
            continue
        onde = ", ".join(encontrados) if encontrados else "nenhum"
        violations.append(
            f"RESULT: '{nome}' é construído em {len(encontrados)} sítio(s) "
            f"({onde}); o esperado é {EXPECTED_CONSTRUCTION_SITES}. Extraia um "
            f"mapeador em {declaradas[nome].name} e chame-o."
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


def error_hierarchy_files(src_root: Path) -> list[Path]:
    """Os arquivos que a regra 11 varre — os que definem a hierarquia de exceções."""
    return [
        py_file
        for py_file in sorted(src_root.rglob("*.py"))
        if any(anchor in posix(py_file) for anchor in ERROR_HIERARCHY_ANCHORS)
    ]


def check_error_hierarchy_protocol(src_root: Path) -> list[str]:
    """Regra 11 — módulo da hierarquia de exceções não menciona o transporte.

    A herança de um erro diz o que ele **é**; o que ele vira para quem chamou é do
    adapter de entrada, num mapa explícito (ADR 3.9.0001). Até a Stage 3.9 a ordem
    das bases de um erro era escolhida para o lookup de handler do framework web, e
    a docstring da raiz definia as classes pelo status — a inversão da Dependency
    Rule escrita no próprio código. A varredura é **textual**, e não por `ast`, de
    propósito: docstring e comentário são exatamente onde a inversão morava.
    """
    violations: list[str] = []

    for py_file in error_hierarchy_files(src_root):
        rel = py_file.relative_to(src_root.parent)
        for numero, linha in enumerate(py_file.read_text(encoding="utf-8").splitlines(), 1):
            achado = PROTOCOL_VOCABULARY.search(linha)
            if achado:
                violations.append(
                    f"PROTOCOLO: {rel}:{numero} — {achado.group(0)!r} num módulo da "
                    f"hierarquia de exceções. O que o erro vira para quem chamou é do "
                    f"adapter de entrada (ADR 3.9.0001); descreva-o lá."
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
# Regra 10 — escrita múltipla só dentro de uma unidade de trabalho (ADR 2.6.0002 §5)
# ---------------------------------------------------------------------------

USE_CASES_ANCHOR = "/application/use_cases/"
PORTS_OUT_ANCHOR = "/application/ports/out/"
REPOSITORY_PORT_SUFFIX = "_repository.py"
UNIT_OF_WORK_PORT = "UnitOfWork"

# Método de port de repositório que NÃO começa com estes prefixos é escrita. A
# classificação por nome é deliberada: é a convenção que os ports já seguem, e o
# teste `test_regra10_o_classificador_bate_com_os_ports_reais` fixa o resultado
# sobre os ports reais — um método novo que fuja da convenção reprova lá.
READ_PREFIXES = ("find_", "exists_", "list_")

# Escritas que atravessam bounded context por gateway — port que não é
# repositório, mas cujo método grava no outro BC. Cada nome é conferido contra o
# port real (entrada que não existe reprova).
GATEWAY_WRITE_METHODS: dict[str, frozenset[str]] = {
    "IdentityGateway": frozenset({"provision_employee_login", "revoke_login_sessions"}),
}

# Use cases tolerados com escrita múltipla fora de unidade, cada um com o motivo.
# A allowlist é contável como a do charter (regra 6): entrada nova reprova até ser
# justificada no teste de não-crescimento, e entrada que já não corresponde a um
# use case que violaria a regra reprova também.
MULTI_WRITE_ALLOWLIST: dict[str, str] = {
    "CreateLoginForEmployeeUseCase": (
        "ADR 2.6.0002 §2 — travessia staff → identity (conta pela fachada, depois o "
        "vínculo em staff); transação entre BCs rejeitada pelo ADR 4.1.0006 Alt. A"
    ),
    "DeactivateEmployeeUseCase": (
        "ADR 2.6.0002 §2 — revoga as sessões em identity antes de gravar o "
        "desligamento em staff (ADR 3.5.0003); transação entre BCs rejeitada"
    ),
}


@dataclass(frozen=True)
class _Escrita:
    linha: int
    alvo: str
    dentro_da_unidade: bool
    em_laco: bool
    seguida_de_raise: bool


@dataclass
class _Varredura:
    escritas: list[_Escrita]
    unidades: list[int]


def _anotacao(no: ast.expr | None) -> str | None:
    if isinstance(no, ast.Name):
        return no.id
    if isinstance(no, ast.Attribute):
        return no.attr
    if isinstance(no, ast.Constant) and isinstance(no.value, str):
        return no.value
    return None


def repository_port_names(src_root: Path) -> set[str]:
    """Classes declaradas em `ports/out/*_repository.py` — derivado, nunca escrito à mão."""
    nomes: set[str] = set()
    for arquivo in src_root.rglob(f"*{REPOSITORY_PORT_SUFFIX}"):
        if PORTS_OUT_ANCHOR not in posix(arquivo):
            continue
        tree = parse(arquivo)
        if tree is not None:
            nomes |= {n.name for n in tree.body if isinstance(n, ast.ClassDef)}
    return nomes


def port_methods(src_root: Path) -> dict[str, set[str]]:
    """Port de saída → nomes dos métodos, para conferir as entradas de gateway."""
    metodos: dict[str, set[str]] = {}
    for arquivo in src_root.rglob("*.py"):
        if PORTS_OUT_ANCHOR not in posix(arquivo):
            continue
        tree = parse(arquivo)
        if tree is None:
            continue
        for classe in (n for n in tree.body if isinstance(n, ast.ClassDef)):
            metodos[classe.name] = {m.name for m in classe.body if isinstance(m, _FUNCOES)}
    return metodos


def is_write(port: str, method: str, repository_ports: set[str]) -> bool:
    """A classificação da regra 10: escrita de repositório ou de gateway."""
    if port in repository_ports:
        return not method.startswith(READ_PREFIXES)
    return method in GATEWAY_WRITE_METHODS.get(port, frozenset())


_FUNCOES = (ast.FunctionDef, ast.AsyncFunctionDef)
_COMPREENSOES = (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)


def _tipos_dos_atributos(classe: ast.ClassDef) -> dict[str, str]:
    """`self._x = x` (ou `self._x: T = x`) no `__init__`, com `x` anotado — atributo → tipo."""
    init = next(
        (m for m in classe.body if isinstance(m, _FUNCOES) and m.name == "__init__"),
        None,
    )
    if init is None:
        return {}
    parametros = {
        a.arg: tipo
        for a in [*init.args.args, *init.args.kwonlyargs]
        if (tipo := _anotacao(a.annotation)) is not None
    }
    tipos: dict[str, str] = {}
    for no in ast.walk(init):
        if isinstance(no, ast.Assign) and len(no.targets) == 1:
            alvo, valor = no.targets[0], no.value
        elif isinstance(no, ast.AnnAssign) and no.value is not None:
            alvo, valor = no.target, no.value
        else:
            continue
        atributo = _atributo_de_self(alvo) if isinstance(alvo, ast.expr) else None
        if atributo is not None and isinstance(valor, ast.Name) and valor.id in parametros:
            tipos[atributo] = parametros[valor.id]
    return tipos


def _atributo_de_self(no: ast.expr) -> str | None:
    if isinstance(no, ast.Attribute) and isinstance(no.value, ast.Name) and no.value.id == "self":
        return no.attr
    return None


def _dentro_de_compreensao(no: ast.AST) -> set[int]:
    """Ids dos nós avaliados a cada iteração de alguma compreensão contida em `no`."""
    ids: set[int] = set()
    for interno in ast.walk(no):
        if isinstance(interno, _COMPREENSOES):
            ids |= {id(n) for n in ast.walk(interno) if n is not interno}
    return ids


class _Varredor:
    """Percorre os métodos de uma classe de use case coletando escritas e unidades.

    Entradas são os métodos públicos; helpers (`self._x()`) entram pelo fecho
    transitivo de quem os chama, no contexto de quem chama (dentro ou fora de
    unidade, em laço ou não). Chamada de público para público não é seguida — o
    chamado já é entrada, e segui-lo contaria a mesma escrita duas vezes.

    Cada **entrada** num bloco de unidade conta: um helper que abre unidade,
    chamado duas vezes, são duas transações; uma unidade dentro de laço conta como
    duas (são N).
    """

    def __init__(self, classe: ast.ClassDef, repository_ports: set[str]) -> None:
        self._metodos = {m.name: m for m in classe.body if isinstance(m, _FUNCOES)}
        self._tipos = _tipos_dos_atributos(classe)
        self._repository_ports = repository_ports

    def varrer(self) -> _Varredura:
        resultado = _Varredura(escritas=[], unidades=[])
        for nome, metodo in self._metodos.items():
            if nome.startswith("_"):
                continue
            self._bloco(metodo.body, resultado, unidade=False, laco=False, pilha=(nome,))
        return resultado

    def _e_unidade(self, item: ast.withitem) -> bool:
        chamada = item.context_expr
        return (
            isinstance(chamada, ast.Call)
            and isinstance(chamada.func, ast.Attribute)
            and chamada.func.attr == "transaction"
            and self._tipos.get(_atributo_de_self(chamada.func.value) or "") == UNIT_OF_WORK_PORT
        )

    def _bloco(
        self,
        corpo: list[ast.stmt],
        resultado: _Varredura,
        *,
        unidade: bool,
        laco: bool,
        pilha: tuple[str, ...],
    ) -> None:
        for i, instrucao in enumerate(corpo):
            seguida_de_raise = i + 1 < len(corpo) and isinstance(corpo[i + 1], ast.Raise)
            self._instrucao(instrucao, resultado, unidade, laco, seguida_de_raise, pilha)

    def _instrucao(  # noqa: PLR0913 — o contexto da varredura é o estado do percurso
        self,
        instrucao: ast.stmt,
        resultado: _Varredura,
        unidade: bool,
        laco: bool,
        seguida_de_raise: bool,
        pilha: tuple[str, ...],
    ) -> None:
        if isinstance(instrucao, ast.With | ast.AsyncWith):
            abre = any(self._e_unidade(item) for item in instrucao.items)
            if abre:
                # Unidade em laço são N transações: conta como duas entradas.
                resultado.unidades.extend([instrucao.lineno] * (2 if laco else 1))
            for item in instrucao.items:
                self._expressao(item.context_expr, resultado, unidade, laco, False, pilha)
            self._bloco(instrucao.body, resultado, unidade=unidade or abre, laco=laco, pilha=pilha)
            return
        if isinstance(instrucao, ast.For | ast.AsyncFor):
            self._expressao(instrucao.iter, resultado, unidade, laco, False, pilha)
            self._bloco(instrucao.body, resultado, unidade=unidade, laco=True, pilha=pilha)
            self._bloco(instrucao.orelse, resultado, unidade=unidade, laco=laco, pilha=pilha)
            return
        if isinstance(instrucao, ast.While):
            # A condição roda a cada volta: escrita nela é escrita em laço.
            self._expressao(instrucao.test, resultado, unidade, True, False, pilha)
            self._bloco(instrucao.body, resultado, unidade=unidade, laco=True, pilha=pilha)
            self._bloco(instrucao.orelse, resultado, unidade=unidade, laco=laco, pilha=pilha)
            return
        if isinstance(instrucao, ast.Match):
            self._expressao(instrucao.subject, resultado, unidade, laco, False, pilha)
            for caso in instrucao.cases:
                self._bloco(caso.body, resultado, unidade=unidade, laco=laco, pilha=pilha)
            return
        blocos = [
            getattr(instrucao, campo)
            for campo in ("body", "orelse", "finalbody")
            if isinstance(getattr(instrucao, campo, None), list)
        ]
        if blocos:
            # As expressões do próprio cabeçalho (o `test` de um `if`, por exemplo)
            # também escrevem: `if not self._tokens.consume(...)` é uma escrita.
            for campo, valor in ast.iter_fields(instrucao):
                if campo not in {"body", "orelse", "finalbody", "handlers"} and isinstance(
                    valor, ast.expr
                ):
                    self._expressao(valor, resultado, unidade, laco, False, pilha)
            for bloco in blocos:
                self._bloco(bloco, resultado, unidade=unidade, laco=laco, pilha=pilha)
            for tratador in getattr(instrucao, "handlers", []):
                self._bloco(tratador.body, resultado, unidade=unidade, laco=laco, pilha=pilha)
            return
        self._expressao(instrucao, resultado, unidade, laco, seguida_de_raise, pilha)

    def _expressao(  # noqa: PLR0913 — idem
        self,
        no: ast.AST,
        resultado: _Varredura,
        unidade: bool,
        laco: bool,
        seguida_de_raise: bool,
        pilha: tuple[str, ...],
    ) -> None:
        em_compreensao = _dentro_de_compreensao(no)
        for interno in ast.walk(no):
            if not (isinstance(interno, ast.Call) and isinstance(interno.func, ast.Attribute)):
                continue
            laco_aqui = laco or id(interno) in em_compreensao
            metodo = interno.func.attr
            dono = interno.func.value
            atributo = _atributo_de_self(dono)
            if isinstance(dono, ast.Name) and dono.id == "self" and metodo in self._metodos:
                if metodo.startswith("_") and metodo not in pilha:
                    self._bloco(
                        self._metodos[metodo].body,
                        resultado,
                        unidade=unidade,
                        laco=laco_aqui,
                        pilha=(*pilha, metodo),
                    )
                continue
            if atributo is None:
                continue
            tipo = self._tipos.get(atributo)
            if tipo is not None and is_write(tipo, metodo, self._repository_ports):
                resultado.escritas.append(
                    _Escrita(
                        linha=interno.lineno,
                        alvo=f"self.{atributo}.{metodo}",
                        dentro_da_unidade=unidade,
                        em_laco=laco_aqui,
                        seguida_de_raise=seguida_de_raise,
                    )
                )


def _violacao_de_escrita_multipla(varredura: _Varredura) -> str | None:
    """Motivo da violação, ou `None` — a regra do ADR 2.6.0002 §5, literal."""
    total = sum(2 if e.em_laco else 1 for e in varredura.escritas)
    if total < 2:  # noqa: PLR2004 — "duas ou mais escritas" é o enunciado da regra
        return None
    if len(varredura.unidades) > 1:
        return f"{len(varredura.unidades)} blocos de unidade — são transações distintas"
    fora = [e for e in varredura.escritas if not e.dentro_da_unidade and not e.seguida_de_raise]
    if fora:
        lista = ", ".join(f"{e.alvo} (linha {e.linha})" for e in fora)
        return f"{total} escritas e estas fora de unidade: {lista}"
    return None


def scan_multi_write_use_cases(src_root: Path) -> dict[str, tuple[str, int, str]]:
    """Use case → (arquivo, linha, motivo) para cada classe que viola a regra 10."""
    repository_ports = repository_port_names(src_root)
    achados: dict[str, tuple[str, int, str]] = {}
    for arquivo in sorted(src_root.rglob("*.py")):
        if USE_CASES_ANCHOR not in posix(arquivo):
            continue
        tree = parse(arquivo)
        if tree is None:
            continue
        for classe in (n for n in tree.body if isinstance(n, ast.ClassDef)):
            motivo = _violacao_de_escrita_multipla(_Varredor(classe, repository_ports).varrer())
            if motivo is not None:
                achados[classe.name] = (
                    str(arquivo.relative_to(src_root.parent)),
                    classe.lineno,
                    motivo,
                )
    return achados


def check_multi_write_unit_of_work(src_root: Path) -> list[str]:
    """Regra 10 — use case que escreve duas vezes escreve dentro de **uma** unidade.

    A prova do que ela fecha está no ADR 2.6.0002 §5: sem ela, mover o `consume`
    de `set_password_with_token` para fora da unidade, partir a unidade em duas
    ou acrescentar uma escrita nova fora dela deixaria a suíte verde e a
    atomicidade perdida. A allowlist só aceita o que o ADR justifica — hoje, as
    duas travessias de staff para identity.
    """
    violacoes: list[str] = []
    achados = scan_multi_write_use_cases(src_root)
    for classe, (arquivo, linha, motivo) in sorted(achados.items()):
        if classe in MULTI_WRITE_ALLOWLIST:
            continue
        violacoes.append(
            f"ESCRITA MÚLTIPLA: {arquivo}:{linha} — '{classe}': {motivo}. Abra uma "
            f"unidade de trabalho em volta das escritas (ADR 2.6.0002 §5)."
        )
    for classe in sorted(set(MULTI_WRITE_ALLOWLIST) - set(achados)):
        violacoes.append(
            f"ESCRITA MÚLTIPLA: '{classe}' está na allowlist mas não viola mais a regra "
            f"10 — tire a entrada (allowlist morta documenta dívida já paga)."
        )
    metodos = port_methods(src_root)
    for port, nomes in sorted(GATEWAY_WRITE_METHODS.items()):
        for nome in sorted(nomes - metodos.get(port, set())):
            violacoes.append(
                f"ESCRITA MÚLTIPLA: GATEWAY_WRITE_METHODS declara '{port}.{nome}', que não "
                f"existe em ports/out — a classificação de escrita está desatualizada."
            )
    return violacoes


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
        *check_result_construction_sites(src_root),
        *check_package_markers(src_root),
        *check_multi_write_unit_of_work(src_root),
        *check_error_hierarchy_protocol(src_root),
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
