"""O gate de citação a doc de domínio, contra violadores plantados (issue #116, ADR 0.0.0017).

**O que o gate protege é o alvo de uma citação.** Doc que cita `docs/domain/**`
por número de linha aponta, uma edição depois, para outra coisa — uma nota datada
numa seção ou uma linha a mais no `references` do frontmatter desloca tudo abaixo,
e nada reclama. As duas regras são "nenhum número de linha depois de uma
referência a doc de domínio" e "toda âncora `§N.M › rótulo` resolve no doc".

**Os violadores são plantados num repositório de mentira** em `tmp_path`, com um
doc de domínio pequeno. Um teste roda contra o repositório real: é ele que trava
a conversão desta issue.
"""

import importlib.util
import pathlib
import sys
import types

import pytest

pytestmark = pytest.mark.unit

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_SCRIPT = _REPO_ROOT / "scripts" / "check_domain_citations.py"


def _carregar_script() -> types.ModuleType:
    """Importa `scripts/check_domain_citations.py` sem mexer no `sys.path`."""
    spec = importlib.util.spec_from_file_location("check_domain_citations", _SCRIPT)
    assert spec is not None and spec.loader is not None
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


gate = _carregar_script()

_SAIDA_FATAL = 2

_ESCALA = """\
---
title: escala
---

# Domínio scheduling/escala

## 2. Língua ubíqua

| Termo | Definição |
|---|---|
| **Faixas de funcionamento** | As faixas **habilitadas por dia** na escala. |

## 3. Conceitos

### 3.1 Escala

- Toda alocação está **dentro do período** da escala.

### 3.10 Fronteiras

- Staff entra por id.

#### 3.6.1 Sobreposição

- **O que valida:** o mesmo registro com duas alocações cujas faixas se
  sobrepõem. **Configurável:** só o modo.

> **Lacuna fechada pela Stage 4.1:** (a) a **forma interna** do
> `TimeRange` — par de instantes.

```markdown
## 9. Título dentro de bloco cercado
```

## 6. Registro

### Lacunas para o concept de cada Stage (consolidado)

| Stage | Lacuna |
|---|---|
| **4.1** | `Schedule` como raiz do agregado — confirmar (§3.1) |
"""

_EQUIPE = """\
---
title: equipe
---

# Domínio staff/equipe

## 3. Conceitos

### 3.8 Login opcional

- O registro pode ter login.
"""


def _repo(
    tmp_path: pathlib.Path, docs: dict[str, str], dominio: dict[str, str] | None = None
) -> pathlib.Path:
    dominio = (
        {"docs/domain/scheduling/escala.md": _ESCALA, "docs/domain/staff/equipe.md": _EQUIPE}
        if dominio is None
        else dominio
    )
    for caminho, texto in {**dominio, **docs}.items():
        destino = tmp_path / caminho
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(texto, encoding="utf-8")
    return tmp_path


def _problemas(tmp_path: pathlib.Path, texto: str, nome: str = "docs/x.md") -> list[str]:
    return list(gate.problemas(_repo(tmp_path, {nome: texto})))


def test_o_repositorio_real_cita_os_docs_de_dominio_so_por_ancora_que_resolve() -> None:
    assert gate.problemas(_REPO_ROOT) == []


def test_o_repositorio_real_tem_ancoras_a_conferir() -> None:
    """O verde acima não é vazio: o corpus real tem centenas de âncoras a docs de domínio."""
    docs, _ = gate.docs_de_dominio(_REPO_ROOT)
    regex = gate.regex_de_referencia(list(docs))
    ancoras = 0
    for arquivo in gate.arquivos(_REPO_ROOT):
        texto = gate.texto_varrido(arquivo)
        for ref in regex.finditer(texto):
            ancoras += len(gate.cadeia_de_ancoras(texto, ref.end()))
    assert ancoras > 300  # noqa: PLR2004 — 414 na conversão da #116


# --- Regra 1: número de linha ---------------------------------------------------


@pytest.mark.parametrize(
    "texto",
    [
        "pelo editor (`escala.md` 108).",
        "o guard (`docs/domain/scheduling/escala.md:171`) é o desenho",
        "- [`escala.md`](../domain/scheduling/escala.md) 481–482 (o modo",
        "`escala.md` 476, 481–482, que cobria",
        '`escala.md` 344: *"não ocupa duas vagas"*',
        "- [`escala.md`](../domain/scheduling/escala.md)\n  §2, §3.1 (a lacuna, line 224), §6.",
        '`escala.md` §3.1 (linha 166: *"O período"*)',
        "`escala.md` §3.1 (l. 166) diz",
        "ver [escala](../domain/scheduling/escala.md#L171)",
        "equipe §3.8 (linhas 470–480)",
        "o doc `equipe.md` 120; e mais",
        "ver [`escala.md`](../domain/scheduling/escala.md#L171) para a regra",
    ],
    ids=[
        "simples",
        "dois-pontos-no-caminho",
        "link-e-faixa",
        "lista",
        "seguido-de-citacao",
        "linha-dentro-da-lista-de-secoes",
        "linha-por-extenso",
        "l-ponto-abreviado",
        "fragmento-de-linha-no-link",
        "nome-sem-extensao-com-secao",
        "outro-doc-de-dominio",
        "fragmento-de-linha-no-link-com-o-nome-do-arquivo",
    ],
)
def test_numero_de_linha_depois_de_doc_de_dominio_reprova(
    tmp_path: pathlib.Path, texto: str
) -> None:
    achados = _problemas(tmp_path, texto)
    assert len(achados) == 1, achados
    assert "número de linha" in achados[0]
    assert achados[0].startswith("docs/x.md:1:")


@pytest.mark.parametrize(
    "texto",
    [
        '(`escala.md` §3.1 › "Toda alocação está dentro do período"; sponsor).',
        '`escala.md` §3.1 ("ação sem permissão retorna 403").',
        "O `escala.md` tem 16 ADRs no `references` e 30 seções.",
        "`escala.md`: Stage 4.1 `done`, nota de 2026-09-26, issue #116.",
        "(`escala.md` §3.1; `.importlinter` 251–277)",
        "`escala.md` §3.1; ADR 4.1.0009 47–51.",
        "`escala.md` §3.1; `overview.md` 46, 130.",
        "Ver `escala.md` §3.1. Em 2025 eram 120, hoje 130.",
        "Ver `escala.md` §3.1\n\nNo parágrafo seguinte, 120, 130.",
        "equipe §3.8: R17 responde 409, como antes",
        "keywords: [domain, escala, equipe, 2026]",
        "o `escala.md` §3.1 e o concept §5.2 (linha 40 do concept)",
        '`escala.md` §3.1 (o ADR antigo dizia *"§6 (line 1086)"*)',
    ],
    ids=[
        "ancora",
        "numero-entre-aspas",
        "quantidade-seguida-de-palavra",
        "stage-data-e-issue",
        "outra-fonte-encerra-o-trecho",
        "numero-de-adr",
        "overview-encerra-o-trecho",
        "fim-de-frase-encerra-o-trecho",
        "paragrafo-encerra-o-trecho",
        "status-http",
        "nome-solto-nao-e-referencia",
        "concept-encerra-o-trecho",
        "linha-dentro-de-citacao",
    ],
)
def test_citacao_por_ancora_e_numeros_que_nao_sao_linha_passam(
    tmp_path: pathlib.Path, texto: str
) -> None:
    assert _problemas(tmp_path, texto) == []


def test_a_linha_do_achado_e_a_da_referencia(tmp_path: pathlib.Path) -> None:
    achados = _problemas(tmp_path, "título\n\ntexto\nver `escala.md` 171.\n")
    assert len(achados) == 1
    assert achados[0].startswith("docs/x.md:4:")


def test_o_achado_nomeia_o_doc_citado(tmp_path: pathlib.Path) -> None:
    achados = _problemas(tmp_path, "ver `equipe.md` 120.")
    assert "docs/domain/staff/equipe.md" in achados[0]


# --- Regra 2: âncora -------------------------------------------------------------


@pytest.mark.parametrize(
    "ancora",
    [
        '§3.1 › "Toda alocação está dentro do período"',
        '§2 › "Faixas de funcionamento"',
        '§2 › "As faixas habilitadas por dia"',
        '§3.6.1 › "o mesmo registro com duas alocações cujas faixas se sobrepõem"',
        '§3.6.1 › "Configurável: só o modo"',
        '§3.6.1 › "a forma interna do TimeRange"',
        "§3.6.1 › `TimeRange`",
        '§6 › "Schedule como raiz do agregado — confirmar"',
        '§"Lacunas para o concept de cada Stage (consolidado)" › "Schedule como raiz"',
        '§"Lacunas para o concept de cada Stage"',
        "§3",
        "§3.10",
    ],
    ids=[
        "trecho-com-negrito",
        "rotulo-de-tabela",
        "trecho-no-meio-da-celula",
        "trecho-quebrando-linha",
        "negrito-no-meio",
        "dentro-de-citacao-e-crase",
        "literal",
        "secao-engloba-subsecoes",
        "secao-entre-aspas-com-rotulo",
        "secao-entre-aspas-por-prefixo",
        "secao-de-nivel-2",
        "secao-de-dois-digitos",
    ],
)
def test_ancora_que_existe_no_doc_passa(tmp_path: pathlib.Path, ancora: str) -> None:
    assert _problemas(tmp_path, f"Ver `escala.md` {ancora}.") == []


@pytest.mark.parametrize(
    ("ancora", "motivo"),
    [
        ("§3.9", "seção §3.9 não existe em docs/domain/scheduling/escala.md"),
        ("§9", "seção §9 não existe"),
        ('§3.1 › "Inexistente"', 'rótulo "Inexistente" não existe em'),
        ("§3.1 › `TimeRange`", "rótulo `TimeRange` não existe em"),
        ('§2 › "Toda alocação está dentro do período"', "não existe em"),
        ('§"Tabela Inexistente"', 'seção §"Tabela Inexistente" não existe'),
        ('§"Lacunas para o concept de cada Stag"', "não existe"),
    ],
    ids=[
        "secao-inexistente",
        "titulo-em-bloco-cercado-nao-conta",
        "rotulo-inexistente",
        "literal-de-outra-secao",
        "rotulo-de-outra-secao",
        "secao-entre-aspas-inexistente",
        "secao-entre-aspas-prefixo-sem-fronteira-de-palavra",
    ],
)
def test_ancora_que_nao_resolve_reprova(tmp_path: pathlib.Path, ancora: str, motivo: str) -> None:
    achados = _problemas(tmp_path, f"Ver `escala.md` {ancora}.")
    assert len(achados) == 1, achados
    assert motivo in achados[0]


def test_secao_n_m_nao_casa_com_o_prefixo_de_n_mm(tmp_path: pathlib.Path) -> None:
    """`§3.1` resolve na 3.1, não na 3.10: o rótulo da 3.10 não está na 3.1."""
    achados = _problemas(tmp_path, 'Ver `escala.md` §3.1 › "Staff entra por id".')
    assert len(achados) == 1


def test_cada_ancora_da_cadeia_e_conferida(tmp_path: pathlib.Path) -> None:
    texto = (
        "- [`escala.md`](../domain/scheduling/escala.md)\n"
        '  §2, §3.1 › "dentro do período" (a lei), §3.6.0/§3.6.1, §3.1–§3.10,\n'
        '  §6 › "Nada disso" (a tabela).'
    )
    achados = _problemas(tmp_path, texto)
    assert len(achados) == 2, achados  # noqa: PLR2004 — §3.6.0 e o rótulo de §6
    assert "§3.6.0 não existe" in achados[0]
    assert '"Nada disso"' in achados[1]
    assert achados[1].startswith("docs/x.md:3:")


def test_um_rotulo_errado_na_lista_reprova_sozinho(tmp_path: pathlib.Path) -> None:
    achados = _problemas(
        tmp_path, 'Ver `escala.md` §3.6.1 › "Configurável: só o modo", "nao existe", `TimeRange`.'
    )
    assert len(achados) == 1
    assert '"nao existe"' in achados[0]


def test_prosa_entre_as_secoes_corta_a_cadeia(tmp_path: pathlib.Path) -> None:
    """`equipe §3.8; as docstrings de §8` — a §8 é do doc que cita, não do doc de domínio."""
    assert _problemas(tmp_path, "nota no equipe §3.8; as docstrings de §8 mudaram.") == []


def test_ancora_depois_de_paragrafo_nao_e_da_referencia(tmp_path: pathlib.Path) -> None:
    assert _problemas(tmp_path, "Ver `escala.md`\n\n§9 deste concept.") == []


def test_a_ancora_e_resolvida_no_doc_citado(tmp_path: pathlib.Path) -> None:
    """`equipe.md` não tem §3.1; `escala.md` tem."""
    achados = _problemas(tmp_path, "Ver `equipe.md` §3.1 e `escala.md` §3.1.")
    assert len(achados) == 1
    assert "docs/domain/staff/equipe.md" in achados[0]


# --- Escopo da varredura ---------------------------------------------------------


def test_a_secao_7_do_technical_e_registro_historico(tmp_path: pathlib.Path) -> None:
    texto = "# T\n\n## 6. Ref\n\nok\n\n## 7. Execução\n\nremapeado `escala.md` 1086→1084.\n"
    assert _problemas(tmp_path, texto, nome="docs/stages/4.1-x/technical.md") == []


def test_antes_da_secao_7_o_technical_e_varrido(tmp_path: pathlib.Path) -> None:
    texto = "# T\n\n## 1. Escopo\n\nver `escala.md` 171.\n\n## 7. Execução\n"
    assert len(_problemas(tmp_path, texto, nome="docs/stages/4.1-x/technical.md")) == 1


def test_a_secao_7_so_e_poupada_no_technical(tmp_path: pathlib.Path) -> None:
    texto = "# C\n\n## 7. Execução\n\nver `escala.md` 171.\n"
    assert len(_problemas(tmp_path, texto, nome="docs/stages/4.1-x/concept.md")) == 1


@pytest.mark.parametrize(
    "nome",
    [
        "CLAUDE.md",
        ".claude/skills/x/SKILL.md",
        ".github/PULL_REQUEST_TEMPLATE.md",
        "docs/roadmap.md",
        "docs/domain/staff/outro.md",
    ],
)
def test_a_raiz_o_harness_o_github_e_os_docs_sao_varridos(
    tmp_path: pathlib.Path, nome: str
) -> None:
    assert len(_problemas(tmp_path, "ver `escala.md` 171.", nome=nome)) == 1


def test_pasta_fora_do_escopo_nao_e_varrida(tmp_path: pathlib.Path) -> None:
    assert _problemas(tmp_path, "ver `escala.md` 171.", nome="htmlcov/x.md") == []


def test_doc_de_dominio_novo_entra_sem_editar_o_gate(tmp_path: pathlib.Path) -> None:
    dominio = {"docs/domain/stock/estoque.md": "# Estoque\n\n## 1. Escopo\n\nok\n"}
    repo = _repo(tmp_path, {"docs/x.md": "ver `estoque.md` 12, e `estoque.md` §2."}, dominio)
    achados = gate.problemas(repo)
    assert len(achados) == 2  # noqa: PLR2004 — a linha e a §2 inexistente


# --- Saída --------------------------------------------------------------------------


def _main(monkeypatch: pytest.MonkeyPatch, repo: pathlib.Path) -> int:
    monkeypatch.setattr(sys, "argv", ["check_domain_citations.py", "--repo", str(repo)])
    return int(gate.main())


def test_main_sai_0_quando_tudo_confere(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _main(monkeypatch, _repo(tmp_path, {"docs/x.md": "Ver `escala.md` §3.1."})) == 0
    assert "resolvem" in capsys.readouterr().out


def test_main_sai_1_e_lista_os_achados(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repo(tmp_path, {"docs/x.md": "Ver `escala.md` 171 e `equipe.md` §9."})
    assert _main(monkeypatch, repo) == 1
    erro = capsys.readouterr().err
    assert "2 problema(s)" in erro
    assert "docs/x.md:1:" in erro


def test_main_sai_2_sem_doc_de_dominio(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "docs").mkdir()
    assert _main(monkeypatch, tmp_path) == _SAIDA_FATAL
    assert "FATAL" in capsys.readouterr().err


def test_main_sai_2_com_dois_docs_de_mesmo_nome(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    dominio = {"docs/domain/a/escala.md": _ESCALA, "docs/domain/b/escala.md": _ESCALA}
    assert _main(monkeypatch, _repo(tmp_path, {}, dominio)) == _SAIDA_FATAL
    assert "mesmo nome" in capsys.readouterr().err


# --- Auditoria de testes (mutações que sobreviviam) ---------------------------------


@pytest.mark.parametrize(
    "texto",
    [
        '`escala.md` §3.1 ("vale de 120, como antes").',
        "`escala.md` §3.1 (*a regra 120, antiga*).",
        "`escala.md` §3.1 (`faixas = [120, 130]` no código)",
        "`escala.md` §3.1 (Step 12, ainda)",
        "`escala.md` §3.1 (https://example.com/a/120, ver)",
        "| `escala.md` §3.1 | 120, 130 |",
        "`escala.md` §3.1; overview 46, 130.",
        "`escala.md` §3.1; CLT art. 71, 120.",
        "`escala.md` §3.1 e `outro.md` 120, 130",
        "Ver `escala.md` (nota\n\nno outro parágrafo) §9.",
        "ver `subescala.md` 171 e `my-escala.md` 171.",
        "`escala.md` §3.1 " + "palavra " * 40 + "120, x",
    ],
    ids=[
        "aspas",
        "italico",
        "literal",
        "step-de-dois-digitos",
        "url",
        "celula-de-tabela",
        "overview-sem-extensao",
        "clt",
        "outro-md",
        "parentese-nao-atravessa-paragrafo",
        "nome-dentro-de-outro-nome",
        "teto-do-trecho",
    ],
)
def test_numeros_neutros_passam(tmp_path: pathlib.Path, texto: str) -> None:
    assert _problemas(tmp_path, texto) == []


def test_secao_de_dois_digitos_e_neutra(tmp_path: pathlib.Path) -> None:
    dominio = {"docs/domain/d/dez.md": "# D\n\n## 10. Dez\n\nok\n\n## 11. Onze\n\nok\n"}
    assert gate.problemas(_repo(tmp_path, {"docs/x.md": "`dez.md` §10, §11."}, dominio)) == []


@pytest.mark.parametrize(
    "texto",
    [
        "`escala.md` §3.1, linha 171 diz",
        "`escala.md` §3.1, 171.",
        "`escala.md` §3.1, 12.",
        "`escala.md` §3.1, l. 166 diz",
        "`escala.md` (171 e seguintes)",
        "`escala.md` §3.1, 171 e 172 diz",
        "`escala.md` §3.1 L171 diz",
        "`escala.md`:L171-L180 diz",
        "`escala.md` §3.1 ln 171 diz",
        "`escala.md` §3.1 line ~171 diz",
    ],
    ids=[
        "linha-depois-da-ancora",
        "numero-solto-no-fim",
        "dois-digitos",
        "l-ponto-depois-da-ancora",
        "parentese-imediato",
        "lista-com-e",
        "l-maiusculo-github",
        "faixa-l-github",
        "ln",
        "line-til",
    ],
)
def test_linha_em_outras_posicoes_reprova(tmp_path: pathlib.Path, texto: str) -> None:
    achados = _problemas(tmp_path, texto)
    assert len(achados) == 1, achados
    assert "número de linha" in achados[0]


@pytest.mark.parametrize(
    ("texto", "motivo"),
    [
        ("Ver `escala.md` §3.6.", "seção §3.6 não existe"),
        ('Ver `escala.md` §3.9 › "x".', "seção §3.9 não existe"),
        ("Ver `escala.md` §3.1 › `está dentro`.", "rótulo `está dentro` não existe"),
        ("Ver `escala.md` §3.1 e §9.", "seção §9 não existe"),
        ('Ver `escala.md` §3.1 > "Inexistente".', "fora da forma"),
        ('Ver `escala.md` §3.1 -> "Inexistente".', "fora da forma"),
        ('Ver `escala.md` §3.1 ›"Inexistente".', "fora da forma"),
    ],
    ids=[
        "numero-e-exato-nao-prefixo",
        "secao-inexistente-com-rotulo",
        "literal-e-cru",
        "cadeia-com-e",
        "seta-maior",
        "seta-ascii",
        "sem-espaco",
    ],
)
def test_ancoras_que_escapavam_reprovam(tmp_path: pathlib.Path, texto: str, motivo: str) -> None:
    achados = _problemas(tmp_path, texto)
    assert len(achados) == 1, achados
    assert motivo in achados[0]
