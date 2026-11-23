"""O ambiente dos testes de borda de scheduling: a app FastAPI com o router real, sem banco.

O router e os handlers são os de produção; os use cases são os reais, sobre os fakes da
suíte de application (`new_world`); o guard é o `InMemoryAccessGuard`, que autentica pelo
cabeçalho `authorization: Bearer <user_id>` e registra cada chamada com o alvo. As duas
sentinelas do fake ganham handler só aqui (401 e 403), no papel que as exceções de identity
têm na app real.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from restaurant_hub.features.scheduling.adapters.inbound.http import router as router_module
from restaurant_hub.features.scheduling.adapters.inbound.http.dependencies import (
    get_access_guard,
)
from restaurant_hub.features.scheduling.adapters.inbound.http.error_handlers import (
    register_scheduling_error_handlers,
)
from restaurant_hub.features.scheduling.application.use_cases.create_schedule import (
    CreateScheduleUseCase,
)
from restaurant_hub.features.scheduling.application.use_cases.evaluate_schedule import (
    EvaluateScheduleUseCase,
)
from restaurant_hub.features.scheduling.application.use_cases.get_calendar import (
    GetCalendarUseCase,
)
from restaurant_hub.features.scheduling.application.use_cases.get_my_schedule import (
    GetMyScheduleUseCase,
)
from restaurant_hub.features.scheduling.application.use_cases.get_schedule import (
    GetScheduleUseCase,
)
from restaurant_hub.features.scheduling.application.use_cases.list_past_schedules import (
    ListPastSchedulesUseCase,
)
from restaurant_hub.features.scheduling.application.use_cases.publish_schedule import (
    PublishScheduleUseCase,
)
from restaurant_hub.shared.infrastructure.http.error_handlers import register_error_handlers
from tests.fakes.features.scheduling.in_memory_access_guard import (
    FakeAuthenticationRejected,
    FakeAuthorizationRejected,
)
from tests.unit.features.scheduling.application.conftest import World, new_world

API = "/api/v1"

# Os provedores do router e o use case real que cada um entrega.
PROVEDORES: dict[Callable[..., Any], Callable[[World], object]] = {
    router_module._get_create_schedule: lambda w: CreateScheduleUseCase(
        w.schedules, w.config, w.ids, w.clock, w.guard
    ),
    router_module._get_get_schedule: lambda w: GetScheduleUseCase(
        w.schedules, w.config, w.staff, w.guard
    ),
    router_module._get_evaluate_schedule: lambda w: EvaluateScheduleUseCase(
        w.schedules, w.config, w.staff, w.guard
    ),
    router_module._get_publish_schedule: lambda w: PublishScheduleUseCase(
        w.schedules, w.config, w.staff, w.clock, w.guard
    ),
    router_module._get_calendar: lambda w: GetCalendarUseCase(w.schedules, w.staff, w.guard),
    router_module._get_list_past_schedules: lambda w: ListPastSchedulesUseCase(
        w.schedules, w.guard
    ),
    router_module._get_my_schedule: lambda w: GetMyScheduleUseCase(w.schedules, w.staff, w.guard),
}


@dataclass
class Ambiente:
    """A app montada sobre um mundo de fakes; `overrides` troca um provedor por um dublê."""

    world: World = field(default_factory=new_world)
    overrides: dict[Callable[..., Any], Callable[[], object]] = field(default_factory=dict)

    @property
    def app(self) -> FastAPI:
        app = FastAPI()
        register_error_handlers(app)
        register_scheduling_error_handlers(app)

        @app.exception_handler(FakeAuthenticationRejected)
        async def _nao_autenticado(request: Request, exc: Exception) -> JSONResponse:
            return JSONResponse(status_code=401, content={"detail": "não autenticado"})

        @app.exception_handler(FakeAuthorizationRejected)
        async def _negado(request: Request, exc: Exception) -> JSONResponse:
            return JSONResponse(status_code=403, content={"detail": "acesso negado"})

        world = self.world
        app.dependency_overrides[get_access_guard] = lambda: world.guard
        for provedor, montar in PROVEDORES.items():
            app.dependency_overrides[provedor] = _sem_parametros(montar, world)
        app.dependency_overrides.update(self.overrides)
        app.include_router(router_module.router, prefix=API)
        return app


def _sem_parametros(montar: Callable[[World], object], world: World) -> Callable[[], object]:
    """Provedor sem parâmetros: o FastAPI leria um parâmetro com default como query."""

    def provedor() -> object:
        return montar(world)

    return provedor


def bearer(user_id: str) -> dict[str, str]:
    return {"authorization": f"Bearer {user_id}"}
