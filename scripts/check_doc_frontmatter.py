"""Guard: o frontmatter dos ADRs e dos docs de domínio é YAML, e o que ele declara bate.

Uso:
    python scripts/check_doc_frontmatter.py
    python scripts/check_doc_frontmatter.py --repo .

Issue #102, ADR 0.0.0015. Ligado em `make docs-check`.

---

**Por que existe.** Os outros gates leem o frontmatter por regex
(`check_adr_bounded_context.py`) ou só parseiam `.claude/` (`check_harness.py`).
Seis ADRs chegaram a `develop` com frontmatter que `yaml.safe_load` recusa — um
`decision:` que começa com crase, um `title:` com `: ` no meio — e nada reclamou.
Duas sessões paralelas criaram ADRs com o mesmo `adr_id` (0.0.0007 em out/2026;
0.0.0011 em 2026-11-02): os nomes de arquivo diferem, o git não acusa conflito.
E o doc de domínio de staff chegou a citar 18 ADRs por link com só 8 no
`references`, com quatro "Lacuna para o concept da Stage N.M" abertas depois da
Stage `done` (issue #37).

**Regras — `docs/adr/*.md`:**

1. O frontmatter existe e é um mapeamento YAML (`yaml.safe_load`).
2. O nome do arquivo é `N_M_NNNN-<slug>.md`.
3. `adr_id` é texto `N.M.NNNN` e bate com o prefixo do nome (`0_0_0012` ↔ `"0.0.0012"`).
4. Nenhum `adr_id` se repete entre os ADRs.

**Regras — `docs/domain/**/*.md`:**

5. O frontmatter existe e é um mapeamento YAML; `references`, se presente, é lista
   de caminhos, e cada um resolve.
6. Todo link relativo do corpo resolve — inline ou definição por referência
   (`[x]: alvo`); o fragmento `#...` é ignorado. Bloco de
   código cercado não conta, nesta regra nem na 7 e na 8: é exemplo citado.
7. Todo ADR linkado no corpo está no `references`.
8. Nenhuma "Lacuna para o concept da Stage N.M" fica aberta com uma Stage listada
   (`N.M`, `N.M/P.Q`) `done` na Tabela de Stages do roadmap. Lacuna fechada se
   reescreve no lugar ("Lacuna fechada pela Stage N.M (fonte)"); a parte que sobra
   para outra Stage se reendereça a ela. A mesma regra vale para a **linha de tabela de
   lacunas** cuja primeira célula é a Stage dona em negrito (`| **4.3** |`,
   `| **4.3 / 4.4** |`, `| **4.1 (technical)** |`): cada Stage `done` da célula exige,
   na mesma linha, "fechada pela Stage N.M" (ou "fechada pelas Stages N.M e P.Q");
   a parte que sobra fica dita na linha ou a célula é reendereçada (issue #117).
   **Fora da tabela, a marca canônica é a única forma** (issue #158): a menção livre —
   "lacuna" ou "delegada" seguida só de conectivos e do número da Stage ("lacuna da
   4.2", "lacuna do concept da 4.3", "(lacuna 4.3/4.4", "lacuna aberta para a 4.2",
   "delegada ao concept da Stage 3.1"), inclusive quebrada entre linhas ou com ênfase
   ou crase no meio — reprova com qualquer status, e se reescreve como "Lacuna para o
   concept da Stage N.M" (aberta) ou "lacuna fechada pela Stage N.M" (fechada). Proibir
   em vez de aceitar mais formas mantém o contrato do ADR 0.0.0015 §Decision 4 numa
   marca só, que um `grep` acha.
   *Limite:* texto livre entre a palavra e a Stage ("a lacuna (b) que o rascunho
   deixava para o concept da 4.1", "lacuna endereçada à 4.2") não é lido — cobrar essa
   forma pegaria a prosa histórica que narra lacunas já fechadas ("as lacunas
   endereçadas à 4.2 foram fechadas"). A #158 reescreveu as que havia em
   `docs/domain/**`.

**Sem válvula.** Até a issue #116 o `shift-scheduling.md` tinha uma exceção à
regra 7 (`VALVULA_REFERENCES`, ADR 0.0.0015 §Decision 5): 16 ADRs linkados fora do
`references`, porque acrescentá-los ao frontmatter deslocaria as citações por
número de linha que ADRs `accepted` e o concept da 4.1 faziam ao doc. A #116
trocou essas citações por âncora e criou o gate que as cobra
(`check_domain_citations.py`, ADR 0.0.0017); os 16 entraram no `references` e a
válvula saiu. Linha nova no frontmatter de um doc de domínio já não desloca
citação nenhuma — não há motivo para exceção voltar.

Códigos de saída:
  0  tudo válido
  1  violação (arquivo + motivo no stderr)
  2  `docs/roadmap.md` ausente ou sem Stage `done` legível (fail closed)
"""

import argparse
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import yaml

ADR_DIR = Path("docs") / "adr"
DOMAIN_DIR = Path("docs") / "domain"
ROADMAP = Path("docs") / "roadmap.md"

_ADR_ARQUIVO = re.compile(r"^(\d+)_(\d+)_(\d{4})-[a-z0-9][a-z0-9-]*\.md$")
_ADR_ID = re.compile(r"^\d+\.\d+\.\d{4}$")

# Alvo de um link markdown inline: `[texto](alvo)` ou `[texto](alvo "título")`.
_LINK = re.compile(r"\]\(\s*<?([^)\s>]+)>?(?:\s+\"[^\"]*\")?\s*\)")
# Definição de link por referência: `[rótulo]: alvo` no começo da linha. Sem ela,
# `[ADR][x]` + `[x]: ../../adr/...` escaparia das regras 6 e 7.
_DEFINICAO = re.compile(r"^ {0,3}\[[^\]]+\]:\s*<?([^\s>]+)>?")
_ESQUEMA = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:")
_CERCA = re.compile(r"^\s*(```|~~~)")

# Menção a lacuna endereçada a Stage, em qualquer forma: "lacuna" (ou "delegada", o verbo
# com que a prosa endereçava a lacuna aberta) seguida só de conectivos e do número da
# Stage — "lacuna da 4.2", "lacuna do concept da 4.3", "(lacuna 4.3/4.4", "lacunas da 4.1",
# "lacuna aberta para a 4.2", "lacuna pendente da 4.2", "delegado ao concept da Stage 3.1"
# e a própria marca canônica. "Aberta"/"pendente" contam como conectivo porque qualificam
# a lacuna sem tirá-la do endereço; "fechada" não conta — é a forma fechada. O separador
# atravessa ênfase (`*`, `_`), crase e **uma** quebra de linha por vez (com `>` de
# citação): a marca quebrada no meio pela largura da linha não escapa; linha em branco
# corta. A palavra começa onde não há letra nem dígito antes — `_lacuna_` (itálico) conta,
# `metalacuna` não. Não é Stage: `§3.2` (seção — o `§` não é separador) nem `4.1.0007`
# (ADR).
_SEP = r"(?:[ \t*_`]*\n[ \t>]*[ \t*_`]*|[ \t*_`]+)"
_CONECTIVOS = r"(?:para|concept|stages?|do|da|de|dos|das|ao|o|a|à|em|aberto|abertas?|pendentes?)"
_STAGE = r"\d+\.\d+(?!\d|\.\d)"
_MENCAO = re.compile(
    rf"(?<![^\W_])(?:lacunas?|delegad[ao]s?)(?:{_SEP}{_CONECTIVOS})*{_SEP}\(?"
    rf"({_STAGE}(?:\s*(?:/|,|\be\b)\s*{_STAGE})*)",
    re.IGNORECASE,
)
# A marca canônica (ADR 0.0.0015 §Decision 4), lida sobre a menção normalizada.
_CANONICA = re.compile(r"^lacunas? para o concept da stages? ", re.IGNORECASE)
# Linha de tabela de lacunas: 1ª célula abre com a(s) Stage(s) dona(s) em negrito, com
# nota opcional entre parênteses dentro do negrito e texto livre depois dele —
# `| **4.3 / 4.4** |`, `| **4.1 (technical)** |`, `| **4.4** (reendereçada da 4.1) |`.
# Só o que está no negrito é Stage dona: a origem de um reendereçamento fica fora dele.
_LINHA_LACUNA = re.compile(
    r"^\s*\|\s*\*\*\s*(\d+\.\d+(?:\s*/\s*\d+\.\d+)*)(?:\s*\([^)|]*\))?\s*\*\*[^|]*\|"
)
_FECHADA = re.compile(
    r"fechada pelas? stages? (\d+\.\d+(?:\s*(?:/|,|\be\b)\s*\d+\.\d+)*)", re.IGNORECASE
)
_NUMERO_STAGE = re.compile(r"\d+\.\d+")
_LINHA_STAGE = re.compile(r"^\|\s*`(\d+\.\d+)-[^`]+`\s*\|")


@dataclass(frozen=True)
class Frontmatter:
    """O frontmatter parseado (ou o erro) e o corpo que vem depois dele."""

    dados: dict[str, object] | None
    erro: str | None
    corpo: str
    linha_corpo: int  # número (1-based) da primeira linha do corpo


def ler_frontmatter(texto: str) -> Frontmatter:
    """Separa o bloco entre os dois primeiros `---` e o parseia com `yaml.safe_load`."""
    linhas = texto.splitlines()
    if not linhas or linhas[0].strip() != "---":
        return Frontmatter(None, "frontmatter ausente (o arquivo não abre com `---`)", texto, 1)
    fim = next((i for i in range(1, len(linhas)) if linhas[i].strip() == "---"), None)
    if fim is None:
        return Frontmatter(None, "frontmatter sem o `---` de fechamento", texto, 1)
    corpo = "\n".join(linhas[fim + 1 :])
    try:
        dados = yaml.safe_load("\n".join(linhas[1:fim]))
    except yaml.YAMLError as exc:
        marca = getattr(exc, "problem_mark", None)
        onde = f" (linha {marca.line + 2})" if marca is not None else ""
        problema = getattr(exc, "problem", None) or str(exc).splitlines()[0]
        return Frontmatter(None, f"frontmatter não é YAML válido{onde}: {problema}", corpo, fim + 2)
    if not isinstance(dados, dict):
        return Frontmatter(None, "frontmatter não é um mapeamento YAML", corpo, fim + 2)
    return Frontmatter(dados, None, corpo, fim + 2)


# --- ADRs ----------------------------------------------------------------------


def problemas_adr(repo_root: Path) -> list[str]:
    """Regras 1–4 sobre `docs/adr/*.md`."""
    saida: list[str] = []
    donos: dict[str, list[str]] = defaultdict(list)
    for caminho in sorted((repo_root / ADR_DIR).glob("*.md")):
        rel = caminho.relative_to(repo_root).as_posix()
        fm = ler_frontmatter(caminho.read_text(encoding="utf-8-sig"))
        if fm.dados is None:
            saida.append(f"{rel}: {fm.erro}")
            continue
        nome = _ADR_ARQUIVO.match(caminho.name)
        if nome is None:
            saida.append(f"{rel}: nome fora do padrão `N_M_NNNN-<slug>.md`")
            continue
        adr_id = fm.dados.get("adr_id")
        if not isinstance(adr_id, str) or not _ADR_ID.match(adr_id):
            saida.append(f'{rel}: `adr_id` ausente ou fora do formato "N.M.NNNN": {adr_id!r}')
            continue
        esperado = ".".join(nome.groups())
        if adr_id != esperado:
            saida.append(
                f"{rel}: `adr_id` {adr_id!r} não bate com o prefixo do nome (esperado {esperado!r})"
            )
            continue
        donos[adr_id].append(rel)
    for adr_id, arquivos in sorted(donos.items()):
        if len(arquivos) > 1:
            saida.append(
                f"`adr_id` {adr_id!r} repetido em {len(arquivos)} ADRs: {', '.join(arquivos)}"
                " — renumere o mais novo para o próximo id livre"
            )
    return saida


# --- docs de domínio -----------------------------------------------------------


def stages_done(roadmap: str) -> set[str]:
    """Os `N.M` com status `done` na Tabela de Stages (coluna "Status")."""
    linhas = roadmap.splitlines()
    try:
        inicio = linhas.index("## Tabela de Stages")
    except ValueError:
        return set()
    feitas: set[str] = set()
    coluna: int | None = None
    for linha in linhas[inicio + 1 :]:
        if linha.startswith("## "):
            break
        if not linha.startswith("|"):
            continue
        celulas = [c.strip() for c in linha.strip().strip("|").split("|")]
        if coluna is None:
            if "Status" in celulas:
                coluna = celulas.index("Status")
            continue
        m = _LINHA_STAGE.match(linha)
        if m and len(celulas) > coluna and celulas[coluna] == "done":
            feitas.add(m.group(1))
    return feitas


def linhas_de_prosa(corpo: str) -> list[tuple[int, str]]:
    """(índice, linha) do corpo fora de blocos de código cercados — exemplo citado não conta."""
    prosa: list[tuple[int, str]] = []
    dentro_de_cerca = False
    for i, linha in enumerate(corpo.splitlines()):
        if _CERCA.match(linha):
            dentro_de_cerca = not dentro_de_cerca
        elif not dentro_de_cerca:
            prosa.append((i, linha))
    return prosa


def links_relativos(corpo: str, primeira_linha: int) -> list[tuple[int, str]]:
    """(linha, alvo) de cada link relativo do corpo, fora de código cercado ou inline."""
    achados: list[tuple[int, str]] = []
    for i, linha in linhas_de_prosa(corpo):
        sem_codigo = re.sub(r"`[^`\n]*`", "", linha)
        definicao = _DEFINICAO.match(linha)
        alvos = [m.group(1) for m in _LINK.finditer(sem_codigo)]
        if definicao is not None:
            alvos.append(definicao.group(1))
        for alvo in alvos:
            if alvo.startswith("#") or _ESQUEMA.match(alvo):
                continue
            achados.append((primeira_linha + i, alvo.split("#", 1)[0]))
    return achados


def _referencias(caminho: Path, rel: str, dados: dict[str, object]) -> tuple[set[Path], list[str]]:
    """Regra 5: os caminhos do `references`, resolvidos, e as violações."""
    cruas = dados.get("references") or []
    if not isinstance(cruas, list) or not all(isinstance(r, str) for r in cruas):
        return set(), [f"{rel}: `references` tem de ser uma lista de caminhos"]
    saida: list[str] = []
    resolvidas: set[Path] = set()
    for ref in cruas:
        alvo = (caminho.parent / ref).resolve()
        if not alvo.exists():
            saida.append(f"{rel}: `references` aponta para {ref!r}, que não existe")
        resolvidas.add(alvo)
    return resolvidas, saida


def _links(
    caminho: Path, rel: str, fm: Frontmatter, referencias: set[Path], pasta_adr: Path
) -> list[str]:
    """Regras 6 e 7: link que não resolve; ADR linkado fora do `references`."""
    saida: list[str] = []
    fora: dict[str, int] = {}
    for linha, alvo_rel in links_relativos(fm.corpo, fm.linha_corpo):
        alvo = (caminho.parent / alvo_rel).resolve()
        if not alvo.exists():
            saida.append(f"{rel}:{linha}: link para {alvo_rel!r}, que não existe")
        elif alvo.parent == pasta_adr and alvo not in referencias:
            fora.setdefault(alvo.name, linha)

    saida.extend(
        f"{rel}:{linha}: ADR {nome} linkado no corpo e ausente do `references`"
        for nome, linha in sorted(fora.items())
    )
    return saida


def _texto_de_lacunas(corpo: str) -> str:
    """O corpo com código cercado e linhas de tabela de lacunas em branco, mesmas linhas.

    A linha de tabela tem a regra própria (`_linha_de_tabela`); a cerca é exemplo citado.
    Linhas em branco no lugar mantêm a contagem e cortam a menção que tentasse atravessá-las.
    """
    linhas = [""] * len(corpo.splitlines())
    for i, linha in linhas_de_prosa(corpo):
        if _LINHA_LACUNA.match(linha) is None:
            linhas[i] = linha
    return "\n".join(linhas)


def _lacunas(rel: str, fm: Frontmatter, feitas: set[str]) -> list[str]:
    """Regra 8: lacuna aberta endereçada a Stage `done`; menção livre é proibida (issue #158)."""
    saida: list[str] = []
    texto = _texto_de_lacunas(fm.corpo)
    for m in _MENCAO.finditer(texto):
        linha = fm.linha_corpo + texto.count("\n", 0, m.start())
        listadas = _NUMERO_STAGE.findall(m.group(1))
        fechadas = [s for s in listadas if s in feitas]
        normalizada = re.sub(r"[\s*_`>]+", " ", m.group(0))
        if _CANONICA.match(normalizada):
            if fechadas:
                saida.append(
                    f"{rel}:{linha}: lacuna para a Stage {m.group(1)} aberta,"
                    f" mas {', '.join(fechadas)} já está done — feche-a no lugar"
                    " ou reenderece o que sobrou"
                )
            continue
        verbo = "estão" if len(fechadas) > 1 else "está"
        done = f" ({', '.join(fechadas)} já {verbo} done)" if fechadas else ""
        saida.append(
            f'{rel}:{linha}: menção livre de lacuna "{normalizada}"{done} — reescreva na'
            ' marca canônica: "Lacuna para o concept da Stage N.M" se aberta,'
            ' "Lacuna fechada pela Stage N.M (fonte)" se fechada'
        )
    for i, texto_linha in linhas_de_prosa(fm.corpo):
        saida.extend(_linha_de_tabela(rel, fm.linha_corpo + i, texto_linha, feitas))
    return saida


def _linha_de_tabela(rel: str, linha: int, texto: str, feitas: set[str]) -> list[str]:
    """Regra 8 na tabela de lacunas: Stage dona `done` sem "fechada pela Stage N.M" na linha."""
    m = _LINHA_LACUNA.match(texto)
    if m is None:
        return []
    donas = _NUMERO_STAGE.findall(m.group(1))
    fechadas = {s for f in _FECHADA.finditer(texto) for s in _NUMERO_STAGE.findall(f.group(1))}
    pendentes = [s for s in donas if s in feitas and s not in fechadas]
    if not pendentes:
        return []
    return [
        f"{rel}:{linha}: linha da tabela de lacunas da Stage {m.group(1)} sem"
        f' "fechada pela Stage {", ".join(pendentes)}", mas já está done — feche-a no lugar'
        " ou reenderece a Stage dona"
    ]


def problemas_dominio(repo_root: Path, feitas: set[str]) -> list[str]:
    """Regras 5–8 sobre `docs/domain/**/*.md`."""
    saida: list[str] = []
    pasta_adr = (repo_root / ADR_DIR).resolve()
    for caminho in sorted((repo_root / DOMAIN_DIR).rglob("*.md")):
        rel = caminho.relative_to(repo_root).as_posix()
        fm = ler_frontmatter(caminho.read_text(encoding="utf-8-sig"))
        if fm.dados is None:
            saida.append(f"{rel}: {fm.erro}")
            continue
        referencias, erros = _referencias(caminho, rel, fm.dados)
        saida.extend(erros)
        saida.extend(_links(caminho, rel, fm, referencias, pasta_adr))
        saida.extend(_lacunas(rel, fm, feitas))
    return saida


def problemas(repo_root: Path) -> list[str]:
    """Todas as violações, como `arquivo[:linha]: motivo`; `FATAL:` se o roadmap falta."""
    caminho_roadmap = repo_root / ROADMAP
    if not caminho_roadmap.exists():
        return [f"FATAL: {ROADMAP.as_posix()} não existe"]
    feitas = stages_done(caminho_roadmap.read_text(encoding="utf-8-sig"))
    if not feitas:
        return [f"FATAL: nenhuma Stage `done` legível na Tabela de Stages de {ROADMAP.as_posix()}"]
    return problemas_adr(repo_root) + problemas_dominio(repo_root, feitas)


def main() -> int:
    """Valida o frontmatter dos ADRs e dos docs de domínio."""
    parser = argparse.ArgumentParser(
        description=(
            "Valida o frontmatter YAML e o adr_id dos ADRs e o frontmatter, os links e as"
            " lacunas dos docs de domínio (issue #102)"
        )
    )
    parser.add_argument("--repo", default=".", help="Raiz do repositório (padrão: .)")
    args = parser.parse_args()

    achados = problemas(Path(args.repo).resolve())
    if achados and achados[0].startswith("FATAL:"):
        print(f"check_doc_frontmatter: {achados[0]}", file=sys.stderr)
        return 2
    if achados:
        print(
            f"check_doc_frontmatter: {len(achados)} problema(s) — CONVENTIONS §2,"
            " ADR 0.0.0003, ADR 0.0.0015:\n",
            file=sys.stderr,
        )
        for achado in achados:
            print(f"  {achado}", file=sys.stderr)
        return 1
    print(
        "check_doc_frontmatter: ADRs e docs de domínio com frontmatter YAML válido,"
        " adr_id único e coerente com o nome, links e references em ordem."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
