"""Guard: doc cita um ADR ou um arquivo de código/config do repo por âncora, nunca por linha.

Uso:
    python scripts/check_adr_code_citations.py
    python scripts/check_adr_code_citations.py --repo .

Issue #154, ADR 0.0.0019. Ligado em `make docs-check`. Terceiro da família de
`check_roadmap_citations.py` (ADR 0.0.0012) e `check_domain_citations.py` (ADR
0.0.0017, que também cobre o `overview.md`).

---

**Por que número de linha não serve.** Um ADR `accepted` ganha banner de errata
no topo e seção de supersessão parcial no fim (CONVENTIONS §5); o código muda a
cada PR. `ADR 4.1.0003 (c) linhas 95–97` e `employee.py 113–116` passam a apontar
para o vizinho sem erro em lugar nenhum.

**A forma estável** (CONVENTIONS §5, "Citação a ADR e a código"):

    ADR 4.1.0003 (c) › "`block` for overlap (one person in two places)"
    ADR 3.1.0001 §Decision (i) › "adjacent intervals do not conflict"
    `employee.py` › `Employee.__post_init__`
    `.importlinter` › `[importlinter:contract:bc-independence]`

*ADR:* `ADR N.N.NNNN` (ou `ADRs`, lista `/0002`, link, nome do arquivo
`N_N_NNNN-slug.md`), um localizador livre sem número de linha (`§Decision 2`,
`(c)`, `§Alternative B`) e, para apontar dentro dele, ` › "<trecho>"` — texto do
ADR, comparado sem `*`, crase, `>` de citação e com o espaço normalizado.

*Código e config:* o arquivo (`<nome>.py`, caminho, `.importlinter`,
`pyproject.toml`, `*.yml`...) e o símbolo depois de ` › ` (`Classe.metodo`,
constante, chave de config, nome de teste).

**As regras.**

1. *Sem número de linha* depois de uma referência a ADR ou a arquivo de código do
   repo (`x.py:113`, `x.py 113–116`, `linha 130`, `#L130`, `ADR N.N.NNNN:79`), no
   mesmo trecho de citação (até `|`, fim de frase, parágrafo ou outra fonte).
2. *O trecho do ADR resolve*: o ADR existe em `docs/adr/` e cada `"<trecho>"`
   depois de ` › ` está no texto dele. O localizador não é conferido (os ADRs não
   têm forma única de subseção).

**O símbolo de código não é conferido.** Os concepts e technicals de Stages
`done` descrevem o código do seu tempo; conferir o símbolo contra o HEAD
reprovaria o histórico a cada refatoração. O ganho do símbolo é que ele não se
desloca com uma linha inserida acima e é buscável (`git log -S`).

**Fora do gate.**
- Arquivo que não é do repo (`engine/base.py` do SQLAlchemy 2.0.51,
  `fastapi/routing.py`): cita uma versão fixa de terceiro, que não muda. É do
  repo o arquivo cujo caminho citado é sufixo de um arquivo do repo, ou cujo nome
  sem pasta é nome de um arquivo do repo.
- Bloco cercado (```` ``` ````): é saída capturada (traceback), não ponteiro.
- A §7 dos `technical.md` (registro histórico), como nos outros dois gates.

Códigos de saída:
  0  nenhuma citação por linha e todo trecho de ADR resolve
  1  há citação por linha ou trecho que não resolve (arquivo:linha + motivo)
  2  `docs/adr/` sem ADR (fail closed)
"""

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ADR_DIR = Path("docs") / "adr"

PASTAS_VARRIDAS = ("docs", ".claude", ".github")
# Onde mora o código e a config que os docs citam.
PASTAS_DE_CODIGO = ("src", "tests", "scripts", "migrations", ".github", ".claude", ".devcontainer")
_IGNORADAS = {".venv", "node_modules", "__pycache__", ".mypy_cache", ".ruff_cache", "htmlcov"}

_SECAO_7 = re.compile(r"^## 7\.", re.MULTILINE)
_ERRATA = re.compile(r"^## Errata\b.*$", re.MULTILINE)
_PROXIMA_SECAO = re.compile(r"^## ", re.MULTILINE)
_CERCA = re.compile(r"^\s*(```|~~~)")

# --- Referências ---------------------------------------------------------------

_ID = r"\d+\.\d+\.\d{4}"
_REF_ADR = re.compile(
    rf"\[?\bADRs?\s+(?P<id>{_ID})"
    # lista: 3.4.0006/0008, 4.1.0007–0012
    rf"(?:\s*(?:[/–,-]|\be\b|\band\b)\s*(?:{_ID}|\d{{4}})\b)*"
    r"\]?(?:\([^)\s]*\))?"
    r"|`?\[?`?(?P<arquivo>\d+_\d+_\d{4})-[\w-]+\.md`?\]?(?:\([^)\s]*\))?`?"
)
_EXT_DE_CODIGO = r"py|pyi|toml|ini|cfg|yml|yaml|json|sh|ps1|lock"
_REF_CODIGO = re.compile(
    rf"(?<![\w./-])(?P<caminho>(?:[\w.-]+/)*(?:[\w-][\w.-]*\.(?:{_EXT_DE_CODIGO})|\.importlinter"
    r"|Makefile|Dockerfile|\.pre-commit-config\.yaml))"
    r"(?![\w-])`?(?:\]\([^)\s]*\))?"
)

# --- Regra 1: número de linha (mesma leitura dos outros dois gates) ------------

_FIM_DO_TRECHO = re.compile(
    r"\||(?<!\bl)\.(?=[\s*_)\]]|$)|\n\s*\n"
    r"|`?[\w./-]+\.(?:md|py|toml|yml|yaml|ini|cfg)`?|`\.[\w-]+`"
    r"|\bADRs?\s+\d|\boverview\b|\bCLT\b|\b(?:concept|technical)\b"
)
_MAX_TRECHO = 240
_NEUTROS = (
    re.compile(r"§\S*"),  # localizador de seção (ADR §2): o número dele não é linha
    re.compile(r'\*?"(?:[^"\n]|\n(?![ \t>]*\n))*"\*?'),  # texto citado (pode quebrar linha)
    re.compile(r"\*[^*\n]+\*"),  # ênfase / citação em itálico
    re.compile(r"`[^`\n]*`"),  # literal
    re.compile(r"\d{4}-\d{2}(?:-\d{2})?(?:/\d{2})?"),  # data (e 2026-08-08/09)
    re.compile(r"\b\d[\d.]*/\d{4}\b"),  # número/ano de norma (Decreto 9.772/2019)
    re.compile(r"\d+(?:\.\d+)+(?:\s*[–-]\s*\d+)?"),  # seção/versão/ADR, com faixa (antes de Stage)
    re.compile(r"\b(?:Stages?|Steps?)\s+\d+(?:\.\d+)?(?:\s*[–/-]\s*\d+(?:\.\d+)?)?", re.IGNORECASE),
    re.compile(r"#\d+"),  # issue / PR
    re.compile(r"https?://\S+"),  # URL
    re.compile(r"\btask-\d+|\bTasks?\s+\d+(?:\s*[/–,-]\s*\d+)*", re.IGNORECASE),  # Task
    re.compile(r"\b0\d\b"),  # número com zero à esquerda (Task 06): linha não tem
    re.compile(r"\b\d+,\d+(?=[^\W\d_]|\b)"),  # decimal com vírgula (22,33h)
    re.compile(r"\b(?:default|padrão)\s+\d+", re.IGNORECASE),  # valor default
    re.compile(r"(?:→|->|=)\s*[1-5]\d{2}\b"),  # → 201, = 422
    re.compile(r"\b[1-5]\d{2}(?:/[1-5]\d{2})+\b"),  # lista de status (401/403/404)
    re.compile(  # status HTTP depois de verbo ou artigo
        r"\b(?:HTTP|status|responde|devolve|retorna|returns?|produced?|vira|a|o|em|um|uma|do|da|ao|no"
        r"|the|an?|for|with|by)\s+[1-5]\d{2}\b",
        re.IGNORECASE,
    ),
    re.compile(  # número de regra, lei, invariante, critério, decisão, divergência
        r"\b(?:invariantes?|regras?|rules?|passos?|itens?|item|CA|decisão|decision|divergência"
        r"|laws?|leis?)\s+#?\d+",
        re.IGNORECASE,
    ),
    re.compile(r"\b\d{1,2}:\d{2}\b"),  # hora (08:00)
    re.compile(r"\b[^\W\d_]{3,9}/\d{4}\b"),  # mês/ano (jul/2026)
    re.compile(r"\d+\(\d+\)|,\s*(?:19|20)\d{2}\b|\b\w+\d:\d{4}\b"),  # bibliografia
    re.compile(r"\b(?:PEP|RFC)\s+\d+"),  # PEP 615, RFC 9110
)
_NUMERO_DE_LINHA = re.compile(r"(?<![\w])\d{2,4}(?=\s*(?:[,;:)/–\]-]|$|\(|(?:e|and)\s+\d))")
_LINHA_EXPLICITA = re.compile(
    r"\b(?:linhas?|lines?|l\.|ln)\s*~?\d{1,4}\b|(?<![\w#])L\d{2,4}\b", re.IGNORECASE
)
_FRAGMENTO_DE_LINHA = re.compile(r"#L\d+")
# Logo depois da referência: `x.py:113`, `x.py 113`, `x.py (113)`, `ADR N:79`, `x.py` linha 3.
_NUMERO_IMEDIATO = re.compile(
    r"^`?[ \t]*:?[ \t]*\(?[ \t]*(?:(?:linhas?|lines?|l\.)[ \t]*)?\d{1,4}\b"
    r"(?![./]\d|-\d{2}-\d)"  # versão (2.2) e data (2026-07-27) não são linha
    r"(?!\s*\N{MULTIPLICATION SIGN}|\s+(?!(?:e|and)\s+\d)[^\W\d_])",  # "(25 tests)": quantidade
    re.IGNORECASE,
)

# --- Regra 2: trecho do ADR ------------------------------------------------------

_LOCALIZADOR = re.compile(
    r"(?:[ \t]+(?:§[\w.-]+(?:[ \t]+(?:[A-Z]\b|\d+\b|\([a-z]{1,4}\)))?|\([a-z]{1,4}\)"
    r"|(?:Decision|Alternative|Option)[ \t]+[\w.]+))*"
)
_ROTULO = r'(?:"[^"\n]+"|`[^`\n]+`)'
_TRECHOS = re.compile(rf" › (?P<rotulos>{_ROTULO}(?:, {_ROTULO})*)")
_ROTULO_ITEM = re.compile(_ROTULO)
_ROTULO_MAL_FORMADO = re.compile(r'[ \t]*(?:->|>|›)[ \t]*["`]')


def normaliza(texto: str) -> str:
    """Sem `*`, sem crase, sem o `>` de citação no começo da linha e com o espaço colapsado."""
    sem_citacao = re.sub(r"^\s*>\s?", "", texto, flags=re.MULTILINE)
    return " ".join(re.sub(r"[*`]", "", sem_citacao).split())


@dataclass(frozen=True)
class Adr:
    """Um ADR: caminho relativo e texto normalizado."""

    rel: str
    texto: str
    cru: str


def adrs(repo_root: Path) -> dict[str, Adr]:
    """`N.N.NNNN` → ADR, a partir do nome do arquivo `N_N_NNNN-slug.md`."""
    resultado: dict[str, Adr] = {}
    for caminho in sorted((repo_root / ADR_DIR).glob("*.md")):
        m = re.match(r"(\d+)_(\d+)_(\d{4})-", caminho.name)
        if m:
            cru = caminho.read_text(encoding="utf-8-sig")
            resultado[".".join(m.groups())] = Adr(
                caminho.relative_to(repo_root).as_posix(), normaliza(cru), cru
            )
    return resultado


def arquivos_de_codigo(repo_root: Path) -> tuple[set[str], set[str]]:
    """(caminhos relativos, nomes sem pasta) dos arquivos de código e config do repo."""
    caminhos: set[str] = set()
    for item in repo_root.iterdir():
        if item.is_file():
            caminhos.add(item.name)
    for pasta in PASTAS_DE_CODIGO:
        base = repo_root / pasta
        if not base.is_dir():
            continue
        for item in base.rglob("*"):
            partes = set(item.relative_to(repo_root).parts)
            if item.is_file() and not partes & _IGNORADAS:
                caminhos.add(item.relative_to(repo_root).as_posix())
    return caminhos, {c.rsplit("/", 1)[-1] for c in caminhos}


def e_do_repo(citado: str, caminhos: set[str], nomes: set[str]) -> bool:
    """O arquivo citado é do repo: caminho que é sufixo de um arquivo do repo, ou nome sem pasta."""
    if "/" not in citado:
        return citado in nomes
    sufixo = re.sub(r"^(?:\.\.?/)+", "", citado)
    return any(c == sufixo or c.endswith("/" + sufixo) for c in caminhos)


def _linha_de(texto: str, pos: int) -> int:
    return texto.count("\n", 0, pos) + 1


def _trecho(texto: str, fim_da_ref: int) -> tuple[str, str]:
    resto = texto[fim_da_ref : fim_da_ref + _MAX_TRECHO]
    fim = _FIM_DO_TRECHO.search(resto)
    return resto, resto[: fim.start()] if fim else resto


def _tem_numero_de_linha(resto: str, trecho: str, *, solto: bool = True) -> bool:
    """Número de linha no trecho. `solto=False` (código) só lê o número logo depois do arquivo
    e a palavra "linha": prosa sobre código conta coisas ("13 → 15", "sobe de 22 para 34")."""
    limpo = trecho
    for neutro in _NEUTROS:
        limpo = neutro.sub(" ", limpo)
    return bool(
        _NUMERO_IMEDIATO.match(resto)
        or _LINHA_EXPLICITA.search(limpo)
        or (solto and _NUMERO_DE_LINHA.search(limpo))
    )


def sem_blocos_cercados(texto: str) -> str:
    """O texto com o frontmatter e os blocos cercados em branco (a numeração das linhas fica)."""
    linhas = texto.split("\n")
    if linhas and linhas[0] == "---" and "---" in linhas[1:]:
        fim = linhas.index("---", 1)
        linhas[: fim + 1] = [""] * (fim + 1)
    dentro = False
    for i, linha in enumerate(linhas):
        if _CERCA.match(linha):
            dentro = not dentro
            linhas[i] = ""
        elif dentro:
            linhas[i] = ""
    return "\n".join(linhas)


def problemas_no_texto(
    texto: str, todos: dict[str, Adr], caminhos: set[str], nomes: set[str]
) -> list[tuple[int, str]]:
    """(linha, motivo) de cada citação por linha a ADR ou código e de cada trecho quebrado."""
    texto = sem_blocos_cercados(texto)
    achados: list[tuple[int, str]] = []
    for ref in _REF_ADR.finditer(texto):
        ident = ref.group("id") or ".".join(ref.group("arquivo").split("_"))
        linha = _linha_de(texto, ref.start())
        resto, trecho = _trecho(texto, ref.end())
        if _FRAGMENTO_DE_LINHA.search(ref.group(0)) or _tem_numero_de_linha(resto, trecho):
            citado = (ref.group(0) + trecho).replace("\n", " ").strip()
            achados.append((linha, f"citação por número de linha ao ADR {ident}: {citado[:100]!r}"))
        local = _LOCALIZADOR.match(texto, ref.end())
        pos = local.end() if local else ref.end()
        if (m := _TRECHOS.match(texto, pos)) is None:
            if _ROTULO_MAL_FORMADO.match(texto, pos) and not texto.startswith(" › ", pos):
                achados.append((linha, f'trecho do ADR {ident} fora da forma ` › "trecho"`'))
            continue
        adr = todos.get(ident)
        if adr is None:
            achados.append((linha, f"ADR {ident} não existe em {ADR_DIR.as_posix()}/"))
            continue
        for rotulo in _ROTULO_ITEM.findall(m.group("rotulos")):
            achou = (
                rotulo.strip("`") in adr.cru
                if rotulo.startswith("`")
                else normaliza(rotulo.strip('"')) in adr.texto
            )
            if not achou:
                achados.append((linha, f"trecho {rotulo} não existe no ADR {ident} ({adr.rel})"))
    for ref in _REF_CODIGO.finditer(texto):
        citado = ref.group("caminho")
        if not e_do_repo(citado, caminhos, nomes):
            continue
        resto, trecho = _trecho(texto, ref.end())
        if (
            _FRAGMENTO_DE_LINHA.search(ref.group(0))
            or _FRAGMENTO_DE_LINHA.match(resto)
            or _tem_numero_de_linha(resto, trecho, solto=False)
        ):
            linha = _linha_de(texto, ref.start())
            mostrado = (ref.group(0) + trecho).replace("\n", " ").strip()
            achados.append((linha, f"citação por número de linha a {citado}: {mostrado[:100]!r}"))
    return sorted(achados)


def texto_varrido(caminho: Path) -> str:
    """O arquivo inteiro, menos a §7 de um technical.md e a `## Errata` de um ADR.

    As duas são registro histórico: a errata de ponteiro de um ADR conta o número que ele
    *dizia* e o que passou a dizer (ADR 3.4.0001), e reescrevê-la apagaria o fato registrado.
    As linhas cortadas viram linhas em branco, para o `arquivo:linha` dos achados não mudar.
    """
    texto = caminho.read_text(encoding="utf-8-sig")
    if caminho.name == "technical.md" and (m := _SECAO_7.search(texto)):
        return texto[: m.start()]
    if caminho.parent.name == "adr" and (m := _ERRATA.search(texto)):
        fim = _PROXIMA_SECAO.search(texto, m.end())
        corte = fim.start() if fim else len(texto)
        return texto[: m.start()] + "\n" * texto.count("\n", m.start(), corte) + texto[corte:]
    return texto


def arquivos(repo_root: Path) -> list[Path]:
    """Os .md que podem citar ADR ou código."""
    candidatos = list(repo_root.glob("*.md"))
    for pasta in PASTAS_VARRIDAS:
        candidatos.extend((repo_root / pasta).rglob("*.md"))
    return sorted(set(candidatos))


def problemas(repo_root: Path) -> list[str]:
    """Todas as violações (`arquivo:linha: motivo`); `FATAL:` se não há ADR para conferir."""
    todos = adrs(repo_root)
    if not todos:
        return [f"FATAL: nenhum ADR em {ADR_DIR.as_posix()}/"]
    caminhos, nomes = arquivos_de_codigo(repo_root)
    saida: list[str] = []
    for arquivo in arquivos(repo_root):
        rel = arquivo.relative_to(repo_root).as_posix()
        for linha, motivo in problemas_no_texto(texto_varrido(arquivo), todos, caminhos, nomes):
            saida.append(f"{rel}:{linha}: {motivo}")
    return saida


def main() -> int:
    """Varre os docs e reprova citação por linha a ADR ou código e trecho de ADR que não resolve."""
    parser = argparse.ArgumentParser(
        description="Reprova citação a ADR ou a código por número de linha (issue #154)"
    )
    parser.add_argument("--repo", default=".", help="Raiz do repositório (padrão: .)")
    args = parser.parse_args()

    achados = problemas(Path(args.repo).resolve())
    if achados and achados[0].startswith("FATAL:"):
        print(f"check_adr_code_citations: {achados[0]}", file=sys.stderr)
        return 2
    if achados:
        print(
            f"check_adr_code_citations: {len(achados)} problema(s). Cite o ADR por localizador e"
            ' trecho (ADR 4.1.0003 (c) › "trecho") e o código por símbolo'
            " (`x.py` › `Classe.metodo`)"
            " — CONVENTIONS §5, ADR 0.0.0019:\n",
            file=sys.stderr,
        )
        for achado in achados:
            print(f"  {achado}", file=sys.stderr)
        return 1
    print("check_adr_code_citations: nenhuma citação por linha a ADR ou a código.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
