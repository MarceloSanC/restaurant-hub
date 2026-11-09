"""Leitura do `Makefile` para os testes que travam a configuração do gate.

Fonte única da leitura de receita (issue #97): `test_ci_workflow.py` e
`test_precommit_config.py` tinham cada um a sua cópia de `_recipe`, e uma
correção feita numa só (a regra duplicada que troca a receita, por exemplo)
deixaria o outro teste cobrando a receita errada.
"""

from __future__ import annotations

import shlex
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
MAKEFILE = REPO_ROOT / "Makefile"


def makefile_lines() -> list[str]:
    """As linhas do `Makefile` da raiz do repositório."""
    return MAKEFILE.read_text(encoding="utf-8").splitlines()


def recipe(target: str) -> list[list[str]]:
    """Os comandos da receita de `target` no Makefile, já quebrados em tokens."""
    lines = makefile_lines()
    header = f"{target}:"
    if header not in lines:
        pytest.fail(f"o Makefile não tem mais o target `{target}`")
    # Uma segunda regra com o mesmo alvo troca a receita (o make avisa "overriding
    # recipe" e roda a última); ler só a primeira seria cobrar a receita morta.
    assert lines.count(header) == 1, (
        f"o Makefile precisa declarar o target `{target}` exatamente uma vez; tem "
        f"{lines.count(header)}"
    )
    commands: list[list[str]] = []
    for line in lines[lines.index(header) + 1 :]:
        if not line.startswith("\t"):
            break
        commands.append(shlex.split(line))
    assert commands, f"o target `{target}` do Makefile não tem receita"
    return commands


def prerequisites(target: str) -> list[str]:
    """Os pré-requisitos de `target`, da linha `target: ...` do Makefile."""
    header = f"{target}:"
    [line] = [line for line in makefile_lines() if line.split(" ", 1)[0] == header]
    return line.removeprefix(header).split()
