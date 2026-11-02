"""Fábrica da aplicação FastAPI.

`create_app()` é o único lugar que monta a aplicação: registra middlewares,
error handlers e routers. Aciona o composition_root para fazer o wiring das
dependências. Usar uma factory (em vez de um app global) facilita testes: cada
teste pode chamar `create_app()` com configurações diferentes.

**Este módulo não conhece feature nenhuma, e isso é uma restrição de arquitetura,
não estilo.** `shared` não importa de `features` (LAYOUT §7); a única exceção
declarada é a cadeia indireta `app → composition_root → features.adapters`, e ela
é suprimida no `.importlinter` **apenas para esse par**. Por isso o composition
root entrega aqui um `HttpWiring` já montado — router, registrador de handlers e
mapa de `dependency_overrides` — em vez de este arquivo ir buscar cada peça.

O mapa de overrides é a peça que fecha o desenho: as chaves são os provedores
`_get_*` definidos **dentro** do módulo do router. Alcançá-los daqui exigiria
importar a feature, e a supressão estreita deixaria de bastar.
"""

from fastapi import FastAPI

from restaurant_hub.composition_root import (
    ApplicationDependencies,
    build_http_wiring,
    wire_dependencies,
)
from restaurant_hub.shared.application.ports.out.email_sender import EmailSender
from restaurant_hub.shared.infrastructure.config.settings import Settings, get_settings
from restaurant_hub.shared.infrastructure.http.error_handlers import register_error_handlers
from restaurant_hub.shared.infrastructure.http.middlewares import register_middlewares
from restaurant_hub.shared.infrastructure.logging.config import configure_logging

API_PREFIX = "/api/v1"


def create_app(
    settings: Settings | None = None,
    *,
    email_sender: EmailSender | None = None,
) -> FastAPI:
    """Cria, configura e retorna a instância FastAPI pronta para uso.

    Ordem de inicialização:
    1. Configura o logging do processo com o `log_level` das settings
    2. Cria o app FastAPI com metadados das settings
    3. Registra middlewares (CORS, etc.)
    4. Registra os error handlers genéricos (DomainError → 422, validação → 422)
    5. Faz o wiring das dependências via composition_root
    6. Registra router, handlers de feature e dependency_overrides

    **O logging é configurado aqui, e não em `main.py`** (issue #6): a regra 5 de
    `scripts/check_layout.py` fixa que o entrypoint conhece a factory e mais nada. E
    vem antes de tudo para que um registro emitido durante a montagem já saia no
    formato e no nível configurados.

    **É estado do processo, não da app, e por isso a chamada se repete sem efeito.**
    O `basicConfig` por trás de `configure_logging` não faz nada quando o root já
    tem handler, nem mudar o nível. No boot real isso não pesa, porque o uvicorn
    importa `main` uma vez por processo servidor e não pendura handler no root. Na
    suíte, que monta dezenas de apps, o plugin de logging do pytest mantém handlers
    no root o tempo todo, e cada chamada só reaplica os níveis de
    `sqlalchemy.engine` e `uvicorn.access`, o que é idempotente. Daí que
    `create_app(Settings(log_level=...))` **não** muda o nível do root dentro da
    suíte: o teste de boot (`tests/unit/test_bootstrap.py`) sobe um interpretador novo.

    `settings` é injetável para que um teste possa montar a app com outro banco ou
    outros TTLs sem mexer em variável de ambiente global — é o que torna o TTL
    observável como configuração. `email_sender` é repassado ao composition root
    pela mesma razão, e por uma específica: o ADR 0.0.0004 §Decision 7 exige que
    nada saia da máquina durante a corrida, então o e2e precisa de uma forma
    honesta de capturar o envio — sem construir um segundo grafo de dependências
    nem alcançar atributo privado de use case já montado.

    **Os handlers genéricos são registrados antes dos de feature de propósito.**
    Starlette resolve o handler pelo `__mro__` da exceção, não pela ordem de
    registro, e como a raiz de cada BC precede `DomainError` em todas as MROs do BC,
    o handler específico vence de qualquer forma. Registrar o
    genérico primeiro deixa claro que ele é a rede de segurança, não o principal.
    """
    cfg = settings or get_settings()
    configure_logging(cfg.log_level)

    app = FastAPI(
        title=cfg.app_name,
        debug=cfg.debug,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    register_middlewares(app)
    register_error_handlers(app)

    deps = wire_dependencies(cfg, email_sender=email_sender)
    _register_feature_routers(app, deps)

    return app


def _register_feature_routers(app: FastAPI, deps: ApplicationDependencies) -> None:
    """Registra o que o composition root montou, sem conhecer a feature."""
    wiring = build_http_wiring(deps)

    # **Itera as coleções, e continua sem conhecer feature nenhuma.** O que mudou
    # na Stage 3.6 foi a cardinalidade — dois bounded contexts com superfície
    # HTTP em vez de um —, e não o que este módulo sabe: ele registra o que o
    # composition root montou, na ordem em que veio.
    for registrar in wiring.register_error_handlers:
        registrar(app)

    app.dependency_overrides.update(wiring.dependency_overrides)

    for router in wiring.routers:
        app.include_router(router, prefix=API_PREFIX)
