"""Guard: doc cita um doc de domínio (`docs/domain/**`) por âncora estável, nunca por linha.

Uso:
    python scripts/check_domain_citations.py
    python scripts/check_domain_citations.py --repo .

Issue #116, ADR 0.0.0017. Ligado em `make docs-check`. Irmão de
`check_roadmap_citations.py` (issue #79, ADR 0.0.0012): a mesma ideia, com a
gramática de âncora dos docs de domínio.

---

**Por que número de linha não serve.** Um doc de domínio cresce no meio — nota
datada numa seção, lacuna fechada reescrita no lugar, ADR novo no `references`
do frontmatter. Uma citação `` `shift-scheduling.md` 171 `` passa a apontar para
outra linha sem erro em lugar nenhum. Foi o que segurou a válvula de `references`
do `shift-scheduling.md` (ADR 0.0.0015 §Decision 5): 16 linhas novas no
frontmatter deslocariam as citações por linha de três ADRs `accepted` e do
concept da 4.1.

**A forma estável** (CONVENTIONS §5, "Citação a doc de domínio"):

    `shift-scheduling.md` §3.4 › "não ocupa duas vagas da mesma demanda"
    `workforce.md` §3.1, §3.8
    `shift-scheduling.md` §6 › "Schedule como raiz do agregado"

Referência: o nome do arquivo de um doc de `docs/domain/` (`<nome>.md`, com ou
sem crase/link, ou o caminho), ou o nome sem `.md` seguido de ` §` (`workforce §3.7`).
Seção: `§N`, `§N.M`, `§N.M.K` (título numerado do doc) ou `§"<título>"`. Rótulo,
depois de ` › ` e separado por vírgula: `"<trecho>"` — texto da seção, comparado
sem `*` nem crase e com o espaço normalizado — ou `` `<literal>` `` (cru).

**As duas regras.**

1. *Sem número de linha.* Depois de uma referência a um doc de domínio, no mesmo
   trecho de citação (até `|`, fim de frase, parágrafo ou outra fonte), não pode
   sobrar número de 2 a 4 dígitos que não seja de seção, issue, data, versão ou
   texto entre aspas; `linha 224`/`line 224`/`l. 224` e `<doc>.md#L224` são linha
   sempre.
2. *Âncora resolve.* Toda `§` no trecho depois da referência tem de existir no
   doc citado, e todo rótulo depois de ` › ` tem de existir dentro da seção.

**Limite.** O gate reconhece a citação pelo nome do doc. Citação sem ele
(`doc §2, linha 107`, com o doc implícito no parágrafo) é invisível — por isso a
forma da CONVENTIONS nomeia o doc em toda âncora com rótulo.

**Fora do escopo:** a §7 dos `technical.md` (do título `## 7.` ao fim) — é
registro histórico e conta remapeamentos passados por número.

Códigos de saída:
  0  nenhuma citação por linha e todas as âncoras resolvem
  1  há citação por linha ou âncora que não resolve (arquivo:linha + motivo)
  2  `docs/domain/` sem doc, ou dois docs de domínio com o mesmo nome (fail closed)
"""

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

DOMAIN_DIR = Path("docs") / "domain"

# Onde moram os docs que citam. A raiz entra só no primeiro nível
# (CLAUDE.md, README.md); `.venv`, `htmlcov` e afins nunca são varridos.
PASTAS_VARRIDAS = ("docs", ".claude", ".github")

# Início da §7 de um technical.md — dali ao fim é registro histórico.
_SECAO_7 = re.compile(r"^## 7\.", re.MULTILINE)

# --- Regra 1: número de linha -------------------------------------------------

# Onde termina o trecho de citação que começa numa referência: fim de frase,
# célula de tabela, parágrafo ou outra fonte. `;` não termina — separa âncoras —,
# nem o ponto de `l. 166`.
_FIM_DO_TRECHO = re.compile(
    r"\||(?<!\bl)\.(?=[\s*_)\]]|$)|\n\s*\n"
    r"|`?[\w./-]+\.(?:md|py|toml|yml|yaml|ini|cfg)`?|`\.[\w-]+`"
    r"|\bADRs?\s+\d|\boverview\b|\bCLT\b|\b(?:concept|technical)\b"
)
_MAX_TRECHO = 240

# Coisas que têm dígitos e não são número de linha. Removidas do trecho antes de
# procurar o número.
_NEUTROS = (
    re.compile(r'\*?"[^"\n]*"\*?'),  # texto citado entre aspas
    re.compile(r"\*[^*\n]+\*"),  # ênfase / citação em itálico
    re.compile(r"`[^`\n]*`"),  # literal
    re.compile(r"§\S*"),  # âncora de seção
    re.compile(r"\b(?:Stages?|Steps?)\s+\d+(?:\.\d+)?(?:\s*[–/-]\s*\d+(?:\.\d+)?)?", re.IGNORECASE),
    re.compile(r"\d{4}-\d{2}(?:-\d{2})?"),  # data
    re.compile(r"#\d+"),  # issue / PR
    re.compile(r"https?://\S+"),  # URL
    re.compile(r"\b(?:HTTP|status|responde|devolve|retorna|returns?)\s+\d{3}\b", re.IGNORECASE),
    re.compile(r"\d+(?:\.\d+)+(?:\s*[–-]\s*\d+)?"),  # número de seção/versão/ADR, com faixa
)
# Número de linha: 2 a 4 dígitos fechando a citação — seguido de pontuação, fim,
# outra faixa/lista ou parêntese. Número seguido de palavra ("16 ADRs") é
# quantidade, não linha.
_NUMERO_DE_LINHA = re.compile(r"(?<![\w])\d{2,4}(?=\s*(?:[,;:)/–\]-]|$|\(|(?:e|and)\s+\d))")
# A palavra "linha" antes do número tira a dúvida, em qualquer ponto do trecho
# fora de texto citado (`*"…line 1086…"*` é citação, não ponteiro).
# `L171` (estilo GitHub, sem o `#`), `ln 171` e `line ~171` também.
_LINHA_EXPLICITA = re.compile(
    r"\b(?:linhas?|lines?|l\.|ln)\s*~?\d{2,4}\b|(?<![\w#])L\d{2,4}\b", re.IGNORECASE
)
# Fragmento de linha no alvo de um link (`...md#L171`, `...md#L171-L175`).
_FRAGMENTO_DE_LINHA = re.compile(r"#L\d+")
# Número logo depois da referência (`x.md` 171, `x.md:171`) é linha sempre.
_NUMERO_IMEDIATO = re.compile(
    r"^\s*:?\s*\(?\s*(?:(?:linhas?|lines?|l\.)\s*)?\d{2,4}\b", re.IGNORECASE
)

# --- Regra 2: âncora ----------------------------------------------------------

_ROTULO = r'(?:"[^"\n]+"|`[^`\n]+`)'
_ANCORA = re.compile(
    r'§(?P<secao>\d+(?:\.\d+)*|"[^"\n]+")'
    rf"(?: › (?P<rotulos>{_ROTULO}(?:, {_ROTULO})*))?"
)
_ROTULO_ITEM = re.compile(_ROTULO)
# Rótulo colado à âncora fora da forma ` › ` (`§3.1 > "x"`, `§3.1 -> "x"`, `§3.1 ›"x"`):
# a regex da âncora não o lê, e a âncora pareceria conferida sem o rótulo ter sido.
_ROTULO_MAL_FORMADO = re.compile(r'[ \t]*(?:->|>|›)[ \t]*["`]')
# O que pode haver entre a referência e a 1ª âncora, ou entre duas âncoras da
# mesma cadeia (`§2, §3.2 (a lacuna), §3.6.0/§3.6.8`, `§3.1–§3.5`, `§3.3(b) e
# §3.5`): um parêntese (com um nível de parêntese dentro) e um separador. Prosa
# entre duas `§` corta a cadeia — `workforce §3.8; as docstrings de §8` não
# atribui ao doc de domínio a §8 do concept que o cita.
_DENTRO = r"(?:[^()\n]|\n(?![ \t>]*\n))"  # quebra de linha, mas não de parágrafo
_PARENTESE = rf"\({_DENTRO}*(?:\({_DENTRO}*\){_DENTRO}*)*\)"
_SEPARADOR = r"[,;/:–—-]|\be\b|\band\b"
_CONECTOR = re.compile(
    rf"[ \t]*(?:{_PARENTESE})?[ \t]*(?:{_SEPARADOR})?[ \t]*(?:\n[ \t>]*)?(?:{_SEPARADOR})?[ \t]*"
)  # uma quebra de linha no máximo: parágrafo novo corta a cadeia
_TITULO = re.compile(r"^(#{1,4}) (.+?)\s*$")
_NUMERO_DO_TITULO = re.compile(r"^(\d+(?:\.\d+)*)\.?\s")
_CERCA = re.compile(r"^\s*(```|~~~)")


@dataclass(frozen=True)
class Secao:
    """Uma seção de um doc de domínio: título, nível e corpo até o próximo título igual ou maior."""

    titulo: str
    nivel: int
    corpo: str

    @property
    def numero(self) -> str | None:
        """`3.6.1` para `#### 3.6.1 Sobreposição...`, `2` para `## 2. Língua ubíqua`."""
        m = _NUMERO_DO_TITULO.match(self.titulo)
        return m.group(1) if m else None


def secoes(doc: str) -> list[Secao]:
    """Quebra o doc nas seções de nível 1 a 4, ignorando `#` dentro de bloco cercado."""
    linhas = doc.splitlines()
    titulos: list[tuple[int, int, str]] = []
    dentro_da_cerca = False
    for i, linha in enumerate(linhas):
        if _CERCA.match(linha):
            dentro_da_cerca = not dentro_da_cerca
            continue
        if not dentro_da_cerca and (m := _TITULO.match(linha)):
            titulos.append((i, len(m.group(1)), m.group(2)))
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
    """`N.M` casa pelo número do título; `"X"` pelo título inteiro ou pelo prefixo."""
    if nome.startswith('"'):
        alvo = nome.strip('"')
        for s in todas:
            if s.titulo == alvo or s.titulo.startswith(alvo + " "):
                return s
        return None
    for s in todas:
        if s.numero == nome:
            return s
    return None


def normaliza(texto: str) -> str:
    """Sem `*`, sem crase, sem o `>` de citação no começo da linha e com o espaço colapsado."""
    sem_citacao = re.sub(r"^\s*>\s?", "", texto, flags=re.MULTILINE)
    return " ".join(re.sub(r"[*`]", "", sem_citacao).split())


def rotulo_resolve(secao: Secao, rotulo: str) -> bool:
    """O rótulo existe no corpo da seção: trecho normalizado ou literal cru."""
    if rotulo.startswith("`"):
        return rotulo.strip("`") in secao.corpo
    return normaliza(rotulo.strip('"')) in normaliza(secao.corpo)


@dataclass(frozen=True)
class Doc:
    """Um doc de domínio: caminho relativo e seções."""

    rel: str
    secoes: list[Secao]


def docs_de_dominio(repo_root: Path) -> tuple[dict[str, Doc], list[str]]:
    """`nome sem .md` → doc; e os nomes repetidos (que tornariam a referência ambígua)."""
    docs: dict[str, Doc] = {}
    repetidos: list[str] = []
    for caminho in sorted((repo_root / DOMAIN_DIR).rglob("*.md")):
        nome = caminho.stem
        rel = caminho.relative_to(repo_root).as_posix()
        if nome in docs:
            repetidos.append(f"{docs[nome].rel} e {rel}")
            continue
        docs[nome] = Doc(rel, secoes(caminho.read_text(encoding="utf-8-sig")))
    return docs, repetidos


def regex_de_referencia(nomes: list[str]) -> re.Pattern[str]:
    """Referência a doc de domínio: `<nome>.md` (com crase e link opcionais) ou `<nome> §`."""
    alternativas = "|".join(re.escape(n) for n in sorted(nomes, key=len, reverse=True))
    return re.compile(
        rf"(?<![\w-])(?P<nome>{alternativas})"
        r"(?:\.md(?P<fragmento>#L\d+)?`?(?:\]\((?P<alvo>[^)\s]*)\))?|(?= §))"
    )


def _linha_de(texto: str, pos: int) -> int:
    return texto.count("\n", 0, pos) + 1


def _trecho(texto: str, fim_da_ref: int) -> tuple[str, str]:
    """(resto bruto, trecho até o fim da citação) depois de uma referência."""
    resto = texto[fim_da_ref : fim_da_ref + _MAX_TRECHO]
    fim = _FIM_DO_TRECHO.search(resto)
    return resto, resto[: fim.start()] if fim else resto


def _tem_numero_de_linha(resto: str, trecho: str) -> bool:
    limpo = trecho
    for neutro in _NEUTROS:
        limpo = neutro.sub(" ", limpo)
    # O número imediato é procurado no `resto`, não no `trecho`: o `.` de
    # `(l. 171)` encerraria o trecho antes do número.
    return bool(
        _NUMERO_IMEDIATO.match(resto)
        or _LINHA_EXPLICITA.search(limpo)
        or _NUMERO_DE_LINHA.search(limpo)
    )


def cadeia_de_ancoras(texto: str, inicio: int) -> list[re.Match[str]]:
    """As âncoras encadeadas a partir de `inicio` (o fim de uma referência)."""
    cadeia: list[re.Match[str]] = []
    pos = inicio
    while True:
        conector = _CONECTOR.match(texto, pos)
        pos = conector.end() if conector else pos
        ancora = _ANCORA.match(texto, pos)
        if ancora is None:
            return cadeia
        cadeia.append(ancora)
        pos = ancora.end()


def problemas_no_texto(texto: str, docs: dict[str, Doc]) -> list[tuple[int, str]]:
    """(linha, motivo) de cada citação por linha e de cada âncora que não resolve."""
    achados: list[tuple[int, str]] = []
    for ref in regex_de_referencia(list(docs)).finditer(texto):
        doc = docs[ref.group("nome")]
        linha = _linha_de(texto, ref.start())
        resto, trecho = _trecho(texto, ref.end())
        # `#L171` no alvo do link (`[`x.md`](../x.md#L171)`) é linha: o link inteiro é
        # consumido pela referência, e o trecho começa depois dele.
        alvo_do_link = ref.group("alvo") or ""
        if (
            ref.group("fragmento")
            or _FRAGMENTO_DE_LINHA.search(alvo_do_link)
            or _tem_numero_de_linha(resto, trecho)
        ):
            citado = (ref.group(0) + trecho).replace("\n", " ").strip()
            achados.append((linha, f"citação por número de linha a {doc.rel}: {citado[:100]!r}"))
        for m in cadeia_de_ancoras(texto, ref.end()):
            nome = m.group("secao")
            secao = acha_secao(doc.secoes, nome)
            linha_da_ancora = _linha_de(texto, m.start())
            if _ROTULO_MAL_FORMADO.match(texto, m.end()):
                achados.append((linha_da_ancora, f'rótulo de §{nome} fora da forma ` › "trecho"`'))
            if secao is None:
                achados.append((linha_da_ancora, f"seção §{nome} não existe em {doc.rel}"))
                continue
            for rotulo in _ROTULO_ITEM.findall(m.group("rotulos") or ""):
                if not rotulo_resolve(secao, rotulo):
                    achados.append(
                        (linha_da_ancora, f"rótulo {rotulo} não existe em {doc.rel} §{nome}")
                    )
    return achados


def texto_varrido(caminho: Path) -> str:
    """O texto sujeito ao gate: o arquivo inteiro, menos a §7 de um technical.md."""
    texto = caminho.read_text(encoding="utf-8-sig")
    if caminho.name == "technical.md" and (m := _SECAO_7.search(texto)):
        return texto[: m.start()]
    return texto


def arquivos(repo_root: Path) -> list[Path]:
    """Os .md que podem citar um doc de domínio (os próprios docs de domínio inclusive)."""
    candidatos = list(repo_root.glob("*.md"))
    for pasta in PASTAS_VARRIDAS:
        candidatos.extend((repo_root / pasta).rglob("*.md"))
    return sorted(set(candidatos))


def problemas(repo_root: Path) -> list[str]:
    """Todas as violações das duas regras (`arquivo:linha: motivo`); `FATAL:` se não dá para ler."""
    docs, repetidos = docs_de_dominio(repo_root)
    if not docs:
        return [f"FATAL: nenhum doc em {DOMAIN_DIR.as_posix()}/"]
    if repetidos:
        return [f"FATAL: docs de domínio com o mesmo nome: {'; '.join(repetidos)}"]
    saida: list[str] = []
    for arquivo in arquivos(repo_root):
        rel = arquivo.relative_to(repo_root).as_posix()
        for linha, motivo in problemas_no_texto(texto_varrido(arquivo), docs):
            saida.append(f"{rel}:{linha}: {motivo}")
    return saida


def main() -> int:
    """Varre os docs e reprova citação por linha ou âncora quebrada a um doc de domínio."""
    parser = argparse.ArgumentParser(
        description=(
            "Reprova citação a docs/domain/** por número de linha ou por âncora que não resolve"
            " (issue #116)"
        )
    )
    parser.add_argument("--repo", default=".", help="Raiz do repositório (padrão: .)")
    args = parser.parse_args()

    achados = problemas(Path(args.repo).resolve())
    if achados and achados[0].startswith("FATAL:"):
        print(f"check_domain_citations: {achados[0]}", file=sys.stderr)
        return 2
    if achados:
        print(
            f"check_domain_citations: {len(achados)} problema(s). Cite o doc de domínio por âncora "
            '(`shift-scheduling.md` §3.4 › "trecho") — CONVENTIONS §5, ADR 0.0.0017:\n',
            file=sys.stderr,
        )
        for achado in achados:
            print(f"  {achado}", file=sys.stderr)
        return 1
    print("check_domain_citations: toda citação a doc de domínio é por âncora, e todas resolvem.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
