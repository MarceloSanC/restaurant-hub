"""`scripts/check_mutation_run.py` reprova a corrida de mutação que não mediu (issue #87).

A corrida noturna morreu na coleta durante dias sem alarme: o job era
`continue-on-error`, e o `mutmut run` que sai com 0 sem ter testado mutante
nenhum (zero mutantes, ou corrida interrompida) passaria até sem ele. O script
lê o resumo do `mutmut export-cicd-stats` e falha nesses casos.

Desde a issue #217, com `--sobreviventes`/`--equivalentes`, também falha com
mutante vivo fora da lista de equivalentes conhecidos e com item da lista que
não sobreviveu (lista desatualizada).
"""

import importlib.util
import json
import pathlib
import subprocess
import sys
import tomllib
import types
from typing import Any

import pytest
import yaml

pytestmark = pytest.mark.unit

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_SCRIPT = _REPO_ROOT / "scripts" / "check_mutation_run.py"


def _carregar_script() -> types.ModuleType:
    """Importa `scripts/check_mutation_run.py` sem mexer no `sys.path`."""
    spec = importlib.util.spec_from_file_location("check_mutation_run", _SCRIPT)
    assert spec is not None and spec.loader is not None
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


_script = _carregar_script()


def _resumo(**contagens: int) -> dict[str, int]:
    """O JSON do `save_cicd_stats` do mutmut 3.7.0, zerado, com as contagens dadas."""
    base = {
        "killed": 0,
        "survived": 0,
        "total": 0,
        "no_tests": 0,
        "skipped": 0,
        "suspicious": 0,
        "timeout": 0,
        "check_was_interrupted_by_user": 0,
        "segfault": 0,
    }
    return {**base, **contagens}


def _gravar(tmp_path: pathlib.Path, resumo: dict[str, int]) -> str:
    caminho = tmp_path / "mutmut-cicd-stats.json"
    caminho.write_text(json.dumps(resumo), encoding="utf-8")
    return str(caminho)


@pytest.mark.parametrize(
    "resumo",
    [
        _resumo(total=10, killed=7, survived=3),
        # Sem a lista, o resumo sozinho não reprova sobrevivente (issue #217:
        # o limiar mora em `--equivalentes`).
        _resumo(total=4, survived=4),
        # Cada desfecho de mutante testado conta para fechar o total.
        _resumo(
            total=7,
            killed=1,
            no_tests=1,
            skipped=1,
            suspicious=1,
            timeout=1,
            segfault=1,
            survived=1,
        ),
    ],
)
def test_corrida_que_testou_todo_mutante_passa(
    tmp_path: pathlib.Path, resumo: dict[str, int], capsys: pytest.CaptureFixture[str]
) -> None:
    assert _script.main([_gravar(tmp_path, resumo)]) == 0
    assert f"{resumo['total']} mutantes testados ({resumo['survived']} sobreviventes)" in (
        capsys.readouterr().out
    )


@pytest.mark.parametrize(
    ("resumo", "trecho"),
    [
        # `only_mutate` que não casa: o mutmut sai com 0 e não gerou nada.
        (_resumo(), "não gerou mutante nenhum"),
        # A coleta morreu depois de gerar os mutantes: todos `not checked`.
        (_resumo(total=12), "12 de 12 mutantes ficaram sem teste"),
        # Um só sem desfecho já é corrida que não mediu a suíte inteira.
        (_resumo(total=12, killed=11), "1 de 12 mutantes ficaram sem teste"),
        # Interrupção não é desfecho de teste.
        (_resumo(total=3, killed=2, check_was_interrupted_by_user=1), "1 de 3 mutantes"),
    ],
)
def test_corrida_que_nao_mediu_reprova(
    tmp_path: pathlib.Path,
    resumo: dict[str, int],
    trecho: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert _script.main([_gravar(tmp_path, resumo)]) == 1
    assert trecho in capsys.readouterr().err


def test_sem_resumo_reprova(tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]) -> None:
    """O `export-cicd-stats` não grava nada quando a coleta quebrou antes da corrida."""
    assert _script.main([str(tmp_path / "ausente.json")]) == 1
    assert "não existe" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("resumo", "codigo"),
    [(None, 1), (_resumo(), 1), (_resumo(total=2, killed=2), 0)],
)
def test_o_codigo_de_saida_do_processo_e_o_veredito(
    tmp_path: pathlib.Path, resumo: dict[str, int] | None, codigo: int
) -> None:
    """O workflow lê o código de saída do processo, não o retorno de `main`."""
    caminho = (
        tmp_path / "ausente.json" if resumo is None else pathlib.Path(_gravar(tmp_path, resumo))
    )

    processo = subprocess.run(
        [sys.executable, str(_SCRIPT), str(caminho)], capture_output=True, check=False
    )

    assert processo.returncode == codigo


def test_sem_argumento_le_o_caminho_do_mutmut(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """O workflow chama sem argumento; o padrão é onde o mutmut 3.7.0 grava."""
    (tmp_path / "mutants").mkdir()
    (tmp_path / "mutants" / "mutmut-cicd-stats.json").write_text(
        json.dumps(_resumo(total=1, killed=1)), encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)

    assert _script.main([]) == 0


# ---------------------------------------------------------------------------
# O workflow que chama o script. Quebra silenciosa (classe 1 do
# `test_ci_workflow.py`): devolver o `continue-on-error` ao job, ou tirar o
# passo, deixa o `make check` verde e a corrida noturna volta a não medir nada
# sem alarme — o defeito da #87.
# ---------------------------------------------------------------------------

_AUDIT_GATE = _REPO_ROOT / ".github" / "workflows" / "audit-gate.yml"


@pytest.fixture(scope="module")
def job_de_mutacao() -> dict[str, Any]:
    workflow: dict[str, Any] = yaml.safe_load(_AUDIT_GATE.read_text(encoding="utf-8"))
    job: dict[str, Any] = workflow["jobs"]["mutation"]
    return job


def _indice_do_passo(job: dict[str, Any], trecho: str) -> int:
    indices = [i for i, passo in enumerate(job["steps"]) if trecho in passo.get("run", "")]
    assert len(indices) == 1, f"esperado um passo com {trecho!r}, achados {indices}"
    return indices[0]


def test_o_job_de_mutacao_nao_engole_a_propria_falha(job_de_mutacao: dict[str, Any]) -> None:
    assert "continue-on-error" not in job_de_mutacao


@pytest.mark.parametrize(
    "trecho",
    ["pytest tests/", "mutmut run", "scripts/check_mutation_run.py"],
)
def test_os_passos_que_decidem_se_a_corrida_mediu_reprovam(
    job_de_mutacao: dict[str, Any], trecho: str
) -> None:
    passo = job_de_mutacao["steps"][_indice_do_passo(job_de_mutacao, trecho)]

    # Nada que pule o passo ou engula a saída dele: `if:`, `continue-on-error`,
    # e qualquer `||` (`|| true`, `|| exit 0`, `|| :`).
    assert "continue-on-error" not in passo
    assert "if" not in passo
    assert "||" not in passo["run"]


def test_a_conferencia_le_o_resumo_da_corrida(job_de_mutacao: dict[str, Any]) -> None:
    corrida = _indice_do_passo(job_de_mutacao, "mutmut run")
    conferencia = _indice_do_passo(job_de_mutacao, "scripts/check_mutation_run.py")
    run = job_de_mutacao["steps"][conferencia]["run"]

    assert conferencia > corrida
    assert run.index("mutmut export-cicd-stats") < run.index("scripts/check_mutation_run.py")


# ---------------------------------------------------------------------------
# Limiar de sobreviventes (issue #217): só os equivalentes conhecidos vivem.
# ---------------------------------------------------------------------------

_A = "restaurant_hub.m.xǁCǁsave__mutmut_34"
_B = "restaurant_hub.m.x_f__mutmut_15"
_C = "restaurant_hub.features.identity.application.use_cases.authorize_action.x_f__mutmut_3"


def _results(**estados: str) -> str:
    """A saída do `mutmut results` do mutmut 3.7.0: `    <nome>: <estado>` por linha."""
    return "".join(f"    {nome}: {estado}\n" for nome, estado in estados.items())


def _linhas(*nomes: str) -> str:
    return "".join(f"{nome}\n" for nome in nomes)


def _rodar_com_lista(
    tmp_path: pathlib.Path, resultados: str, lista: str, resumo: dict[str, int] | None = None
) -> int:
    saida = tmp_path / "mutmut-results.txt"
    saida.write_text(resultados, encoding="utf-8")
    conhecidos = tmp_path / "equivalentes.txt"
    conhecidos.write_text(lista, encoding="utf-8")
    stats = _gravar(tmp_path, resumo or _resumo(total=10, killed=8, survived=2))
    argumentos = [stats, "--sobreviventes", str(saida), "--equivalentes", str(conhecidos)]
    return int(_script.main(argumentos))


def test_so_os_equivalentes_conhecidos_vivos_passa(tmp_path: pathlib.Path) -> None:
    lista = "# comentário\n\n" + f"{_A}  # premissa\n" + _linhas(_B)
    resultados = _results(**{_A: "survived", _B: "survived", _C: "killed"})

    assert _rodar_com_lista(tmp_path, resultados, lista) == 0


@pytest.mark.parametrize("estado", ["survived", "no tests", "suspicious", "skipped"])
def test_mutante_vivo_fora_da_lista_reprova(
    tmp_path: pathlib.Path, estado: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """O defeito que a #217 fecha: um sobrevivente novo no código de acesso passava calado."""
    resultados = _results(**{_A: "survived", _B: "survived", _C: estado})

    assert _rodar_com_lista(tmp_path, resultados, _linhas(_A, _B)) == 1
    assert f"fora da lista de equivalentes: {_C} ({estado})" in capsys.readouterr().err


@pytest.mark.parametrize("estado", ["killed", "timeout", "segfault", "caught by type check"])
def test_estado_de_mutante_morto_nao_conta_como_vivo(tmp_path: pathlib.Path, estado: str) -> None:
    resultados = _results(**{_A: "survived", _B: "survived", _C: estado})

    assert _rodar_com_lista(tmp_path, resultados, _linhas(_A, _B)) == 0


def test_equivalente_que_nao_sobreviveu_reprova_como_lista_desatualizada(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Editar a função renumera os mutantes; teste novo pode matar um deles."""
    resultados = _results(**{_A: "survived", _B: "killed"})

    assert _rodar_com_lista(tmp_path, resultados, _linhas(_A, _B)) == 1
    assert f"lista desatualizada): {_B}" in capsys.readouterr().err


def test_linha_que_nao_e_mutante_nao_conta(tmp_path: pathlib.Path) -> None:
    resultados = "WARNING: algo do uv\n" + _results(**{_A: "survived"})

    assert _rodar_com_lista(tmp_path, resultados, _linhas(_A)) == 0


def test_a_lista_nao_dispensa_a_corrida_que_nao_mediu(tmp_path: pathlib.Path) -> None:
    assert _rodar_com_lista(tmp_path, "", "", _resumo(total=12, killed=11)) == 1


@pytest.mark.parametrize(
    "argumentos",
    [
        ["--sobreviventes", "x.txt"],
        ["--equivalentes", "x.txt"],
        ["--sobreviventes"],
        ["a.json", "b.json"],
    ],
)
def test_metade_da_lista_e_uso_errado(argumentos: list[str]) -> None:
    assert _script.main(argumentos) == 2  # noqa: PLR2004


def test_arquivo_da_lista_ausente_reprova(tmp_path: pathlib.Path) -> None:
    stats = _gravar(tmp_path, _resumo(total=1, killed=1))
    ausente = str(tmp_path / "ausente.txt")

    assert _script.main([stats, "--sobreviventes", ausente, "--equivalentes", ausente]) == 1


def test_o_job_confere_os_sobreviventes_contra_a_lista_do_repo(
    job_de_mutacao: dict[str, Any],
) -> None:
    """Tirar os argumentos devolve o job ao "qualquer número de sobreviventes passa"."""
    passo = _indice_do_passo(job_de_mutacao, "scripts/check_mutation_run.py")
    run = job_de_mutacao["steps"][passo]["run"]

    assert run.index("mutmut results > mutmut-results.txt") < run.index("check_mutation_run.py")
    assert "--sobreviventes mutmut-results.txt" in run
    assert "--equivalentes scripts/mutation_equivalents.txt" in run
    assert (_REPO_ROOT / "scripts" / "mutation_equivalents.txt").is_file()


def test_todo_equivalente_da_lista_e_de_um_modulo_do_escopo() -> None:
    """Item de módulo fora do `only_mutate` nunca sobreviveria: entrada morta na lista."""
    lista = (_REPO_ROOT / "scripts" / "mutation_equivalents.txt").read_text(encoding="utf-8")
    with (_REPO_ROOT / "pyproject.toml").open("rb") as arquivo:
        escopo = tomllib.load(arquivo)["tool"]["mutmut"]["only_mutate"]
    modulos = {
        caminho.removeprefix("src/").removesuffix(".py").replace("/", ".") for caminho in escopo
    }

    nomes = _script.equivalentes(lista)
    assert nomes
    for nome in nomes:
        assert "__mutmut_" in nome
        assert any(nome.startswith(f"{modulo}.") for modulo in modulos), nome
