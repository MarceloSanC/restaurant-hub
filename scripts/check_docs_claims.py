"""Guard: todo caminho que o `docs/LAYOUT.md` §2 desenha existe no repositório.

Uso:
    python scripts/check_docs_claims.py
    python scripts/check_docs_claims.py --repo .

Gate 5 da issue #45. Ligado em `make docs-check`.

---

**O que é uma "claim".** O bloco de árvore da §2 não ilustra: ele **afirma**.
Cada linha diz "este caminho existe e é aqui que esta coisa mora", e é a partir
dele que se decide onde um arquivo novo vai. Uma linha falsa não é imprecisão de
documento — é uma instrução errada dada a quem for criar o próximo arquivo, e
não há erro de compilação que a corrija.

`application/ports/in/` foi exatamente isso: seis Stages de documento afirmando
um diretório que nunca existiu, e mais duas seções inteiras do LAYOUT (§5 e §8)
escritas para explicar como contornar a keyword `in` num pacote que ninguém
tinha. O gate é o que impede a terceira.

**`<feature>` é template, e a claim correspondente é existencial.** A §2 desenha
UMA feature genérica; ela não afirma que todo bounded context tem toda pasta.
`staff` legitimamente não tinha `adapters/inbound/` até a Stage 3.6, e cobrar a
existência em **todas** as features transformaria o gate num gerador de pastas
vazias — o oposto do que ele existe para fazer. A claim é: *pelo menos uma*
feature tem este caminho. Um caminho que não existe em feature nenhuma é uma
promessa que o repositório inteiro desmente, e é essa que reprova.

**`[planejado]` é a válvula, e ela é cobrada nos dois sentidos.** Um caminho
anotado é uma promessa declarada como futura — legítima. Mas caminho anotado que
**já existe** também reprova: a anotação vira mentira ao contrário, e uma
válvula que ninguém fecha deixa de significar coisa alguma.

Códigos de saída:
  0  todas as claims conferem
  1  há claim falsa (caminho + motivo impressos)
  2  não foi possível localizar o bloco de árvore (fail closed)
"""

import argparse
import re
import sys
from pathlib import Path

SECAO = "## 2. Estrutura de Pastas"

# Os traços de desenho da árvore. Cada nível ocupa exatamente 4 colunas —
# `│   `, `├── `, `└── ` ou 4 espaços.
_TRACOS = " \t│├└─"
_LARGURA_DO_NIVEL = 4
_LINHA = re.compile(rf"^([{_TRACOS}]*)([^{_TRACOS}].*)$")

# Comentário de fim de linha: dois espaços ou mais, depois `#`. O limiar de dois
# espaços evita cortar um nome de arquivo que contenha `#`.
_COMENTARIO = re.compile(r"\s{2,}#(.*)$")

# Anotação que marca a claim como futura. Fica no comentário da linha, onde quem
# lê a árvore a encontra junto da promessa que ela qualifica.
ANOTACAO_DE_PLANEJADO = "[planejado]"

# Placeholders da árvore. `<feature>` é o bounded context; `<entity>` é o
# agregado dentro dele. Os dois viram varredura, nunca literal.
PLACEHOLDER_DE_FEATURE = "<feature>"
PLACEHOLDER_DE_ENTIDADE = "<entity>"

# Onde as features vivem, para expandir `<feature>`.
RAIZ_DAS_FEATURES = Path("src") / "restaurant_hub" / "features"


class Claim:
    """Um caminho afirmado pela árvore, com a anotação que o qualifica."""

    def __init__(self, caminho: str, *, planejado: bool, linha: int) -> None:
        self.caminho = caminho
        self.planejado = planejado
        self.linha = linha

    def __repr__(self) -> str:
        return f"Claim({self.caminho!r}, planejado={self.planejado})"


def bloco_da_arvore(layout: Path) -> str | None:
    """O conteúdo da primeira cerca de código depois do título da §2."""
    texto = layout.read_text(encoding="utf-8-sig")
    if SECAO not in texto:
        return None
    depois = texto.split(SECAO, 1)[1]
    partes = depois.split("```")
    minimo_de_partes = 2
    return partes[1] if len(partes) >= minimo_de_partes else None


def claims(bloco: str) -> list[Claim]:
    """Reconstrói os caminhos da árvore a partir da indentação.

    A profundidade sai do número de colunas de traço, e uma pilha guarda o
    ancestral de cada nível. É o que transforma um desenho em caminhos
    verificáveis — sem isso, cada linha seria só um nome solto.
    """
    encontrados: list[Claim] = []
    pilha: list[str] = []

    for numero, linha in enumerate(bloco.splitlines(), start=1):
        if not linha.strip(_TRACOS):
            continue

        comentario = _COMENTARIO.search(linha)
        sem_comentario = _COMENTARIO.sub("", linha).rstrip()
        casou = _LINHA.match(sem_comentario)
        if casou is None:
            continue

        prefixo, nome = casou.group(1), casou.group(2)
        profundidade = len(prefixo) // _LARGURA_DO_NIVEL
        pilha = pilha[:profundidade]
        pilha.append(nome.rstrip("/"))

        planejado = ANOTACAO_DE_PLANEJADO in (comentario.group(1) if comentario else "")
        encontrados.append(Claim("/".join(pilha), planejado=planejado, linha=numero))

    return encontrados


def features(repo_root: Path) -> list[str]:
    """Os bounded contexts que existem, para expandir `<feature>`."""
    raiz = repo_root / RAIZ_DAS_FEATURES
    if not raiz.exists():
        return []
    return sorted(
        pasta.name
        for pasta in raiz.iterdir()
        if pasta.is_dir() and not pasta.name.startswith(("_", "."))
    )


def resolve(repo_root: Path, caminho: str, bounded_contexts: list[str]) -> bool:
    """True se o caminho existe — expandindo `<feature>` e `<entity>`.

    Para um caminho com `<feature>`, a claim é **existencial**: basta um
    bounded context tê-lo. Ver a docstring do módulo para o porquê.
    """
    candidatos = (
        [caminho.replace(PLACEHOLDER_DE_FEATURE, bc) for bc in bounded_contexts]
        if PLACEHOLDER_DE_FEATURE in caminho
        else [caminho]
    )

    for candidato in candidatos:
        if PLACEHOLDER_DE_ENTIDADE in candidato:
            padrao = candidato.replace(PLACEHOLDER_DE_ENTIDADE, "*")
            if any(repo_root.glob(padrao)):
                return True
        elif (repo_root / candidato).exists():
            return True

    return False


def claims_falsas(repo_root: Path) -> list[str]:
    """As claims da §2 que o repositório desmente, nos dois sentidos."""
    layout = repo_root / "docs" / "LAYOUT.md"
    if not layout.exists():
        return [f"FATAL: {layout} não existe"]

    bloco = bloco_da_arvore(layout)
    if bloco is None:
        return [f"FATAL: bloco de árvore não encontrado sob '{SECAO}' em {layout.name}"]

    bounded_contexts = features(repo_root)
    problemas: list[str] = []

    for claim in claims(bloco):
        existe = resolve(repo_root, claim.caminho, bounded_contexts)

        if not existe and not claim.planejado:
            problemas.append(
                f"AUSENTE: LAYOUT.md §2 (linha {claim.linha} do bloco) desenha "
                f"'{claim.caminho}', que não existe. A árvore não ilustra, ela "
                f"afirma: é dela que sai a decisão de onde criar o arquivo "
                f"seguinte. Crie o caminho, remova a linha, ou anote-a com "
                f"'{ANOTACAO_DE_PLANEJADO}'."
            )
        elif existe and claim.planejado:
            problemas.append(
                f"ANOTAÇÃO MORTA: LAYOUT.md §2 (linha {claim.linha} do bloco) "
                f"marca '{claim.caminho}' como {ANOTACAO_DE_PLANEJADO}, e o "
                f"caminho já existe. Remova a anotação — válvula que ninguém "
                f"fecha deixa de significar alguma coisa."
            )

    return problemas


def main() -> int:
    """Verifica as claims da §2 do LAYOUT contra o repositório."""
    parser = argparse.ArgumentParser(
        description="Reprova caminho afirmado pelo LAYOUT.md §2 que não existe (issue #45, Gate 5)"
    )
    parser.add_argument("--repo", default=".", help="Raiz do repositório (padrão: .)")
    args = parser.parse_args()

    repo_root = Path(args.repo).resolve()
    problemas = claims_falsas(repo_root)

    if problemas and problemas[0].startswith("FATAL:"):
        print(f"check_docs_claims: {problemas[0]}", file=sys.stderr)
        return 2

    if problemas:
        print(f"check_docs_claims: {len(problemas)} claim(s) falsa(s):\n", file=sys.stderr)
        for problema in problemas:
            print(f"  {problema}", file=sys.stderr)
        return 1

    print("check_docs_claims: a árvore do LAYOUT §2 confere com o repositório.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
