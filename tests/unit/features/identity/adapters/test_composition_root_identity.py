"""Wiring dos repositórios de identity no composition root — CA17.

Dois testes com propósitos diferentes: o primeiro confere que o grafo é montado; o
segundo é o **guarda mecânico** da regra que o `ignore_imports` do import-linter
deixou de cobrir.

Esse segundo teste existe porque a regra "só o composition root instancia adapter"
é fácil de violar sem querer (basta um import "prático" num router da 2.4) e
invisível numa revisão de diff — exatamente o perfil de regra que precisa de gate
automático em vez de prosa. LAYOUT §6 registra que o `check_layout.py` não detecta
o caminho indireto; este teste fecha essa lacuna pelo lado do consumidor.
"""

import ast
import pathlib
from datetime import timedelta

import pytest

from restaurant_hub.composition_root import ApplicationDependencies, wire_dependencies
from restaurant_hub.features.identity.adapters.out.postgres.restaurant_repository import (
    PostgresRestaurantRepository,
)
from restaurant_hub.features.identity.adapters.out.postgres.session_repository import (
    PostgresSessionRepository,
)
from restaurant_hub.features.identity.adapters.out.postgres.unit_repository import (
    PostgresUnitRepository,
)
from restaurant_hub.features.identity.adapters.out.postgres.user_repository import (
    PostgresUserRepository,
)
from restaurant_hub.features.identity.application.use_cases.authenticate_user import (
    AuthenticateUserUseCase,
)
from restaurant_hub.features.identity.application.use_cases.create_user import (
    CreateUserUseCase,
)
from restaurant_hub.features.identity.application.use_cases.refresh_session import (
    RefreshSessionUseCase,
)
from restaurant_hub.shared.infrastructure.config.settings import Settings

pytestmark = pytest.mark.unit

_SRC = pathlib.Path(__file__).resolve().parents[5] / "src" / "restaurant_hub"
# **Prefixo AMPLIADO na Stage 2.4.** Antes ele apontava só para
# `...adapters.out.postgres`, e a Stage acrescentou dois adapters de produção
# (`adapters.out.security`) mais o adapter de entrada. Com o prefixo antigo, o
# teste continuaria verde sem NUNCA olhar para os módulos novos — "continua
# passando" seria trivialmente verdade e completamente vazio.
_MODULO_DE_ADAPTERS = "restaurant_hub.features.identity.adapters"
_COMPOSITION_ROOT = _SRC / "composition_root.py"


def test_wire_dependencies_monta_os_use_cases() -> None:
    """O grafo real, com as implementações concretas.

    A partir da Stage 2.4 o contêiner expõe **use cases**, e os repositórios
    recuam para dentro deles — que é o que o docstring do composition root já
    antecipava desde a 2.3.

    Note que `wire_dependencies()` roda **sem banco no ar**: `create_engine` não
    abre conexão, então o boot não depende de o Postgres já ter subido.
    """
    deps = wire_dependencies(Settings(_env_file=None))

    assert isinstance(deps, ApplicationDependencies)
    assert isinstance(deps.identity_authenticate_user, AuthenticateUserUseCase)
    assert isinstance(deps.identity_refresh_session, RefreshSessionUseCase)
    assert isinstance(deps.identity_create_user, CreateUserUseCase)
    assert deps.identity_guard is not None


def test_os_adapters_concretos_continuam_sendo_os_do_postgres() -> None:
    """Os repositórios não sumiram — recuaram para dentro dos use cases.

    Sem esta asserção, trocar o Postgres por um fake no composition root passaria
    despercebido: o teste acima só veria "é um use case".
    """
    deps = wire_dependencies(Settings(_env_file=None))
    use_case = deps.identity_authenticate_user

    assert isinstance(use_case._users, PostgresUserRepository)
    assert isinstance(use_case._sessions, PostgresSessionRepository)
    assert isinstance(deps.identity_create_unit._units, PostgresUnitRepository)
    assert isinstance(deps.identity_create_unit._restaurants, PostgresRestaurantRepository)


def test_ttl_dos_tokens_vem_da_configuracao() -> None:
    """CA25 (metade do wiring) — TTL é configuração, não constante.

    Este número é a janela de revogação do produto: revogar a sessão corta o
    refresh na hora, e o access sobrevive no máximo isso. Um literal no corpo do
    use case tornaria a principal alavanca de segurança do sistema inalcançável
    sem deploy.
    """
    cfg = Settings(_env_file=None, access_token_ttl_minutes=7, refresh_token_ttl_days=3)

    deps = wire_dependencies(cfg)

    assert deps.identity_authenticate_user._access_token_ttl == timedelta(minutes=7)
    assert deps.identity_authenticate_user._refresh_token_ttl == timedelta(days=3)
    assert deps.identity_refresh_session._access_token_ttl == timedelta(minutes=7)


def test_duas_chamadas_devolvem_grafos_independentes() -> None:
    """Sem singleton global (skill `composition-root`).

    Um `Engine` guardado em variável de módulo faria dois testes compartilharem
    conexão e estado, e tornaria impossível montar um grafo apontando para outro
    banco sem contaminar o primeiro.
    """
    primeiro = wire_dependencies(Settings(_env_file=None))
    segundo = wire_dependencies(Settings(_env_file=None))

    assert primeiro is not segundo
    assert primeiro.identity_authenticate_user is not segundo.identity_authenticate_user


def _modulos_que_importam_adapters() -> set[str]:
    """Varre `src/` por imports do pacote de adapters Postgres de identity.

    Ignora os arquivos **de dentro do próprio pacote**: um repositório importar
    `mappers`, `tables` ou `integrity_errors` do vizinho é coesão interna, não a
    violação que este teste procura (um consumidor externo pulando o composition
    root).
    """
    pacote_de_adapters = _SRC / "features" / "identity" / "adapters"
    culpados: set[str] = set()
    for arquivo in _SRC.rglob("*.py"):
        if arquivo.is_relative_to(pacote_de_adapters):
            continue
        arvore = ast.parse(arquivo.read_text(encoding="utf-8"), filename=str(arquivo))
        for no in ast.walk(arvore):
            alvo = ""
            if isinstance(no, ast.ImportFrom) and no.module:
                alvo = no.module
            elif isinstance(no, ast.Import):
                alvo = " ".join(alias.name for alias in no.names)
            if _MODULO_DE_ADAPTERS in alvo:
                culpados.add(str(arquivo.relative_to(_SRC)))
    return culpados


def test_so_o_composition_root_importa_os_adapters_de_identity() -> None:
    """A regra que o `ignore_imports` deixou de cobrir, como asserção mecânica.

    O contrato `shared-independence` do import-linter ganhou uma supressão para o
    par `shared.infrastructure.http.app -> composition_root` (LAYOUT §6). A
    supressão é estreita, mas ainda assim abre uma janela: nada no import-linter
    impediria um **outro** módulo de importar os adapters direto. Este teste fecha
    a janela pelo lado do consumidor.
    """
    esperado = {str(_COMPOSITION_ROOT.relative_to(_SRC))}
    assert _modulos_que_importam_adapters() == esperado, (
        "apenas composition_root.py pode importar "
        f"{_MODULO_DE_ADAPTERS}; receba o repositório por injeção (LAYOUT §6)"
    )


def test_a_varredura_alcanca_os_adapters_novos_da_stage() -> None:
    """O prefixo ampliado cobre de fato `out.security` e `in.http`.

    Sem esta asserção, a ampliação do prefixo seria uma mudança de string que
    ninguém verifica: o teste acima continuaria verde tanto com o prefixo largo
    quanto com o antigo — porque em ambos os casos o único culpado é o
    composition root. O que se verifica aqui é a **cobertura da varredura**, não
    o resultado dela.
    """
    modulos_novos = (
        "restaurant_hub.features.identity.adapters.out.security.argon2_hasher",
        "restaurant_hub.features.identity.adapters.out.security.jwt_issuer",
        "restaurant_hub.features.identity.adapters.in.http.router",
    )

    for modulo in modulos_novos:
        assert _MODULO_DE_ADAPTERS in modulo, (
            f"{modulo} ficaria fora da varredura — o prefixo não o cobre"
        )


def test_um_import_proibido_plantado_reprova() -> None:
    """Teste negativo: o detector detecta.

    Um guarda que nunca viu um caso positivo não é um guarda — é uma função que
    devolve conjunto vazio. Aqui o import proibido é plantado num arquivo
    sintético e submetido ao mesmo `ast` que a varredura usa.
    """
    codigo_violador = (
        "from restaurant_hub.features.identity.adapters.out.security.jwt_issuer "
        "import JwtTokenIssuer"
    )
    arvore = ast.parse(codigo_violador)

    alvos = [no.module for no in ast.walk(arvore) if isinstance(no, ast.ImportFrom) and no.module]

    assert any(_MODULO_DE_ADAPTERS in alvo for alvo in alvos)
