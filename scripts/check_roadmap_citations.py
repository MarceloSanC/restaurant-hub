"""Guard: doc cita o `roadmap.md` por âncora estável, nunca por número de linha.

Uso:
    python scripts/check_roadmap_citations.py
    python scripts/check_roadmap_citations.py --repo .

Issue #79, ADR 0.0.0012. Ligado em `make docs-check`.

---

**Por que número de linha não serve.** O roadmap cresce no meio: cada issue nova
ganha uma linha na Tabela de Issues, que fica *acima* de todos os blocos de Step,
e cada Stage promovida ganha um bloco antes das seguintes. Uma citação
`` `roadmap.md` 1362 `` passa a apontar para outra coisa no PR seguinte, sem
erro em lugar nenhum. Três remapeamentos em massa (Stages 4.1, 3.7 e 3.8)
consertaram o sintoma e o deslocamento voltou no PR seguinte — a #79 nasceu
porque o de +65 da Stage 2.6 ficou de fora.

**A forma estável** (CONVENTIONS §5, "Citação ao roadmap"):

    `roadmap.md` §Stage 4.1 › "Descrição humana", `definition_of_done`
    `roadmap.md` §Step 4 › nota 2026-09-14
    `roadmap.md` §"Tabela de Stages" › `4.1-scheduling-domain`

Seção: `§Stage N.M`, `§Step N` ou `§"<título de seção do roadmap>"`. Rótulo,
depois de ` › ` e separado por vírgula: `"<texto em negrito>"`,
`` `<literal>` `` (chave YAML, célula, aresta do grafo), `nota AAAA-MM-DD` ou
`#N` (linha da Tabela de Issues).

**As duas regras.**

1. *Sem número de linha.* Depois de uma referência ao roadmap, no mesmo trecho
   de citação (até `;`, `|`, fim de frase ou outra fonte), não pode sobrar
   número de 2 a 4 dígitos que não seja de Stage/Step, de issue, de data ou de
   texto entre aspas.
2. *Âncora resolve.* Toda `§Stage N.M` e `§Step N` tem de existir no roadmap,
   e todo rótulo depois de ` › ` tem de existir dentro da seção. Seção renomeada
   ou rótulo apagado quebra aqui, em vez de apontar em silêncio para o vizinho.

**Fora do escopo:** o próprio `roadmap.md` e a §7 dos `technical.md` (do título
`## 7.` ao fim) — a §7 é registro histórico e conta remapeamentos passados por
número ("1481→1517"); reescrevê-los apagaria o fato que registram.

Códigos de saída:
  0  nenhuma citação por linha e todas as âncoras resolvem
  1  há citação por linha ou âncora que não resolve (arquivo:linha + motivo)
  2  `docs/roadmap.md` não existe (fail closed)
"""

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROADMAP = Path("docs") / "roadmap.md"

# Onde moram os docs que citam o roadmap. A raiz entra só no primeiro nível
# (CLAUDE.md, README.md); `.venv`, `htmlcov` e afins nunca são varridos.
PASTAS_VARRIDAS = ("docs", ".claude", ".github")

# Início da §7 de um technical.md — dali ao fim é registro histórico.
_SECAO_7 = re.compile(r"^## 7\.", re.MULTILINE)

# --- Regra 1: número de linha -------------------------------------------------

# Uma referência ao roadmap: a palavra `roadmap` (com ou sem `.md`), seguida
# opcionalmente da crase de fechamento e do alvo de um link markdown.
_REF_ROADMAP = re.compile(r"roadmap(?:\.md)?`?(?:\]\([^)\s]*\))?", re.IGNORECASE)

# Onde termina o trecho de citação que começa numa referência ao roadmap: fim de
# frase, célula de tabela, parágrafo ou outra fonte. `;` não termina — é o
# separador de uma lista de âncoras, e um número escondido depois dele
# (`§Step 4; Step 5 (1577)`) ainda é linha do roadmap.
_FIM_DO_TRECHO = re.compile(
    r"\||\.(?=[\s*_)\]]|$)|\n\s*\n"
    r"|`?[\w./-]+\.(?:md|py|toml|yml|yaml|ini|cfg)`?|`\.[\w-]+`"
    r"|\bADRs?\s+\d|\boverview\b|\bCLT\b"
)
_MAX_TRECHO = 160

# Coisas que têm dígitos e não são número de linha. Removidas do trecho antes de
# procurar o número.
_NEUTROS = (
    re.compile(r'\*?"[^"\n]*"\*?'),  # texto citado entre aspas
    re.compile(r"\*[^*\n]+\*"),  # ênfase / citação em itálico
    re.compile(r"`[^`\n]*`"),  # literal
    re.compile(r"§\S*"),  # âncora de seção
    re.compile(r"\b(?:Stages?|Steps?)\s+\d+(?:\.\d+)?(?:\s*[–/-]\s*\d+(?:\.\d+)?)?", re.IGNORECASE),
    re.compile(r"\bnota\s+\d{4}-\d{2}-\d{2}"),
    re.compile(r"\d{4}-\d{2}(?:-\d{2})?"),  # data
    re.compile(r"#\d+"),  # issue / PR
    re.compile(r"https?://\S+"),  # URL
    re.compile(r"task-\d+"),  # marca de Task de commit
    re.compile(r"\bROADMAP-\d+"),
    re.compile(r"\d+(?:\.\d+)+(?:\s*[–-]\s*\d+)?"),  # número de Stage/versão/ADR, com faixa
)
# Número de linha: 2 a 4 dígitos fechando a citação — seguido de pontuação, fim,
# outra faixa/lista ou parêntese. Número seguido de palavra ("16 use cases",
# "30 seconds") é quantidade, não linha.
_NUMERO_DE_LINHA = re.compile(r"(?<![\w])\d{2,4}(?=\s*(?:[,;:)/–\]-]|$|\(|(?:e|and)\s+\d))")

# Número logo depois da referência (`roadmap.md` 1362 pede…, `roadmap.md:366`,
# `roadmap` (linha 366)) é linha sempre, venha o que vier depois.
_NUMERO_IMEDIATO = re.compile(
    r"^\s*:?\s*\(?\s*(?:(?:linhas?|lines?|l\.)\s*)?\d{2,4}\b", re.IGNORECASE
)

# Fragmento de linha do GitHub (`roadmap.md#L1362`, `[roadmap](../roadmap.md#L1362)`)
# é número de linha com outra roupa.
_FRAGMENTO_DE_LINHA = re.compile(r"roadmap\.md#L\d", re.IGNORECASE)

# --- Regra 2: âncora ----------------------------------------------------------

_ROTULO = r'(?:"[^"\n]+"|`[^`\n]+`|nota \d{4}-\d{2}-\d{2}|#\d+)'
_ANCORA = re.compile(
    r'§(?P<secao>Stage \d+\.\d+|Step \d+|"[^"\n]+")'
    rf"(?: › (?P<rotulos>{_ROTULO}(?:, {_ROTULO})*))?"
)
_ROTULO_ITEM = re.compile(_ROTULO)
_TITULO = re.compile(r"^(#{2,4}) (.+?)\s*$")


@dataclass(frozen=True)
class Secao:
    """Uma seção do roadmap: título, nível e corpo até o próximo título igual ou maior."""

    titulo: str
    nivel: int
    corpo: str


def secoes(roadmap: str) -> list[Secao]:
    """Quebra o roadmap nas seções de nível 2 a 4."""
    linhas = roadmap.splitlines()
    titulos = [
        (i, len(m.group(1)), m.group(2)) for i, ln in enumerate(linhas) if (m := _TITULO.match(ln))
    ]
    resultado: list[Secao] = []
    for k, (i, nivel, titulo) in enumerate(titulos):
        fim = len(linhas)
        for j, nivel_seguinte, _ in titulos[k + 1 :]:
            if nivel_seguinte <= nivel:
                fim = j
                break
        resultado.append(Secao(titulo, nivel, "\n".join(linhas[i + 1 : fim])))
    return resultado


def acha_secao(todas: list[Secao], nome: str) -> Secao | None:
    """`Stage N.M`/`Step N` casam pelo prefixo do título; `"X"` pelo título inteiro ou prefixo."""
    if nome.startswith('"'):
        alvo = nome.strip('"')
        for s in todas:
            if s.titulo == alvo or s.titulo.startswith(alvo + " "):
                return s
        return None
    for s in todas:
        if s.titulo.startswith(nome + " —"):
            return s
    return None


def rotulo_resolve(secao: Secao, rotulo: str) -> bool:
    """O rótulo existe no corpo da seção, na forma que o seu tipo exige."""
    if rotulo.startswith('"'):
        return f"**{rotulo.strip(chr(34))}" in secao.corpo
    if rotulo.startswith("`"):
        return rotulo.strip("`") in secao.corpo
    if rotulo.startswith("nota "):
        return f"**Nota ({rotulo[5:]}" in secao.corpo
    numero = rotulo[1:]
    return re.search(rf"^\| \[?#{numero}\b", secao.corpo, re.MULTILINE) is not None


def _linha_de(texto: str, pos: int) -> int:
    return texto.count("\n", 0, pos) + 1


def citacoes_por_linha(texto: str) -> list[tuple[int, str]]:
    """(linha, trecho) de cada citação ao roadmap que carrega número de linha."""
    achados: list[tuple[int, str]] = []
    for ref in _REF_ROADMAP.finditer(texto):
        resto = texto[ref.end() : ref.end() + _MAX_TRECHO]
        fim = _FIM_DO_TRECHO.search(resto)
        trecho = resto[: fim.start()] if fim else resto
        limpo = trecho
        for neutro in _NEUTROS:
            limpo = neutro.sub(" ", limpo)
        # O número imediato é procurado no `resto`, não no `trecho`: o `.` de
        # `(l. 1362)` encerraria o trecho antes do número.
        if (
            _NUMERO_IMEDIATO.match(resto)
            or _NUMERO_DE_LINHA.search(limpo)
            or _FRAGMENTO_DE_LINHA.search(texto, ref.start(), ref.end() + len("#L0"))
        ):
            achados.append(
                (_linha_de(texto, ref.start()), (ref.group(0) + trecho).replace("\n", " ").strip())
            )
    return achados


def ancoras_quebradas(texto: str, todas: list[Secao]) -> list[tuple[int, str]]:
    """(linha, motivo) de cada âncora ao roadmap que não resolve."""
    problemas: list[tuple[int, str]] = []
    for m in _ANCORA.finditer(texto):
        nome, rotulos = m.group("secao"), m.group("rotulos")
        aspas = nome.startswith('"')
        if aspas and not rotulos and not re.match(r'"(?:Stage|Step) \d', nome):
            # `§"X"` sem rótulo pode ser seção de outro doc — não é âncora ao roadmap.
            continue
        secao = acha_secao(todas, nome)
        linha = _linha_de(texto, m.start())
        if secao is None:
            problemas.append((linha, f"seção §{nome} não existe no roadmap"))
            continue
        for rotulo in _ROTULO_ITEM.findall(rotulos or ""):
            if not rotulo_resolve(secao, rotulo):
                problemas.append((linha, f"rótulo {rotulo} não existe em §{nome}"))
    return problemas


def texto_varrido(caminho: Path) -> str:
    """O texto sujeito ao gate: o arquivo inteiro, menos a §7 de um technical.md."""
    texto = caminho.read_text(encoding="utf-8-sig")
    if caminho.name == "technical.md" and (m := _SECAO_7.search(texto)):
        return texto[: m.start()]
    return texto


def arquivos(repo_root: Path) -> list[Path]:
    """Os .md que podem citar o roadmap, menos o próprio roadmap."""
    candidatos = list(repo_root.glob("*.md"))
    for pasta in PASTAS_VARRIDAS:
        candidatos.extend((repo_root / pasta).rglob("*.md"))
    roadmap = (repo_root / ROADMAP).resolve()
    return sorted(p for p in candidatos if p.resolve() != roadmap)


def problemas(repo_root: Path) -> list[str]:
    """Todas as violações das duas regras, como `arquivo:linha: motivo`."""
    caminho_roadmap = repo_root / ROADMAP
    if not caminho_roadmap.exists():
        return [f"FATAL: {ROADMAP.as_posix()} não existe"]
    todas = secoes(caminho_roadmap.read_text(encoding="utf-8-sig"))

    saida: list[str] = []
    for arquivo in arquivos(repo_root):
        texto = texto_varrido(arquivo)
        rel = arquivo.relative_to(repo_root).as_posix()
        for linha, trecho in citacoes_por_linha(texto):
            saida.append(f"{rel}:{linha}: citação por número de linha ao roadmap: {trecho[:100]!r}")
        for linha, motivo in ancoras_quebradas(texto, todas):
            saida.append(f"{rel}:{linha}: {motivo}")
    return saida


def main() -> int:
    """Varre os docs e reprova citação por linha ou âncora quebrada ao roadmap."""
    parser = argparse.ArgumentParser(
        description=(
            "Reprova citação ao roadmap.md por número de linha ou por âncora que não resolve"
            " (issue #79)"
        )
    )
    parser.add_argument("--repo", default=".", help="Raiz do repositório (padrão: .)")
    args = parser.parse_args()

    achados = problemas(Path(args.repo).resolve())
    if achados and achados[0].startswith("FATAL:"):
        print(f"check_roadmap_citations: {achados[0]}", file=sys.stderr)
        return 2
    if achados:
        print(
            f"check_roadmap_citations: {len(achados)} problema(s). Cite o roadmap por âncora "
            '(`roadmap.md` §Stage N.M › "Rótulo") — CONVENTIONS §5, ADR 0.0.0012:\n',
            file=sys.stderr,
        )
        for achado in achados:
            print(f"  {achado}", file=sys.stderr)
        return 1
    print("check_roadmap_citations: toda citação ao roadmap é por âncora, e todas resolvem.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
