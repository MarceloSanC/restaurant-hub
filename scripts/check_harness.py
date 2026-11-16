"""Valida o harness do Claude Code: frontmatter, estrutura de skills, subagentes e hooks.

Uso: python scripts/check_harness.py   (exit 0 = ok, 1 = achados)

O Claude Code não reporta erro de frontmatter: YAML inválido carrega a skill "with no fields
set", campo desconhecido é ignorado em silêncio, e a descrição é truncada no listing em 1.536
caracteres (docs: code.claude.com/docs/en/skills, /sub-agents). Caso real que motivou o script:
` #` num valor sem aspas é comentário YAML — a descrição da `issue-audit` era lida com 165 dos
1.491 caracteres, sem aviso (issue #56).

Estrutura (issue #65, port da FF#161) — o que a doc oficial só recomenda
(platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices):

- corpo do `SKILL.md` ≤ 500 linhas ("Keep SKILL.md body under 500 lines");
- `reference/`/`references/` um nível só ("Keep references one level deep from SKILL.md"):
  sem subpasta, e todo arquivo dali citado pelo `SKILL.md`;
- arquivo de referência > 100 linhas com sumário no topo ("For reference files longer than
  100 lines, include a table of contents at the top");
- link relativo e `scripts/<x>.py` citados no `SKILL.md` e nos arquivos de `reference/`
  existem (o link, relativo ao arquivo que o traz ou à raiz do repo; o script, à skill ou à
  raiz);
- âncora (`#...`) de link para Markdown casa com um título do arquivo-alvo (issue #196): do
  `SKILL.md` para `reference/`, de volta (`../SKILL.md#...`) e dentro do próprio arquivo, que
  é o caso do sumário. A regra de slug é a do GitHub, descrita em `_slug`. Link dentro de
  bloco de código cercado é exemplo e não conta; script citado ali conta;
- `skills:` de subagente aponta skill existente; script de hook em `.claude/settings.json`
  (`${CLAUDE_PROJECT_DIR}/...`) existe.

Débito anterior à regra fica em `KNOWN_DEBT` (chave → motivo, issue); entrada que não
ocorre mais reprova — a lista só encolhe.
"""

from __future__ import annotations

import json
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any
from urllib.parse import unquote

import yaml

ROOT = Path(__file__).resolve().parent.parent
DESC_CAP = 1536
SKILL_BODY_CAP = 500
TOC_THRESHOLD = 100
TOC_WINDOW = 30  # linhas do topo em que o sumário precisa aparecer
REFERENCE_DIRS = ("reference", "references")
PROJECT_DIR = "${CLAUDE_PROJECT_DIR}/"
SKILL_FIELDS = {
    "name", "description", "when_to_use", "argument-hint", "arguments",
    "disable-model-invocation", "user-invocable", "allowed-tools", "disallowed-tools",
    "model", "effort", "context", "agent", "background", "hooks", "paths", "shell",
    "metadata", "license", "compatibility",
}  # fmt: skip
AGENT_FIELDS = {
    "name", "description", "tools", "disallowedTools", "model", "permissionMode", "maxTurns",
    "skills", "mcpServers", "hooks", "memory", "background", "omitClaudeMd", "effort",
    "isolation", "color", "initialPrompt", "experimental",
}  # fmt: skip
# Débito de estrutura anterior à regra (#65): chave do achado → (motivo, issue).
# Vazio desde a #162, que trouxe `stage-audit` e `issue-audit` para o teto de 500 linhas.
KNOWN_DEBT: dict[str, tuple[str, int]] = {}

_TOC_HEADING = re.compile(r"#{1,6}\s+(sumário|índice|conteúdo|contents|table of contents)\b", re.I)
_ANCHOR_LINK = re.compile(r"\]\(#[^)\s]+\)")
_MD_LINK = re.compile(r"\]\(([^)#\s]*)(?:#([^)\s]*))?\)")  # (alvo, âncora)
_SCRIPT_REF = re.compile(r"(?<![\w/.-])((?:\.claude/skills/[\w-]+/)?scripts/[\w./-]+\.py)\b")
_FENCE = re.compile(r"[ \t]*(`{3,}|~{3,})(.*)")
_HEADING = re.compile(r" {0,3}#{1,6}[ \t]+(.*?)(?:[ \t]+#+)?[ \t]*$")
_INLINE_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_WORD_CATEGORIES = ("L", "M", "Nd", "Pc")  # letra, marca (o U+FE0F do emoji), dígito e `_`


def _frontmatter(text: str) -> tuple[str, dict[str, Any]] | str:
    if not text.startswith("---"):
        return "sem frontmatter (o `---` de abertura precisa ser a 1ª linha)"
    parts = text.split("---", 2)
    if len(parts) < 3:  # noqa: PLR2004 — abertura + corpo do YAML + resto
        return "frontmatter sem `---` de fechamento"
    try:
        data = yaml.safe_load(parts[1])
    except yaml.YAMLError as exc:
        return f"YAML inválido: {str(exc).splitlines()[0]}"
    if not isinstance(data, dict):
        return "frontmatter não é um mapa YAML"
    return parts[1], data


def _raw_value(raw_yaml: str, key: str) -> str:
    for line in raw_yaml.splitlines():
        if line.startswith(f"{key}:"):
            return line.split(":", 1)[1].strip()
    return ""


def check_file(path: Path, allowed: set[str], required: tuple[str, ...]) -> list[str]:
    parsed = _frontmatter(path.read_text(encoding="utf-8"))
    if isinstance(parsed, str):
        return [parsed]
    raw_yaml, data = parsed
    problems = [f"campo obrigatório ausente: `{k}`" for k in required if not data.get(k)]
    problems += [
        f"campo desconhecido (ignorado em silêncio): `{k}`" for k in data if k not in allowed
    ]
    desc = str(data.get("description") or "")
    raw = _raw_value(raw_yaml, "description")
    plain = raw and not raw.startswith(('"', "'", ">", "|"))
    if plain and " #" in raw:  # YAML: ` #` em escalar sem aspas abre comentário
        problems.append(f"descrição truncada pelo YAML em ` #` ({len(desc)} chars lidos)")
    total = len(desc) + len(str(data.get("when_to_use") or ""))
    if total > DESC_CAP:
        problems.append(
            f"description+when_to_use = {total} > {DESC_CAP} (cauda cortada no listing)"
        )
    return problems


def check_overrides(settings: Path, skill_names: set[str]) -> list[str]:
    if not settings.exists():
        return []
    overrides = json.loads(settings.read_text(encoding="utf-8")).get("skillOverrides", {})
    return [
        f"skillOverrides aponta skill inexistente: `{n}`" for n in overrides if n not in skill_names
    ]


def _body(text: str) -> str:
    """Texto depois da linha `---` que fecha o frontmatter (o texto inteiro se não houver)."""
    parts = text.split("---", 2)
    if text.startswith("---") and len(parts) == 3:  # noqa: PLR2004
        return parts[2].removeprefix("\n")
    return text


def has_toc(text: str) -> bool:
    """Sumário no topo: título de sumário ou ≥ 2 links para âncoras nas primeiras linhas."""
    top = text.splitlines()[:TOC_WINDOW]
    anchors = sum(len(_ANCHOR_LINK.findall(line)) for line in top)
    return any(_TOC_HEADING.match(line.strip()) for line in top) or anchors >= 2  # noqa: PLR2004


def _prose(text: str) -> str:
    """O texto sem os blocos de código cercados (``` ou ~~~), que não rendem link nem título."""
    kept: list[str] = []
    fence = ""
    for line in text.splitlines():
        match = _FENCE.match(line)
        if fence:
            # fecha com a mesma marca, de tamanho igual ou maior, e mais nada na linha
            if match and match[1].startswith(fence) and not match[2].strip():
                fence = ""
        elif match and not (match[1][0] == "`" and "`" in match[2]):  # ```a``` é código em linha
            fence = match[1]
        else:
            kept.append(line)
    return "\n".join(kept)


def _slug(title: str) -> str:
    """Âncora que o GitHub gera para um título, sem o sufixo de título repetido.

    Minúsculas (Unicode: `NÃO` vira `não`); sai tudo que não é letra, marca combinante,
    dígito, `_`, hífen ou espaço; cada espaço vira um hífen. Por isso `Literal ≠ espírito`
    dá `literal--espírito`, com dois hífens: o `≠` some e os dois espaços ficam. De um link
    no título sobra só o texto. Fonte: docs.github.com, "Basic writing and formatting
    syntax" § "Section links". Conferida em 2026-11-16 contra os ids que o GitHub gerou
    (`gh api .../contents/<arquivo> -H "Accept: application/vnd.github.html+json"`) para
    todos os `.md` de `.claude/skills/` e de `docs/` (32 arquivos, 458 títulos, nenhum
    divergente de `heading_anchors`).

    Limite conhecido: a ênfase com sublinhado (`_assim_`), que o GitHub desfaz, aqui mantém
    os `_`. Nenhum título de skill usa; se usar, o link certo reprova (vermelho, não calado).
    """
    text = _INLINE_LINK.sub(r"\1", title).lower()
    kept = (
        char
        for char in text
        if char in "- " or unicodedata.category(char).startswith(_WORD_CATEGORIES)
    )
    return "".join(kept).replace(" ", "-")


def heading_anchors(text: str) -> set[str]:
    """Âncoras dos títulos ATX (`# ...`) do texto; o título repetido ganha `-1`, `-2`...

    O frontmatter sai antes (o `# ...` ali é comentário YAML, não título).
    """
    anchors: set[str] = set()
    seen: dict[str, int] = {}
    for line in _prose(_body(text)).splitlines():
        match = _HEADING.match(line)
        if not match:
            continue
        slug = _slug(match[1])
        anchors.add(f"{slug}-{seen[slug]}" if slug in seen else slug)
        seen[slug] = seen.get(slug, 0) + 1
    return anchors


def _existing(target: str, bases: tuple[Path, ...]) -> Path | None:
    return next((base / target for base in bases if (base / target).exists()), None)


def _has_anchor(dest: Path, anchor: str) -> bool:
    """Só Markdown tem título a conferir: âncora em outro tipo de alvo (`x.py#L10`) passa."""
    return dest.suffix != ".md" or anchor in heading_anchors(dest.read_text(encoding="utf-8"))


def check_citations(path: Path, key: str, skill_dir: Path, root: Path) -> dict[str, str]:
    """Arquivo, script e âncora citados em `path` (o `SKILL.md` ou um `reference/*.md`).

    `key` prefixa a chave do achado. O script citado vale em qualquer ponto do texto, bloco
    de código incluso (é onde o comando aparece); o link só vale fora dele.
    """
    text = _body(path.read_text(encoding="utf-8"))
    found: dict[str, str] = {}
    for script in sorted(set(_SCRIPT_REF.findall(text))):
        if _existing(script, (skill_dir, root)) is None:
            found[f"{key}::missing:{script}"] = f"cita `{script}`, que não existe"
    for target, anchor in sorted(set(_MD_LINK.findall(_prose(text)))):
        # com `:` é URL; sem `/` nem `.` é placeholder de exemplo (`[texto](caminho)`)
        if ":" in target or (target and "/" not in target and "." not in target):
            continue
        dest = _existing(target, (path.parent, root)) if target else path
        if dest is None:
            found[f"{key}::missing:{target}"] = f"cita `{target}`, que não existe"
        elif anchor and not _has_anchor(dest, unquote(anchor)):
            found[f"{key}::anchor:{target}#{anchor}"] = (
                f"âncora `{target}#{anchor}` não casa com título de `{dest.name}`"
            )
    return found


def check_skill_layout(skill_md: Path, root: Path) -> dict[str, str]:
    """`{chave: achado}` de estrutura de uma skill; a chave é estável (para `KNOWN_DEBT`)."""
    skill_dir = skill_md.parent
    rel = skill_dir.relative_to(root).as_posix()
    text = skill_md.read_text(encoding="utf-8")
    body = _body(text)
    found: dict[str, str] = {}
    lines = len(body.splitlines())
    if lines > SKILL_BODY_CAP:
        found[f"{rel}::body"] = f"corpo do SKILL.md com {lines} linhas > {SKILL_BODY_CAP}"
    for name in REFERENCE_DIRS:
        ref_dir = skill_dir / name
        if not ref_dir.is_dir():
            continue
        for sub in sorted(p for p in ref_dir.iterdir() if p.is_dir()):
            found[f"{rel}/{name}/{sub.name}::depth"] = (
                f"`{name}/{sub.name}/`: referência a mais de um nível do SKILL.md"
            )
        for ref in sorted(ref_dir.glob("*.md")):
            ref_rel = f"{name}/{ref.name}"
            if ref_rel not in body:
                found[f"{rel}/{ref_rel}::unlinked"] = (
                    f"`{ref_rel}` não é citado pelo SKILL.md (precisa de link direto)"
                )
            ref_text = ref.read_text(encoding="utf-8")
            if len(ref_text.splitlines()) > TOC_THRESHOLD and not has_toc(ref_text):
                found[f"{rel}/{ref_rel}::toc"] = (
                    f"`{ref_rel}` tem > {TOC_THRESHOLD} linhas e não abre com sumário"
                )
            found |= check_citations(ref, f"{rel}/{ref_rel}", skill_dir, root)
    found |= check_citations(skill_md, rel, skill_dir, root)
    return found


def check_agent_skills(agent: Path, skill_names: set[str]) -> list[str]:
    parsed = _frontmatter(agent.read_text(encoding="utf-8"))
    if isinstance(parsed, str):
        return []  # o `check_file` já reporta
    skills = parsed[1].get("skills") or []
    if isinstance(skills, str):
        skills = [s.strip() for s in skills.split(",")]
    return [f"`skills:` aponta skill inexistente: `{s}`" for s in skills if s not in skill_names]


def _strings(node: object) -> list[str]:
    if isinstance(node, str):
        return [node]
    if isinstance(node, dict):
        return [s for value in node.values() for s in _strings(value)]
    if isinstance(node, list):
        return [s for item in node for s in _strings(item)]
    return []


def check_hook_scripts(settings: Path, root: Path) -> list[str]:
    """Todo `${CLAUDE_PROJECT_DIR}/<arquivo>` dos hooks existe (hook sem arquivo falha calado)."""
    if not settings.exists():
        return []
    hooks = json.loads(settings.read_text(encoding="utf-8")).get("hooks", {})
    paths = {
        token[len(PROJECT_DIR) :].strip("\"'")
        for value in _strings(hooks)
        for token in value.split()
        if token.startswith(PROJECT_DIR)
    }
    return [
        f"hook aponta arquivo inexistente: `{p}`" for p in sorted(paths) if not (root / p).is_file()
    ]


def reconcile_debt(found: dict[str, str], debt: dict[str, tuple[str, int]]) -> list[str]:
    """Achados fora do débito + débito morto + débito sem motivo/issue (que não tolera nada)."""
    owned = {key for key, (motivo, issue) in debt.items() if motivo.strip() and issue > 0}
    problems = [f"{key.split('::')[0]}: {text}" for key, text in found.items() if key not in owned]
    for key, (motivo, issue) in debt.items():
        if not motivo.strip() or issue <= 0:
            problems.append(f"KNOWN_DEBT `{key}` sem motivo ou issue (débito sem dono)")
        elif key not in found:
            problems.append(f"KNOWN_DEBT `{key}` não ocorre mais (remover a entrada)")
    return problems


def main() -> int:
    findings: list[str] = []
    skills = sorted((ROOT / ".claude" / "skills").glob("*/SKILL.md"))
    skill_names = {p.parent.name for p in skills}
    layout: dict[str, str] = {}
    for path in skills:
        findings += [f"{path.relative_to(ROOT)}: {p}" for p in check_file(path, SKILL_FIELDS, ())]
        layout |= check_skill_layout(path, ROOT)
    findings += reconcile_debt(layout, KNOWN_DEBT)
    for path in sorted((ROOT / ".claude" / "agents").glob("*.md")):
        found = check_file(path, AGENT_FIELDS, ("name", "description"))
        found += check_agent_skills(path, skill_names)
        findings += [f"{path.relative_to(ROOT)}: {p}" for p in found]
    settings = ROOT / ".claude" / "settings.json"
    findings += check_overrides(settings, skill_names)
    findings += check_hook_scripts(settings, ROOT)
    for line in findings:
        print(line)
    print(f"check_harness: {len(findings)} achado(s)", file=sys.stderr)
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
