"""O gate de citação ao roadmap, contra violadores plantados (issue #79, ADR 0.0.0011).

**O que o gate protege é o alvo de uma citação.** Doc que cita o roadmap por
número de linha aponta, um PR depois, para outra coisa: o roadmap cresce no meio
(Tabela de Issues acima dos blocos de Step) e nada reclama. As duas regras são
"nenhum número de linha depois de uma referência ao roadmap" e "toda âncora
`§Seção › rótulo` resolve dentro da seção".

**Os violadores são plantados num repositório de mentira** em `tmp_path` — o
script recebe `repo_root`, então dá para exercitar cada forma de citação que já
apareceu no corpus (lista, faixa, barra, parênteses, continuação depois de `;`)
sem tocar nos docs reais. Um teste roda contra o repositório real: é ele que
trava a conversão desta issue.
"""

import importlib.util
import pathlib
import sys
import types

import pytest

pytestmark = pytest.mark.unit

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_SCRIPT = _REPO_ROOT / "scripts" / "check_roadmap_citations.py"


def _carregar_script() -> types.ModuleType:
    """Importa `scripts/check_roadmap_citations.py` sem mexer no `sys.path`."""
    spec = importlib.util.spec_from_file_location("check_roadmap_citations", _SCRIPT)
    assert spec is not None and spec.loader is not None
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


gate = _carregar_script()

_SAIDA_FATAL = 2

_ROADMAP = """\
# Roadmap

## Visão geral

```mermaid
  S31 --> S41
```

## Tabela de Stages

| Stage | Título |
|---|---|
| `4.1-scheduling-domain` | Domínio da escala |

## Tabela de Issues

| Issue | Título |
|---|---|
| [#56](https://example.invalid/56) | Harness |

## Detalhamento por Step

### Step 4 — Escala manual

- **Resultado de negócio:** gerente monta a escala.

> **Nota (2026-09-14, revista em 2026-09-26): gate de domínio.**

#### Stage 4.1 — `4.1-scheduling-domain`

> **Nota (2026-09-26): `depends_on` corrigido.**

**Descrição humana:** modelar Escala.

```yaml
definition_of_done:
  - "montagem da escala"
```

#### Stage 4.2 — `4.2-validation-policies`

**Escopo exclusivo:** só na 4.2.

### Step 5 — Auto-preenchimento

## Lacunas conhecidas

- **Formato da imagem da escala** — ADR na 4.7.
"""


def _repo(tmp_path: pathlib.Path, docs: dict[str, str], roadmap: str = _ROADMAP) -> pathlib.Path:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "roadmap.md").write_text(roadmap, encoding="utf-8")
    for caminho, texto in docs.items():
        destino = tmp_path / caminho
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(texto, encoding="utf-8")
    return tmp_path


def _problemas(tmp_path: pathlib.Path, texto: str, nome: str = "docs/x.md") -> list[str]:
    return list(gate.problemas(_repo(tmp_path, {nome: texto})))


def test_o_repositorio_real_cita_o_roadmap_so_por_ancora_que_resolve() -> None:
    assert gate.problemas(_REPO_ROOT) == []


# --- Regra 1: número de linha ---------------------------------------------------


@pytest.mark.parametrize(
    "texto",
    [
        "Período (`roadmap.md` 1362; sponsor).",
        "o guard (`docs/roadmap.md:366`) é o desenho",
        "- [`roadmap.md`](../roadmap.md) 1368–1371 (the three-entity file list",
        "`roadmap.md` Stage 4.2 (1421, 1428) closes the list",
        "o fluxo do roadmap (1447, 1463,\n  1514) lê-se como",
        "texto do roadmap 2.4 (linha 366); ADR",
        "- [`roadmap.md`](../roadmap.md) — §Step 4; Step 5 (1577–1625).",
        '`roadmap.md` §Stage 4.1 › "Descrição humana", 1421/1428 (ex-HALT)',
        "delegado pelo roadmap 1902 (§3.8)",
        "`roadmap.md` 1362 pede o evento de publicação",
        "the roadmap (lines 820–824).",
    ],
    ids=[
        "simples",
        "dois-pontos",
        "link-e-faixa",
        "stage-e-parenteses",
        "lista-quebrando-linha",
        "linha-por-extenso",
        "depois-de-ponto-e-virgula",
        "barra-depois-de-ancora",
        "sem-extensao",
        "seguido-de-palavra",
        "lines-em-ingles",
    ],
)
def test_numero_de_linha_depois_do_roadmap_reprova(tmp_path: pathlib.Path, texto: str) -> None:
    achados = _problemas(tmp_path, texto)
    assert len(achados) == 1
    assert "número de linha" in achados[0]
    assert achados[0].startswith("docs/x.md:1:")


@pytest.mark.parametrize(
    "texto",
    [
        'Período (`roadmap.md` §Stage 4.1 › "Descrição humana"; sponsor).',
        'roadmap §Stage 4.1 DoD ("ação sem permissão retorna 403").',
        "Reading `roadmap.md` answers the question in 30 seconds.",
        "o roadmap (cópia que duplica), o fluxo com os 16 use cases reais.",
        "`roadmap.md`: Stage 4.1 `done`, nota de 2026-09-26.",
        "roadmap — Issue [#49](https://github.com/o/r/issues/49)",
        "`docs(roadmap): corrigir bloco [1.1/task-08]`",
        "(`roadmap.md` §Stage 4.1 › `definition_of_done`; `.importlinter` 251–277)",
        "roadmap (bloco 4.2); ADRs 4.2.0001–0002 `accepted`",
        "`roadmap.md` §Step 4; `overview.md` 46, 130.",
        'a premissa (`roadmap.md` §"Lacunas conhecidas" › "Formato da imagem da escala")',
        "cabe no roadmap, §12 100% sim, cabe em 3–12 Tasks.",
    ],
    ids=[
        "ancora",
        "numero-entre-aspas",
        "quantidade-seguida-de-palavra",
        "contagem-no-meio-da-frase",
        "stage-e-data",
        "url-de-issue",
        "marca-de-task",
        "outra-fonte-encerra-o-trecho",
        "numero-de-adr",
        "overview-encerra-o-trecho",
        "secao-entre-aspas",
        "porcentagem-e-faixa-pequena",
    ],
)
def test_citacao_por_ancora_e_numeros_que_nao_sao_linha_passam(
    tmp_path: pathlib.Path, texto: str
) -> None:
    assert _problemas(tmp_path, texto) == []


def test_a_linha_do_achado_e_a_da_referencia_ao_roadmap(tmp_path: pathlib.Path) -> None:
    achados = _problemas(tmp_path, "título\n\ntexto\nver `roadmap.md` 1362.\n")
    assert len(achados) == 1
    assert achados[0].startswith("docs/x.md:4:")


# --- Regra 2: âncora -------------------------------------------------------------


@pytest.mark.parametrize(
    "ancora",
    [
        '§Stage 4.1 › "Descrição humana", `definition_of_done`',
        "§Stage 4.1 › nota 2026-09-26",
        '§Step 4 › "Resultado de negócio"',
        "§Step 4 › nota 2026-09-14",
        '§"Tabela de Issues" › #56',
        '§"Tabela de Stages" › `4.1-scheduling-domain`',
        '§"Visão geral" › `S31 --> S41`',
        '§"Lacunas conhecidas" › "Formato da imagem da escala"',
        '§"Stage 4.1 — `4.1-scheduling-domain`"',
        "§Stage 4.2",
        "§Step 5",
    ],
)
def test_ancora_que_existe_no_roadmap_passa(tmp_path: pathlib.Path, ancora: str) -> None:
    assert _problemas(tmp_path, f"Ver `roadmap.md` {ancora}.") == []


@pytest.mark.parametrize(
    ("ancora", "motivo"),
    [
        ("§Stage 9.9", "seção §Stage 9.9 não existe"),
        ("§Step 7", "seção §Step 7 não existe"),
        ('§Stage 4.1 › "Inexistente"', 'rótulo "Inexistente" não existe em §Stage 4.1'),
        ("§Stage 4.1 › `non_goals`", "rótulo `non_goals` não existe em §Stage 4.1"),
        ("§Stage 4.1 › nota 2020-01-01", "rótulo nota 2020-01-01 não existe"),
        ('§"Tabela de Issues" › #57', "rótulo #57 não existe"),
        ('§"Tabela Inexistente" › "x"', 'seção §"Tabela Inexistente" não existe'),
        ('§"Stage 4.9 — `4.9-x`"', "não existe no roadmap"),
    ],
)
def test_ancora_que_nao_resolve_reprova(tmp_path: pathlib.Path, ancora: str, motivo: str) -> None:
    achados = _problemas(tmp_path, f"Ver `roadmap.md` {ancora}.")
    assert len(achados) == 1
    assert motivo in achados[0]


def test_o_rotulo_e_procurado_so_dentro_da_secao(tmp_path: pathlib.Path) -> None:
    """Rótulo de outra seção não resolve: a âncora diz *onde*, não só *o quê*."""
    achados = _problemas(
        tmp_path, 'Ver §Stage 4.1 › "Escopo exclusivo" e §Stage 4.1 › "Resultado de negócio".'
    )
    assert len(achados) == 2  # noqa: PLR2004 — uma por âncora


def test_o_step_engloba_os_blocos_das_suas_stages(tmp_path: pathlib.Path) -> None:
    assert _problemas(tmp_path, 'Ver §Step 4 › "Escopo exclusivo".') == []


def test_um_rotulo_errado_na_lista_reprova_sozinho(tmp_path: pathlib.Path) -> None:
    achados = _problemas(
        tmp_path, 'Ver §Stage 4.1 › "Descrição humana", `nao_existe`, `definition_of_done`.'
    )
    assert len(achados) == 1
    assert "`nao_existe`" in achados[0]


def test_secao_entre_aspas_sem_rotulo_pode_ser_de_outro_doc(tmp_path: pathlib.Path) -> None:
    assert _problemas(tmp_path, 'Ver workforce.md §"Escopo da função".') == []


# --- Escopo da varredura ---------------------------------------------------------


def test_a_secao_7_do_technical_e_registro_historico(tmp_path: pathlib.Path) -> None:
    texto = (
        "# T\n\n## 6. Referências\n\nok\n\n## 7. Execução\n\nremapeado `roadmap.md` 1481→1517.\n"
    )
    assert _problemas(tmp_path, texto, nome="docs/stages/4.1-x/technical.md") == []


def test_antes_da_secao_7_o_technical_e_varrido(tmp_path: pathlib.Path) -> None:
    texto = "# T\n\n## 1. Escopo\n\nver `roadmap.md` 1362.\n\n## 7. Execução\n"
    assert len(_problemas(tmp_path, texto, nome="docs/stages/4.1-x/technical.md")) == 1


def test_a_secao_7_so_e_poupada_no_technical(tmp_path: pathlib.Path) -> None:
    texto = "# C\n\n## 7. Execução\n\nver `roadmap.md` 1362.\n"
    assert len(_problemas(tmp_path, texto, nome="docs/stages/4.1-x/concept.md")) == 1


@pytest.mark.parametrize(
    "nome", ["CLAUDE.md", ".claude/skills/x/SKILL.md", ".github/PULL_REQUEST_TEMPLATE.md"]
)
def test_a_raiz_o_harness_e_o_github_sao_varridos(tmp_path: pathlib.Path, nome: str) -> None:
    assert len(_problemas(tmp_path, "ver `roadmap.md` 1362.", nome=nome)) == 1


def test_o_proprio_roadmap_nao_e_varrido(tmp_path: pathlib.Path) -> None:
    roadmap = _ROADMAP + "\n## Histórico\n\n- citações remapeadas (`roadmap.md` 1362).\n"
    assert gate.problemas(_repo(tmp_path, {}, roadmap=roadmap)) == []


def test_pasta_fora_do_escopo_nao_e_varrida(tmp_path: pathlib.Path) -> None:
    assert _problemas(tmp_path, "ver `roadmap.md` 1362.", nome="htmlcov/x.md") == []


# --- Saída --------------------------------------------------------------------------


def _main(monkeypatch: pytest.MonkeyPatch, repo: pathlib.Path) -> int:
    monkeypatch.setattr(sys, "argv", ["check_roadmap_citations.py", "--repo", str(repo)])
    return int(gate.main())


def test_main_sai_0_quando_tudo_confere(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _main(monkeypatch, _repo(tmp_path, {"docs/x.md": "Ver `roadmap.md` §Stage 4.1."})) == 0
    assert "resolvem" in capsys.readouterr().out


def test_main_sai_1_e_lista_os_achados(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repo(tmp_path, {"docs/x.md": "Ver `roadmap.md` 1362 e §Stage 9.9."})
    assert _main(monkeypatch, repo) == 1
    erro = capsys.readouterr().err
    assert "2 problema(s)" in erro
    assert "docs/x.md:1:" in erro


def test_main_sai_2_sem_roadmap(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "docs").mkdir()
    assert _main(monkeypatch, tmp_path) == _SAIDA_FATAL
    assert "FATAL" in capsys.readouterr().err
