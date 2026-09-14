"""Guard: todo nome público de `shared/` tem pelo menos um uso em `src/`.

Uso:
    python scripts/check_dead_shared.py
    python scripts/check_dead_shared.py --src src/restaurant_hub

Gate 7 da issue #45. Ligado em `make layout-check`.

---

**Por que `shared/domain/` e `shared/application/`, e não o repositório todo.**

Este não é um detector de código morto genérico — é um detector do modo de falha
específico de um pacote **transversal**. Um símbolo sem uso dentro de uma feature
é dívida local: quem lê a feature vê o arquivo inteiro e o encontra. Um símbolo
sem uso em `shared/` é diferente em três aspectos, e os três se realizaram na
auditoria de 2026-08-29:

1. **Ele parece contrato.** `Pagination` estava em `shared/domain/value_objects/`
   e o próprio LAYOUT §4 o citava como exemplo do que mora em `shared/` — isto é,
   como código que 2+ features usam. Nenhuma usava. O documento afirmava a
   reutilização que justificava a promoção, e a afirmação nunca foi medida.
2. **Ele nunca é exercitado, e ainda assim é lido por todos.** `Pagination`
   levantava `ValueError` cru, não `DomainError`: alcançado pelo HTTP produziria
   **500**, que é exatamente o modo de falha que o ADR 2.2.0003 existe para
   evitar. A primeira feature a usá-lo herdaria o defeito sem revisar o arquivo,
   porque "está em shared, então já foi decidido".
3. **Ele não cria aresta de import**, logo nem `lint-imports` nem
   `check_layout.py` o veem. Código morto é a única violação de arquitetura que
   se caracteriza pela **ausência** de import, e por isso precisa de um detector
   próprio.

`shared/infrastructure/` fica **de fora** de propósito: ali moram implementações
alcançadas por injeção (`SystemClock`, `Uuid4Generator`, `ConsoleSender`), e o
único módulo que as nomeia é o `composition_root` — que este script conta como
uso, mas cuja ausência de menção seria um falso positivo previsível assim que a
configuração passar a escolher o adapter por string.

**Uso = o nome aparecer como identificador em outro módulo de `src/`.** É a
mesma técnica do CA12 de `tests/unit/features/staff/test_bc_independence.py`:
`ast` em vez de `grep`, para que menção dentro de docstring **não** conte. A
distinção é o ponto — `Pagination` era citado em prosa em três documentos e usado
em nenhum lugar, e um detector textual teria confirmado a citação como uso.

Códigos de saída:
  0  nenhum nome público sem uso
  1  há nome público sem uso (arquivo + nome impressos)
"""

import argparse
import ast
import sys
from pathlib import Path

# Os dois pacotes de `shared/` cujo conteúdo é contrato, não implementação.
PACOTES_VIGIADOS = ("/shared/domain/", "/shared/application/")

# `__init__.py` é marcador de pacote (regra 9 do check_layout) — não declara nome
# público nenhum, e varrê-lo só produziria ruído.
MARCADOR_DE_PACOTE = "__init__.py"


def posix(caminho: Path) -> str:
    """Caminho normalizado — os padrões são escritos com `/` mesmo no Windows."""
    return caminho.as_posix().replace("\\", "/")


def parse(caminho: Path) -> ast.Module | None:
    """Árvore do arquivo, ou None se ele não for Python analisável."""
    try:
        return ast.parse(caminho.read_text(encoding="utf-8"), filename=str(caminho))
    except SyntaxError:
        return None


def nomes_publicos(arvore: ast.Module) -> set[str]:
    """Classes, funções e constantes de módulo que não começam com `_`.

    Só o nível do módulo: método de `Protocol` e atributo de `dataclass` não são
    superfície independente — eles existem *porque* o tipo que os contém existe,
    e cobrá-los separadamente reprovaria `Clock.now` no dia em que alguém
    chamasse o port por variável.
    """
    encontrados: set[str] = set()
    for no in arvore.body:
        e_definicao = isinstance(no, ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef)
        if e_definicao and not no.name.startswith("_"):
            encontrados.add(no.name)
        elif isinstance(no, ast.Assign):
            encontrados.update(
                alvo.id
                for alvo in no.targets
                if isinstance(alvo, ast.Name) and not alvo.id.startswith("_")
            )
        elif (
            isinstance(no, ast.AnnAssign)
            and isinstance(no.target, ast.Name)
            and not no.target.id.startswith("_")
        ):
            encontrados.add(no.target.id)
    return encontrados


def identificadores(arvore: ast.Module) -> set[str]:
    """Nomes que o módulo **usa**, em qualquer posição sintática.

    Colhe de onde um identificador pode aparecer sem ser conteúdo de string:
    referência, acesso a atributo, alias de import, anotação e argumento
    nomeado. Texto dentro de docstring **não** conta, e é justamente essa
    exclusão que dá valor ao detector.
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
        elif isinstance(no, ast.arg) or (isinstance(no, ast.keyword) and no.arg is not None):
            nomes.add(no.arg)
    return nomes


def declaracoes(src_root: Path) -> dict[str, Path]:
    """Nome público → módulo de `shared/` que o declara."""
    declarados: dict[str, Path] = {}
    for arquivo in sorted(src_root.rglob("*.py")):
        caminho = posix(arquivo)
        if arquivo.name == MARCADOR_DE_PACOTE:
            continue
        if not any(pacote in caminho for pacote in PACOTES_VIGIADOS):
            continue
        arvore = parse(arquivo)
        if arvore is None:
            continue
        for nome in nomes_publicos(arvore):
            declarados[nome] = arquivo
    return declarados


def usos_por_arquivo(src_root: Path) -> dict[Path, set[str]]:
    """Identificadores usados por cada módulo de `src/`, numa passada só.

    O índice é por arquivo — e não um conjunto único — porque cada nome precisa
    ser conferido contra `src/` **menos o módulo que o declara**: toda
    declaração se auto-menciona, e a própria `class Pagination` põe
    `Pagination` na varredura. Somar tudo faria todo nome público parecer usado,
    e o gate seria vacuamente verde.

    Uma passada, e não uma por nome: com a varredura repetida por símbolo, o
    custo cresce com o produto de nomes por arquivos — e é justamente o pacote
    `shared/`, que toda feature lê, quem cresce nos dois eixos.
    """
    indice: dict[Path, set[str]] = {}
    for arquivo in sorted(src_root.rglob("*.py")):
        arvore = parse(arquivo)
        if arvore is not None:
            indice[arquivo] = identificadores(arvore)
    return indice


def nomes_mortos(src_root: Path) -> list[str]:
    """Nomes públicos de `shared/` que nenhum outro módulo de `src/` usa."""
    declarados = declaracoes(src_root)
    indice = usos_por_arquivo(src_root)
    mortos: list[str] = []

    for nome, arquivo in sorted(declarados.items()):
        usado_fora = any(nome in nomes for outro, nomes in indice.items() if outro != arquivo)
        if usado_fora:
            continue
        rel = arquivo.relative_to(src_root.parent)
        mortos.append(
            f"MORTO: {rel} declara '{nome}', que nenhum módulo de src/ usa. "
            f"Em `shared/` isso não é dívida local: o símbolo parece contrato, "
            f"é lido por todas as features e nunca foi exercitado. Remova-o — "
            f"promoção para shared/ se justifica por consumidor medido, não "
            f"previsto (LAYOUT §4)."
        )

    return mortos


def main() -> int:
    """Varre `shared/` e reporta os nomes públicos sem uso."""
    parser = argparse.ArgumentParser(
        description="Reprova nome público de shared/ sem uso em src/ (issue #45, Gate 7)"
    )
    parser.add_argument(
        "--src",
        default="src/restaurant_hub",
        help="Caminho para o pacote fonte (padrão: src/restaurant_hub)",
    )
    args = parser.parse_args()

    src_root = Path(args.src)
    if not src_root.exists():
        print(f"ERRO: diretório não encontrado: {src_root}", file=sys.stderr)
        return 1

    mortos = nomes_mortos(src_root)
    if mortos:
        print(f"check_dead_shared: {len(mortos)} nome(s) público(s) sem uso:\n", file=sys.stderr)
        for morto in mortos:
            print(f"  {morto}", file=sys.stderr)
        return 1

    print("check_dead_shared: nenhum nome público de shared/ sem uso.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
