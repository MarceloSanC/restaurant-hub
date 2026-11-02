"""`scripts/check_mutation_run.py` reprova a corrida de mutação que não mediu (issue #87).

A corrida noturna morreu na coleta durante dias sem alarme: o job era
`continue-on-error`, e o `mutmut run` que sai com 0 sem ter testado mutante
nenhum (zero mutantes, ou corrida interrompida) passaria até sem ele. O script
lê o resumo do `mutmut export-cicd-stats` e falha nesses casos — e só neles:
sobrevivente continua observacional (limiar da issue #45).
"""

import importlib.util
import json
import pathlib
import subprocess
import sys
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
        # Sobrevivente não reprova: o limiar é a issue #45, não esta.
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
    job: dict[str, Any] = workflow["jobs"]["mutation-access-modules"]
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
