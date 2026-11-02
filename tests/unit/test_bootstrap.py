"""Testes do bootstrap da aplicação — composition_root e entrypoint main."""

import json
import os
import runpy
import subprocess
import sys
import textwrap
from collections.abc import Callable
from pathlib import Path

import pytest
import uvicorn
from fastapi import FastAPI

from restaurant_hub import main
from restaurant_hub.composition_root import ApplicationDependencies, wire_dependencies
from restaurant_hub.shared.infrastructure.config.settings import Settings
from restaurant_hub.shared.infrastructure.http import app as app_module

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


def test_create_app_configura_o_logging_com_as_settings_que_recebeu(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """O nível vem das settings injetadas na factory, as mesmas que montam a app.

    No boot real as duas coisas são `get_settings()`, então o teste de boot não
    distingue uma da outra: `configure_logging(get_settings().log_level)` passava em
    toda a suíte. Aqui elas se separam. O efeito no root não aparece in-process (o
    pytest mantém handlers nele), mas o valor que chega a `configure_logging` aparece.
    """
    recebidos: list[str] = []
    monkeypatch.setattr(app_module, "configure_logging", recebidos.append)

    app_module.create_app(Settings(_env_file=None, log_level="CRITICAL"))

    assert recebidos == ["CRITICAL"]


def test_create_app_configura_o_logging_antes_de_montar_a_app(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A ordem que o docstring de `create_app` afirma: o logging vem antes de tudo.

    É o que garante que um registro emitido durante a montagem (middlewares, error
    handlers, wiring) já saia no formato e no nível configurados. Medido na auditoria
    de testes da issue #6: mover a chamada para logo antes do `return app` passava
    em toda a suíte, porque nenhum outro teste olha a ordem.
    """
    eventos: list[str] = []

    def espiar(nome: str, original: Callable[..., object]) -> Callable[..., object]:
        def espia(*args: object, **kwargs: object) -> object:
            eventos.append(nome)
            return original(*args, **kwargs)

        return espia

    for nome in ("configure_logging", "FastAPI", "register_middlewares", "wire_dependencies"):
        monkeypatch.setattr(app_module, nome, espiar(nome, getattr(app_module, nome)))

    app_module.create_app(Settings(_env_file=None))

    assert eventos == ["configure_logging", "FastAPI", "register_middlewares", "wire_dependencies"]


def test_python_m_entrega_ao_uvicorn_a_app_ja_montada(monkeypatch: pytest.MonkeyPatch) -> None:
    """`python -m restaurant_hub.main`, o outro boot que `main.py` documenta, também é um só.

    Com a string de import, o uvicorn reimportava `restaurant_hub.main`, que nesse
    caminho roda como `__main__` e é outro módulo para o import, e montava a app e o
    logging de novo no mesmo processo. A issue #6 mediu duas chamadas de
    `create_app` e duas de `configure_logging`. Com o objeto não há import:
    `uvicorn.importer.import_from_string` devolve sem tocar no que não é string.

    O teste roda o arquivo como `__main__` aqui mesmo, com o `uvicorn.run` trocado,
    e não num subprocess, porque esta é a linha que a cobertura precisa ver. O
    reimport em si não se reproduz in-process (o módulo já está em `sys.modules`);
    o que se trava é o contrato que o evita: o uvicorn recebe **a** app já montada.
    """
    recebidas: list[object] = []
    monkeypatch.setattr(uvicorn, "run", lambda app, **_: recebidas.append(app))

    globais = runpy.run_path(main.__file__, run_name="__main__")

    assert len(recebidas) == 1
    assert isinstance(recebidas[0], FastAPI)
    assert recebidas[0] is globais["app"]
