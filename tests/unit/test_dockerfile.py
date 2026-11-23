"""Invariantes do `Dockerfile`: as imagens instalam as versões do `uv.lock`.

Por que este teste existe (issue #244): as duas stages instalavam com
`uv pip install` a partir do `pyproject.toml`, que declara faixas
(`tzdata>=2024.1`). A imagem resolvia as versões no momento do build e podia sair
com outras que não as que o CI testou, sem nenhum sinal — o gate `lock-check`
confere o lock, não o que a imagem instala. A correção (`uv sync --locked`) é uma
flag por linha, e trocá-la de volta deixaria a suíte verde; daí este arquivo.

O build de verdade roda no workflow `docker-build.yml`, só quando mudam os
arquivos que decidem o conteúdo da imagem. Este teste é a parte barata, em todo
`make check`: a forma do `Dockerfile`, a do `postCreateCommand` do devcontainer
(que reinstala o venv no volume) e o filtro de caminhos do workflow.

Não testar aqui nomes de stage além dos dois que o compose e o Makefile usam,
pacotes de sistema nem comentários.
"""

from __future__ import annotations

import json
import re
import shlex
from itertools import pairwise
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
DOCKERFILE = REPO_ROOT / "Dockerfile"
DEVCONTAINER = REPO_ROOT / ".devcontainer" / "devcontainer.json"
DOCKER_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "docker-build.yml"

# As duas stages que alguém consome: `builder` (compose/devcontainer,
# `make docker-build`) e `runtime` (`make docker-build-prod`, deploy).
STAGES = ("builder", "runtime")

# Arquivos que decidem o que a imagem instala: mudar qualquer um precisa
# construir as stages no CI.
IMAGE_INPUTS = ("Dockerfile", ".dockerignore", "pyproject.toml", "uv.lock")


def _instructions(text: str) -> list[str]:
    """Instruções do Dockerfile, uma por item, com continuações juntadas."""
    joined = re.sub(r"\\\n", " ", text)
    return [
        line.strip()
        for line in joined.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


def _stages(text: str) -> dict[str, list[str]]:
    """Instruções de cada stage, pelo nome do `FROM ... AS <nome>`."""
    stages: dict[str, list[str]] = {}
    current: list[str] = []
    for instruction in _instructions(text):
        match = re.match(r"FROM\s+\S+\s+AS\s+(\S+)", instruction, re.IGNORECASE)
        if match:
            current = stages.setdefault(match.group(1), [])
            continue
        current.append(instruction)
    return stages


def _uv_sync_calls(instruction: str) -> list[list[str]]:
    """Argumentos de cada `uv sync` de uma instrução `RUN`."""
    if not instruction.startswith("RUN "):
        return []
    calls = []
    for segment in re.split(r"&&|;", instruction.removeprefix("RUN ")):
        tokens = [t for t in shlex.split(segment) if not t.startswith("--mount=")]
        if tokens[:2] == ["uv", "sync"]:
            calls.append(tokens[2:])
    return calls


@pytest.fixture(scope="module")
def dockerfile() -> str:
    return DOCKERFILE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def stages(dockerfile: str) -> dict[str, list[str]]:
    return _stages(dockerfile)


def test_dockerfile_nao_instala_pelo_pip_interface(dockerfile: str) -> None:
    """Nenhum `pip install` (nem `uv pip install`): ele resolve fora do lock."""
    offenders = [i for i in _instructions(dockerfile) if re.search(r"\bpip\s+install\b", i)]
    assert offenders == [], f"instalação fora do uv.lock: {offenders}"


@pytest.mark.parametrize("stage", STAGES)
def test_stage_instala_o_projeto_pelo_lock(stage: str, stages: dict[str, list[str]]) -> None:
    """Todo `uv sync` da stage tem `--locked`, e um deles instala o projeto.

    `--locked` falha o build com o lock fora de sincronia com o pyproject; o
    `--frozen` usaria o lock sem conferir, e sem flag o uv o reescreveria.
    """
    calls = [c for i in stages[stage] for c in _uv_sync_calls(i)]
    assert calls, f"a stage {stage} não instala com `uv sync`"
    unlocked = [c for c in calls if "--locked" not in c]
    assert unlocked == [], f"`uv sync` sem --locked na stage {stage}: {unlocked}"
    assert any("--no-install-project" not in c for c in calls), (
        f"a stage {stage} só instala as dependências, nunca o projeto"
    )


@pytest.mark.parametrize("stage", STAGES)
def test_lock_entra_na_stage_antes_do_primeiro_sync(
    stage: str, stages: dict[str, list[str]]
) -> None:
    """O `uv.lock` é copiado (com o pyproject) antes do primeiro `uv sync`."""
    instructions = stages[stage]
    first_sync = next(n for n, i in enumerate(instructions) if _uv_sync_calls(i))
    copied = " ".join(i for i in instructions[:first_sync] if i.startswith("COPY "))
    for name in ("pyproject.toml", "uv.lock"):
        assert re.search(rf"(^|\s){re.escape(name)}(\s|$)", copied), (
            f"{name} não chega à stage {stage} antes do primeiro `uv sync`"
        )


def test_runtime_nao_instala_dependencias_de_dev(stages: dict[str, list[str]]) -> None:
    """A runtime não pede extra nenhuma e exclui os grupos de dev."""
    calls = [c for i in stages["runtime"] for c in _uv_sync_calls(i)]
    for call in calls:
        assert not any(a in {"--extra", "--all-extras"} or a.startswith("--extra=") for a in call)
        assert "--no-dev" in call, f"`uv sync` da runtime sem --no-dev: {call}"


def test_builder_instala_a_extra_dev(stages: dict[str, list[str]]) -> None:
    """O builder (devcontainer) traz ruff/mypy/pytest — a extra `dev`."""
    calls = [c for i in stages["builder"] for c in _uv_sync_calls(i)]
    assert calls
    for call in calls:
        assert "--extra=dev" in call or any(
            a == "--extra" and b == "dev" for a, b in pairwise(call)
        ), f"`uv sync` do builder sem a extra dev: {call}"


def test_uv_da_imagem_tem_versao_fixada(dockerfile: str) -> None:
    """A imagem do uv é uma versão `X.Y.Z`, nunca `latest`.

    O `--locked` depende de como o uv lê o lock; com `latest`, essa leitura
    muda sem commit nenhum (doc do uv, "Using uv in Docker": pin a version).
    """
    refs = re.findall(r"ghcr\.io/astral-sh/uv:(\S+)", dockerfile)
    assert refs, "o Dockerfile não copia o uv da imagem oficial"
    assert all(re.fullmatch(r"\d+\.\d+\.\d+", ref) for ref in refs), refs


def test_devcontainer_reinstala_pelo_lock() -> None:
    """O `postCreateCommand` reinstala o venv do volume pelo lock, não pelo pip."""
    config: dict[str, Any] = json.loads(DEVCONTAINER.read_text(encoding="utf-8"))
    command = config["postCreateCommand"]
    assert "pip install" not in command
    assert "uv sync --locked" in command


@pytest.mark.parametrize("event", ["pull_request", "push"])
def test_workflow_constroi_quando_muda_o_que_a_imagem_instala(event: str) -> None:
    """O filtro de caminhos do `docker-build.yml` cobre todo arquivo que decide a imagem."""
    workflow: dict[Any, Any] = yaml.safe_load(DOCKER_WORKFLOW.read_text(encoding="utf-8"))
    # O YAML 1.1 do PyYAML lê a chave `on` como o booleano True.
    triggers: dict[str, Any] = workflow.get("on") or workflow[True]
    paths = set(triggers[event]["paths"])
    missing = sorted(set(IMAGE_INPUTS) - paths)
    assert missing == [], f"{event} não constrói a imagem quando mudam: {missing}"


def test_workflow_so_le_o_repositorio() -> None:
    """O token do `docker-build.yml` só lê: PR de fork (repo público) dispara o build."""
    workflow: dict[Any, Any] = yaml.safe_load(DOCKER_WORKFLOW.read_text(encoding="utf-8"))
    assert workflow.get("permissions") == {"contents": "read"}
    triggers: dict[str, Any] = workflow.get("on") or workflow[True]
    assert "pull_request_target" not in triggers
    for job in workflow["jobs"].values():
        assert "permissions" not in job, "permissão de job amplia a do workflow"
