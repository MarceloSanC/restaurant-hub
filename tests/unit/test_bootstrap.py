"""Testes do bootstrap da aplicação — composition_root e entrypoint main."""

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
