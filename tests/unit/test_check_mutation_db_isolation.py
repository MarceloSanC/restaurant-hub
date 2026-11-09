"""`scripts/check_mutation_db_isolation.py` reprova a corrida com disputa de Postgres (issue #132).

O run 41475839122 reportou 581/581 mutantes mortos com 11 `deadlock detected` e
49 `relation ... does not exist` no log do service: workers do mutmut recriando
o schema uns sob os outros. O script lê o log do Postgres durante o `mutmut run`
e reprova qualquer uma das duas assinaturas.
"""

import importlib.util
import pathlib
import types
from typing import Any

import pytest
import yaml

pytestmark = pytest.mark.unit

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_SCRIPT = _REPO_ROOT / "scripts" / "check_mutation_db_isolation.py"


def _load_script() -> types.ModuleType:
    spec = importlib.util.spec_from_file_location("check_mutation_db_isolation", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_script = _load_script()

# Linhas no formato do log do `postgres:16-alpine`, tiradas do run 41475839122.
_DEADLOCK = "2026-10-30 04:21:07.120 UTC [812] ERROR:  deadlock detected"
_MISSING = (
    '2026-10-30 04:21:09.871 UTC [907] ERROR:  relation "users" does not exist at character 13'
)
_DUPLICATE = (
    "2026-10-30 04:22:01.004 UTC [955] ERROR:  duplicate key value violates "
    'unique constraint "uq_users_email"'
)
_NOTICE = 'NOTICE:  database "restaurant_hub_mutmut_812" does not exist, skipping'


def _run(tmp_path: pathlib.Path, *lines: str) -> int:
    log = tmp_path / "postgres.log"
    log.write_text("\n".join(lines) + "\n", encoding="utf-8")
    result: int = _script.main([str(log)])
    return result


def test_log_sem_disputa_passa(tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert _run(tmp_path, _DUPLICATE, _NOTICE) == 0
    out = capsys.readouterr().out
    assert "deadlock detected: 0" in out
    assert 'relation "..." does not exist: 0' in out
    assert "linhas do log lidas: 2" in out


@pytest.mark.parametrize("line", [_DEADLOCK, _MISSING])
def test_cada_assinatura_de_disputa_reprova_sozinha(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str], line: str
) -> None:
    assert _run(tmp_path, _DUPLICATE, line) == 1
    assert "issue #132" in capsys.readouterr().err


def test_conta_as_linhas_de_cada_assinatura() -> None:
    log = "\n".join([_DEADLOCK, _MISSING, _DEADLOCK, _DUPLICATE, _MISSING, _MISSING])
    assert _script.contention(log) == {
        "deadlock detected": 2,
        'relation "..." does not exist': 3,
    }


def test_banco_inexistente_nao_e_tabela_sumida() -> None:
    """O `DROP DATABASE IF EXISTS` do worker avisa no log; não é a disputa."""
    assert not any(_script.contention(_NOTICE).values())


def test_log_ausente_reprova(tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert _script.main([str(tmp_path / "nao-existe.log")]) == 1
    assert "não existe" in capsys.readouterr().err


@pytest.mark.parametrize("argv", [[], ["a.log", "b.log"]])
def test_exige_exatamente_um_log(argv: list[str]) -> None:
    assert _script.main(argv) == 1


# ---------------------------------------------------------------------------
# O workflow que chama o script: sem o passo, ou com ele engolindo a saída, a
# disputa volta sem alarme e a contagem de mortos deixa de medir a suíte.
# ---------------------------------------------------------------------------

_AUDIT_GATE = _REPO_ROOT / ".github" / "workflows" / "audit-gate.yml"


@pytest.fixture(scope="module")
def steps() -> list[dict[str, Any]]:
    workflow: dict[str, Any] = yaml.safe_load(_AUDIT_GATE.read_text(encoding="utf-8"))
    found: list[dict[str, Any]] = workflow["jobs"]["mutation-access-modules"]["steps"]
    return found


def _index(steps: list[dict[str, Any]], fragment: str) -> int:
    indices = [i for i, step in enumerate(steps) if fragment in step.get("run", "")]
    assert len(indices) == 1, f"esperado um passo com {fragment!r}, achados {indices}"
    return indices[0]


def test_o_passo_le_o_log_do_service_desde_o_inicio_da_corrida(
    steps: list[dict[str, Any]],
) -> None:
    run_step = steps[_index(steps, "mutmut run")]["run"]
    check = _index(steps, "scripts/check_mutation_db_isolation.py")
    check_run = steps[check]["run"]

    assert check > _index(steps, "mutmut run")
    # O instante é gravado antes da corrida, no mesmo passo.
    assert run_step.index("MUTMUT_STARTED_AT") < run_step.index("mutmut run")
    assert '--since "$MUTMUT_STARTED_AT"' in check_run
    assert "job.services.postgres.id" in check_run
    assert check_run.index("docker logs") < check_run.index("check_mutation_db_isolation.py")


def test_o_passo_reprova(steps: list[dict[str, Any]]) -> None:
    step = steps[_index(steps, "scripts/check_mutation_db_isolation.py")]

    assert "continue-on-error" not in step
    assert "if" not in step
    assert "||" not in step["run"]
