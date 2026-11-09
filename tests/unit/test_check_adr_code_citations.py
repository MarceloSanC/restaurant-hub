"""O gate de citação a ADR e a código, contra violadores plantados (issue #154, ADR 0.0.0019).

**O que o gate protege é o alvo de uma citação.** Um ADR `accepted` ganha banner de
errata no topo; o código muda a cada PR. `ADR 4.1.0003 (c) linhas 95–97` e
`employee.py 113–116` passam a apontar para o vizinho sem erro. As regras são "nenhum
número de linha depois de uma referência a ADR ou a arquivo do repo" e "todo trecho
`ADR X › "..."` existe no ADR".

**Os violadores são plantados num repositório de mentira** em `tmp_path`. Um teste
roda contra o repositório real: é ele que trava a conversão desta issue.
"""

import importlib.util
import pathlib
import sys
import types

import pytest

pytestmark = pytest.mark.unit

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_SCRIPT = _REPO_ROOT / "scripts" / "check_adr_code_citations.py"


def _carregar_script() -> types.ModuleType:
    """Importa `scripts/check_adr_code_citations.py` sem mexer no `sys.path`."""
    spec = importlib.util.spec_from_file_location("check_adr_code_citations", _SCRIPT)
    assert spec is not None and spec.loader is not None
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


gate = _carregar_script()

_SAIDA_FATAL = 2

_ADR = """\
---
title: ADR 4.1.0003
---

# ADR 4.1.0003 — política

## Decision

### (c) Mode defaults: `block` only for physical impossibility

`block` for overlap (one person in two places) and for **unavailability**.

## Errata

| Onde | Dizia | Diz |
|---|---|---|
| References | `employee.py:113-116` | `:120-125` |

## References

- nada
"""

_CODIGO = {
    "src/restaurant_hub/staff/employee.py": "class Employee:\n    pass\n",
    "scripts/check_layout.py": "REQUIRED_FEATURE_DIRS = ()\n",
    ".importlinter": "[importlinter]\n",
    "Makefile": "check:\n",
    ".github/workflows/ci.yml": "jobs: {}\n",
}


def _repo(
    tmp_path: pathlib.Path, docs: dict[str, str], adrs: dict[str, str] | None = None
) -> pathlib.Path:
    adrs = {"docs/adr/4_1_0003-politica.md": _ADR} if adrs is None else adrs
    for caminho, texto in {**adrs, **_CODIGO, **docs}.items():
        destino = tmp_path / caminho
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(texto, encoding="utf-8")
    return tmp_path


def _problemas(tmp_path: pathlib.Path, texto: str, nome: str = "docs/x.md") -> list[str]:
    return list(gate.problemas(_repo(tmp_path, {nome: texto})))


def test_o_repositorio_real_cita_adr_e_codigo_sem_numero_de_linha() -> None:
    assert gate.problemas(_REPO_ROOT) == []


def test_o_repositorio_real_tem_trechos_de_adr_a_conferir() -> None:
    """O verde acima não é vazio: a conversão da #154 deixou dezenas de trechos conferidos."""
    todos = gate.adrs(_REPO_ROOT)
    trechos = 0
    for arquivo in gate.arquivos(_REPO_ROOT):
        texto = gate.sem_blocos_cercados(gate.texto_varrido(arquivo))
        for ref in gate._REF_ADR.finditer(texto):
            local = gate._LOCALIZADOR.match(texto, ref.end())
            m = gate._TRECHOS.match(texto, local.end() if local else ref.end())
            if m and (ref.group("id") or "") in todos:
                trechos += len(gate._ROTULO_ITEM.findall(m.group("rotulos")))
    assert trechos > 100  # noqa: PLR2004


# --- Regra 1: número de linha ao ADR ------------------------------------------------


@pytest.mark.parametrize(
    "texto",
    [
        "o ADR 4.1.0003 (c) linhas 95–97 diz",
        "ver ADR 4.1.0003 95–97.",
        "(ADR 4.1.0003:79) diz",
        "o [ADR 4.1.0003](./4_1_0003-politica.md) lines 91–98, e",
        "o [ADR 4.1.0003](./4_1_0003-politica.md) 155–157); depois",
        "`4_1_0003-politica.md` 12, e diz",
        "ADR 4.1.0003 §2 (linhas 70–79: o corte)",
        "ADR 4.1.0003 (a), linha 74; (c) confirma",
        "ADR 4.1.0003 41, 83 — sponsor",
    ],
    ids=[
        "linhas-depois-do-localizador",
        "faixa-imediata",
        "dois-pontos",
        "link-e-lines",
        "link-e-faixa",
        "nome-do-arquivo",
        "secao-nao-esconde-a-linha",
        "linha-depois-de-letra",
        "lista",
    ],
)
def test_numero_de_linha_depois_de_adr_reprova(tmp_path: pathlib.Path, texto: str) -> None:
    achados = _problemas(tmp_path, texto)
    assert len(achados) == 1, achados
    assert "número de linha ao ADR 4.1.0003" in achados[0]


@pytest.mark.parametrize(
    "texto",
    [
        'ADR 4.1.0003 (c) › "block only for physical impossibility" diz.',
        'ADR 4.1.0003 §Decision 2 › "one person in two places", "unavailability" diz.',
        'o [ADR 4.1.0003](./4_1_0003-politica.md) › "physical impossibility"; e',
        "ADRs 4.1.0003/0004 e 4.1.0007–0012 decidem.",
        "ADR 4.1.0003 (2026-07-27) deu à Stage 4.2 um teto.",
        "ADR 4.1.0003 diz que o 404 vem antes do 422.",
        "ADR 4.1.0003 (regra 15; invariante 23, Tasks 05–08, 2\N{MULTIPLICATION SIGN}).",
        "ADR 4.1.0003 (Decreto 9.772/2019; 22,33h; default 168; jul/2026; 08:00).",
        "ADR 4.1.0003 [4.1/task-07]; status 401/403/404, e → 201.",
    ],
    ids=[
        "trecho",
        "localizador-e-lista",
        "link-e-trecho",
        "listas-de-adr",
        "data",
        "status",
        "numeros-de-regra",
        "norma-decimal-default-mes-hora",
        "marca-e-status",
    ],
)
def test_adr_por_ancora_e_numeros_que_nao_sao_linha_passam(
    tmp_path: pathlib.Path, texto: str
) -> None:
    assert _problemas(tmp_path, texto) == []


# --- Regra 2: trecho do ADR ---------------------------------------------------------


@pytest.mark.parametrize(
    ("texto", "motivo"),
    [
        ('ADR 4.1.0003 (c) › "block for everything".', 'trecho "block for everything" não existe'),
        ('ADR 4.1.0003 › "physical impossibility", "zzz".', 'trecho "zzz" não existe'),
        ('ADR 9.9.0001 › "x".', "ADR 9.9.0001 não existe"),
        ('ADR 4.1.0003 (c) > "block".', "fora da forma"),
        ("ADR 4.1.0003 › `blocks`.", "trecho `blocks` não existe"),
    ],
    ids=["trecho-inexistente", "um-da-lista", "adr-inexistente", "seta-errada", "literal-cru"],
)
def test_trecho_de_adr_que_nao_resolve_reprova(
    tmp_path: pathlib.Path, texto: str, motivo: str
) -> None:
    achados = _problemas(tmp_path, texto)
    assert len(achados) == 1, achados
    assert motivo in achados[0]


def test_trecho_de_adr_e_comparado_sem_negrito_nem_crase(tmp_path: pathlib.Path) -> None:
    assert _problemas(tmp_path, 'ADR 4.1.0003 › "block for overlap", "for unavailability".') == []


def test_literal_e_comparado_cru(tmp_path: pathlib.Path) -> None:
    assert _problemas(tmp_path, "ADR 4.1.0003 › `block` for overlap.") == []


# --- Regra 1: número de linha ao código --------------------------------------------


@pytest.mark.parametrize(
    "texto",
    [
        "o guard (`employee.py:113`) recusa",
        "o guard (`employee.py:113-116`) recusa",
        "o guard (`employee.py` 113–116) recusa",
        "o guard (`src/restaurant_hub/staff/employee.py` linha 3) recusa",
        "`check_layout.py` (`REQUIRED_FEATURE_DIRS`, linha 130)",
        "o contrato (`.importlinter` 251–277)",
        "o alvo (`Makefile:81`)",
        "o job (`.github/workflows/ci.yml:15-16`)",
        "ver [x](../src/restaurant_hub/staff/employee.py#L113)",
        "o guard (`staff/employee.py` (113)) recusa",
    ],
    ids=[
        "dois-pontos",
        "faixa-com-hifen",
        "faixa-solta",
        "linha-por-extenso",
        "linha-depois-do-simbolo",
        "config-sem-extensao",
        "makefile",
        "yml-com-caminho",
        "fragmento-do-link",
        "sufixo-de-caminho",
    ],
)
def test_numero_de_linha_depois_de_arquivo_do_repo_reprova(
    tmp_path: pathlib.Path, texto: str
) -> None:
    achados = _problemas(tmp_path, texto)
    assert len(achados) == 1, achados
    assert "número de linha a" in achados[0]


@pytest.mark.parametrize(
    "texto",
    [
        "o guard (`employee.py` › `Employee.__post_init__`) recusa",
        "`.importlinter` › `[importlinter:contract:bc-independence]`",
        "`employee.py` (25 testes) e `employee.py` (2\N{MULTIPLICATION SIGN})",
        "`employee.py` sobe de 22 para 34 e passa de 13 → 15",
        "SQLAlchemy 2.0.51 `engine/base.py:867` e `fastapi/routing.py:343-346`",
        "`nao_existe.py:40` é de outro projeto",
        "```\nemployee.py:113: in execute\n```",
        "`employee.py` (2026-07-27) ganhou o guard",
    ],
    ids=[
        "simbolo",
        "contrato",
        "quantidade",
        "prosa-com-numeros",
        "terceiro-com-versao-fixa",
        "arquivo-fora-do-repo",
        "bloco-cercado",
        "data",
    ],
)
def test_codigo_por_simbolo_e_o_que_nao_e_do_repo_passam(
    tmp_path: pathlib.Path, texto: str
) -> None:
    assert _problemas(tmp_path, texto) == []


# --- Escopo ---------------------------------------------------------------------------


def test_a_errata_de_um_adr_e_registro_historico(tmp_path: pathlib.Path) -> None:
    """A `## Errata` do ADR plantado cita `employee.py:113-116` como o que *dizia*: não reprova."""
    assert gate.problemas(_repo(tmp_path, {})) == []


def test_fora_da_errata_o_adr_e_varrido(tmp_path: pathlib.Path) -> None:
    adr = _ADR.replace("- nada", "- `employee.py:113`")
    achados = gate.problemas(_repo(tmp_path, {}, {"docs/adr/4_1_0003-politica.md": adr}))
    assert len(achados) == 1, achados
    assert achados[0].startswith("docs/adr/4_1_0003-politica.md:21:")


def test_a_errata_so_e_poupada_no_adr(tmp_path: pathlib.Path) -> None:
    texto = "## Errata\n\n- `employee.py:113`\n"
    assert len(_problemas(tmp_path, texto)) == 1


def test_o_frontmatter_nao_e_varrido(tmp_path: pathlib.Path) -> None:
    assert _problemas(tmp_path, "---\ntitle: ADR 4.1.0003 95–97\n---\n\nok\n") == []


def test_a_secao_7_do_technical_e_registro_historico(tmp_path: pathlib.Path) -> None:
    texto = "# T\n\n## 2. Tasks\n\nok\n\n## 7. Pós-execução\n\n- `employee.py:113` → `:120`\n"
    assert _problemas(tmp_path, texto, "docs/stages/9.9-x/technical.md") == []
    assert len(_problemas(tmp_path, texto, "docs/stages/9.9-x/concept.md")) == 1


def test_a_linha_do_achado_e_a_da_referencia(tmp_path: pathlib.Path) -> None:
    achados = _problemas(tmp_path, "linha 1\n\nlinha 3 (`employee.py:113`)\n")
    assert len(achados) == 1, achados
    assert achados[0].startswith("docs/x.md:3: citação por número de linha a employee.py:")


@pytest.mark.parametrize("pasta", [".claude", ".github", "docs"])
def test_a_raiz_o_harness_o_github_e_os_docs_sao_varridos(
    tmp_path: pathlib.Path, pasta: str
) -> None:
    assert len(_problemas(tmp_path, "`employee.py:113`", f"{pasta}/y.md")) == 1


def test_os_md_da_raiz_sao_varridos(tmp_path: pathlib.Path) -> None:
    assert len(_problemas(tmp_path, "`employee.py:113`", "README.md")) == 1


def test_pasta_fora_do_escopo_nao_e_varrida(tmp_path: pathlib.Path) -> None:
    assert _problemas(tmp_path, "`employee.py:113`", "outra/y.md") == []


def test_pastas_ignoradas_nao_contam_como_codigo_do_repo(tmp_path: pathlib.Path) -> None:
    repo = _repo(tmp_path, {"docs/x.md": "`vendor.py:40` é de terceiro"})
    (repo / "src" / ".venv").mkdir(parents=True)
    (repo / "src" / ".venv" / "vendor.py").write_text("x = 1\n", encoding="utf-8")
    assert gate.problemas(repo) == []


# --- main ------------------------------------------------------------------------------


def _main(monkeypatch: pytest.MonkeyPatch, repo: pathlib.Path) -> int:
    monkeypatch.setattr(sys, "argv", ["check_adr_code_citations.py", "--repo", str(repo)])
    resultado: int = gate.main()
    return resultado


def test_main_sai_0_quando_tudo_confere(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _main(monkeypatch, _repo(tmp_path, {"docs/x.md": "ok"})) == 0
    assert "nenhuma citação por linha" in capsys.readouterr().out


def test_main_sai_1_e_lista_os_achados(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repo(tmp_path, {"docs/x.md": "`employee.py:1` e ADR 4.1.0003 95."})
    assert _main(monkeypatch, repo) == 1
    erro = capsys.readouterr().err
    assert "2 problema(s)" in erro
    assert "docs/x.md:1:" in erro


def test_main_sai_2_sem_adr(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _main(monkeypatch, _repo(tmp_path, {}, adrs={})) == _SAIDA_FATAL
    assert "FATAL" in capsys.readouterr().err


# --- Auditoria de mutação (sobreviventes da primeira rodada) ----------------------------

_ADR_4 = "# ADR 4.1.0004\n\n## Decision\n\nhr reads schedules in member units.\n"
_EXTRAS = {"pyproject.toml": "[project]\n", "uv.lock": "version = 1\n"}


def _repo2(tmp_path: pathlib.Path, texto: str) -> list[str]:
    adrs = {"docs/adr/4_1_0003-politica.md": _ADR, "docs/adr/4_1_0004-rh.md": _ADR_4}
    return list(gate.problemas(_repo(tmp_path, {**_EXTRAS, "docs/x.md": texto}, adrs)))


@pytest.mark.parametrize(
    "texto",
    [
        "ver [`employee.py`](../src/restaurant_hub/staff/employee.py#L113) antes",
        "o [ADR 4.1.0003](./4_1_0003-politica.md#L79) diz",
        "ver [`4_1_0003-politica.md`](./4_1_0003-politica.md#L12).",
        "o guard ([`employee.py`](../src/restaurant_hub/staff/employee.py) 113–116) recusa",
        "o guard (`employee.py` 113 e 120) recusa",
        "o guard (``employee.py``:113) recusa",
        "`employee.py` (`Employee`, linha 3) recusa",
        "o guard (`employee.py` L113) recusa",
        "`employee.py` (`Employee`, l. 113) recusa",
        "`employee.py` (`Employee`, ln 113) recusa",
        "`employee.py` (`Employee`, line ~113) recusa",
        "ADR 4.1.0003 (c), 95.",
        "ADR 4.1.0003 (c) 95 e 97 diz",
        "ADR 4.1.0003 (c) 79: o corte",
        "ADR 4.1.0003 (c, l. 79) diz",
        "ADRs 4.1.0003 95–97.",
        "a regra (`pyproject.toml:12`) liga",
        "o lock (`uv.lock:40`) fixa",
    ],
)
def test_formas_de_linha_que_escapavam_reprovam(tmp_path: pathlib.Path, texto: str) -> None:
    achados = _repo2(tmp_path, texto)
    assert len(achados) == 1, achados
    assert "número de linha" in achados[0]


@pytest.mark.parametrize(
    ("texto", "alvo"),
    [
        ("ADR 4.1.0003 (c) e ADR 4.1.0004 95.", "ao ADR 4.1.0004"),
        ("ADR 4.1.0003 (c) e `check_layout.py` 130.", "a check_layout.py"),
    ],
)
def test_o_trecho_acaba_na_proxima_fonte(tmp_path: pathlib.Path, texto: str, alvo: str) -> None:
    achados = _repo2(tmp_path, texto)
    assert len(achados) == 1, achados
    assert alvo in achados[0]


@pytest.mark.parametrize(
    ("texto", "motivo"),
    [
        ('ADRs 4.1.0003 e 4.1.0004 › "zzz".', 'trecho "zzz" não existe'),
        ('ver [`4_1_0003-politica.md`](./4_1_0003-politica.md) › "zzz".', 'trecho "zzz"'),
        ('ADR 4.1.0003 Alternative B › "zzz".', 'trecho "zzz"'),
        ('ADR 4.1.0003 §Decision 2 › "zzz".', 'trecho "zzz"'),
        ('ADR 4.1.0003 (c) -> "block".', "fora da forma"),
        ('ADRs 4.1.0003/0009 › "block".', "ADR 4.1.0009 não existe"),
    ],
)
def test_trechos_que_escapavam_reprovam(tmp_path: pathlib.Path, texto: str, motivo: str) -> None:
    achados = _repo2(tmp_path, texto)
    assert len(achados) == 1, achados
    assert motivo in achados[0]


@pytest.mark.parametrize(
    "texto",
    [
        "ADRs 4.1.0003 e 0004, ambos aceitos.",
        'ADRs 4.1.0003/0004 › "hr reads schedules in member units".',
        "ADR 4.1.0003 › `**unavailability**`.",
        'ADR 4.1.0003 › "".',
        "o `aff/employee.py:113` de outro projeto",
        "veja `/employee.py:113` no container",
        "~~~\nemployee.py:113: in execute\n~~~",
        "- item\n\n  ```\n  employee.py:113: in execute\n  ```",
        'ADR 4.1.0003 diz "até 44, no máximo".',
        "ADR 4.1.0003 diz *até 44, no máximo*.",
        "ADR 4.1.0003 fixa `limite(44)` aqui.",
        "ADR 4.1.0003 (Steps 10–12) entrou.",
        "ADR 4.1.0003 (Tasks 10–12) aplicam.",
        "ADR 4.1.0003 (corte às 22:30) vale.",
    ],
)
def test_o_que_nao_e_linha_passa(tmp_path: pathlib.Path, texto: str) -> None:
    assert _repo2(tmp_path, texto) == []


def test_achados_saem_em_ordem_de_linha(tmp_path: pathlib.Path) -> None:
    achados = _repo2(tmp_path, "`employee.py:1` e ADR 4.1.0003 95.")
    assert [a.split(": ", 1)[1][:30] for a in achados] == sorted(
        a.split(": ", 1)[1][:30] for a in achados
    )
    assert "employee.py" in achados[0]


def test_errata_de_subtitulo_nao_e_poupada(tmp_path: pathlib.Path) -> None:
    adr = _ADR.replace("## Errata", "### Errata")
    achados = gate.problemas(_repo(tmp_path, {}, {"docs/adr/4_1_0003-politica.md": adr}))
    assert len(achados) == 1, achados


def test_a_errata_vai_ate_o_proximo_titulo_de_nivel_2(tmp_path: pathlib.Path) -> None:
    adr = _ADR.replace("| References |", "### 2026-07\n\n- `employee.py:113`\n\n| References |")
    assert gate.problemas(_repo(tmp_path, {}, {"docs/adr/4_1_0003-politica.md": adr})) == []
