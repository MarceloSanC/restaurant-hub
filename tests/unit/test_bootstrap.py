"""Testes do bootstrap da aplicação — composition_root e entrypoint main."""

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest
from fastapi import FastAPI

from restaurant_hub import main
from restaurant_hub.composition_root import ApplicationDependencies, wire_dependencies
from restaurant_hub.shared.infrastructure.config.settings import Settings

pytestmark = pytest.mark.unit


def test_wire_dependencies_monta_o_container() -> None:
    deps = wire_dependencies()
    assert isinstance(deps, ApplicationDependencies)


def test_wire_dependencies_aceita_settings_explicito() -> None:
    deps = wire_dependencies(Settings(_env_file=None))
    assert isinstance(deps, ApplicationDependencies)


def test_main_expoe_app_asgi() -> None:
    assert isinstance(main.app, FastAPI)


# ---------------------------------------------------------------------------
# Issue #6 — o logging configurado no boot real, não só a função
# ---------------------------------------------------------------------------

# Sobe a app pelo caminho do `uvicorn restaurant_hub.main:app`: o `Config` aplica o
# logging do próprio uvicorn e o `load()` importa o módulo da app. A espia entra
# antes do import, então conta todas as chamadas do boot e só elas. O resultado vai
# para um arquivo, e não para o stdout, porque com `LOG_LEVEL=DEBUG` o próprio boot
# escreve no stdout, que é para onde o handler configurado aponta.
_BOOT = textwrap.dedent(
    """
    import json
    import logging
    import sys

    import uvicorn

    from restaurant_hub.shared.infrastructure.logging import config as logging_config

    chamadas = []
    original = logging_config.configure_logging

    def espia(level="INFO"):
        chamadas.append(level)
        original(level)

    logging_config.configure_logging = espia
    uvicorn.Config("restaurant_hub.main:app").load()

    root = logging.getLogger()
    with open(sys.argv[1], "w", encoding="utf-8") as saida:
        json.dump(
            {
                "chamadas": chamadas,
                "root": logging.getLevelName(root.level),
                "handlers": [
                    [type(h).__name__, getattr(getattr(h, "stream", None), "name", None)]
                    for h in root.handlers
                ],
                "sqlalchemy": logging.getLevelName(
                    logging.getLogger("sqlalchemy.engine").level
                ),
            },
            saida,
        )
    """
)


def _subir_a_app(tmp_path: Path, log_level: str | None) -> dict[str, object]:
    """Boot completo num interpretador novo; devolve o estado do logging depois dele."""
    # pydantic-settings lê o ambiente sem distinguir caixa: uma `log_level` qualquer
    # da máquina vazaria para o caso "sem LOG_LEVEL".
    ambiente = {nome: valor for nome, valor in os.environ.items() if nome.upper() != "LOG_LEVEL"}
    if log_level is not None:
        ambiente["LOG_LEVEL"] = log_level
    saida = tmp_path / "boot.json"

    resultado = subprocess.run(
        [sys.executable, "-c", _BOOT, str(saida)],
        # Sem `.env` no diretório: o nível vem só do ambiente montado acima.
        cwd=tmp_path,
        env=ambiente,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    assert resultado.returncode == 0, resultado.stderr
    estado: dict[str, object] = json.loads(saida.read_text(encoding="utf-8"))
    return estado


@pytest.mark.slow
@pytest.mark.parametrize(
    ("log_level", "esperado"),
    [(None, "INFO"), ("DEBUG", "DEBUG"), ("ERROR", "ERROR")],
    ids=["sem-LOG_LEVEL", "DEBUG", "ERROR"],
)
def test_boot_real_configura_o_logging_uma_vez_no_nivel_do_ambiente(
    tmp_path: Path, log_level: str | None, esperado: str
) -> None:
    """CA1 e CA2 da issue #6: uma chamada no boot, e o root no nível do ambiente.

    **Por que um interpretador novo.** Dentro da suíte o root nunca está vazio: o
    plugin de logging do pytest pendura handlers nele na coleta e em cada fase, e o
    `basicConfig` sem `force` não faz nada quando o root já tem handler, nem mudar o
    nível (medido: `basicConfig(level=DEBUG)` dentro de um teste deixa o root em
    `WARNING`). Um teste in-process só enxergaria o boot se arrancasse os handlers
    do pytest, e aí já não seria o boot.

    **Por que esses três níveis.** O root de um processo que ninguém configurou fica
    em `WARNING`. Nenhum dos três casos coincide com ele, então cada um sozinho já
    reprova se a chamada sumir. O caso sem `LOG_LEVEL` prova o default das settings;
    `DEBUG` e `ERROR`, que o valor vem do ambiente e não de uma constante.
    """
    boot = _subir_a_app(tmp_path, log_level)

    # Exatamente uma chamada, com o valor das settings. Uma segunda chamada não
    # deixaria rastro no root (o `basicConfig` repetido não faz nada), então é aqui
    # que ela reprova.
    assert boot["chamadas"] == [esperado]
    assert boot["root"] == esperado
    # O `basicConfig` aplicou de fato: um handler só, no stdout. Um handler que algo
    # pendurasse no root antes do boot apareceria aqui, e teria anulado a chamada.
    assert boot["handlers"] == [["StreamHandler", "<stdout>"]]
    assert boot["sqlalchemy"] == "WARNING"
