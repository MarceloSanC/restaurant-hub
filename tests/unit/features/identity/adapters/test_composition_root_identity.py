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
import io
import pathlib
from collections.abc import Callable
from datetime import timedelta

import pytest

from restaurant_hub.composition_root import ApplicationDependencies, wire_dependencies
from restaurant_hub.features.identity.adapters.out.postgres.password_setup_token_repository import (
    PostgresPasswordSetupTokenRepository,
)
from restaurant_hub.features.identity.adapters.out.postgres.restaurant_repository import (
    PostgresRestaurantRepository,
)
from restaurant_hub.features.identity.adapters.out.postgres.session_repository import (
    PostgresSessionRepository,
)
from restaurant_hub.features.identity.adapters.out.postgres.unit_of_work import (
    PostgresUnitOfWork,
)
from restaurant_hub.features.identity.adapters.out.postgres.unit_repository import (
    PostgresUnitRepository,
)
from restaurant_hub.features.identity.adapters.out.postgres.user_repository import (
    PostgresUserRepository,
)
from restaurant_hub.features.identity.adapters.out.security.argon2_hasher import (
    Argon2PasswordHasher,
)
from restaurant_hub.features.identity.application.use_cases.authenticate_user import (
    AuthenticateUserUseCase,
)
from restaurant_hub.features.identity.application.use_cases.create_user import (
    CreateUserUseCase,
)
from restaurant_hub.features.identity.application.use_cases.invite_user import (
    InviteUserUseCase,
)
from restaurant_hub.features.identity.application.use_cases.refresh_session import (
    RefreshSessionUseCase,
)
from restaurant_hub.features.identity.application.use_cases.request_password_reset import (
    RequestPasswordResetUseCase,
)
from restaurant_hub.features.identity.application.use_cases.set_password_with_token import (
    SetPasswordWithTokenUseCase,
)
from restaurant_hub.shared.infrastructure.config.settings import Settings
from restaurant_hub.shared.infrastructure.email.console_sender import ConsoleSender

pytestmark = pytest.mark.unit

_SRC = pathlib.Path(__file__).resolve().parents[5] / "src" / "restaurant_hub"
# **Prefixo AMPLIADO na Stage 2.4.** Antes ele apontava só para
# `...adapters.out.postgres`, e a Stage acrescentou dois adapters de produção
# (`adapters.out.security`) mais o adapter de entrada. Com o prefixo antigo, o
# teste continuaria verde sem NUNCA olhar para os módulos novos — "continua
# passando" seria trivialmente verdade e completamente vazio.
_MODULO_DE_ADAPTERS = "restaurant_hub.features.identity.adapters"
# **Segundo prefixo, acrescentado na Stage 2.5.** A 2.5 introduziu o primeiro
# adapter de saída que mora em `shared/` — `ConsoleSender`, implementação do port
# compartilhado `EmailSender` (ADR 2.5.0001). Ele fica **fora** do prefixo acima,
# de modo que a varredura, sozinha, não o veria: alguém poderia instanciá-lo
# dentro de um router e o teste continuaria verde. `check_layout.py` também não
# pega, porque `shared/infrastructure` é importável de qualquer lugar por regra.
_MODULO_DE_ADAPTERS_COMPARTILHADOS = "restaurant_hub.shared.infrastructure.email"
_PREFIXOS_DE_ADAPTERS = (_MODULO_DE_ADAPTERS, _MODULO_DE_ADAPTERS_COMPARTILHADOS)
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
    assert isinstance(deps.identity_invite_user, InviteUserUseCase)
    assert isinstance(deps.identity_request_password_reset, RequestPasswordResetUseCase)
    assert isinstance(deps.identity_set_password_with_token, SetPasswordWithTokenUseCase)
    assert deps.identity_guard is not None


def test_o_adapter_de_email_do_grafo_e_o_console_sender() -> None:
    """CA17 — o sender concreto é escolhido no composition root, e é o desta Stage.

    Sem esta asserção, trocar `ConsoleSender()` por um sender que engole tudo
    passaria despercebido em toda a suíte que não exige Postgres: o teste acima
    só veria "é um use case", e o e2e — que pegaria — é justamente o que um
    `-m "not e2e"` pula.
    """
    deps = wire_dependencies(Settings(_env_file=None))

    assert isinstance(deps.identity_invite_user._email_sender, ConsoleSender)
    assert isinstance(deps.identity_request_password_reset._email_sender, ConsoleSender)


def test_costura_de_email_sender_substitui_apenas_o_envio() -> None:
    """A costura existe para o e2e capturar o e-mail sem sair da máquina.

    O que ela **não** pode fazer é trocar mais nada: se substituir o sender
    trocasse também repositório ou hasher, o e2e deixaria de exercitar o caminho
    real e viraria um teste de fakes caro.
    """
    outro = ConsoleSender(stream=io.StringIO())

    deps = wire_dependencies(Settings(_env_file=None), email_sender=outro)

    assert deps.identity_invite_user._email_sender is outro
    assert isinstance(deps.identity_authenticate_user._users, PostgresUserRepository)
    assert isinstance(deps.identity_invite_user._hasher, Argon2PasswordHasher)


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


# Stage 2.6 — os use cases com unidade de trabalho e, para cada um, o conjunto
# EXATO de atributos que guardam repositório. Exato de propósito: um filtro por
# `isinstance` pularia em silêncio um embrulho (cache, métrica) montado sobre outro
# engine, e o teste continuaria verde.
_COM_UNIDADE: dict[str, tuple[Callable[[ApplicationDependencies], object], set[str]]] = {
    "set_password_with_token": (
        lambda d: d.identity_set_password_with_token,
        {"_users", "_sessions", "_tokens"},
    ),
    "invite_user": (
        lambda d: d.identity_invite_user,
        {"_users", "_restaurants", "_units", "_tokens"},
    ),
    # O da fachada, dentro do gateway de staff — o caminho da travessia entre BCs.
    "provision_account": (
        lambda d: d.staff_identity_gateway._facade._provision_account,
        {"_users", "_restaurants", "_units", "_tokens"},
    ),
    # Issue #67 — restaurante e dono (ADR 0.0.0014).
    "provision_restaurant": (
        lambda d: d.identity_provision_restaurant,
        {"_restaurants", "_users"},
    ),
    "request_password_reset": (
        lambda d: d.identity_request_password_reset,
        {"_users", "_tokens"},
    ),
    "refresh_session": (
        lambda d: d.identity_refresh_session,
        {"_users", "_sessions"},
    ),
}
_REPOSITORIOS_POSTGRES = (
    PostgresRestaurantRepository,
    PostgresUnitRepository,
    PostgresUserRepository,
    PostgresSessionRepository,
    PostgresPasswordSetupTokenRepository,
)


@pytest.mark.parametrize("nome", sorted(_COM_UNIDADE))
def test_unidade_e_repositorios_do_use_case_compartilham_o_engine(nome: str) -> None:
    """CA9 (concept 2.6 R7) — a unidade é chaveada pelo `Engine`.

    Um repositório montado sobre outro engine escreveria fora da unidade em
    silêncio: a suíte inteira continuaria verde e a atomicidade sumiria em
    produção. Aqui a fiação real é conferida repositório a repositório.
    """
    obter, esperados = _COM_UNIDADE[nome]
    atributos = vars(obter(wire_dependencies(Settings(_env_file=None))))
    unidade = atributos["_unit_of_work"]
    com_engine = {k for k, v in atributos.items() if hasattr(v, "_engine")} - {"_unit_of_work"}

    assert isinstance(unidade, PostgresUnitOfWork)
    assert com_engine == esperados
    for atributo in esperados:
        repositorio = atributos[atributo]
        assert isinstance(repositorio, _REPOSITORIOS_POSTGRES), atributo
        assert repositorio._engine is unidade._engine, atributo


def _use_cases_que_recebem_unidade() -> set[str]:
    """Classes de `use_cases/` cujo `__init__` recebe `unit_of_work` — derivado do código."""
    pasta = _SRC / "features" / "identity" / "application" / "use_cases"
    nomes: set[str] = set()
    for arquivo in sorted(pasta.glob("*.py")):
        arvore = ast.parse(arquivo.read_text("utf-8"))
        for classe in (n for n in arvore.body if isinstance(n, ast.ClassDef)):
            parametros = {
                a.arg
                for m in classe.body
                if isinstance(m, ast.FunctionDef) and m.name == "__init__"
                for a in m.args.args + m.args.kwonlyargs
            }
            if "unit_of_work" in parametros:
                nomes.add(classe.name)
    return nomes


def test_todo_use_case_com_unidade_esta_na_conferencia_do_engine() -> None:
    """A totalidade de `_COM_UNIDADE`: a conferência acima é por caso, e um sexto use
    case que ganhasse unidade (a regra 10 obriga quem escreve duas vezes) ficaria fora
    dela em silêncio — com um repositório de outro engine escrevendo fora da unidade.
    """
    deps = wire_dependencies(Settings(_env_file=None))
    conferidos = {type(obter(deps)).__name__ for obter, _ in _COM_UNIDADE.values()}

    assert conferidos == _use_cases_que_recebem_unidade()


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


def test_ttls_do_token_de_setup_vem_da_configuracao() -> None:
    """Os dois prazos são alavancas de segurança, e são **diferentes**.

    O teste passa valores distintos e assere cada um no seu use case, de propósito:
    com o mesmo valor nos dois, trocar `invitation_ttl` por `reset_ttl` no
    composition root continuaria verde — e a troca embarcaria uma janela de
    redefinição de senha de 72 horas, que é exatamente o oposto da defesa que o
    prazo curto existe para dar.
    """
    cfg = Settings(
        _env_file=None,
        invitation_token_ttl_hours=5,
        password_reset_token_ttl_minutes=11,
    )

    deps = wire_dependencies(cfg)

    assert deps.identity_invite_user._invitation_ttl == timedelta(hours=5)
    assert deps.identity_request_password_reset._reset_ttl == timedelta(minutes=11)


def test_ttls_de_provisao_vem_da_configuracao_com_valores_distintos() -> None:
    """Stage 3.5 — os dois prazos do `ProvisionAccountUseCase` são alavancas diferentes.

    Valores distintos de propósito, pelo mesmo motivo do teste acima: com os
    dois iguais, trocar `invitation_ttl` por `handover_ttl` no composition root
    continuaria verde — e o link em mãos passaria a expirar em horas de e-mail.
    O use case fica **dentro** da fachada, que fica dentro do gateway de staff:
    o caminho até ele é o caminho da única aresta entre os BCs.
    """
    cfg = Settings(
        _env_file=None,
        invitation_token_ttl_hours=5,
        handover_link_ttl_hours=9,
    )

    deps = wire_dependencies(cfg)

    provisao = deps.staff_identity_gateway._facade._provision_account
    assert provisao._invitation_ttl == timedelta(hours=5)
    assert provisao._handover_ttl == timedelta(hours=9)
    assert provisao._invitation_ttl == deps.identity_invite_user._invitation_ttl


def test_base_url_do_link_vem_da_configuracao() -> None:
    """O link do e-mail aponta para a aplicação web, e o endereço é ambiente."""
    cfg = Settings(_env_file=None, app_base_url="https://app.exemplo.com")

    deps = wire_dependencies(cfg)

    assert deps.identity_invite_user._base_url == "https://app.exemplo.com"
    assert deps.identity_request_password_reset._base_url == "https://app.exemplo.com"
    assert (
        deps.staff_identity_gateway._facade._provision_account._base_url
        == "https://app.exemplo.com"
    )


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
            if any(prefixo in alvo for prefixo in _PREFIXOS_DE_ADAPTERS):
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
        "restaurant_hub.features.identity.adapters.inbound.http.router",
        # Stage 2.5 — os dois adapters novos de identity...
        "restaurant_hub.features.identity.adapters.out.security.setup_token_issuer",
        "restaurant_hub.features.identity.adapters.out.postgres.password_setup_token_repository",
        # ...e o primeiro que mora em `shared/`, que só é alcançado pelo
        # segundo prefixo. Sem ele, um `ConsoleSender()` dentro de um router
        # passaria pela varredura sem ser notado.
        "restaurant_hub.shared.infrastructure.email.console_sender",
    )

    for modulo in modulos_novos:
        assert any(prefixo in modulo for prefixo in _PREFIXOS_DE_ADAPTERS), (
            f"{modulo} ficaria fora da varredura — nenhum prefixo o cobre"
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
