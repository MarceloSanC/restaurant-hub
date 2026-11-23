"""A independência do BC scheduling em relação a identity e a staff — CA18.

**Por que na raiz de `tests/unit/features/scheduling/`, e não dentro de uma
camada.** As varreduras deste arquivo falam do bounded context **inteiro** (todos
os módulos de `features/scheduling/`) e de um arquivo de configuração do
repositório (`.importlinter`); nenhuma delas é regra de `domain/`,
`application/` ou `adapters/`. Pô-lo dentro de uma dessas pastas afirmaria que a
regra é da camada, o que é falso. É o mesmo raciocínio — e agora o precedente
literal — de `tests/unit/features/staff/test_bc_independence.py`.

**Por que um teste, se `lint-imports` já roda em `make check`.** Os dois cobrem
coisas diferentes:

- `lint-imports` prova que o contrato **como está escrito** passa. Um
  `ignore_imports` acrescentado ao contrato o mantém verde enquanto abre a
  fronteira — a supressão é invisível para ele, porque é ele quem a obedece.
- Este arquivo prova que o contrato **não foi afrouxado** e que o BC não
  **nomeia** o vocabulário do outro lado, que é mais estreito que não importar:
  um `Literal["cook"]` é aceitável, um `DayPeriod` importado não é — e a
  distinção não é expressável como contrato de import.

**A fronteira é dupla, e é o que este arquivo tem de novo em relação ao de
staff.** Scheduling é o terceiro BC: ele tem **dois** vizinhos, e a varredura de
import é sobre os dois prefixos. O contrato `bc-independence` do `.importlinter`
é `type = independence`, que já é par a par entre todos os módulos listados — o
que este arquivo guarda é que scheduling **está** na lista (a asserção de
cobertura da pasta vive no arquivo de staff, onde o contrato inteiro é o sujeito).

**As duas arestas.** Scheduling lê staff por **um** caminho (Stage 4.4, ADR 4.4.0004):
`adapters/out/staff/` importa **só** `staff.application.facade`. E, desde a Stage 4.5 (ADR
4.5.0003), decide acesso por **um** caminho: `adapters/out/identity/` importa **só**
`identity.application.facade`. Cada aresta é um par nomeado no `.importlinter`; as varreduras
cobram, para cada pasta, o único vizinho e o único módulo dele que ela pode importar — o
gateway de staff importando identity, ou o guard importando staff, reprova.
"""

import ast
import configparser
import pathlib

import pytest

pytestmark = pytest.mark.unit

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[4]
_SCHEDULING = _REPO_ROOT / "src" / "restaurant_hub" / "features" / "scheduling"
_IMPORTLINTER = _REPO_ROOT / ".importlinter"

_SECAO_BC_INDEPENDENCE = "importlinter:contract:bc-independence"
_MODULO_SCHEDULING = "restaurant_hub.features.scheduling"
_MODULOS_VIZINHOS = (
    "restaurant_hub.features.identity",
    "restaurant_hub.features.staff",
)

# As duas arestas: para cada pacote de scheduling que pode importar um vizinho, o único
# módulo do vizinho que ele pode importar (ADR 4.4.0004; ADR 4.5.0003), e os pares tal como
# o `.importlinter` os escreve.
_PACOTE_DO_GATEWAY = pathlib.PurePosixPath("adapters/out/staff")
_MODULO_DA_FACHADA = "restaurant_hub.features.staff.application.facade"
_PACOTE_DO_GUARD = pathlib.PurePosixPath("adapters/out/identity")
_MODULO_DA_FACHADA_DE_IDENTITY = "restaurant_hub.features.identity.application.facade"
_ARESTAS: dict[pathlib.PurePosixPath, str] = {
    _PACOTE_DO_GATEWAY: _MODULO_DA_FACHADA,
    _PACOTE_DO_GUARD: _MODULO_DA_FACHADA_DE_IDENTITY,
}
_PAR_DE_SCHEDULING = (
    "restaurant_hub.features.scheduling.adapters.out.staff.* -> "
    "restaurant_hub.features.staff.application.facade"
)
_PAR_DE_SCHEDULING_IDENTITY = (
    "restaurant_hub.features.scheduling.adapters.out.identity.* -> "
    "restaurant_hub.features.identity.application.facade"
)
_GATEWAY = _SCHEDULING / "adapters" / "out" / "staff" / "local_staff_read_adapter.py"
_GUARD = _SCHEDULING / "adapters" / "out" / "identity" / "local_access_guard.py"

# O vocabulário de decisão dos vizinhos. Não basta não importar: **nomear** o
# tipo já é conhecer como o outro BC decide, e é o começo de reimplementar a
# decisão aqui (ADR 3.4.0001, alternativa D).
#
# **`EmployeeId` e `JobFunctionId` NÃO entram, e a ausência é deliberada.** Os
# **valores** são emitidos por staff, mas os **tipos** são próprios de scheduling
# (concept §4, §7): o BC declara os seus oito identificadores e é obrigado a
# nomeá-los em toda entidade. Proibi-los aqui reprovaria `identifiers.py` no
# primeiro commit da Stage por uma regra que não existe. O que a lista contém é
# só o vocabulário **de decisão alheia** — os enums e tipos fechados com que o
# outro BC decide, e as suas entidades.
_VOCABULARIO_DE_IDENTITY = frozenset({"Role", "Permission"})
_VOCABULARIO_DE_STAFF = frozenset(
    {
        "DayPeriod",
        "ShiftPreference",
        "WorkloadProfile",
        "FixedSchedule",
        "OnDemand",
        "UnavailabilityPeriod",
        "Employee",
        "JobFunction",
    }
)
_VOCABULARIO_DOS_VIZINHOS = _VOCABULARIO_DE_IDENTITY | _VOCABULARIO_DE_STAFF

# Os identificadores próprios do BC, que a lista acima não pode conter. A
# asserção que usa esta tupla é a guarda contra o zelo excessivo: é o erro que
# **este** BC convida, por ser o primeiro cujos identificadores repetem nomes de
# entidades alheias.
_IDENTIFICADORES_PROPRIOS = ("EmployeeId", "JobFunctionId")


def _modulos_de_scheduling() -> list[pathlib.Path]:
    """Todos os `.py` do BC — sem filtro por camada, que é o ponto do CA18."""
    return sorted(_SCHEDULING.rglob("*.py"))


def _identificadores(arvore: ast.AST) -> set[str]:
    """Nomes que o módulo **usa**, em qualquer posição sintática.

    Colhe de onde um identificador pode aparecer sem ser conteúdo de string:
    referência (`Name`), acesso a atributo (`Attribute`), alias de import,
    definição de classe/função, parâmetro e argumento nomeado. Texto dentro de
    docstring **não** conta: citar o outro BC em prosa é referência, usá-lo é
    acoplamento — e é o que permite a docstring de `errors.py` citar o espelho
    de `InvalidDayPeriodError` sem reprovar este teste.
    """
    nomes: set[str] = set()
    for no in ast.walk(arvore):
        if isinstance(no, ast.Name):
            nomes.add(no.id)
        elif isinstance(no, ast.Attribute):
            nomes.add(no.attr)
        elif isinstance(no, ast.alias):
            nomes.add(no.name.split(".")[-1])
            if no.asname:
                nomes.add(no.asname)
        elif isinstance(no, ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            nomes.add(no.name)
        elif isinstance(no, ast.arg) or (isinstance(no, ast.keyword) and no.arg is not None):
            nomes.add(no.arg)
    return nomes


def _alvos_de_import(arvore: ast.AST) -> set[str]:
    """Módulos alcançados por `import X` e `from X import ...`."""
    alvos: set[str] = set()
    for no in ast.walk(arvore):
        if isinstance(no, ast.ImportFrom) and no.module:
            alvos.add(no.module)
        elif isinstance(no, ast.Import):
            alvos.update(alias.name for alias in no.names)
    return alvos


def _contrato_bc_independence() -> configparser.SectionProxy:
    """A seção do `.importlinter`, lida como configuração e não como texto."""
    parser = configparser.ConfigParser()
    parser.read(_IMPORTLINTER, encoding="utf-8")
    assert parser.has_section(_SECAO_BC_INDEPENDENCE), (
        f"o contrato {_SECAO_BC_INDEPENDENCE!r} sumiu do .importlinter — "
        f"apagá-lo deixaria `lint-imports` verde com a fronteira aberta"
    )
    return parser[_SECAO_BC_INDEPENDENCE]


def _violacoes_da_aresta(caminho_relativo: pathlib.PurePosixPath, alvos: set[str]) -> list[str]:
    """Por que um módulo de scheduling que importa um vizinho **não** é uma aresta permitida.

    Vazio quando nenhum vizinho é importado, ou quando o módulo está sob uma das pastas de
    `_ARESTAS` **e** todo import de vizinho é a fachada que aquela pasta pode importar.
    """
    vizinhos = sorted(alvo for alvo in alvos if alvo.startswith(_MODULOS_VIZINHOS))
    if not vizinhos:
        return []
    pacote = next((p for p in _ARESTAS if caminho_relativo.is_relative_to(p)), None)
    if pacote is None:
        pastas = " e ".join(f"{p}/" for p in _ARESTAS)
        return [f"fora de {pastas} — só os adapters das arestas podem importar vizinho"]
    alem_da_fachada = [alvo for alvo in vizinhos if alvo != _ARESTAS[pacote]]
    if alem_da_fachada:
        return [f"importa vizinho além da fachada de {pacote}/: {alem_da_fachada}"]
    return []


def test_a_varredura_de_modulos_de_scheduling_nao_esta_vazia() -> None:
    """Guarda contra o falso-verde deste arquivo.

    As duas varreduras abaixo devolvem conjunto vazio quando o BC está limpo — e
    devolveriam conjunto vazio também se `rglob` não achasse arquivo nenhum (uma
    pasta renomeada, um `parents[4]` a mais). O relatório do pytest diria
    exatamente o mesmo de antes.
    """
    assert _modulos_de_scheduling(), (
        f"nenhum .py encontrado em {_SCHEDULING} — a descoberta quebrou, e sem "
        f"esta asserção as duas varreduras teriam sumido sem sintoma"
    )


def test_ca18_so_os_adapters_das_arestas_importam_vizinho_e_so_a_fachada() -> None:
    """A varredura é sobre o BC inteiro, um arquivo de cada vez.

    `lint-imports` já cobriria isto, mas o faz sobre o grafo que o contrato descreve — e o
    contrato é editável. Aqui a asserção não passa por ele: os únicos importadores de
    vizinho são o gateway de staff e o guard de identity, cada um importando só a fachada do
    seu vizinho.
    """
    culpados: dict[str, list[str]] = {}
    importadores: dict[str, set[str]] = {fachada: set() for fachada in _ARESTAS.values()}
    for arquivo in _modulos_de_scheduling():
        arvore = ast.parse(arquivo.read_text(encoding="utf-8"), filename=str(arquivo))
        relativo = pathlib.PurePosixPath(arquivo.relative_to(_SCHEDULING).as_posix())
        alvos = _alvos_de_import(arvore)
        razoes = _violacoes_da_aresta(relativo, alvos)
        if razoes:
            culpados[str(relativo)] = razoes
        for fachada, quem in importadores.items():
            if fachada in alvos:
                quem.add(str(relativo))

    assert culpados == {}, (
        f"módulos de scheduling atravessando a fronteira fora das arestas: {culpados}. "
        f"O dado de staff chega pelo `StaffReadPort`; a decisão de acesso, pelo `AccessGuard`."
    )
    # Cada par do `.importlinter` serve a um adapter: se ele deixar de importar a fachada, a
    # supressão vira erro (`unmatched_ignore_imports_alerting`) — e aqui também.
    assert importadores == {
        _MODULO_DA_FACHADA: {_GATEWAY.relative_to(_SCHEDULING).as_posix()},
        _MODULO_DA_FACHADA_DE_IDENTITY: {_GUARD.relative_to(_SCHEDULING).as_posix()},
    }


def test_ca18_nenhum_modulo_de_scheduling_nomeia_o_vocabulario_dos_vizinhos() -> None:
    """Mais estreito que não importar — e é a metade que o import-linter não vê.

    Um `DayPeriod` que chegasse por `TYPE_CHECKING`, por `importlib` ou por
    `globals()` não apareceria como import no grafo, e o contrato seguiria verde.
    O que o desenho proíbe é scheduling **conhecer** o vocabulário fechado do
    outro BC — por isso a asserção é sobre o nome usado, não sobre a aresta.
    """
    culpados: dict[str, list[str]] = {}
    for arquivo in _modulos_de_scheduling():
        arvore = ast.parse(arquivo.read_text(encoding="utf-8"), filename=str(arquivo))
        encontrados = _identificadores(arvore) & _VOCABULARIO_DOS_VIZINHOS
        if encontrados:
            culpados[str(arquivo.relative_to(_SCHEDULING))] = sorted(encontrados)

    assert culpados == {}, (
        f"scheduling nomeia o vocabulário dos vizinhos: {culpados}. A decisão "
        f'alheia atravessa a fronteira como **valor** (`"cook"`), nunca como enum.'
    )


def test_o_vocabulario_proibido_nao_contem_identificador_proprio_do_bc() -> None:
    """A guarda contra o zelo excessivo — o erro que este BC convida.

    `EmployeeId` e `JobFunctionId` são dos **oito** identificadores que o
    concept §4 declara como próprios de scheduling. Pôr um deles na lista
    proibida reprovaria `identifiers.py` e toda entidade que os carrega, e a
    saída mais curta para quem visse a falha seria **renomear** o tipo próprio ou
    passar a importar o de staff — exatamente a violação que este arquivo mede.
    """
    intrusos = sorted(set(_IDENTIFICADORES_PROPRIOS) & _VOCABULARIO_DOS_VIZINHOS)

    assert intrusos == [], (
        f"identificadores próprios do BC na lista de vocabulário proibido: "
        f"{intrusos}. Os valores são emitidos por staff; os tipos são deste BC."
    )


def test_ca18_os_pares_que_tocam_scheduling_sao_os_das_duas_arestas() -> None:
    """A supressão que ninguém decidiu é a que este teste guarda — para scheduling.

    O `ignore_imports` é o caminho de menor resistência no dia em que um import cross-BC
    aparecer. Há **dois** pares envolvendo scheduling, ambos decididos: o gateway sobre a
    fachada de staff (ADR 4.4.0004) e o guard sobre a fachada de identity (ADR 4.5.0003).
    Qualquer outro — scheduling do lado importado, um terceiro pacote — reprova aqui. A
    lista exata do contrato inteiro é cobrada no teste de staff.
    """
    contrato = _contrato_bc_independence()
    pares = [
        linha.strip() for linha in contrato.get("ignore_imports", "").splitlines() if linha.strip()
    ]

    tocando_scheduling = [par for par in pares if _MODULO_SCHEDULING in par]

    assert tocando_scheduling == [_PAR_DE_SCHEDULING, _PAR_DE_SCHEDULING_IDENTITY], (
        f"o contrato `bc-independence` suprime import envolvendo scheduling: "
        f"{tocando_scheduling}. As arestas de scheduling são o gateway sobre a fachada de "
        f"staff (ADR 4.4.0004) e o guard sobre a fachada de identity (ADR 4.5.0003)."
    )


def test_ca18_scheduling_esta_no_contrato_bc_independence() -> None:
    """Sem isto, o BC novo ficaria fora do contrato e nada reclamaria.

    `type = independence` é par a par entre os módulos listados, logo um BC
    ausente da lista não viola nada: o contrato seguiria **KEPT** com a fronteira
    de scheduling inteiramente aberta. A cobrança do contrato **contra a pasta**
    (o conjunto dos BCs que existem) vive em
    `tests/unit/features/staff/test_bc_independence.py`, onde o sujeito é o
    contrato inteiro e não um BC.
    """
    contrato = _contrato_bc_independence()

    assert contrato["type"] == "independence"
    assert _MODULO_SCHEDULING in contrato["modules"].split()


def test_os_dois_detectores_reprovam_um_caso_plantado() -> None:
    """Teste negativo: guarda que nunca viu um positivo não é guarda.

    Os dois detectores são varreduras que devolvem conjunto vazio quando o
    código está limpo — e devolveriam conjunto vazio também se estivessem
    quebrados. O código violador é analisado aqui, nunca gravado em `src/`, onde
    seria copiado por analogia.

    O violador atravessa os **dois** vizinhos de propósito: um detector que só
    conhecesse o prefixo de identity (o copiar-e-colar mais provável a partir do
    arquivo de staff) passaria com o import de staff intacto.
    """
    violador = ast.parse(
        "from restaurant_hub.features.identity.domain.value_objects.permission "
        "import Permission\n"
        "from restaurant_hub.features.staff.domain.value_objects.shift_preference "
        "import DayPeriod\n"
        "def decide(role: Role, periodo: DayPeriod) -> Permission: ...\n"
    )
    alvos = _alvos_de_import(violador)

    for vizinho in _MODULOS_VIZINHOS:
        assert any(alvo.startswith(vizinho) for alvo in alvos), (
            f"o detector de import não alcança {vizinho}"
        )
    assert _identificadores(violador) & _VOCABULARIO_DOS_VIZINHOS == {
        "Role",
        "Permission",
        "DayPeriod",
    }


def test_o_detector_de_vocabulario_nao_acusa_o_identificador_proprio() -> None:
    """A outra direção: um módulo que usa os tipos do BC passa limpo.

    Sem este caso, um detector que acusasse **todo** nome terminado em `Id`
    passaria no teste plantado acima. Falso positivo num gate de independência é
    pior que falso negativo: a saída de quem o vê é remover o nome da lista — ou
    o tipo do domínio.
    """
    legitimo = ast.parse(
        "from restaurant_hub.features.scheduling.domain.value_objects.identifiers "
        "import EmployeeId, JobFunctionId\n"
        "def aloca(employee_id: EmployeeId, job_function_id: JobFunctionId) -> None: ...\n"
    )

    assert _identificadores(legitimo) & _VOCABULARIO_DOS_VIZINHOS == set()
    assert not any(alvo.startswith(_MODULOS_VIZINHOS) for alvo in _alvos_de_import(legitimo))


@pytest.mark.parametrize(
    ("caminho", "alvo", "razao_esperada"),
    [
        pytest.param(
            "application/use_cases/get_calendar.py",
            _MODULO_DA_FACHADA,
            "fora de",
            id="fachada-importada-fora-do-gateway",
        ),
        pytest.param(
            "adapters/out/staff/local_staff_read_adapter.py",
            "restaurant_hub.features.staff.application.ports.out.employee_repository",
            "além da fachada",
            id="gateway-importando-o-port-de-staff",
        ),
        pytest.param(
            "adapters/out/staff/local_staff_read_adapter.py",
            "restaurant_hub.features.identity.application.facade",
            "além da fachada",
            id="gateway-importando-identity",
        ),
        pytest.param(
            "adapters/inbound/http/router.py",
            _MODULO_DA_FACHADA_DE_IDENTITY,
            "fora de",
            id="fachada-de-identity-importada-fora-do-guard",
        ),
        pytest.param(
            "adapters/out/identity/local_access_guard.py",
            "restaurant_hub.features.identity.domain.value_objects.permission",
            "além da fachada",
            id="guard-importando-o-dominio-de-identity",
        ),
        pytest.param(
            "adapters/out/identity/local_access_guard.py",
            _MODULO_DA_FACHADA,
            "além da fachada",
            id="guard-importando-staff",
        ),
    ],
)
def test_o_detector_da_aresta_reprova_os_dois_lados_da_forma(
    caminho: str, alvo: str, razao_esperada: str
) -> None:
    """A forma da aresta tem dois lados (quem importa; o que importa) — cada um reprova só."""
    razoes = _violacoes_da_aresta(pathlib.PurePosixPath(caminho), {alvo})

    assert len(razoes) == 1
    assert razao_esperada in razoes[0]


def test_o_detector_da_aresta_aceita_exatamente_o_gateway_sobre_a_fachada() -> None:
    razoes = _violacoes_da_aresta(
        pathlib.PurePosixPath("adapters/out/staff/local_staff_read_adapter.py"),
        {_MODULO_DA_FACHADA, "restaurant_hub.features.scheduling.application.ports.out"},
    )

    assert razoes == []


def test_o_detector_da_aresta_aceita_exatamente_o_guard_sobre_a_fachada_de_identity() -> None:
    razoes = _violacoes_da_aresta(
        pathlib.PurePosixPath("adapters/out/identity/local_access_guard.py"),
        {_MODULO_DA_FACHADA_DE_IDENTITY, "restaurant_hub.features.scheduling.application"},
    )

    assert razoes == []
