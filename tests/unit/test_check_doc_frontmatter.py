"""O gate de frontmatter de ADR e de doc de domínio, contra violadores plantados (issue #102).

**O que o gate protege.** Frontmatter que `yaml.safe_load` recusa passa por todo
gate que lê por regex; `adr_id` repetido passa pelo git porque os nomes de
arquivo diferem; doc de domínio que linka ADR fora do `references`, ou que deixa
"Lacuna para o concept da Stage N.M" aberta depois da Stage `done`, envelhece em
silêncio (issue #37).

**Os violadores são plantados num repositório de mentira** em `tmp_path` — o
script recebe `repo_root`. Um teste roda contra o repositório real, e outro trava
a ligação do script no `make docs-check`.
"""

import importlib.util
import pathlib
import sys
import types

import pytest

pytestmark = pytest.mark.unit

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_SCRIPT = _REPO_ROOT / "scripts" / "check_doc_frontmatter.py"


def _carregar_script() -> types.ModuleType:
    """Importa `scripts/check_doc_frontmatter.py` sem mexer no `sys.path`."""
    spec = importlib.util.spec_from_file_location("check_doc_frontmatter", _SCRIPT)
    assert spec is not None and spec.loader is not None
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


gate = _carregar_script()

_SAIDA_FATAL = 2

_ROADMAP = """\
# Roadmap

## Tabela de Stages

| Stage | Título | Camada-alvo | Status | Depende de |
|---|---|---|---|---|
| `4.1-scheduling-domain` | Domínio da escala | domain | done | — |
| `4.2-validation-policies` | Políticas | domain | done | `4.1-scheduling-domain` |
| `4.4-scheduling-persistence` | Persistência done em breve | adapters | draft | — |
| `4.5-scheduling-http` | API | done | draft | — |

## Tabela de Issues

| Issue | Status |
|---|---|
| `9.9-falsa` | done |
"""

_DOMINIO = "docs/domain/scheduling/escala.md"


def _adr(adr_id: str, decision: str = "Uma frase.", extra: str = "") -> str:
    return (
        "---\n"
        f"title: ADR {adr_id} — Título\n"
        "status: accepted\n"
        f"adr_id: {adr_id}\n"
        f"decision: {decision}\n"
        f"{extra}"
        "---\n\n# ADR\n"
    )


def _dominio(corpo: str, references: str = "references: []\n") -> str:
    return f"---\ntitle: Domínio\nstatus: accepted\n{references}---\n{corpo}"


def _repo(tmp_path: pathlib.Path, arquivos: dict[str, str]) -> pathlib.Path:
    """Planta um repositório: roadmap padrão + os arquivos dados (caminho → texto)."""
    todos = {"docs/roadmap.md": _ROADMAP, **arquivos}
    for rel, texto in todos.items():
        caminho = tmp_path / rel
        caminho.parent.mkdir(parents=True, exist_ok=True)
        caminho.write_text(texto, encoding="utf-8")
    (tmp_path / "docs" / "adr").mkdir(parents=True, exist_ok=True)
    (tmp_path / "docs" / "domain").mkdir(parents=True, exist_ok=True)
    return tmp_path


# --- repositório real e ligação -------------------------------------------------


def test_o_repositorio_real_passa() -> None:
    assert gate.problemas(_REPO_ROOT) == []


def test_o_docs_check_chama_o_script_e_o_check_depende_dele() -> None:
    makefile = (_REPO_ROOT / "Makefile").read_text(encoding="utf-8")
    alvo = makefile.split("\ndocs-check:\n", 1)[1].split("\n\n", 1)[0]
    assert "\tuv run python scripts/check_doc_frontmatter.py" in alvo.splitlines()
    linha_check = next(ln for ln in makefile.splitlines() if ln.startswith("check:"))
    assert "docs-check" in linha_check.split()


# --- ADRs: YAML -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("decision", "trecho"),
    [
        ("`Port` ganha um método", "found character '`'"),
        ("Gates do PR: sem rede", "mapping values are not allowed"),
    ],
)
def test_adr_com_yaml_invalido_reprova(tmp_path: pathlib.Path, decision: str, trecho: str) -> None:
    repo = _repo(tmp_path, {"docs/adr/0_0_0001-a.md": _adr('"0.0.0001"', decision)})
    [achado] = gate.problemas(repo)
    assert achado.startswith("docs/adr/0_0_0001-a.md: frontmatter não é YAML válido (linha 5)")
    assert trecho in achado


def test_adr_com_o_valor_entre_aspas_passa(tmp_path: pathlib.Path) -> None:
    repo = _repo(
        tmp_path,
        {"docs/adr/0_0_0001-a.md": _adr('"0.0.0001"', "'`Port` ganha: um método'")},
    )
    assert gate.problemas(repo) == []


@pytest.mark.parametrize(
    ("texto", "motivo"),
    [
        ("# ADR sem frontmatter\n", "frontmatter ausente"),
        ("---\ntitle: x\nadr_id: '0.0.0001'\n", "sem o `---` de fechamento"),
        ("---\n- a\n- b\n---\n", "não é um mapeamento YAML"),
        ("---\n---\n", "não é um mapeamento YAML"),
    ],
)
def test_adr_sem_frontmatter_mapeado_reprova(
    tmp_path: pathlib.Path, texto: str, motivo: str
) -> None:
    repo = _repo(tmp_path, {"docs/adr/0_0_0001-a.md": texto})
    [achado] = gate.problemas(repo)
    assert achado.startswith("docs/adr/0_0_0001-a.md: ")
    assert motivo in achado


# --- ADRs: adr_id ---------------------------------------------------------------


def test_adr_id_sem_aspas_e_texto_e_passa(tmp_path: pathlib.Path) -> None:
    repo = _repo(tmp_path, {"docs/adr/2_3_0001-a.md": _adr("2.3.0001")})
    assert gate.problemas(repo) == []


@pytest.mark.parametrize("adr_id", ["1.1", "12", '"0.0.1"', '"0.0.00001"', '"a.0.0001"', "null"])
def test_adr_id_fora_do_formato_reprova(tmp_path: pathlib.Path, adr_id: str) -> None:
    repo = _repo(tmp_path, {"docs/adr/0_0_0001-a.md": _adr(adr_id)})
    [achado] = gate.problemas(repo)
    assert "`adr_id` ausente ou fora do formato" in achado


def test_adr_sem_adr_id_reprova(tmp_path: pathlib.Path) -> None:
    repo = _repo(tmp_path, {"docs/adr/0_0_0001-a.md": "---\ntitle: x\n---\n"})
    [achado] = gate.problemas(repo)
    assert "`adr_id` ausente ou fora do formato" in achado


@pytest.mark.parametrize(
    ("arquivo", "adr_id", "esperado"),
    [
        ("0_0_0012-a.md", '"0.0.0011"', "0.0.0012"),  # número
        ("3_5_0001-a.md", '"3.4.0001"', "3.5.0001"),  # Stage
        ("1_1_0001-a.md", '"2.1.0001"', "1.1.0001"),  # Step
    ],
)
def test_adr_id_que_nao_bate_com_o_nome_reprova(
    tmp_path: pathlib.Path, arquivo: str, adr_id: str, esperado: str
) -> None:
    repo = _repo(tmp_path, {f"docs/adr/{arquivo}": _adr(adr_id)})
    [achado] = gate.problemas(repo)
    assert f"não bate com o prefixo do nome (esperado '{esperado}')" in achado


@pytest.mark.parametrize("arquivo", ["0_0_001-a.md", "adr-0001.md", "0_0_0001.md", "0_0_0001-A.md"])
def test_nome_de_adr_fora_do_padrao_reprova(tmp_path: pathlib.Path, arquivo: str) -> None:
    repo = _repo(tmp_path, {f"docs/adr/{arquivo}": _adr('"0.0.0001"')})
    [achado] = gate.problemas(repo)
    assert "nome fora do padrão" in achado


def test_adr_id_repetido_em_arquivos_de_slug_diferente_reprova(tmp_path: pathlib.Path) -> None:
    repo = _repo(
        tmp_path,
        {
            "docs/adr/0_0_0011-cite-the-roadmap.md": _adr('"0.0.0011"'),
            "docs/adr/0_0_0011-delete-refuses-link.md": _adr('"0.0.0011"'),
            "docs/adr/0_0_0012-outro.md": _adr('"0.0.0012"'),
        },
    )
    [achado] = gate.problemas(repo)
    assert achado.startswith("`adr_id` '0.0.0011' repetido em 2 ADRs:")
    assert "docs/adr/0_0_0011-cite-the-roadmap.md" in achado
    assert "docs/adr/0_0_0011-delete-refuses-link.md" in achado


def test_varios_adrs_validos_passam(tmp_path: pathlib.Path) -> None:
    repo = _repo(
        tmp_path,
        {f"docs/adr/0_0_000{n}-a.md": _adr(f'"0.0.000{n}"') for n in range(1, 4)},
    )
    assert gate.problemas(repo) == []


# --- domínio: frontmatter e references ------------------------------------------


def test_dominio_com_yaml_invalido_reprova(tmp_path: pathlib.Path) -> None:
    repo = _repo(tmp_path, {_DOMINIO: "---\ntitle: a: b\n---\ncorpo\n"})
    [achado] = gate.problemas(repo)
    assert achado.startswith(f"{_DOMINIO}: frontmatter não é YAML válido (linha 2)")


def test_dominio_em_subpasta_profunda_e_varrido(tmp_path: pathlib.Path) -> None:
    repo = _repo(tmp_path, {"docs/domain/a/b/c.md": "corpo sem frontmatter\n"})
    [achado] = gate.problemas(repo)
    assert achado.startswith("docs/domain/a/b/c.md: frontmatter ausente")


@pytest.mark.parametrize("references", ["references: x.md\n", "references:\n  - 3\n"])
def test_references_que_nao_e_lista_de_caminhos_reprova(
    tmp_path: pathlib.Path, references: str
) -> None:
    repo = _repo(tmp_path, {_DOMINIO: _dominio("corpo\n", references)})
    [achado] = gate.problemas(repo)
    assert achado == f"{_DOMINIO}: `references` tem de ser uma lista de caminhos"


def test_references_vazio_ou_ausente_passa(tmp_path: pathlib.Path) -> None:
    repo = _repo(
        tmp_path,
        {
            _DOMINIO: _dominio("corpo\n", "references:\n"),
            "docs/domain/staff/b.md": _dominio("corpo\n", ""),
        },
    )
    assert gate.problemas(repo) == []


def test_reference_que_nao_existe_reprova(tmp_path: pathlib.Path) -> None:
    repo = _repo(
        tmp_path, {_DOMINIO: _dominio("corpo\n", "references:\n  - ../../adr/0_0_0009-x.md\n")}
    )
    [achado] = gate.problemas(repo)
    assert achado == (
        f"{_DOMINIO}: `references` aponta para '../../adr/0_0_0009-x.md', que não existe"
    )


# --- domínio: links -------------------------------------------------------------


def test_link_relativo_quebrado_reprova_com_a_linha(tmp_path: pathlib.Path) -> None:
    corpo = "\n# Título\n\nVer [o outro](../staff/nao-existe.md#secao).\n"
    repo = _repo(tmp_path, {_DOMINIO: _dominio(corpo)})
    [achado] = gate.problemas(repo)
    # frontmatter de 5 linhas (---, title, status, references, ---) + "", "# Título", "", link
    assert achado == f"{_DOMINIO}:9: link para '../staff/nao-existe.md', que não existe"


def test_links_que_nao_sao_arquivo_do_repositorio_sao_ignorados(tmp_path: pathlib.Path) -> None:
    corpo = (
        "[web](https://example.invalid/x.md) [mail](mailto:a@b.c) [âncora](#secao)\n"
        "`[em código](../nao-existe.md)`\n"
        "```\n[cercado](../nao-existe.md)\n```\n"
        '[com título](../staff/b.md "Título") [angular](<../staff/b.md>)\n'
    )
    repo = _repo(
        tmp_path,
        {_DOMINIO: _dominio(corpo), "docs/domain/staff/b.md": _dominio("corpo\n")},
    )
    assert gate.problemas(repo) == []


def test_link_depois_de_bloco_cercado_volta_a_ser_conferido(tmp_path: pathlib.Path) -> None:
    corpo = "~~~\n[cercado](../x.md)\n~~~\n[fora](../y.md)\n"
    repo = _repo(tmp_path, {_DOMINIO: _dominio(corpo)})
    [achado] = gate.problemas(repo)
    assert "link para '../y.md'" in achado


# --- domínio: ADR linkado ⊆ references ------------------------------------------

_ADR_A = "docs/adr/4_1_0001-a.md"
_ADR_B = "docs/adr/4_1_0002-b.md"
_LINK_A = "[ADR 4.1.0001](../../adr/4_1_0001-a.md)"
_LINK_B = "[ADR 4.1.0002](../../adr/4_1_0002-b.md#decision)"


def _com_adrs(corpo: str, references: str) -> dict[str, str]:
    return {
        _ADR_A: _adr('"4.1.0001"'),
        _ADR_B: _adr('"4.1.0002"'),
        _DOMINIO: _dominio(corpo, references),
    }


def test_adr_linkado_fora_do_references_reprova(tmp_path: pathlib.Path) -> None:
    corpo = f"\n{_LINK_A}\n\n{_LINK_B} e de novo {_LINK_B}\n"
    repo = _repo(tmp_path, _com_adrs(corpo, "references:\n  - ../../adr/4_1_0001-a.md\n"))
    [achado] = gate.problemas(repo)
    assert achado == f"{_DOMINIO}:10: ADR 4_1_0002-b.md linkado no corpo e ausente do `references`"


def test_adr_linkado_por_referencia_fora_do_references_reprova(tmp_path: pathlib.Path) -> None:
    corpo = "\nVer [o ADR][a].\n\n[a]: ../../adr/4_1_0001-a.md\n[b]: <../staff/nao-existe.md>\n"
    repo = _repo(tmp_path, _com_adrs(corpo, "references: []\n"))
    assert gate.problemas(repo) == [
        f"{_DOMINIO}:10: link para '../staff/nao-existe.md', que não existe",
        f"{_DOMINIO}:9: ADR 4_1_0001-a.md linkado no corpo e ausente do `references`",
    ]


def test_adr_linkado_e_no_references_passa(tmp_path: pathlib.Path) -> None:
    refs = "references:\n  - ../../adr/4_1_0001-a.md\n  - ../../adr/4_1_0002-b.md\n"
    repo = _repo(tmp_path, _com_adrs(f"{_LINK_A} {_LINK_B}\n", refs))
    assert gate.problemas(repo) == []


def test_doc_que_nao_e_adr_linkado_nao_exige_references(tmp_path: pathlib.Path) -> None:
    corpo = "[staff](../staff/b.md) [conv](../../CONVENTIONS.md)\n"
    repo = _repo(
        tmp_path,
        {
            _DOMINIO: _dominio(corpo),
            "docs/domain/staff/b.md": _dominio("corpo\n"),
            "docs/CONVENTIONS.md": "# x\n",
        },
    )
    assert gate.problemas(repo) == []


def test_adr_so_citado_em_texto_sem_link_nao_exige_references(tmp_path: pathlib.Path) -> None:
    repo = _repo(tmp_path, _com_adrs("Ver ADR 4.1.0001 e `4_1_0002-b.md`.\n", "references: []\n"))
    assert gate.problemas(repo) == []


# --- domínio: sem válvula --------------------------------------------------------


def test_nao_ha_excecao_a_regra_dos_references() -> None:
    """A válvula do `shift-scheduling.md` saiu na #116 (ADR 0.0.0017): nenhum doc é exceção."""
    assert not hasattr(gate, "VALVULA_REFERENCES")


def test_o_doc_da_antiga_valvula_nao_e_excecao(tmp_path: pathlib.Path) -> None:
    """Exceção reintroduzida com outro nome, pelo caminho do doc, também reprova."""
    arquivos = _com_adrs(f"{_LINK_A}\n", "references: []\n")
    arquivos["docs/domain/scheduling/shift-scheduling.md"] = arquivos.pop(_DOMINIO)
    [achado] = gate.problemas(_repo(tmp_path, arquivos))
    assert achado.startswith("docs/domain/scheduling/shift-scheduling.md:")
    assert "ADR 4_1_0001-a.md linkado no corpo e ausente do `references`" in achado


def test_o_doc_da_antiga_valvula_lista_todo_adr_que_linka() -> None:
    """Os 16 ADRs que a válvula deixava de fora estão no `references` do `shift-scheduling.md`."""
    doc = _REPO_ROOT / "docs" / "domain" / "scheduling" / "shift-scheduling.md"
    fm = gate.ler_frontmatter(doc.read_text(encoding="utf-8-sig"))
    assert fm.dados is not None
    referencias = {pathlib.PurePosixPath(r).name for r in fm.dados["references"]}
    linkados = {
        pathlib.PurePosixPath(alvo).name
        for _, alvo in gate.links_relativos(fm.corpo, fm.linha_corpo)
        if "/adr/" in alvo
    }
    assert len(linkados) > 16  # noqa: PLR2004 — o doc linka mais que os 16 da válvula
    assert linkados <= referencias


# --- domínio: lacunas -----------------------------------------------------------


@pytest.mark.parametrize(
    ("marca", "fechadas"),
    [
        ("Lacuna para o concept da Stage 4.1:", "4.1"),
        ("lacuna para o concept da Stage 4.2", "4.2"),
        ("Lacuna para o concept da Stage 4.4/4.2 — x", "4.2"),
        ("Lacuna para o concept da Stage 4.1 / 4.2:", "4.1, 4.2"),
        ("Lacuna para o concept da Stages 4.1/4.5", "4.1"),  # plural
    ],
)
def test_lacuna_aberta_com_stage_done_reprova(
    tmp_path: pathlib.Path, marca: str, fechadas: str
) -> None:
    corpo = f"\n> **{marca}** a pergunta.\n"
    repo = _repo(tmp_path, {_DOMINIO: _dominio(corpo)})
    [achado] = gate.problemas(repo)
    assert achado.startswith(f"{_DOMINIO}:7: lacuna para a Stage ")
    assert f"mas {fechadas} já está done" in achado


@pytest.mark.parametrize(
    "marca",
    [
        "Lacuna para o concept da Stage 4.4:",  # draft
        "Lacuna para o concept da Stage 4.4/4.5:",  # ambas draft (4.5 tem "done" noutra coluna)
        "Lacuna para o concept da Stage 9.9:",  # "done" só na Tabela de Issues
        "Lacuna fechada pela Stage 4.1 (ADR 4.1.0007):",
        "lacuna para o concept da Stage — nunca decidido aqui",
    ],
)
def test_lacuna_sem_stage_done_passa(tmp_path: pathlib.Path, marca: str) -> None:
    repo = _repo(tmp_path, {_DOMINIO: _dominio(f"> **{marca}** a pergunta.\n")})
    assert gate.problemas(repo) == []


# --- domínio: tabela de lacunas (issue #117) ------------------------------------

_TABELA = "\n| Stage dona | Lacuna (§) |\n|---|---|\n"


@pytest.mark.parametrize(
    ("linha", "pendentes"),
    [
        ("| **4.1** | a pergunta (§3.2) |", "4.1"),
        ("| **4.1 (technical)** | a pergunta |", "4.1"),
        ("|**4.2**| a pergunta |", "4.2"),
        ("| **4.4/4.2** | a pergunta |", "4.2"),
        ("| **4.1 / 4.2** | a pergunta |", "4.1, 4.2"),
        ("| **4.1 / 4.2** | a pergunta — *fechada pela Stage 4.1 (ADR)* |", "4.2"),
        ("| **4.1** | a pergunta — *fechada pela Stage 4.4 (ADR)* |", "4.1"),
        ("| **4.1** | a pergunta — *fechada pela Stage 4.11 (ADR)* |", "4.1"),
        ("| **4.1** | a pergunta — *Lacuna da Stage 4.1 (ADR)* |", "4.1"),
        ("| **4.1** | a pergunta — fechada pela 4.1 |", "4.1"),
        # reendereçada: a Stage dona do negrito continua guardada, a nota de fora não conta
        ("| **4.1** (reendereçada da 4.4) | a pergunta |", "4.1"),
        ("| **4.1 (*technical*)** | a pergunta |", "4.1"),
        # auditoria de testes por mutação: "fechada" é parte da marca, e só a lista que a
        # segue fecha — número de ADR na fonte não fecha a Stage dona
        ("| **4.1** | a pergunta — aberta pela Stage 4.1 |", "4.1"),
        ("| **4.1** | x — *fechada pela Stage 4.4 (ADR 4.1.0007)* |", "4.1"),
    ],
)
def test_linha_da_tabela_com_stage_done_sem_marca_reprova(
    tmp_path: pathlib.Path, linha: str, pendentes: str
) -> None:
    repo = _repo(tmp_path, {_DOMINIO: _dominio(_TABELA + linha + "\n")})
    [achado] = gate.problemas(repo)
    assert achado.startswith(f"{_DOMINIO}:9: linha da tabela de lacunas da Stage ")
    assert f'sem "fechada pela Stage {pendentes}", mas já está done' in achado


@pytest.mark.parametrize(
    "linha",
    [
        "| **4.1** | a pergunta — *fechada pela Stage 4.1 (ADR 4.1.0007)* |",
        "| **4.1 (technical)** | a pergunta — *Fechada pela Stage 4.1 (concept)* |",
        "| **4.1/4.2** | a pergunta — *fechada pelas Stages 4.1 e 4.2 (ADRs)* |",
        "| **4.1/4.2** | a pergunta — *fechada pelas Stages 4.2, 4.1 (ADRs)* |",
        "| **4.1/4.2** | a pergunta — *fechada pelas Stages 4.1/4.2 (ADRs)* |",
        "| **4.1/4.2** | x — *fechada pela Stage 4.1 (a)*; *fechada pela Stage 4.2 (b)* |",
        "| **4.1 / 4.4** | a pergunta — *fechada pela Stage 4.1: a 4.4 implementa* |",
        "| **4.4 / 4.5** | a pergunta |",  # nenhuma done
        "| **9.9** | a pergunta |",  # "done" só na Tabela de Issues
        "| **sem Stage (roadmap)** | a pergunta |",
        "| **4.4** (reendereçada da 4.1) | a pergunta |",  # 4.1 fora do negrito
        "| 4.1 | sem negrito na célula dona |",
        "| a 1ª célula | **4.1** em outra célula |",
        "| a 1ª célula | **4.1** | a pergunta |",  # negrito fechando a 2ª célula
    ],
)
def test_linha_da_tabela_fechada_ou_sem_stage_done_passa(
    tmp_path: pathlib.Path, linha: str
) -> None:
    repo = _repo(tmp_path, {_DOMINIO: _dominio(_TABELA + linha + "\n")})
    assert gate.problemas(repo) == []


def test_mensagem_da_tabela_nomeia_a_celula_e_so_as_pendentes(tmp_path: pathlib.Path) -> None:
    repo = _repo(tmp_path, {_DOMINIO: _dominio(_TABELA + "| **4.4/4.2** | a pergunta |\n")})
    assert gate.problemas(repo) == [
        f'{_DOMINIO}:9: linha da tabela de lacunas da Stage 4.4/4.2 sem "fechada pela Stage 4.2",'
        " mas já está done — feche-a no lugar ou reenderece a Stage dona"
    ]


def test_linha_da_tabela_dentro_de_bloco_cercado_e_exemplo(tmp_path: pathlib.Path) -> None:
    corpo = "```markdown\n| **4.1** | a pergunta |\n```\n"
    repo = _repo(tmp_path, {_DOMINIO: _dominio(corpo)})
    assert gate.problemas(repo) == []


def test_tabela_real_reprova_se_uma_linha_done_perde_a_marca(tmp_path: pathlib.Path) -> None:
    """A mutação do critério de aceite da #117, sobre o doc e o roadmap reais."""
    rel = "docs/domain/scheduling/shift-scheduling.md"
    texto = (_REPO_ROOT / rel).read_text(encoding="utf-8")
    alvo = next(
        linha
        for linha in texto.splitlines()
        if linha.startswith("| **4.3** | DTO próprio do `StaffReadPort`")
    )
    sem_marca = alvo.split(" — *fechada pela Stage")[0] + " |"
    repo = _repo(
        tmp_path,
        {
            "docs/roadmap.md": (_REPO_ROOT / "docs/roadmap.md").read_text(encoding="utf-8"),
            rel: texto.replace(alvo, sem_marca),
        },
    )
    achados = [a for a in gate.problemas(repo) if "tabela de lacunas" in a]
    numero = texto.splitlines().index(alvo) + 1
    assert achados == [
        f'{rel}:{numero}: linha da tabela de lacunas da Stage 4.3 sem "fechada pela Stage 4.3",'
        " mas já está done — feche-a no lugar ou reenderece a Stage dona"
    ]


# --- roadmap --------------------------------------------------------------------


def test_stages_done_le_a_coluna_status_da_tabela_de_stages() -> None:
    assert gate.stages_done(_ROADMAP) == {"4.1", "4.2"}


def test_stages_done_sem_tabela_e_vazio() -> None:
    assert gate.stages_done("# Roadmap\n") == set()


def test_roadmap_ausente_e_fatal(tmp_path: pathlib.Path) -> None:
    assert gate.problemas(tmp_path) == ["FATAL: docs/roadmap.md não existe"]


def test_roadmap_sem_stage_done_e_fatal(tmp_path: pathlib.Path) -> None:
    repo = _repo(tmp_path, {"docs/roadmap.md": _ROADMAP.replace("| done |", "| draft |")})
    [achado] = gate.problemas(repo)
    assert achado.startswith("FATAL: nenhuma Stage `done`")


# --- main -----------------------------------------------------------------------


def _main(monkeypatch: pytest.MonkeyPatch, repo: pathlib.Path) -> int:
    monkeypatch.setattr(sys, "argv", ["check_doc_frontmatter.py", "--repo", str(repo)])
    return int(gate.main())


def test_main_verde(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repo(tmp_path, {"docs/adr/0_0_0001-a.md": _adr('"0.0.0001"')})
    assert _main(monkeypatch, repo) == 0
    assert "frontmatter YAML válido" in capsys.readouterr().out


def test_main_com_violacao(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repo(tmp_path, {"docs/adr/0_0_0001-a.md": _adr('"0.0.0002"')})
    assert _main(monkeypatch, repo) == 1
    erro = capsys.readouterr().err
    assert "1 problema(s)" in erro
    assert "  docs/adr/0_0_0001-a.md: `adr_id`" in erro


def test_main_fatal(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _main(monkeypatch, tmp_path) == _SAIDA_FATAL
    assert "FATAL: docs/roadmap.md não existe" in capsys.readouterr().err


# --- auditoria de testes (mutação real): o que os casos acima não travavam --------


def test_lacuna_no_meio_do_doc_reprova_com_a_linha(tmp_path: pathlib.Path) -> None:
    corpo = "\n" * 20 + "> **Lacuna para o concept da Stage 4.1:** x\n"
    repo = _repo(tmp_path, {_DOMINIO: _dominio(corpo)})
    [achado] = gate.problemas(repo)
    assert achado.startswith(f"{_DOMINIO}:26: lacuna para a Stage 4.1")


def test_duas_lacunas_na_mesma_linha_sao_lidas_as_duas(tmp_path: pathlib.Path) -> None:
    corpo = "Lacuna para o concept da Stage 4.4 e Lacuna para o concept da Stage 4.1.\n"
    repo = _repo(tmp_path, {_DOMINIO: _dominio(corpo)})
    [achado] = gate.problemas(repo)
    assert "mas 4.1 já está done" in achado


def test_lacuna_e_link_dentro_de_bloco_cercado_sao_exemplo(tmp_path: pathlib.Path) -> None:
    corpo = "```markdown\n> **Lacuna para o concept da Stage 4.1:** x\n[a](../x.md)\n```\n"
    repo = _repo(tmp_path, {_DOMINIO: _dominio(corpo)})
    assert gate.problemas(repo) == []


def test_arquivo_com_bom_e_lido(tmp_path: pathlib.Path) -> None:
    repo = _repo(
        tmp_path,
        {
            "docs/adr/0_0_0001-a.md": "﻿" + _adr('"0.0.0001"'),
            _DOMINIO: "﻿" + _dominio("corpo\n"),
        },
    )
    assert gate.problemas(repo) == []


def test_cercas_do_frontmatter_com_espaco_no_fim_valem(tmp_path: pathlib.Path) -> None:
    texto = "--- \ntitle: x\nadr_id: '0.0.0001'\n---  \n"
    repo = _repo(tmp_path, {"docs/adr/0_0_0001-a.md": texto})
    assert gate.problemas(repo) == []


def test_stages_done_para_na_tabela_de_stages() -> None:
    roadmap = _ROADMAP.replace(
        "| `9.9-falsa` | done |", "| `9.9-falsa` | x | y | done | — |"
    ).replace("| Issue | Status |", "| Issue | a | b | Status | c |")
    assert gate.stages_done(roadmap) == {"4.1", "4.2"}


def test_stages_done_exige_a_celula_de_stage_com_slug() -> None:
    roadmap = _ROADMAP.replace(
        "## Tabela de Issues", "| 4.6 nota | x | y | done | — |\n\n## Tabela de Issues"
    )
    assert "4.6" not in gate.stages_done(roadmap)


def test_erro_de_adr_nao_esconde_erro_de_dominio(tmp_path: pathlib.Path) -> None:
    repo = _repo(
        tmp_path,
        {"docs/adr/0_0_0001-a.md": _adr('"0.0.0002"'), _DOMINIO: _dominio("[x](../x.md)\n")},
    )
    adr, dominio = gate.problemas(repo)
    assert adr.startswith("docs/adr/")
    assert dominio.startswith(_DOMINIO)


def test_adr_linkado_fora_do_references_aponta_a_primeira_linha(tmp_path: pathlib.Path) -> None:
    corpo = f"\n\n{_LINK_B}\n\n{_LINK_B}\n"
    repo = _repo(tmp_path, _com_adrs(corpo, "references: []\n"))
    [achado] = gate.problemas(repo)
    assert achado.startswith(f"{_DOMINIO}:8: ADR 4_1_0002-b.md")


def test_so_docs_adr_na_raiz_sao_adr(tmp_path: pathlib.Path) -> None:
    """Um `adr/` noutra pasta não é a pasta de ADRs; subpasta de `docs/adr/` não é varrida."""
    repo = _repo(
        tmp_path,
        {
            "docs/archive/adr/x.md": "# velho\n",
            "docs/adr/template/README.md": "sem frontmatter\n",
            _DOMINIO: _dominio("[velho](../../archive/adr/x.md)\n"),
        },
    )
    assert gate.problemas(repo) == []


@pytest.mark.parametrize(
    ("texto", "motivo"),
    [
        ("---\n- a\n---\n", "não é um mapeamento YAML"),
        ("---\ntitle: x\n", "sem o `---` de fechamento"),
    ],
)
def test_dominio_sem_frontmatter_mapeado_reprova(
    tmp_path: pathlib.Path, texto: str, motivo: str
) -> None:
    repo = _repo(tmp_path, {_DOMINIO: texto + "[x](../x.md)\n"})
    [achado] = gate.problemas(repo)
    assert achado.startswith(f"{_DOMINIO}: ")
    assert motivo in achado
